"""
FinTech Agent — Conversational Chat API Route
Provides conversational LLM endpoint with request tracing, multi-turn history,
conversation persistence in agent_metadata_db, rate limiting, and error shielding.
"""

from datetime import datetime, timezone
import time
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.agent.graph import agent_graph
from backend.app.config import settings
from backend.app.core.deadline import RequestDeadline
from backend.app.core.exceptions import FinTechAgentException
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
        504: {"model": ErrorResponse, "description": "Request or query deadline exceeded"},
    }
)
async def chat_endpoint(request: ChatRequest):
    """Processes natural language inquiries via the configured LLM provider under deadline tracking."""
    request_id = f"req-{uuid.uuid4().hex}"
    conv_id = request.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    start_time = time.time()
    deadline = RequestDeadline(settings.REQUEST_TIMEOUT_SECONDS, request_id)

    logger.info(f"[{request_id}] Received chat request for conversation='{conv_id}', length={len(request.message)}")

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

        # Build the initial LangGraph agent state
        initial_state = {
            "request_id": request_id,
            "natural_language_query": request.message,
            "conversation_history": history_messages,
            "thread_id": conv_id,
            "request_started_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": 0,
            "max_retries": settings.MAX_RETRY_ATTEMPTS,
            "trace": [],
            "all_attempts": [],
            "result_truncated": False,
            "dry_run": False,
            "schedule_approved": False,
            "is_api_request": True,
        }

        # Invoke the 9-node LangGraph pipeline
        final_state = await agent_graph.ainvoke(initial_state)

        # Extract the composed reply; fall back gracefully if composer did not run
        reply_text = (
            final_state.get("graph_response")
            or final_state.get("formatted_response")
            or "I was unable to process your request. Please try again."
        )

        deadline.check_deadline("response_assembly")

        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(f"[{request_id}] Successfully generated response in {duration_ms}ms")

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
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "latency_ms": duration_ms
            }
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

        req_mode = final_state.get("request_mode")
        intent_reason = final_state.get("intent_reason")
        guardrail_status = final_state.get("guardrail_status")

        pipeline_spec = final_state.get("pipeline_spec") or final_state.get("generated_pipeline")
        target_col = final_state.get("selected_collection") or final_state.get("target_collection")
        is_valid = final_state.get("is_pipeline_valid") or (final_state.get("validation_status") == "VALID")
        val_status = "passed" if is_valid else ("failed" if pipeline_spec else None)
        query_expl = final_state.get("pipeline_explanation") or final_state.get("query_explanation")
        trace_data = final_state.get("trace")

        return ChatResponse(
            success=True,
            status="success",
            conversation_id=conv_id,
            request_id=request_id,
            message=reply_text,
            response=reply_text,
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
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
            schedule_preview=final_state.get("schedule_preview"),
            preview_id=final_state.get("preview_id"),
        )
    except FinTechAgentException as fae:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        safe_msg = sanitize_error_message(fae.message)
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
