"""
FinTech Agent — LLM Provider Service
Provider-independent adapter supporting Mock, Anthropic, OpenAI, Groq, and Gemini.
Includes multi-turn history handling, provider response safety shields, and fail-fast production checks.
"""

from abc import ABC, abstractmethod
import asyncio
import random
import ssl
import time
from typing import Any, Dict, List, Optional
import httpx


_CACHED_SSL_CONTEXT: Optional[ssl.SSLContext] = None


def _get_ssl_context() -> ssl.SSLContext:
    """Caches the verified TLS/SSL context once so retries on Windows do not reload root CAs repeatedly."""
    global _CACHED_SSL_CONTEXT
    if _CACHED_SSL_CONTEXT is None:
        _CACHED_SSL_CONTEXT = httpx.create_ssl_context()
    return _CACHED_SSL_CONTEXT

from backend.app.config import settings
from backend.app.core.deadline import (
    get_active_request_context,
    get_request_preferred_provider,
    set_request_preferred_provider,
)
from backend.app.core.exceptions import (
    LLMFallbackExhaustedError,
    MissingAPIKeyError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderAPIError,
)
from backend.app.core.execution_monitor import execution_monitor
from backend.app.core.logging import logger, sanitize_error_message

SYSTEM_PROMPT = (
    "You are FinTech Agent, an AI banking intelligence assistant for financial institutions. "
    "You assist banking operations, risk, compliance, and fraud analysts by explaining banking terminology, "
    "regulatory concepts (e.g., KYC, AML, NPA, DPD), and operational workflows accurately and professionally. "
    "Be concise, clear, and domain-accurate."
)


class NormalizedLLMResponse(str):
    """
    Normalized response object returned by all LLM providers and fallback managers.
    Inherits from str so it is 100% backward compatible with string operations, JSON parsers,
    markdown fences, and assertions (isinstance(resp, str) is True).
    """

    def __new__(
        cls,
        content: str,
        *,
        provider: str,
        model: str,
        finish_reason: Optional[str] = "stop",
        latency_ms: Optional[float] = None,
        usage: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        is_local: bool = False,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ):
        clean_text = str(content)
        instance = super().__new__(cls, clean_text)
        instance.content = clean_text
        instance.provider = str(provider)
        instance.model = str(model)
        instance.finish_reason = finish_reason or "stop"
        instance.latency_ms = float(latency_ms) if latency_ms is not None else None
        instance.usage = dict(usage or {})
        instance.request_id = str(request_id) if request_id else None
        instance.is_local = bool(is_local)
        instance.raw_metadata = dict(raw_metadata or {})
        return instance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
            "usage": self.usage,
            "request_id": self.request_id,
            "is_local": self.is_local,
        }


