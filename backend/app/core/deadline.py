"""
FinTech Agent — Request Deadline and Timeout Enforcement
Monitors request deadlines across pipeline stages and evaluates retry eligibility.
"""

import contextvars
import time
from dataclasses import dataclass
from typing import Optional
from backend.app.core.exceptions import (
    FinTechAgentException,
    DatabaseWriteProhibitedError,
    DatabaseCredentialsError,
    MissingAPIKeyError,
    ProviderAuthenticationError,
    InvalidRequestError,
    NonRetryableError,
    RequestTimeoutError,
)


@dataclass(frozen=True)
class ActiveRequestContext:
    """Async-safe request context propagated across LangGraph nodes and LLM calls."""

    request_id: str
    conversation_id: Optional[str] = None
    deadline: Optional["RequestDeadline"] = None


_active_request_ctx: contextvars.ContextVar[Optional[ActiveRequestContext]] = contextvars.ContextVar(
    "fintech_agent_active_request",
    default=None,
)

_request_preferred_provider: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "fintech_agent_preferred_provider",
    default=None,
)


def set_active_request_context(ctx: Optional[ActiveRequestContext]) -> contextvars.Token:
    """Binds ActiveRequestContext to the current async context and returns the reset token."""
    return _active_request_ctx.set(ctx)


def reset_active_request_context(token: contextvars.Token) -> None:
    """Restores the prior ActiveRequestContext after request completion."""
    _active_request_ctx.reset(token)


def get_active_request_context() -> Optional[ActiveRequestContext]:
    """Returns the currently bound ActiveRequestContext, if any."""
    return _active_request_ctx.get()


def set_request_preferred_provider(provider: Optional[str]) -> contextvars.Token:
    """Sets the preferred healthy LLM provider for the current request context."""
    return _request_preferred_provider.set(provider)


def get_request_preferred_provider() -> Optional[str]:
    """Returns the preferred healthy LLM provider recorded for the current request context."""
    return _request_preferred_provider.get()


def reset_request_preferred_provider(token: contextvars.Token) -> None:
    """Resets the preferred provider context variable."""
    _request_preferred_provider.reset(token)


class RequestDeadline:
    """Tracks elapsed and remaining time against an absolute request deadline."""

    # Non-retryable exception types according to architecture specification
    NON_RETRYABLE_EXCEPTION_TYPES = (
        DatabaseWriteProhibitedError,
        DatabaseCredentialsError,
        MissingAPIKeyError,
        ProviderAuthenticationError,
        InvalidRequestError,
        NonRetryableError,
        PermissionError,
        ValueError,
        TypeError,
    )

    def __init__(self, timeout_seconds: float, request_id: Optional[str] = None):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.timeout_seconds = float(timeout_seconds)
        self.request_id = request_id or "unknown"
        self._start_monotonic = time.monotonic()

    @property
    def start_time(self) -> float:
        return self._start_monotonic

    def elapsed_seconds(self) -> float:
        """Returns elapsed time in seconds since deadline initialization."""
        return time.monotonic() - self._start_monotonic

    def remaining_seconds(self) -> float:
        """Returns remaining time in seconds before deadline expiration."""
        return max(0.0, self.timeout_seconds - self.elapsed_seconds())

    def is_expired(self) -> bool:
        """Checks if deadline has elapsed."""
        return self.elapsed_seconds() >= self.timeout_seconds

    def check_deadline(self, stage: Optional[str] = None) -> None:
        """
        Raises RequestTimeoutError if the deadline has expired.
        Call before initiating heavy sub-operations (e.g. LLM calls, DB queries).
        """
        elapsed = self.elapsed_seconds()
        if elapsed >= self.timeout_seconds:
            raise RequestTimeoutError(
                elapsed_seconds=elapsed,
                limit_seconds=self.timeout_seconds,
                stage=stage
            )

    def can_retry(self, min_needed_seconds: float = 2.0) -> bool:
        """
        Determines whether sufficient time remains to attempt another retry.
        If less than min_needed_seconds remain, retrying will inevitably timeout.
        """
        return not self.is_expired() and self.remaining_seconds() >= min_needed_seconds

    @classmethod
    def is_retryable_error(cls, exc: Exception) -> bool:
        """
        Determines whether a given exception is eligible for retry.
        Deterministic errors (validation, auth failure, security violations)
        must NEVER be retried.
        """
        if isinstance(exc, cls.NON_RETRYABLE_EXCEPTION_TYPES):
            return False

        # If it's a FinTechAgentException with a 4xx status code, it's deterministic client/auth error
        if isinstance(exc, FinTechAgentException):
            if exc.status_code in (400, 401, 403, 422):
                return False

        # Known prompt injection or security violation markers in messages
        err_str = str(exc).lower()
        if any(marker in err_str for marker in ("injection", "prohibited", "unauthorized", "forbidden")):
            return False

        return True
