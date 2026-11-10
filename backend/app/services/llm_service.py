"""
FinTech Agent — LLM Provider Service
Provider-independent adapter supporting Mock, Anthropic, OpenAI, Groq, and Gemini.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
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
    async def generate_response(self, user_message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        """Sends prompt to provider and extracts text completion."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline provider for unit testing and local development without API keys."""

    async def generate_response(self, user_message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        msg_lower = user_message.lower()
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

    async def generate_response(self, user_message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        if not self.api_key:
            raise MissingAPIKeyError("anthropic")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
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
                if content and isinstance(content, list) and "text" in content[0]:
                    return content[0]["text"]
                raise ProviderAPIError("anthropic", "Malformed response structure from Anthropic API.")
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

    async def generate_response(self, user_message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise MissingAPIKeyError(self.provider_name)

        headers = {
            "Authorization": f"Bearer {self.api_key or 'none'}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
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
                if choices and len(choices) > 0 and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
                raise ProviderAPIError(self.provider_name, "Malformed response structure from chat completion endpoint.")
        except httpx.TimeoutException:
            raise ProviderTimeoutError(self.provider_name, self.timeout)
        except httpx.RequestError as e:
            raise ProviderAPIError(self.provider_name, f"Network connection error: {str(e)}")


class LLMService:
    """Factory and dispatcher for externalized LLM providers."""

    def __init__(self):
        self._provider_instance: Optional[BaseLLMProvider] = None

    def get_provider(self) -> BaseLLMProvider:
        provider_name = (settings.LLM_PROVIDER or "mock").lower().strip()
        model = settings.LLM_MODEL
        api_key = settings.LLM_API_KEY
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
            # Standard Google GenAI endpoint via OpenAI-compatible endpoint or REST
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

    async def ask(self, user_message: str) -> str:
        """Dispatches message to configured provider adapter."""
        provider = self.get_provider()
        logger.info(f"Dispatching query to provider='{settings.LLM_PROVIDER}', model='{settings.LLM_MODEL}'")
        return await provider.generate_response(user_message)


# Global singleton instance
llm_service = LLMService()