class BaseLLMProvider(ABC):
    """Abstract interface for LLM provider adapters."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        operation_timeout: Optional[float] = None,
        max_attempts: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
    ):
        self.model = model
        self.api_key = api_key
        default_attempt = float(min(settings.LLM_ATTEMPT_TIMEOUT_SECONDS, settings.LLM_TIMEOUT_SECONDS))
        self.timeout = float(timeout) if timeout is not None else default_attempt
        self._configured_timeout = self.timeout
        self.max_attempts = int(max_attempts) if max_attempts is not None else int(settings.LLM_MAX_ATTEMPTS)
        self.retry_base_delay = (
            float(retry_base_delay) if retry_base_delay is not None else float(settings.LLM_RETRY_BASE_DELAY_SECONDS)
        )
        self.retry_max_delay = (
            float(retry_max_delay) if retry_max_delay is not None else float(settings.LLM_RETRY_MAX_DELAY_SECONDS)
        )
        default_op = float(settings.LLM_OPERATION_TIMEOUT_SECONDS)
        self.operation_timeout = float(operation_timeout) if operation_timeout is not None else default_op

    def _emit_provider_event(
        self,
        event_type: str,
        *,
        status: str,
        elapsed_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = get_active_request_context()
        if not ctx:
            return
        execution_monitor.emit(
            event_type,
            request_id=ctx.request_id,
            conversation_id=ctx.conversation_id,
            status=status,
            elapsed_ms=elapsed_ms,
            details=details or {},
        )

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Sends prompt/conversation to provider and extracts text completion."""
        pass

    def _build_messages_payload(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        include_system_role: bool = False,
        system_prompt: str = SYSTEM_PROMPT
    ) -> List[Dict[str, str]]:
        """Constructs a sliding window of conversation messages within configured turn limits."""
        msgs: List[Dict[str, str]] = []
        if include_system_role and system_prompt:
            msgs.append({"role": "system", "content": system_prompt})

        if conversation_history:
            max_msgs = settings.MAX_CONVERSATION_HISTORY_TURNS * 2
            recent = conversation_history[-max_msgs:]
            for item in recent:
                role = item.get("role", "user")
                content = item.get("content", "")
                if role in {"user", "assistant"} and content:
                    msgs.append({"role": role, "content": content})

        if user_message:
            msgs.append({"role": "user", "content": user_message})

        return msgs


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline provider for unit testing and local development without API keys."""

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        t0 = time.monotonic()
        self._emit_provider_event(
            "PROVIDER_REQUEST_STARTED",
            status="STARTED",
            details={
                "provider": "mock",
                "model": self.model,
                "attempt": 1,
                "max_attempts": 1,
            },
        )
        msg_lower = user_message.lower()

        # Context-aware follow-up recognition
        if conversation_history and any(k in msg_lower for k in ("explain more", "what about", "elaborate", "tell me more")):
            last_asst = next((m.get("content", "") for m in reversed(conversation_history) if m.get("role") == "assistant"), None)
            if last_asst:
                reply = (
                    f"[FinTech Agent Follow-up] Building upon previous discussion: '{last_asst[:80]}...'. "
                    "Ensure ongoing compliance with regulatory guidelines and internal audit procedures."
                )
                self._emit_provider_event(
                    "PROVIDER_SUCCESS",
                    status="SUCCESS",
                    elapsed_ms=(time.monotonic() - t0) * 1000,
                    details={"provider": "mock", "model": self.model, "attempts_used": 1, "http_status": 200},
                )
                return NormalizedLLMResponse(
                    reply,
                    provider="mock",
                    model=self.model,
                    finish_reason="stop",
                    latency_ms=(time.monotonic() - t0) * 1000,
                    is_local=True,
                )
        if "npa" in msg_lower:
            reply = (
                "A Non-Performing Asset (NPA) is a loan or advance for which the principal or interest "
                "payment remains overdue for a specified period, typically 90 days or more according to banking regulations. "
                "NPAs are classified into Sub-standard, Doubtful, and Loss assets based on recovery risk."
            )
        elif "kyc" in msg_lower:
            reply = (
                "Know Your Customer (KYC) is a mandatory banking compliance process to verify customer identity "
                "using officially valid documents (such as Passport, Aadhaar, PAN) before onboarding and periodically thereafter."
            )
        elif "fraud" in msg_lower:
            reply = (
                "A fraud alert flags suspicious transactions or anomalous customer behavior for investigation "
                "by the risk and fraud operations department."
            )
        else:
            reply = (
                f"[FinTech Agent Mock Response] Processed query: '{user_message}'. "
                "System is operating in verified Phase 2 conversational mode."
            )

        self._emit_provider_event(
            "PROVIDER_SUCCESS",
            status="SUCCESS",
            elapsed_ms=(time.monotonic() - t0) * 1000,
            details={"provider": "mock", "model": self.model, "attempts_used": 1, "http_status": 200},
        )
        return NormalizedLLMResponse(
            reply,
            provider="mock",
            model=self.model,
            finish_reason="stop",
            latency_ms=(time.monotonic() - t0) * 1000,
            is_local=True,
        )


class AnthropicProvider(BaseLLMProvider):
    """Adapter for Anthropic Messages API."""

    ENDPOINT = "https://api.anthropic.com/v1/messages"

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        if not self.api_key:
            self._emit_provider_event(
                "PROVIDER_FAILURE",
                status="FAILED",
                details={"provider": "anthropic", "model": self.model, "error_code": "MISSING_API_KEY"},
            )
            raise MissingAPIKeyError("anthropic")

        t0 = time.monotonic()
        ctx = get_active_request_context()
        effective_timeout = float(self.timeout)
        if ctx and ctx.deadline:
            rem = max(0.0, ctx.deadline.remaining_seconds() - float(settings.BACKEND_PROCESSING_RESERVE_SECONDS))
            if rem <= 0.1:
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="TIMEOUT",
                    details={"provider": "anthropic", "model": self.model, "error_code": "PROVIDER_TIMEOUT"},
                )
                raise ProviderTimeoutError("anthropic", effective_timeout)
            effective_timeout = min(effective_timeout, rem)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        msgs = self._build_messages_payload(
            user_message=user_message,
            conversation_history=conversation_history,
            include_system_role=False,
            system_prompt=system_prompt
        )

        # Anthropic requires messages list to begin with a user turn
        if msgs and msgs[0]["role"] != "user":
            msgs = msgs[1:]
        if not msgs:
            msgs = [{"role": "user", "content": user_message}]

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": msgs,
        }

        self._emit_provider_event(
            "PROVIDER_REQUEST_STARTED",
            status="STARTED",
            details={
                "provider": "anthropic",
                "model": self.model,
                "attempt": 1,
                "max_attempts": 1,
                "attempt_timeout_seconds": round(effective_timeout, 2),
            },
        )
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(effective_timeout, connect=min(5.0, effective_timeout)),
                verify=_get_ssl_context(),
            ) as client:
                res = await asyncio.wait_for(
                    client.post(self.ENDPOINT, headers=headers, json=payload),
                    timeout=effective_timeout + 0.1,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000
                if res.status_code == 401:
                    self._emit_provider_event("PROVIDER_FAILURE", status="FAILED", elapsed_ms=elapsed_ms, details={"provider": "anthropic", "model": self.model, "http_status": 401, "error_code": "PROVIDER_AUTH_ERROR"})
                    raise ProviderAuthenticationError("anthropic", "Invalid Anthropic API key.")
                elif res.status_code == 429:
                    self._emit_provider_event("PROVIDER_FAILURE", status="FAILED", elapsed_ms=elapsed_ms, details={"provider": "anthropic", "model": self.model, "http_status": 429, "error_code": "PROVIDER_RATE_LIMIT"})
                    raise ProviderRateLimitError("anthropic", res.text)
                elif res.status_code >= 400:
                    self._emit_provider_event("PROVIDER_FAILURE", status="FAILED", elapsed_ms=elapsed_ms, details={"provider": "anthropic", "model": self.model, "http_status": res.status_code, "error_code": "PROVIDER_API_ERROR"})
                    raise ProviderAPIError("anthropic", f"Status {res.status_code}: {res.text}", status_code=res.status_code)

                data = res.json()
                content = data.get("content", [])
                text_blocks = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and (item.get("type") == "text" or "text" in item)
                ]
                if text_blocks:
                    self._emit_provider_event("PROVIDER_RESPONSE_RECEIVED", status="OK", elapsed_ms=elapsed_ms, details={"provider": "anthropic", "model": self.model, "attempt": 1, "max_attempts": 1, "http_status": 200})
                    self._emit_provider_event("PROVIDER_SUCCESS", status="SUCCESS", elapsed_ms=elapsed_ms, details={"provider": "anthropic", "model": self.model, "attempts_used": 1})
                    return NormalizedLLMResponse(
                        "".join(text_blocks).strip(),
                        provider="anthropic",
                        model=self.model,
                        finish_reason="stop",
                        latency_ms=elapsed_ms,
                        is_local=False,
                    )
                raise ProviderAPIError("anthropic", "Malformed response structure: no text content blocks returned from Anthropic API.")
        except asyncio.CancelledError:
            self._emit_provider_event("PROVIDER_FAILURE", status="CANCELLED", elapsed_ms=(time.monotonic() - t0) * 1000, details={"provider": "anthropic", "model": self.model, "error_code": "REQUEST_CANCELLED"})
            raise
        except (httpx.TimeoutException, asyncio.TimeoutError):
            self._emit_provider_event("PROVIDER_FAILURE", status="TIMEOUT", elapsed_ms=(time.monotonic() - t0) * 1000, details={"provider": "anthropic", "model": self.model, "error_code": "PROVIDER_TIMEOUT"})
            raise ProviderTimeoutError("anthropic", effective_timeout)
        except httpx.RequestError as e:
            self._emit_provider_event("PROVIDER_FAILURE", status="FAILED", elapsed_ms=(time.monotonic() - t0) * 1000, details={"provider": "anthropic", "model": self.model, "error_code": "PROVIDER_NETWORK_ERROR"})
            raise ProviderAPIError("anthropic", f"Network connection error: {str(e)}")


class OpenAICompatibleProvider(BaseLLMProvider):
    """Adapter for OpenAI, Groq, Gemini, or self-hosted OpenAI-compatible LLM endpoints."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        provider_name: str = "openai",
        operation_timeout: Optional[float] = None,
        max_attempts: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
    ):
        # Preserve test semantics when explicit custom timeout is provided directly without operation_timeout
        effective_max_attempts = int(max_attempts) if max_attempts is not None else int(settings.LLM_MAX_ATTEMPTS)
        resolved_op = operation_timeout
        if resolved_op is None and timeout is not None:
            resolved_op = max(float(settings.LLM_OPERATION_TIMEOUT_SECONDS), float(timeout) * max(1, effective_max_attempts))
        super().__init__(
            model=model,
            api_key=api_key,
            timeout=timeout,
            operation_timeout=resolved_op,
            max_attempts=effective_max_attempts,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
        )
        self.provider_name = provider_name
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def _compute_backoff(self, attempt: int, retry_after_header: Optional[str] = None) -> float:
        if retry_after_header and retry_after_header.strip().isdigit():
            raw = float(retry_after_header.strip())
            return min(raw, max(self.retry_max_delay, 4.0))
        exp = self.retry_base_delay * (2 ** attempt)
        jitter = random.uniform(0.05, 0.25) if self.retry_max_delay > 0 else 0.0
        return min(exp + jitter, self.retry_max_delay)

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: Optional[str] = None,
        **kwargs: Any,
    ) -> NormalizedLLMResponse:
        is_local_endpoint = (
            self.provider_name == "ollama"
            or "localhost" in self.base_url
            or "127.0.0.1" in self.base_url
        )
        if not self.api_key and not is_local_endpoint:
            self._emit_provider_event(
                "PROVIDER_FAILURE",
                status="FAILED",
                details={"provider": self.provider_name, "model": self.model, "error_code": "MISSING_API_KEY"},
            )
            raise MissingAPIKeyError(self.provider_name)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "FinTechAgent/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider_name == "gemini" and self.api_key:
            headers["x-goog-api-key"] = self.api_key

        msgs = self._build_messages_payload(
            user_message=user_message,
            conversation_history=conversation_history,
            include_system_role=True,
            system_prompt=system_prompt
        )

        payload = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": 1024,
            "temperature": 0.2,
        }
        if reasoning_effort and self.provider_name in {"gemini", "google", "openai", "groq"}:
            payload["reasoning_effort"] = str(reasoning_effort).lower().strip()

        url = f"{self.base_url}/chat/completions"
        max_attempts = max(1, int(self.max_attempts))
        ctx = get_active_request_context()
        op_start = time.monotonic()

        effective_op_budget = float(self.operation_timeout)
        if ctx and ctx.deadline:
            reserve = float(settings.BACKEND_PROCESSING_RESERVE_SECONDS)
            rem_req = max(0.0, ctx.deadline.remaining_seconds() - reserve)
            if rem_req <= 0.1:
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="TIMEOUT",
                    elapsed_ms=0.0,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "error_code": "PROVIDER_TIMEOUT",
                        "error_message": "Request deadline budget exhausted prior to provider call.",
                    },
                )
                raise ProviderTimeoutError(
                    self.provider_name,
                    self.timeout,
                    message=f"Request deadline budget exhausted before calling {self.provider_name}.",
                )
            effective_op_budget = min(effective_op_budget, rem_req)

        op_deadline = op_start + effective_op_budget
        base_timeout = httpx.Timeout(float(self.timeout), connect=min(10.0, float(self.timeout)))
        async with httpx.AsyncClient(timeout=base_timeout, verify=_get_ssl_context()) as client:
            return await self._execute_with_retry_client(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                max_attempts=max_attempts,
                op_start=op_start,
                op_deadline=op_deadline,
                effective_op_budget=effective_op_budget,
                reasoning_effort=reasoning_effort,
            )

    async def _execute_with_retry_client(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        max_attempts: int,
        op_start: float,
        op_deadline: float,
        effective_op_budget: float,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        last_exception: Optional[Exception] = None
        last_http_status: Optional[int] = None
        attempt_reserve = min(
            float(getattr(settings, "LLM_ATTEMPT_RESERVE_SECONDS", 1.0)),
            max(0.05, effective_op_budget * 0.1),
        )
        min_retry_budget = min(
            float(getattr(settings, "LLM_MIN_RETRY_BUDGET_SECONDS", 4.0)),
            max(0.15, effective_op_budget * 0.35),
        )

        for attempt in range(max_attempts):
            attempt_num = attempt + 1
            remaining_op = op_deadline - time.monotonic()
            if remaining_op <= 0.25:
                break

            # Calculate this attempt's allowable timeout dynamically from remaining operation budget
            budget_for_attempt = max(0.1, remaining_op - attempt_reserve)
            attempt_timeout = max(0.05, min(float(self.timeout), budget_for_attempt) if self.timeout else budget_for_attempt)
            attempt_start = time.monotonic()
            self._emit_provider_event(
                "PROVIDER_REQUEST_STARTED",
                status="STARTED",
                details={
                    "provider": self.provider_name,
                    "model": self.model,
                    "attempt": attempt_num,
                    "max_attempts": max_attempts,
                    "attempt_timeout_seconds": round(attempt_timeout, 2),
                    "remaining_budget_seconds": round(remaining_op, 2),
                    **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
                },
            )

            try:
                client_timeout = httpx.Timeout(attempt_timeout, connect=min(5.0, attempt_timeout))
                res = await asyncio.wait_for(
                    client.post(url, headers=headers, json=payload, timeout=client_timeout),
                    timeout=attempt_timeout + 0.15,
                )
                attempt_ms = (time.monotonic() - attempt_start) * 1000
                total_ms = (time.monotonic() - op_start) * 1000
                last_http_status = res.status_code

                # 1. Non-retryable authentication & client errors
                if res.status_code == 401:
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": 401,
                            "error_code": "PROVIDER_AUTH_ERROR",
                        },
                    )
                    raise ProviderAuthenticationError(self.provider_name, "Invalid API key.")
                elif res.status_code == 403:
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": 403,
                            "error_code": "PROVIDER_AUTH_ERROR",
                        },
                    )
                    raise ProviderAuthenticationError(self.provider_name, f"Forbidden / Permission denied (403): {res.text}")
                elif res.status_code in (400, 404):
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": res.status_code,
                            "error_code": "PROVIDER_API_ERROR",
                        },
                    )
                    raise ProviderAPIError(self.provider_name, f"Status {res.status_code}: {res.text}", status_code=res.status_code)

                # 2. Rate limit & quota errors
                elif res.status_code == 429:
                    error_text = res.text.lower()
                    if "insufficient_quota" in error_text or "quota_exceeded" in error_text or "billing" in error_text:
                        self._emit_provider_event(
                            "PROVIDER_FAILURE",
                            status="FAILED",
                            elapsed_ms=total_ms,
                            details={
                                "provider": self.provider_name,
                                "model": self.model,
                                "attempt": attempt_num,
                                "max_attempts": max_attempts,
                                "http_status": 429,
                                "error_code": "PROVIDER_RATE_LIMIT",
                            },
                        )
                        raise ProviderRateLimitError(self.provider_name, f"Quota exhausted: {res.text}")

                    self._emit_provider_event(
                        "PROVIDER_RETRYABLE_ERROR",
                        status="RATE_LIMIT",
                        elapsed_ms=attempt_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": 429,
                            "error_type": "HTTP_429",
                        },
                    )
                    wait_sec = self._compute_backoff(attempt, res.headers.get("retry-after"))
                    rem_after_attempt = op_deadline - time.monotonic()
                    budget_for_next_attempt = rem_after_attempt - wait_sec
                    if attempt < max_attempts - 1 and budget_for_next_attempt >= min_retry_budget:
                        self._emit_provider_event(
                            "PROVIDER_RETRY_SCHEDULED",
                            status="RETRYING",
                            details={
                                "provider": self.provider_name,
                                "model": self.model,
                                "attempt": attempt_num,
                                "next_attempt": attempt_num + 1,
                                "max_attempts": max_attempts,
                                "delay_seconds": round(wait_sec, 2),
                                "reason": "HTTP_429",
                            },
                        )
                        logger.warning(f"[{self.provider_name}] Transient 429 rate limit. Retrying in {wait_sec:.2f}s (attempt {attempt_num}/{max_attempts}, remaining budget {budget_for_next_attempt:.1f}s)...")
                        await asyncio.sleep(wait_sec)
                        continue
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempts_used": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": 429,
                            "error_code": "PROVIDER_RATE_LIMIT",
                        },
                    )
                    raise ProviderRateLimitError(self.provider_name, res.text)

                # 3. Server-side transient errors (500, 502, 503, 504)
                elif res.status_code in (500, 502, 503, 504):
                    self._emit_provider_event(
                        "PROVIDER_RETRYABLE_ERROR",
                        status=f"HTTP_{res.status_code}",
                        elapsed_ms=attempt_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": res.status_code,
                            "error_type": f"HTTP_{res.status_code}",
                        },
                    )
                    last_exception = ProviderAPIError(self.provider_name, f"Status {res.status_code}: {res.text}", status_code=res.status_code)
                    wait_sec = self._compute_backoff(attempt, res.headers.get("retry-after"))
                    rem_after_attempt = op_deadline - time.monotonic()
                    budget_for_next_attempt = rem_after_attempt - wait_sec
                    if attempt < max_attempts - 1 and budget_for_next_attempt >= min_retry_budget:
                        self._emit_provider_event(
                            "PROVIDER_RETRY_SCHEDULED",
                            status="RETRYING",
                            details={
                                "provider": self.provider_name,
                                "model": self.model,
                                "attempt": attempt_num,
                                "next_attempt": attempt_num + 1,
                                "max_attempts": max_attempts,
                                "delay_seconds": round(wait_sec, 2),
                                "reason": f"HTTP_{res.status_code}",
                            },
                        )
                        logger.warning(f"[{self.provider_name}] Transient status {res.status_code}. Retrying in {wait_sec:.2f}s (attempt {attempt_num}/{max_attempts}, remaining budget {budget_for_next_attempt:.1f}s)...")
                        await asyncio.sleep(wait_sec)
                        continue
                    err_code = "PROVIDER_UNAVAILABLE" if res.status_code == 503 else "PROVIDER_RETRY_EXHAUSTED"
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempts_used": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": res.status_code,
                            "error_code": err_code,
                        },
                    )
                    raise ProviderRetryExhaustedError(
                        self.provider_name,
                        f"Status {res.status_code}: {res.text}",
                        status_code=res.status_code,
                        error_code=err_code,
                    )

                elif res.status_code >= 400:
                    self._emit_provider_event(
                        "PROVIDER_FAILURE",
                        status="FAILED",
                        elapsed_ms=total_ms,
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempts_used": attempt_num,
                            "max_attempts": max_attempts,
                            "http_status": res.status_code,
                            "error_code": "PROVIDER_API_ERROR",
                        },
                    )
                    raise ProviderAPIError(self.provider_name, f"Status {res.status_code}: {res.text}", status_code=res.status_code)

                self._emit_provider_event(
                    "PROVIDER_RESPONSE_RECEIVED",
                    status="OK",
                    elapsed_ms=attempt_ms,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempt": attempt_num,
                        "max_attempts": max_attempts,
                        "http_status": res.status_code,
                    },
                )

                data = res.json()
                choices = data.get("choices", [])
                if not choices:
                    raise ProviderAPIError(self.provider_name, "Empty choices returned from chat completion endpoint.")

                first_choice = choices[0]
                finish_reason = first_choice.get("finish_reason")
                if finish_reason == "content_filter":
                    raise ProviderAPIError(self.provider_name, "Response was filtered by provider safety controls.", status_code=400)

                message_obj = first_choice.get("message", {})
                content_text = message_obj.get("content")
                if content_text is None:
                    refusal = message_obj.get("refusal")
                    if refusal:
                        self._emit_provider_event(
                            "PROVIDER_SUCCESS",
                            status="SUCCESS",
                            elapsed_ms=total_ms,
                            details={"provider": self.provider_name, "model": self.model, "attempts_used": attempt_num, "http_status": 200},
                        )
                        return f"[Refusal]: {refusal}"
                    raise ProviderAPIError(self.provider_name, "Null content received in chat completion response.")

                self._emit_provider_event(
                    "PROVIDER_SUCCESS",
                    status="SUCCESS",
                    elapsed_ms=total_ms,
                    details={"provider": self.provider_name, "model": self.model, "attempts_used": attempt_num, "http_status": 200},
                )
                return NormalizedLLMResponse(
                    content_text.strip(),
                    provider=self.provider_name,
                    model=self.model,
                    finish_reason=finish_reason or "stop",
                    latency_ms=total_ms,
                    usage=data.get("usage") or {},
                    request_id=data.get("id"),
                    is_local=(self.provider_name == "ollama"),
                )

            except asyncio.CancelledError:
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="CANCELLED",
                    elapsed_ms=(time.monotonic() - op_start) * 1000,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempts_used": attempt_num,
                        "max_attempts": max_attempts,
                        "error_code": "REQUEST_CANCELLED",
                    },
                )
                raise
            except (ProviderAuthenticationError, ProviderRateLimitError, ProviderConfigurationError):
                raise
            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                last_exception = exc
                attempt_ms = (time.monotonic() - attempt_start) * 1000
                total_ms = (time.monotonic() - op_start) * 1000
                self._emit_provider_event(
                    "PROVIDER_RETRYABLE_ERROR",
                    status="TIMEOUT",
                    elapsed_ms=attempt_ms,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempt": attempt_num,
                        "max_attempts": max_attempts,
                        "error_type": "TIMEOUT",
                    },
                )
                wait_sec = self._compute_backoff(attempt)
                rem_after_attempt = op_deadline - time.monotonic()
                budget_for_next_attempt = rem_after_attempt - wait_sec
                if attempt < max_attempts - 1 and budget_for_next_attempt >= min_retry_budget:
                    self._emit_provider_event(
                        "PROVIDER_RETRY_SCHEDULED",
                        status="RETRYING",
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "next_attempt": attempt_num + 1,
                            "max_attempts": max_attempts,
                            "delay_seconds": round(wait_sec, 2),
                            "reason": "TIMEOUT",
                        },
                    )
                    logger.warning(f"[{self.provider_name}] Timeout encountered. Retrying in {wait_sec:.2f}s (attempt {attempt_num}/{max_attempts}, remaining budget {budget_for_next_attempt:.1f}s)...")
                    await asyncio.sleep(wait_sec)
                    continue
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="TIMEOUT",
                    elapsed_ms=total_ms,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempts_used": attempt_num,
                        "max_attempts": max_attempts,
                        "error_code": "PROVIDER_TIMEOUT",
                    },
                )
                if isinstance(exc, httpx.ConnectTimeout):
                    to_msg = f"Call to {self.provider_name} connection handshake timed out after {attempt_ms/1000:.2f}s."
                else:
                    to_msg = f"Call to {self.provider_name} timed out after {round(attempt_timeout, 2)} seconds."
                raise ProviderTimeoutError(self.provider_name, round(attempt_timeout, 2), message=to_msg)
            except httpx.RequestError as exc:
                last_exception = exc
                attempt_ms = (time.monotonic() - attempt_start) * 1000
                total_ms = (time.monotonic() - op_start) * 1000
                self._emit_provider_event(
                    "PROVIDER_RETRYABLE_ERROR",
                    status="NETWORK_ERROR",
                    elapsed_ms=attempt_ms,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempt": attempt_num,
                        "max_attempts": max_attempts,
                        "error_type": type(exc).__name__,
                    },
                )
                wait_sec = self._compute_backoff(attempt)
                rem_after_attempt = op_deadline - time.monotonic()
                budget_for_next_attempt = rem_after_attempt - wait_sec
                if attempt < max_attempts - 1 and budget_for_next_attempt >= min_retry_budget:
                    self._emit_provider_event(
                        "PROVIDER_RETRY_SCHEDULED",
                        status="RETRYING",
                        details={
                            "provider": self.provider_name,
                            "model": self.model,
                            "attempt": attempt_num,
                            "next_attempt": attempt_num + 1,
                            "max_attempts": max_attempts,
                            "delay_seconds": round(wait_sec, 2),
                            "reason": "NETWORK_ERROR",
                        },
                    )
                    logger.warning(f"[{self.provider_name}] Network connection error: {exc}. Retrying in {wait_sec:.2f}s (attempt {attempt_num}/{max_attempts}, remaining budget {budget_for_next_attempt:.1f}s)...")
                    await asyncio.sleep(wait_sec)
                    continue
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="FAILED",
                    elapsed_ms=total_ms,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "attempts_used": attempt_num,
                        "max_attempts": max_attempts,
                        "error_code": "PROVIDER_RETRY_EXHAUSTED",
                    },
                )
                raise ProviderRetryExhaustedError(
                    self.provider_name,
                    f"Network connection error: {str(exc)}",
                    status_code=503,
                    error_code="PROVIDER_RETRY_EXHAUSTED",
                )

        # Deadline budget exhausted between attempts before reaching max_attempts
        total_ms = (time.monotonic() - op_start) * 1000
        self._emit_provider_event(
            "PROVIDER_FAILURE",
            status="TIMEOUT",
            elapsed_ms=total_ms,
            details={
                "provider": self.provider_name,
                "model": self.model,
                "attempts_used": max_attempts if last_exception is None else None,
                "max_attempts": max_attempts,
                "http_status": last_http_status,
                "error_code": "PROVIDER_TIMEOUT",
                "error_message": "Provider operation deadline exhausted across retries.",
            },
        )
        if isinstance(last_exception, (httpx.TimeoutException, asyncio.TimeoutError)) or last_exception is None:
            raise ProviderTimeoutError(
                self.provider_name,
                round(effective_op_budget, 2),
                message=f"Call to {self.provider_name} exceeded operation deadline of {effective_op_budget:.1f}s.",
            )
        if isinstance(last_exception, ProviderAPIError):
            raise ProviderRetryExhaustedError(
                self.provider_name,
                f"Operation deadline exceeded after transient failures: {last_exception.message}",
                status_code=last_exception.status_code,
                error_code="PROVIDER_UNAVAILABLE" if last_exception.status_code == 503 else "PROVIDER_RETRY_EXHAUSTED",
            )
        raise ProviderRetryExhaustedError(
            self.provider_name,
            f"Network connection error: {last_exception}",
            status_code=503,
            error_code="PROVIDER_RETRY_EXHAUSTED",
        )


