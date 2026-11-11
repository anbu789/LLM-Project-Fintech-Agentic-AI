"""
FinTech Agent — Core Exceptions
Standardized exception classes for LLM provider, validation, and API errors.
"""

from typing import Dict, List, Optional


class FinTechAgentException(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class MissingAPIKeyError(FinTechAgentException):
    """Raised when an external LLM call is attempted without an API key."""
    def __init__(self, provider: str, details: Optional[str] = None):
        msg = f"API key for LLM provider '{provider}' is not configured. Please set LLM_API_KEY in .env."
        if details:
            msg += f" ({details})"
        super().__init__(msg, error_code="MISSING_API_KEY", status_code=400)


class ProviderConfigurationError(FinTechAgentException):
    """Raised when provider configuration is invalid or unsupported."""
    def __init__(self, message: str):
        super().__init__(message, error_code="INVALID_PROVIDER_CONFIG", status_code=400)


class ProviderAuthenticationError(FinTechAgentException):
    """Raised when the LLM provider rejects authentication (invalid API key)."""
    def __init__(self, provider: str, message: str = "Authentication with provider failed."):
        super().__init__(f"{provider} authentication error: {message}", error_code="PROVIDER_AUTH_ERROR", status_code=401)


class ProviderRateLimitError(FinTechAgentException):
    """Raised when rate limits are exceeded at the LLM provider."""
    def __init__(self, provider: str, message: str = "Rate limit exceeded."):
        super().__init__(f"{provider} rate limit error: {message}", error_code="PROVIDER_RATE_LIMIT", status_code=429)


class ProviderTimeoutError(FinTechAgentException):
    """Raised when the LLM provider call times out."""
    def __init__(
        self,
        provider: str,
        timeout: float,
        message: Optional[str] = None,
        error_code: str = "PROVIDER_TIMEOUT",
    ):
        msg = message or f"Call to {provider} timed out after {timeout} seconds."
        super().__init__(msg, error_code=error_code, status_code=504)


class ProviderAPIError(FinTechAgentException):
    """Raised when the LLM provider returns a non-transient API failure."""
    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int = 502,
        error_code: str = "PROVIDER_API_ERROR",
    ):
        super().__init__(f"{provider} API error: {message}", error_code=error_code, status_code=status_code)


class ProviderUnavailableError(ProviderAPIError):
    """Raised when the LLM provider is temporarily unavailable (e.g., HTTP 503)."""
    def __init__(self, provider: str, message: str = "Provider service unavailable.", status_code: int = 503):
        super().__init__(
            provider=provider,
            message=message,
            status_code=status_code,
            error_code="PROVIDER_UNAVAILABLE",
        )


class ProviderRetryExhaustedError(ProviderAPIError):
    """Raised when all retry attempts to an LLM provider are exhausted."""
    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int = 503,
        error_code: str = "PROVIDER_RETRY_EXHAUSTED",
    ):
        super().__init__(
            provider=provider,
            message=message,
            status_code=status_code,
            error_code=error_code,
        )


class LLMFallbackExhaustedError(ProviderRetryExhaustedError):
    """Raised when the primary LLM provider and all configured fallback providers have failed or been skipped."""
    def __init__(
        self,
        attempted_providers: List[str],
        failure_reasons: Dict[str, str],
        deadline_exhausted: bool = False,
        skipped_providers: Optional[Dict[str, str]] = None,
        status_code: int = 503,
    ):
        self.attempted_providers = list(attempted_providers)
        self.failure_reasons = dict(failure_reasons)
        self.deadline_exhausted = deadline_exhausted
        self.skipped_providers = dict(skipped_providers or {})

        details = []
        for p in self.attempted_providers:
            details.append(f"{p} (failed: {self.failure_reasons.get(p, 'unknown')})")
        for p, r in self.skipped_providers.items():
            details.append(f"{p} (skipped: {r})")

        summary = "; ".join(details) if details else "All configured providers failed."
        msg = f"All LLM providers in fallback chain failed: {summary}"
        err_code = "PROVIDER_TIMEOUT" if deadline_exhausted else "LLM_FALLBACK_EXHAUSTED"
        super().__init__(
            provider="fallback_manager",
            message=msg,
            status_code=504 if deadline_exhausted else status_code,
            error_code=err_code,
        )


class InvalidRequestError(FinTechAgentException):
    """Raised when user input violates validation rules."""
    def __init__(self, message: str):
        super().__init__(message, error_code="INVALID_REQUEST", status_code=422)


class DatabaseWriteProhibitedError(FinTechAgentException, PermissionError):
    """Raised when an attempt is made to mutate the read-only banking database."""
    def __init__(self, operation: str, details: Optional[str] = None):
        msg = f"Write operation '{operation}' is strictly prohibited on the banking database."
        if details:
            msg += f" {details}"
        super().__init__(msg, error_code="BANKING_WRITE_PROHIBITED", status_code=403)


class DatabaseTimeoutError(FinTechAgentException):
    """Raised when a MongoDB query exceeds QUERY_TIMEOUT_MS or deadline."""
    def __init__(self, timeout_ms: int, details: Optional[str] = None):
        msg = f"Database query timed out after {timeout_ms}ms."
        if details:
            msg += f" {details}"
        super().__init__(msg, error_code="DATABASE_TIMEOUT", status_code=504)


class DatabaseCredentialsError(FinTechAgentException):
    """Raised when database authentication credentials are required but missing or invalid."""
    def __init__(self, message: str):
        super().__init__(message, error_code="DATABASE_CREDENTIALS_ERROR", status_code=500)


class RequestTimeoutError(FinTechAgentException):
    """Raised when an end-to-end request exceeds the configured REQUEST_TIMEOUT_SECONDS."""
    def __init__(self, elapsed_seconds: float, limit_seconds: float, stage: Optional[str] = None):
        msg = f"Request exceeded deadline of {limit_seconds}s (elapsed: {elapsed_seconds:.2f}s)."
        if stage:
            msg = f"Request timed out during '{stage}': {msg}"
        super().__init__(msg, error_code="REQUEST_TIMEOUT", status_code=504)


class NonRetryableError(FinTechAgentException):
    """Raised or classified when an error is deterministic and must not be retried."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, error_code="NON_RETRYABLE_ERROR", status_code=400)
        self.original_error = original_error

