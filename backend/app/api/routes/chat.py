"""
FinTech Agent — Conversational Chat API Route
Provides conversational LLM endpoint with request tracing, multi-turn history,
conversation persistence in agent_metadata_db, rate limiting, and error shielding.
"""

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.agent.graph import agent_graph
from backend.app.config import settings
from backend.app.core.auth import AuthenticatedUser, get_optional_authenticated_user
from backend.app.core.deadline import (
    ActiveRequestContext,
    RequestDeadline,
    reset_active_request_context,
    set_active_request_context,
    get_request_preferred_provider,
    set_request_preferred_provider,
    reset_request_preferred_provider,
)
from backend.app.core.exceptions import FinTechAgentException, RequestTimeoutError
from backend.app.core.execution_monitor import execution_monitor, summarize_query_safely
from backend.app.core.logging import logger, sanitize_error_message
from backend.app.core.rate_limit import chat_rate_limiter
from backend.app.db.mongo_client import mongo_manager
from backend.app.schemas.chat import (
    CONVERSATION_ID_REGEX,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    DeleteConversationResponse,
    ErrorResponse,
)

router = APIRouter(tags=["Chat"])


def _sanitize_message_metadata(value: Any) -> Any:
    """Normalizes structured metadata into plain JSON primitives for safe persistence."""
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return json.loads(
        json.dumps(
            value,
            default=lambda obj: obj.model_dump(mode="json") if isinstance(obj, BaseModel) else str(obj),
        )
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(chat_rate_limiter)],
    responses={
        400: {"model": ErrorResponse, "description": "Missing configuration or invalid request"},
        401: {"model": ErrorResponse, "description": "LLM provider authentication failed"},
        403: {"model": ErrorResponse, "description": "Forbidden operation"},
        413: {"model": ErrorResponse, "description": "Payload too large"},
        422: {"model": ErrorResponse, "description": "Request validation error"},
        429: {"model": ErrorResponse, "description": "Provider or client rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        502: {"model": ErrorResponse, "description": "LLM provider communication error"},
        503: {"model": ErrorResponse, "description": "LLM provider temporarily unavailable"},
        504: {"model": ErrorResponse, "description": "Request or query deadline exceeded"},
    }
)
async def chat_endpoint(
    request: ChatRequest,
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_authenticated_user),
):
    """Processes natural language inquiries via the configured LLM provider under deadline tracking."""
    request_id = f"req-{uuid.uuid4().hex}"
    conv_id = request.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    start_time = time.time()
    deadline = RequestDeadline(settings.REQUEST_TIMEOUT_SECONDS, request_id)
    ctx_token = set_active_request_context(
        ActiveRequestContext(request_id=request_id, conversation_id=conv_id, deadline=deadline)
    )
    pref_token = set_request_preferred_provider(None)

    logger.info(f"[{request_id}] Received chat request for conversation='{conv_id}', length={len(request.message)}")
    execution_monitor.emit(
        "REQUEST_STARTED",
        request_id=request_id,
        conversation_id=conv_id,
        status="STARTED",
        details={
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            **summarize_query_safely(request.message),
        },
    )

    try:
        # Load conversation history from agent_metadata_db for multi-turn context
        history_messages = []
        try:
            meta_db = mongo_manager.get_metadata_db()
            existing_conv = meta_db.conversations.find_one({"conversation_id": conv_id})
            if existing_conv:
                history_messages = existing_conv.get("messages", [])
        except Exception as e:
            logger.warning(f"[{request_id}] Could not fetch history from metadata db: {e}")

        deadline.check_deadline("agent_dispatch")

        # Build the initial LangGraph agent state (query_max_retries=0 enforces at-most-once execution per request)
        initial_state = {
            "request_id": request_id,
            "natural_language_query": request.message,
            "conversation_history": history_messages,
            "thread_id": conv_id,
            "selected_provider": None,
            "request_started_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": 0,
            "max_retries": settings.QUERY_MAX_RETRY_ATTEMPTS,
            "trace": [],
            "all_attempts": [],
            "result_truncated": False,
            "dry_run": False,
            "schedule_approved": False,
            "is_api_request": True,
        }
        if current_user is not None:
            initial_state["user_id"] = current_user.user_id
            initial_state["owner_id"] = current_user.user_id

        # Invoke the 9-node LangGraph pipeline strictly bounded by overall request deadline
        try:
            final_state = await asyncio.wait_for(
                agent_graph.ainvoke(initial_state),
                timeout=max(0.25, deadline.remaining_seconds()),
            )
        except asyncio.TimeoutError:
            raise RequestTimeoutError(
                elapsed_seconds=time.time() - start_time,
                limit_seconds=settings.REQUEST_TIMEOUT_SECONDS,
                stage="agent_pipeline",
            )

        # Extract the composed reply; fall back gracefully if composer did not run
        reply_text = (
            final_state.get("graph_response")
            or final_state.get("formatted_response")
            or "I was unable to process your request. Please try again."
        )

        deadline.check_deadline("response_assembly")

        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(f"[{request_id}] Successfully generated response in {duration_ms}ms")

        req_mode = final_state.get("request_mode")
        intent_reason = final_state.get("intent_reason")
        guardrail_status = final_state.get("guardrail_status")

        pipeline_spec = _sanitize_message_metadata(
            final_state.get("pipeline_spec") or final_state.get("generated_pipeline")
        )
        target_col = final_state.get("selected_collection") or final_state.get("target_collection")
        is_valid = final_state.get("is_pipeline_valid") or (final_state.get("validation_status") == "VALID")
        val_status = "passed" if is_valid else ("failed" if pipeline_spec else None)
        query_expl = final_state.get("pipeline_explanation") or final_state.get("query_explanation")
        trace_data = final_state.get("trace")
        schedule_preview_data = _sanitize_message_metadata(final_state.get("schedule_preview"))
        preview_id = final_state.get("preview_id")

        actual_provider = (
            final_state.get("selected_provider")
            or final_state.get("llm_provider")
            or settings.LLM_PROVIDER
        )
        actual_model = final_state.get("llm_model") or settings.LLM_MODEL

        # Persist conversation turn in agent_metadata_db
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            user_entry = {
                "role": "user",
                "content": request.message,
                "timestamp": now_iso,
                "request_id": request_id
            }
            assistant_entry = {
                "role": "assistant",
                "content": reply_text,
                "timestamp": now_iso,
                "request_id": request_id,
                "provider": actual_provider,
                "model": actual_model,
                "latency_ms": duration_ms,
            }
            if pipeline_spec is not None:
                assistant_entry["pipeline_spec"] = pipeline_spec
            if target_col is not None:
                assistant_entry["selected_collection"] = str(target_col)
            if val_status is not None:
                assistant_entry["validation_status"] = val_status
            if query_expl is not None:
                assistant_entry["query_explanation"] = str(query_expl)
            if schedule_preview_data is not None:
                assistant_entry["schedule_preview"] = schedule_preview_data
            if preview_id is not None:
                assistant_entry["preview_id"] = str(preview_id)

            meta_db = mongo_manager.get_metadata_db()
            meta_db.conversations.update_one(
                {"conversation_id": conv_id},
                {
                    "$setOnInsert": {
                        "conversation_id": conv_id,
                        "title": request.message[:50] + ("..." if len(request.message) > 50 else ""),
                        "created_at": now_iso
                    },
                    "$set": {
                        "updated_at": now_iso
                    },
                    "$push": {
                        "messages": {"$each": [user_entry, assistant_entry]}
                    }
                },
                upsert=True
            )
        except Exception as persist_err:
            logger.warning(f"[{request_id}] Failed to persist conversation history: {persist_err}")

        execution_monitor.emit(
            "REQUEST_COMPLETED",
            request_id=request_id,
            conversation_id=conv_id,
            status=final_state.get("final_status") or "success",
            elapsed_ms=duration_ms,
            details={
                "http_status": 200,
                "provider": actual_provider,
                "model": actual_model,
                "request_mode": req_mode,
                "guardrail_status": guardrail_status,
                "validation_status": final_state.get("validation_status"),
                "selected_collection": target_col,
                "execution_status": final_state.get("execution_status"),
                "verification_status": final_state.get("verification_status"),
            },
        )

        return ChatResponse(
            success=True,
            status="success",
            conversation_id=conv_id,
            request_id=request_id,
            message=reply_text,
            response=reply_text,
            provider=actual_provider,
            model=actual_model,
            latency_ms=duration_ms,
            intent=req_mode,
            intent_reason=intent_reason,
            guardrail_status=guardrail_status,
            request_mode=req_mode,
            pipeline_spec=pipeline_spec,
            selected_collection=target_col,
            validation_status=val_status,
            query_explanation=query_expl,
            trace=trace_data,
            schedule_preview=schedule_preview_data,
            preview_id=preview_id,
        )
    except asyncio.CancelledError:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        execution_monitor.emit(
            "REQUEST_CANCELLED",
            request_id=request_id,
            conversation_id=conv_id,
            status="CANCELLED",
            elapsed_ms=duration_ms,
            details={
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "error_code": "REQUEST_CANCELLED",
            },
        )
        raise
    except FinTechAgentException as fae:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        safe_msg = sanitize_error_message(fae.message)
        is_timeout = fae.error_code in ("PROVIDER_TIMEOUT", "REQUEST_TIMEOUT", "DATABASE_TIMEOUT")
        execution_monitor.emit(
            "REQUEST_TIMEOUT" if is_timeout else "REQUEST_FAILED",
            request_id=request_id,
            conversation_id=conv_id,
            status="TIMEOUT" if is_timeout else "FAILED",
            elapsed_ms=duration_ms,
            details={
                "http_status": fae.status_code,
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "error_code": fae.error_code,
                "error_message": safe_msg,
            },
        )
        logger.warning(f"[{request_id}] Handled application error ({fae.error_code}) in {duration_ms}ms: {safe_msg}")
        raise HTTPException(
            status_code=fae.status_code,
            detail={
                "success": False,
                "error_code": fae.error_code,
                "message": safe_msg,
                "request_id": request_id,
            }
        )
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        safe_exc = sanitize_error_message(str(exc))
        execution_monitor.emit(
            "REQUEST_FAILED",
            request_id=request_id,
            conversation_id=conv_id,
            status="FAILED",
            elapsed_ms=duration_ms,
            details={
                "http_status": 500,
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "error_code": "INTERNAL_SERVER_ERROR",
                "error_message": safe_exc,
            },
        )
        logger.error(f"[{request_id}] Unexpected error in {duration_ms}ms: {safe_exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing your request. Please try again later.",
                "request_id": request_id,
            }
        )
    finally:
        reset_active_request_context(ctx_token)
        reset_request_preferred_provider(pref_token)