def is_recoverable_failure(exc: Exception) -> bool:
    """
    Classifies whether an exception is an eligible recoverable failure for multi-provider fallback.
    Eligible: network errors, timeouts, HTTP 500, 502, 503, 504, temporary rate limits.
    Ineligible: HTTP 400, 401, 403, 404, quota exhaustion, cancellation, security rejections.
    """
    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, ProviderAuthenticationError):
        return False
    if isinstance(exc, MissingAPIKeyError):
        return False
    if isinstance(exc, ProviderRateLimitError):
        msg = str(exc).lower()
        if any(term in msg for term in ("insufficient_quota", "quota_exceeded", "billing", "quota exhausted")):
            return False
        return True
    if isinstance(exc, ProviderTimeoutError):
        return True
    if isinstance(exc, ProviderUnavailableError):
        return True
    if isinstance(exc, ProviderRetryExhaustedError):
        return True
    if isinstance(exc, ProviderAPIError):
        if exc.status_code in (400, 401, 403, 404):
            return False
        if exc.status_code in (500, 502, 503, 504, 520, 521, 522, 523, 524):
            return True
        if "network" in str(exc).lower() or "connection" in str(exc).lower():
            return True
        return False
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, httpx.RequestError)):
        return True
    return False


class FallbackProviderManager(OpenAICompatibleProvider):
    """
    Centralized multi-provider fallback manager.
    Coordinates sequential execution:
        Primary (Gemini 3.8 Flash) -> Fallback 1 (Groq GPT-OSS 120B) -> Fallback 2 (Local Ollama K2 Horizon 3.7B) -> Controlled Error.
    Inherits from OpenAICompatibleProvider so existing callers and test assertions
    (e.g. isinstance(provider, OpenAICompatibleProvider)) continue to pass seamlessly.
    """

    def __init__(
        self,
        primary_provider: BaseLLMProvider,
        fallback_providers: List[BaseLLMProvider],
        operation_timeout: Optional[float] = None,
        min_retry_budget: Optional[float] = None,
    ):
        super().__init__(
            model=primary_provider.model,
            api_key=primary_provider.api_key,
            timeout=primary_provider.timeout,
            provider_name=getattr(primary_provider, "provider_name", "gemini"),
            operation_timeout=operation_timeout or primary_provider.operation_timeout,
            max_attempts=primary_provider.max_attempts,
            retry_base_delay=primary_provider.retry_base_delay,
            retry_max_delay=primary_provider.retry_max_delay,
        )
        self.primary_provider = primary_provider
        self.fallback_providers = list(fallback_providers)
        self.min_retry_budget = (
            float(min_retry_budget)
            if min_retry_budget is not None
            else float(settings.LLM_MIN_RETRY_BUDGET_SECONDS)
        )

    @property
    def provider_chain(self) -> List[BaseLLMProvider]:
        return [self.primary_provider] + self.fallback_providers

    def _is_provider_eligible(self, provider: BaseLLMProvider) -> bool:
        """Determines if a provider is eligible to run as fallback based on credentials and configuration."""
        prov_name = getattr(provider, "provider_name", "unknown").lower()
        if prov_name == "groq" and not provider.api_key:
            return False
        if prov_name == "ollama" and not getattr(settings, "OLLAMA_ENABLED", True):
            return False
        if prov_name in ("gemini", "anthropic", "openai") and not provider.api_key:
            return False
        return True

    def get_effective_chain(self, preferred_provider: Optional[str] = None) -> List[BaseLLMProvider]:
        """
        Orders provider execution sequence according to request-scoped provider selection.
        If a preferred healthy provider is set, places it first, followed by subsequent providers
        in the fallback sequence to prevent retrying a failed primary provider.
        """
        configured_chain = [self.primary_provider] + self.fallback_providers
        if not preferred_provider:
            return configured_chain
        pref_clean = preferred_provider.strip().lower()
        match_idx = -1
        for idx, prov in enumerate(configured_chain):
            if getattr(prov, "provider_name", "").strip().lower() == pref_clean:
                match_idx = idx
                break
        if match_idx == -1:
            return configured_chain
        # Rotate chain so preferred provider is evaluated first, followed by remaining sequence
        return configured_chain[match_idx:] + configured_chain[:match_idx]

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        **kwargs: Any,
    ) -> NormalizedLLMResponse:
        op_start = time.monotonic()
        ctx = get_active_request_context()

        effective_op_budget = float(self.operation_timeout)
        if ctx and ctx.deadline:
            reserve = float(settings.BACKEND_PROCESSING_RESERVE_SECONDS)
            rem_req = max(0.0, ctx.deadline.remaining_seconds() - reserve)
            if rem_req <= 0.1:
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="TIMEOUT",
                    elapsed_ms=0.0,
                    details={
                        "provider": self.provider_name,
                        "model": self.model,
                        "error_code": "PROVIDER_TIMEOUT",
                        "error_message": "Request deadline budget exhausted prior to fallback dispatch.",
                    },
                )
                raise ProviderTimeoutError(
                    self.provider_name,
                    self.timeout,
                    message=f"Request deadline budget exhausted before calling {self.provider_name}.",
                )
            effective_op_budget = min(effective_op_budget, rem_req)

        op_deadline = op_start + effective_op_budget
        attempted_providers: List[str] = []
        failure_reasons: Dict[str, str] = {}
        skipped_providers: Dict[str, str] = {}
        prev_provider: Optional[BaseLLMProvider] = None

        effective_preferred = preferred_provider or get_request_preferred_provider()
        chain = self.get_effective_chain(effective_preferred)
        if effective_preferred:
            logger.info(
                f"[fallback_manager] Request-scoped provider selection active: starting with preferred provider "
                f"'{effective_preferred}' (sequence: {[getattr(p, 'provider_name', '') for p in chain]})"
            )

        for idx, provider in enumerate(chain):
            prov_name = getattr(provider, "provider_name", "unknown")
            is_fallback = (idx > 0)
            now = time.monotonic()
            rem_op = op_deadline - now

            # If overall deadline exhausted:
            if rem_op <= 0.25:
                skipped_providers[prov_name] = "deadline_budget_exhausted"
                break

            # If fallback provider, verify conditions:
            if is_fallback:
                # 1. Budget check:
                if rem_op < self.min_retry_budget:
                    reason = f"insufficient_budget ({rem_op:.2f}s < {self.min_retry_budget:.1f}s)"
                    skipped_providers[prov_name] = reason
                    self._emit_provider_event(
                        "PROVIDER_FALLBACK_SKIPPED",
                        status="SKIPPED",
                        details={
                            "provider": prov_name,
                            "model": provider.model,
                            "reason": "insufficient_budget",
                            "remaining_budget_seconds": round(rem_op, 2),
                        },
                    )
                    logger.warning(f"[fallback_manager] Skipping fallback to '{prov_name}': {reason}")
                    continue

                # 2. Availability / configuration check:
                if prov_name == "groq" and not provider.api_key:
                    reason = "missing_api_key"
                    skipped_providers[prov_name] = reason
                    self._emit_provider_event(
                        "PROVIDER_FALLBACK_SKIPPED",
                        status="SKIPPED",
                        details={
                            "provider": prov_name,
                            "model": provider.model,
                            "reason": reason,
                            "remaining_budget_seconds": round(rem_op, 2),
                        },
                    )
                    logger.warning(f"[fallback_manager] Skipping fallback to '{prov_name}': GROQ_API_KEY is not configured.")
                    continue

                if prov_name == "ollama" and not settings.OLLAMA_ENABLED:
                    reason = "ollama_disabled"
                    skipped_providers[prov_name] = reason
                    self._emit_provider_event(
                        "PROVIDER_FALLBACK_SKIPPED",
                        status="SKIPPED",
                        details={
                            "provider": prov_name,
                            "model": provider.model,
                            "reason": reason,
                            "remaining_budget_seconds": round(rem_op, 2),
                        },
                    )
                    logger.warning(f"[fallback_manager] Skipping fallback to '{prov_name}': OLLAMA_ENABLED is false.")
                    continue

                # Emit fallback started event:
                self._emit_provider_event(
                    "PROVIDER_FALLBACK_STARTED",
                    status="STARTED",
                    details={
                        "source_provider": getattr(prev_provider, "provider_name", "primary"),
                        "target_provider": prov_name,
                        "target_model": provider.model,
                        "remaining_budget_seconds": round(rem_op, 2),
                    },
                )
                logger.info(
                    f"[fallback_manager] Activating fallback '{prov_name}' (model='{provider.model}', "
                    f"remaining_budget={rem_op:.1f}s)..."
                )

            # Allocate provider budget so an individual provider cannot consume the entire remaining budget
            # and starve subsequent eligible fallback providers.
            subsequent_eligible = [
                p for p in chain[idx + 1:]
                if self._is_provider_eligible(p)
            ]
            if subsequent_eligible and rem_op > self.min_retry_budget:
                allocated_budget = max(0.5, rem_op - self.min_retry_budget)
            else:
                allocated_budget = rem_op

            provider.operation_timeout = allocated_budget
            base_timeout = getattr(provider, "_configured_timeout", provider.timeout)
            provider.timeout = max(0.2, min(base_timeout, allocated_budget - 0.2))
            prev_provider = provider

            try:
                # Parameter mapping: Ollama rejects reasoning_effort!
                effort = reasoning_effort if prov_name in {"gemini", "google", "openai", "groq"} else None
                resp = await provider.generate_response(
                    user_message=user_message,
                    conversation_history=conversation_history,
                    system_prompt=system_prompt,
                    reasoning_effort=effort,
                )
                attempted_providers.append(prov_name)

                # Record healthy selected provider in request context
                set_request_preferred_provider(prov_name)
                if effective_preferred and effective_preferred.lower() != prov_name.lower():
                    logger.info(
                        f"[fallback_manager] Transitioned preferred provider from '{effective_preferred}' to '{prov_name}'."
                    )
                else:
                    logger.info(
                        f"[fallback_manager] Provider '{prov_name}' succeeded. Preserved as request-scoped preferred provider."
                    )

                # Normalize response
                if not isinstance(resp, NormalizedLLMResponse):
                    resp = NormalizedLLMResponse(
                        str(resp),
                        provider=prov_name,
                        model=provider.model,
                        finish_reason="stop",
                        latency_ms=(time.monotonic() - now) * 1000,
                        is_local=(prov_name == "ollama"),
                    )

                self._emit_provider_event(
                    "PROVIDER_ATTEMPT_COMPLETED",
                    status="COMPLETED",
                    elapsed_ms=(time.monotonic() - now) * 1000,
                    details={
                        "provider": prov_name,
                        "model": provider.model,
                        "is_fallback": is_fallback,
                        "selected_provider": prov_name,
                    },
                )
                return resp

            except asyncio.CancelledError:
                self._emit_provider_event(
                    "PROVIDER_FAILURE",
                    status="CANCELLED",
                    elapsed_ms=(time.monotonic() - op_start) * 1000,
                    details={"provider": prov_name, "model": provider.model, "error_code": "REQUEST_CANCELLED"},
                )
                raise

            except Exception as exc:
                attempted_providers.append(prov_name)
                failure_reasons[prov_name] = str(exc)
                self._emit_provider_event(
                    "PROVIDER_ATTEMPT_FAILED",
                    status="FAILED",
                    elapsed_ms=(time.monotonic() - now) * 1000,
                    details={
                        "provider": prov_name,
                        "model": provider.model,
                        "error_type": type(exc).__name__,
                        "error_message": sanitize_error_message(str(exc)),
                        "is_recoverable": is_recoverable_failure(exc),
                    },
                )

                # Strict check: Non-recoverable failures abort immediately without further fallback
                if not is_recoverable_failure(exc):
                    logger.warning(
                        f"[fallback_manager] Provider '{prov_name}' failed with non-recoverable error "
                        f"({type(exc).__name__}: {exc}). Aborting fallback chain immediately."
                    )
                    raise

                logger.warning(
                    f"[fallback_manager] Provider '{prov_name}' failed with recoverable error "
                    f"({type(exc).__name__}: {exc}). Continuing to next eligible provider in chain."
                )

            finally:
                # Restore original configured timeout on provider instance
                provider.timeout = base_timeout

        total_ms = (time.monotonic() - op_start) * 1000
        deadline_exhausted = (time.monotonic() >= op_deadline - 0.5)
        self._emit_provider_event(
            "PROVIDER_CHAIN_EXHAUSTED",
            status="FAILED",
            elapsed_ms=total_ms,
            details={
                "attempted_providers": attempted_providers,
                "failure_reasons": failure_reasons,
                "skipped_providers": skipped_providers,
                "deadline_exhausted": deadline_exhausted,
            },
        )
        raise LLMFallbackExhaustedError(
            attempted_providers=attempted_providers,
            failure_reasons=failure_reasons,
            deadline_exhausted=deadline_exhausted,
            skipped_providers=skipped_providers,
        )


