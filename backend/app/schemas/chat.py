"""
FinTech Agent — Pydantic Request & Response Schemas
Defines structured API contracts for health and conversational endpoints.
Includes strict input sanitization, conversation ID validation, and latency tracking.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

CONVERSATION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


class ChatRequest(BaseModel):
    """Payload sent by the frontend for a conversational turn."""
    message: str = Field(..., description="User message text")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation session identifier")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        trimmed = v.strip() if v else ""
        if not trimmed:
            raise ValueError("Message cannot be empty or contain only whitespace.")
        if len(trimmed) > 2000:
            raise ValueError(f"Message exceeds maximum allowed length of 2000 characters (received {len(trimmed)}).")
        return trimmed

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if "\r" in cleaned or "\n" in cleaned:
            raise ValueError("conversation_id contains prohibited CRLF characters.")
        if len(cleaned) > 64:
            raise ValueError(f"conversation_id exceeds maximum length of 64 characters (received {len(cleaned)}).")
        if not CONVERSATION_ID_REGEX.match(cleaned):
            raise ValueError("conversation_id must be 1-64 alphanumeric characters, hyphens, or underscores only.")
        return cleaned


class ChatResponse(BaseModel):
    """Normalized response payload returned to the frontend."""
    success: bool = Field(default=True, description="Whether the request succeeded")
    conversation_id: str = Field(..., description="Conversation session identifier")
    request_id: str = Field(..., description="Unique request tracing identifier")
    message: str = Field(..., description="LLM generated conversational response")
    provider: str = Field(..., description="Configured LLM provider name")
    model: str = Field(..., description="Configured LLM model name")
    latency_ms: Optional[float] = Field(default=None, description="Total execution duration in milliseconds")


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(default="healthy", description="Application service status")
    service: str = Field(default="fintech-agent-api", description="Service identifier")
    version: str = Field(default="1.0.0", description="API version")


class ConversationSummary(BaseModel):
    """Summary of a stored conversation session."""
    conversation_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    """Full detail of a stored conversation with its message history."""
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list = Field(default_factory=list)


class DeleteConversationResponse(BaseModel):
    """Result of deleting a conversation."""
    success: bool = True
    conversation_id: str
    message: str = "Conversation deleted"


class ErrorResponse(BaseModel):
    """Structured error contract returned on validation or provider failures."""
    success: bool = Field(default=False, description="Failure status flag")
    error_code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable safe error message")
    request_id: Optional[str] = Field(default=None, description="Request tracing identifier")
