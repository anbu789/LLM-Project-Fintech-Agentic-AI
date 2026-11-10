"""
FinTech Agent — Pydantic Request & Response Schemas
Defines structured API contracts for health and conversational endpoints.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


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


class ChatResponse(BaseModel):
    """Normalized response payload returned to the frontend."""
    success: bool = Field(default=True, description="Whether the request succeeded")
    conversation_id: str = Field(..., description="Conversation session identifier")
    request_id: str = Field(..., description="Unique request tracing identifier")
    message: str = Field(..., description="LLM generated conversational response")
    provider: str = Field(..., description="Configured LLM provider name")
    model: str = Field(..., description="Configured LLM model name")


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(default="healthy", description="Application service status")
    service: str = Field(default="fintech-agent-api", description="Service identifier")
    version: str = Field(default="1.0.0", description="API version")


class ErrorResponse(BaseModel):
    """Structured error contract returned on validation or provider failures."""
    success: bool = Field(default=False, description="Failure status flag")
    error_code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable safe error message")
    request_id: Optional[str] = Field(default=None, description="Request tracing identifier")