@router.get("/chat/conversations", response_model=List[ConversationSummary])
async def list_conversations():
    """Returns a list of recent conversations stored in agent_metadata_db."""
    try:
        meta_db = mongo_manager.get_metadata_db()
        cursor = meta_db.conversations.find(
            {},
            {"conversation_id": 1, "title": 1, "created_at": 1, "updated_at": 1, "messages": 1, "_id": 0}
        ).sort("updated_at", -1).limit(50)

        summaries = []
        for doc in cursor:
            summaries.append(ConversationSummary(
                conversation_id=doc.get("conversation_id", ""),
                title=doc.get("title", "Untitled Conversation"),
                message_count=len(doc.get("messages", [])),
                created_at=doc.get("created_at", ""),
                updated_at=doc.get("updated_at", "")
            ))
        return summaries
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        return []


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    """Retrieves full conversation history by conversation_id."""
    clean_id = conversation_id.strip()
    if not CONVERSATION_ID_REGEX.match(clean_id):
        raise HTTPException(status_code=422, detail="Invalid conversation_id format.")

    meta_db = mongo_manager.get_metadata_db()
    conv = meta_db.conversations.find_one({"conversation_id": clean_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation '{clean_id}' not found.")

    return ConversationDetail(
        conversation_id=conv.get("conversation_id", clean_id),
        title=conv.get("title", "Untitled"),
        created_at=conv.get("created_at", ""),
        updated_at=conv.get("updated_at", ""),
        messages=conv.get("messages", [])
    )


@router.delete("/chat/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(conversation_id: str):
    """Deletes a conversation from agent_metadata_db."""
    clean_id = conversation_id.strip()
    if not CONVERSATION_ID_REGEX.match(clean_id):
        raise HTTPException(status_code=422, detail="Invalid conversation_id format.")

    meta_db = mongo_manager.get_metadata_db()
    res = meta_db.conversations.delete_one({"conversation_id": clean_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Conversation '{clean_id}' not found.")

    return DeleteConversationResponse(
        success=True,
        conversation_id=clean_id,
        message=f"Conversation '{clean_id}' deleted successfully."
    )