class LLMService:
    """Factory and dispatcher for externalized LLM providers with centralized fallback orchestration."""

    def __init__(self):
        self._provider_instance: Optional[BaseLLMProvider] = None

    def _build_single_provider(self, name: str) -> BaseLLMProvider:
        prov = (name or "").lower().strip()
        attempt_timeout = float(min(settings.LLM_ATTEMPT_TIMEOUT_SECONDS, settings.LLM_TIMEOUT_SECONDS))
        op_timeout = float(settings.LLM_OPERATION_TIMEOUT_SECONDS)
        max_attempts = int(settings.LLM_MAX_ATTEMPTS)
        base_delay = float(settings.LLM_RETRY_BASE_DELAY_SECONDS)
        max_delay = float(settings.LLM_RETRY_MAX_DELAY_SECONDS)

        if prov == "mock":
            return MockLLMProvider(
                model=settings.LLM_MODEL,
                api_key=settings.get_provider_api_key("mock"),
                timeout=attempt_timeout,
                operation_timeout=op_timeout,
                max_attempts=1,
            )
        elif prov == "anthropic":
            return AnthropicProvider(
                model=settings.LLM_MODEL,
                api_key=settings.get_provider_api_key("anthropic"),
                timeout=attempt_timeout,
                operation_timeout=op_timeout,
                max_attempts=1,
            )
        elif prov == "openai":
            return OpenAICompatibleProvider(
                model=settings.LLM_MODEL,
                api_key=settings.get_provider_api_key("openai"),
                base_url=settings.LLM_API_BASE_URL or "https://api.openai.com/v1",
                timeout=attempt_timeout,
                provider_name="openai",
                operation_timeout=op_timeout,
                max_attempts=max_attempts,
                retry_base_delay=base_delay,
                retry_max_delay=max_delay,
            )
        elif prov == "groq":
            return OpenAICompatibleProvider(
                model=settings.GROQ_MODEL,
                api_key=settings.get_provider_api_key("groq"),
                base_url=settings.GROQ_BASE_URL,
                timeout=attempt_timeout,
                provider_name="groq",
                operation_timeout=op_timeout,
                max_attempts=1,
                retry_base_delay=base_delay,
                retry_max_delay=max_delay,
            )
        elif prov == "ollama":
            return OpenAICompatibleProvider(
                model=settings.OLLAMA_MODEL,
                api_key=None,
                base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
                timeout=attempt_timeout,
                provider_name="ollama",
                operation_timeout=op_timeout,
                max_attempts=1,
                retry_base_delay=base_delay,
                retry_max_delay=max_delay,
            )
        elif prov in {"gemini", "google"}:
            base_url = settings.LLM_API_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai"
            return OpenAICompatibleProvider(
                model=settings.LLM_MODEL,
                api_key=settings.get_provider_api_key("gemini"),
                base_url=base_url,
                timeout=attempt_timeout,
                provider_name="gemini",
                operation_timeout=op_timeout,
                max_attempts=min(max_attempts, 2),  # Permit at most 1 retry for primary Gemini
                retry_base_delay=base_delay,
                retry_max_delay=max_delay,
            )
        else:
            raise ProviderConfigurationError(f"Unsupported LLM provider: '{prov}'. Supported: mock, anthropic, openai, groq, gemini, ollama.")

    def get_provider(self) -> BaseLLMProvider:
        provider_name = (settings.LLM_PROVIDER or "").lower().strip()

        # Fail-fast check for production environment
        if settings.APP_ENV == "production":
            if not provider_name or provider_name == "mock":
                raise ProviderConfigurationError("Mock provider or unconfigured LLM_PROVIDER is prohibited in production environment.")

        if not provider_name:
            provider_name = "mock"

        # Mock mode does not use multi-provider fallback unless explicitly configured
        if provider_name == "mock":
            return self._build_single_provider("mock")

        # Fallback disabled: return single configured provider directly
        if not getattr(settings, "LLM_FALLBACK_ENABLED", True):
            return self._build_single_provider(provider_name)

        # Fallback enabled: construct primary + fallback chain
        primary = self._build_single_provider(provider_name)
        # When multi-provider fallback is active, give primary 1 full attempt so recoverable
        # errors fail over swiftly to Fallback 1 (Groq) within the shared deadline budget
        primary.max_attempts = 1

        fallbacks: List[BaseLLMProvider] = []
        order = getattr(settings, "llm_fallback_order_list", ["groq", "ollama"])
        for fb_name in order:
            if fb_name != provider_name:
                try:
                    fallbacks.append(self._build_single_provider(fb_name))
                except Exception as build_err:
                    logger.warning(f"[llm_service] Could not build fallback provider '{fb_name}': {build_err}")

        return FallbackProviderManager(
            primary_provider=primary,
            fallback_providers=fallbacks,
            operation_timeout=float(settings.LLM_OPERATION_TIMEOUT_SECONDS),
            min_retry_budget=float(settings.LLM_MIN_RETRY_BUDGET_SECONDS),
        )

    async def ask(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_effort: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        **kwargs: Any,
    ) -> NormalizedLLMResponse:
        """Dispatches message and optional history to configured provider adapter or fallback manager."""
        provider = self.get_provider()
        history_len = len(conversation_history) if conversation_history else 0
        logger.info(f"Dispatching query to provider='{settings.LLM_PROVIDER}', model='{settings.LLM_MODEL}', history_turns={history_len}")
        return await provider.generate_response(
            user_message,
            conversation_history=conversation_history,
            reasoning_effort=reasoning_effort,
            preferred_provider=preferred_provider,
            **kwargs,
        )

    async def check_provider_health(self) -> Dict[str, Any]:
        """
        Lightweight health inspection of configured providers without expensive inference generation.
        Distinguishes: configured, missing_credentials, endpoint_unreachable, model_unavailable,
        healthy, temporarily_unavailable, authentication_failure, timed_out, disabled.
        Runs checks concurrently with a strict 3.0s per-provider timeout.
        """
        results: Dict[str, Any] = {}

        if (settings.LLM_PROVIDER or "").lower() == "mock":
            results["mock"] = {
                "status": "healthy",
                "model": "mock",
                "configured": True,
                "role": "primary",
            }
            return {
                "primary_provider": "mock",
                "fallback_enabled": False,
                "fallback_order": [],
                "providers": results,
            }

        async def _check_gemini() -> tuple[str, Dict[str, Any]]:
            gem_key = settings.get_provider_api_key("gemini")
            if not gem_key:
                return "gemini", {
                    "status": "missing_credentials",
                    "model": settings.LLM_MODEL,
                    "configured": False,
                    "role": "primary",
                    "detail": "GEMINI_API_KEY is not configured.",
                }
            base_url = settings.LLM_API_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai"
            try:
                async with httpx.AsyncClient(timeout=3.0, verify=_get_ssl_context()) as client:
                    resp = await client.get(
                        f"{base_url.rstrip('/')}/models",
                        headers={"Authorization": f"Bearer {gem_key}", "x-goog-api-key": gem_key},
                    )
                    if resp.status_code == 200:
                        return "gemini", {"status": "healthy", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
                    elif resp.status_code in (401, 403):
                        return "gemini", {"status": "authentication_failure", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
                    elif resp.status_code == 503:
                        return "gemini", {"status": "temporarily_unavailable", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
                    else:
                        return "gemini", {"status": "configured", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
            except (httpx.TimeoutException, asyncio.TimeoutError):
                return "gemini", {"status": "timed_out", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
            except httpx.RequestError:
                return "gemini", {"status": "endpoint_unreachable", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}
            except Exception:
                return "gemini", {"status": "configured", "model": settings.LLM_MODEL, "configured": True, "role": "primary"}

        async def _check_groq() -> tuple[str, Dict[str, Any]]:
            groq_key = settings.get_provider_api_key("groq")
            if not groq_key:
                return "groq", {
                    "status": "missing_credentials",
                    "model": settings.GROQ_MODEL,
                    "configured": False,
                    "role": "fallback_1",
                    "detail": "GROQ_API_KEY is not configured.",
                }
            try:
                async with httpx.AsyncClient(timeout=3.0, verify=_get_ssl_context()) as client:
                    resp = await client.get(
                        f"{settings.GROQ_BASE_URL.rstrip('/')}/models",
                        headers={"Authorization": f"Bearer {groq_key}", "User-Agent": "FinTechAgent/1.0"},
                    )
                    if resp.status_code == 200:
                        return "groq", {"status": "healthy", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
                    elif resp.status_code in (401, 403):
                        return "groq", {"status": "authentication_failure", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
                    elif resp.status_code == 503:
                        return "groq", {"status": "temporarily_unavailable", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
                    else:
                        return "groq", {"status": "configured", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
            except (httpx.TimeoutException, asyncio.TimeoutError):
                return "groq", {"status": "timed_out", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
            except httpx.RequestError:
                return "groq", {"status": "endpoint_unreachable", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}
            except Exception:
                return "groq", {"status": "configured", "model": settings.GROQ_MODEL, "configured": True, "role": "fallback_1"}

        async def _check_ollama() -> tuple[str, Dict[str, Any]]:
            if not settings.OLLAMA_ENABLED:
                return "ollama", {
                    "status": "disabled",
                    "model": settings.OLLAMA_MODEL,
                    "configured": False,
                    "role": "fallback_2",
                    "is_local": True,
                }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
                    if resp.status_code == 200:
                        data = resp.json()
                        available_models = [m.get("name") for m in data.get("models", [])]
                        if settings.OLLAMA_MODEL in available_models or any(settings.OLLAMA_MODEL in m for m in available_models if m):
                            return "ollama", {
                                "status": "healthy",
                                "model": settings.OLLAMA_MODEL,
                                "configured": True,
                                "role": "fallback_2",
                                "is_local": True,
                            }
                        else:
                            return "ollama", {
                                "status": "model_unavailable",
                                "model": settings.OLLAMA_MODEL,
                                "configured": True,
                                "role": "fallback_2",
                                "is_local": True,
                                "detail": f"Model tag '{settings.OLLAMA_MODEL}' not present in Ollama tags.",
                            }
                    else:
                        return "ollama", {"status": "endpoint_unreachable", "model": settings.OLLAMA_MODEL, "configured": True, "role": "fallback_2", "is_local": True}
            except (httpx.TimeoutException, asyncio.TimeoutError):
                return "ollama", {"status": "timed_out", "model": settings.OLLAMA_MODEL, "configured": True, "role": "fallback_2", "is_local": True}
            except httpx.RequestError:
                return "ollama", {"status": "endpoint_unreachable", "model": settings.OLLAMA_MODEL, "configured": True, "role": "fallback_2", "is_local": True}
            except Exception:
                return "ollama", {"status": "configured", "model": settings.OLLAMA_MODEL, "configured": True, "role": "fallback_2", "is_local": True}

        check_tasks = [_check_gemini(), _check_groq(), _check_ollama()]
        completed_checks = await asyncio.gather(*check_tasks, return_exceptions=True)
        for check in completed_checks:
            if isinstance(check, tuple) and len(check) == 2:
                prov_name, prov_info = check
                results[prov_name] = prov_info

        return {
            "primary_provider": settings.LLM_PROVIDER,
            "fallback_enabled": settings.LLM_FALLBACK_ENABLED,
            "fallback_order": settings.llm_fallback_order_list,
            "providers": results,
        }


# Global singleton instance
llm_service = LLMService()
