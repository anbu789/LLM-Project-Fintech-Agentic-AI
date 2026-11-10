"""
FinTech Agent — Conversational Chat API Route
Provides basic conversational LLM shell endpoint with request tracing,
deadline monitoring, rate limiting, and error shielding.
"""

import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import settings
from backend.app.core.deadline import RequestDeadline
from backend.app.core.exceptions import FinTechAgentException
from backend.app.core.logging import logger, sanitize_error_message
from backend.app.core.rate_limit import chat_rate_limiter
from backend.app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from backend.app.services.llm_service import llm_service

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
        deadline.check_deadline("llm_dispatch")
        reply_text = await llm_service.ask(request.message)
        deadline.check_deadline("response_assembly")

        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(f"[{request_id}] Successfully generated response in {duration_ms}ms")

        return ChatResponse(
            success=True,
            conversation_id=conv_id,
            request_id=request_id,
            message=reply_text,
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
            latency_ms=duration_ms
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
