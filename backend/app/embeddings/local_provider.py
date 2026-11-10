"""
FinTech Agent — Local SentenceTransformers Embedding Provider
Uses local transformer models (e.g. all-MiniLM-L6-v2) for offline embeddings.
"""

from typing import List, Optional
from backend.app.core.exceptions import ProviderAPIError
from backend.app.core.logging import logger
from backend.app.embeddings.base import BaseEmbeddingProvider


class SentenceTransformersEmbeddingProvider(BaseEmbeddingProvider):
    """Generates embeddings using a local HuggingFace / SentenceTransformer model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dimension: int = 384):
        self._model_name = model_name
        self._dimension = dimension
        self._model = None

    @property
    def provider_name(self) -> str:
        return "sentence-transformers"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                # Verify dimension
                test_dim = self._model.get_sentence_embedding_dimension()
                if test_dim:
                    self._dimension = test_dim
            except ImportError:
                raise ProviderAPIError(
                    "sentence-transformers",
                    "The 'sentence-transformers' library is not installed. Please install it or use 'mock'."
                )
            except Exception as exc:
                logger.error(f"Failed to load local model '{self._model_name}': {exc}")
                raise ProviderAPIError(
                    "sentence-transformers",
                    f"Failed to initialize model '{self._model_name}': {str(exc)}"
                )

    def embed_text(self, text: str) -> List[float]:
        self._load_model()
        vec = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        self._load_model()
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [[float(x) for x in row] for row in vecs]
