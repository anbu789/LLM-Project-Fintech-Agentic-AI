"""
FinTech Agent — OpenAI-Compatible Embedding Provider
Generates vector embeddings via OpenAI or OpenAI-compatible embedding REST endpoints.
"""

from typing import List, Optional
import httpx

from backend.app.config import settings
from backend.app.core.exceptions import (
    MissingAPIKeyError,
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from backend.app.core.logging import logger, sanitize_error_message
from backend.app.embeddings.base import BaseEmbeddingProvider


class OpenAICompatibleEmbeddingProvider(BaseEmbeddingProvider):
    """Generates embeddings using standard OpenAI /v1/embeddings protocol."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        dimension: int = 1536,
        batch_size: int = 32,
    ):
        self._model_name = model_name
        if api_key is not None:
            self._api_key = api_key.strip() if api_key.strip() else None
        else:
            self._api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self._base_url = (base_url or settings.LLM_API_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        self._dimension = dimension
        self._batch_size = batch_size

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_api_key(self) -> str:
        if not self._api_key:
            raise MissingAPIKeyError("openai", "EMBEDDING_API_KEY or LLM_API_KEY is not configured.")
        return self._api_key

    def embed_text(self, text: str) -> List[float]:
        """Generates embedding for a single text."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a list of texts with batching and error shielding."""
        if not texts:
            return []

        api_key = self._get_api_key()
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        all_embeddings: List[List[float]] = []

        # Process in batches
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            payload = {
                "input": batch,
                "model": self._model_name
            }

            try:
                with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                    resp = client.post(url, json=payload, headers=headers)

                if resp.status_code == 401:
                    raise ProviderAuthenticationError("openai", "Invalid embedding API key.")
                elif resp.status_code == 429:
                    raise ProviderRateLimitError("openai", "Embedding API rate limit exceeded.")
                elif resp.status_code >= 400:
                    safe_msg = sanitize_error_message(resp.text)
                    raise ProviderAPIError("openai", f"Status {resp.status_code}: {safe_msg}")

                data = resp.json()
                sorted_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                batch_embeddings = [item["embedding"] for item in sorted_data]

                # Update dimension if returned
                if batch_embeddings and len(batch_embeddings[0]) != self._dimension:
                    self._dimension = len(batch_embeddings[0])

                all_embeddings.extend(batch_embeddings)

            except httpx.TimeoutException:
                raise ProviderTimeoutError("openai", settings.LLM_TIMEOUT_SECONDS)
            except (ProviderAuthenticationError, ProviderRateLimitError, ProviderAPIError, ProviderTimeoutError):
                raise
            except Exception as exc:
                safe_exc = sanitize_error_message(str(exc))
                logger.error(f"OpenAI embedding request failed: {safe_exc}")
                raise ProviderAPIError("openai", f"Embedding network failure: {safe_exc}")

        return all_embeddings
