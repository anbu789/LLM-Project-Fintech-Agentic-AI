"""
FinTech Agent — LLM Provider Service
Provider-independent adapter supporting Mock, Anthropic, OpenAI, Groq, and Gemini.
Includes multi-turn history handling, provider response safety shields, and fail-fast production checks.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx

from backend.app.config import settings
from backend.app.core.exceptions import (
    MissingAPIKeyError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderAPIError,
)
from backend.app.core.logging import logger

SYSTEM_PROMPT = (
    "You are FinTech Agent, an AI banking intelligence assistant for financial institutions. "
    "You assist banking operations, risk, compliance, and fraud analysts by explaining banking terminology, "
    "regulatory concepts (e.g., KYC, AML, NPA, DPD), and operational workflows accurately and professionally. "
    "Be concise, clear, and domain-accurate."
)


class BaseLLMProvider(ABC):
    """Abstract interface for LLM provider adapters."""

    def __init__(self, model: str, api_key: Optional[str] = None, timeout: int = 30):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT
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
        system_prompt: str = SYSTEM_PROMPT
    ) -> str:
        msg_lower = user_message.lower()

        # Context-aware follow-up recognition
        if conversation_history and any(k in msg_lower for k in ("explain more", "what about", "elaborate", "tell me more")):
            last_asst = next((m.get("content", "") for m in reversed(conversation_history) if m.get("role") == "assistant"), None)
            if last_asst:
                return (
                    f"[FinTech Agent Follow-up] Building upon previous discussion: '{last_asst[:80]}...'. "
                    "Ensure ongoing compliance with regulatory guidelines and internal audit procedures."
                )

        if "npa" in msg_lower:
            return (
                "A Non-Performing Asset (NPA) is a loan or advance for which the principal or interest "
                "payment remains overdue for a specified period, typically 90 days or more according to banking regulations. "
                "NPAs are classified into Sub-standard, Doubtful, and Loss assets based on recovery risk."
            )
        elif "kyc" in msg_lower:
            return (
                "Know Your Customer (KYC) is a mandatory banking compliance process to verify customer identity "
                "using officially valid documents (such as Passport, Aadhaar, PAN) before onboarding and periodically thereafter."
            )
        elif "fraud" in msg_lower:
            return (
                "A fraud alert flags suspicious transactions or anomalous customer behavior for investigation "
                "by the risk and fraud operations department."
            )
        return (
            f"[FinTech Agent Mock Response] Processed query: '{user_message}'. "
            "System is operating in verified Phase 2 conversational mode."
        )


class AnthropicProvider(BaseLLMProvider):
    """Adapter for Anthropic Messages API."""

    ENDPOINT = "https://api.anthropic.com/v1/messages"

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT
    ) -> str:
        if not self.api_key:
            raise MissingAPIKeyError("anthropic")

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

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                res = await client.post(self.ENDPOINT, headers=headers, json=payload)
                if res.status_code == 401:
                    raise ProviderAuthenticationError("anthropic", "Invalid Anthropic API key.")
                elif res.status_code == 429:
                    raise ProviderRateLimitError("anthropic", res.text)
                elif res.status_code >= 400:
                    raise ProviderAPIError("anthropic", f"Status {res.status_code}: {res.text}", status_code=res.status_code)

                data = res.json()
                content = data.get("content", [])
                text_blocks = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and (item.get("type") == "text" or "text" in item)
                ]
                if text_blocks:
                    return "".join(text_blocks).strip()
                raise ProviderAPIError("anthropic", "Malformed response structure: no text content blocks returned from Anthropic API.")
        except httpx.TimeoutException:
            raise ProviderTimeoutError("anthropic", self.timeout)
        except httpx.RequestError as e:
            raise ProviderAPIError("anthropic", f"Network connection error: {str(e)}")


class OpenAICompatibleProvider(BaseLLMProvider):
    """Adapter for OpenAI, Groq, or self-hosted OpenAI-compatible LLM endpoints."""

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: int = 30, provider_name: str = "openai"):
        super().__init__(model, api_key, timeout)
        self.provider_name = provider_name
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = SYSTEM_PROMPT
    ) -> str:
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise MissingAPIKeyError(self.provider_name)

        headers = {
            "Authorization": f"Bearer {self.api_key or 'none'}",
            "Content-Type": "application/json",
        }
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

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 401:
                    raise ProviderAuthenticationError(self.provider_name, "Invalid API key.")
                elif res.status_code == 429:
                    raise ProviderRateLimitError(self.provider_name, res.text)
                elif res.status_code >= 400:
                    raise ProviderAPIError(self.provider_name, f"Status {res.status_code}: {res.text}", status_code=res.status_code)

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
                        return f"[Refusal]: {refusal}"
                    raise ProviderAPIError(self.provider_name, "Null content received in chat completion response.")
                return content_text.strip()
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.provider_name, self.timeout)
        except httpx.RequestError as e:
            raise ProviderAPIError(self.provider_name, f"Network connection error: {str(e)}")


class LLMService:
    """Factory and dispatcher for externalized LLM providers."""

    def __init__(self):
        self._provider_instance: Optional[BaseLLMProvider] = None

    def get_provider(self) -> BaseLLMProvider:
        provider_name = (settings.LLM_PROVIDER or "").lower().strip()

        # Fail-fast check for production environment
        if settings.APP_ENV == "production":
            if not provider_name or provider_name == "mock":
                raise ProviderConfigurationError("Mock provider or unconfigured LLM_PROVIDER is prohibited in production environment.")

        if not provider_name:
            provider_name = "mock"

        model = settings.LLM_MODEL
        api_key = settings.get_provider_api_key(provider_name)
        timeout = settings.LLM_TIMEOUT_SECONDS

        if provider_name == "mock":
            return MockLLMProvider(model=model, api_key=api_key, timeout=timeout)
        elif provider_name == "anthropic":
            return AnthropicProvider(model=model, api_key=api_key, timeout=timeout)
        elif provider_name == "openai":
            return OpenAICompatibleProvider(
                model=model,
                api_key=api_key,
                base_url=settings.LLM_API_BASE_URL or "https://api.openai.com/v1",
                timeout=timeout,
                provider_name="openai"
            )
        elif provider_name == "groq":
            return OpenAICompatibleProvider(
                model=model,
                api_key=api_key,
                base_url=settings.LLM_API_BASE_URL or "https://api.groq.com/openai/v1",
                timeout=timeout,
                provider_name="groq"
            )
        elif provider_name in {"gemini", "google"}:
            base_url = settings.LLM_API_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai"
            return OpenAICompatibleProvider(
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                provider_name="gemini"
            )
        else:
            raise ProviderConfigurationError(f"Unsupported LLM provider: '{provider_name}'. Supported: mock, anthropic, openai, groq, gemini.")

    async def ask(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Dispatches message and optional history to configured provider adapter."""
        provider = self.get_provider()
        history_len = len(conversation_history) if conversation_history else 0
        logger.info(f"Dispatching query to provider='{settings.LLM_PROVIDER}', model='{settings.LLM_MODEL}', history_turns={history_len}")
        return await provider.generate_response(user_message, conversation_history=conversation_history)


# Global singleton instance
llm_service = LLMService()
