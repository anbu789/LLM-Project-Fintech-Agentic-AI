"""
FinTech Agent — ChromaDB Persistent Schema Vector Store
Manages persistent vector storage for the schema catalog in ChromaDB,
enforcing deterministic upserts, metadata constraints, and model compatibility checks.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import chromadb
from chromadb.api.models.Collection import Collection

from backend.app.config import settings
from backend.app.core.exceptions import FinTechAgentException
from backend.app.core.logging import logger
from backend.app.schema.models import RAGDocument


class ChromaModelMismatchError(FinTechAgentException):
    """Raised when configured embedding dimension or model mismatches existing ChromaDB index."""
    def __init__(self, message: str):
        super().__init__(message, error_code="CHROMA_MODEL_MISMATCH", status_code=500)


def _sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures metadata contains only ChromaDB-compatible primitive types (str, int, float, bool)."""
    clean = {}
    for k, v in meta.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, list):
            clean[k] = ", ".join(str(item) for item in v)
        else:
            clean[k] = str(v)
    return clean


class ChromaSchemaStore:
    """Persistent ChromaDB vector store wrapper for schema documents."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None
    ):
        self.persist_dir = Path(persist_dir or settings.CHROMA_PERSIST_DIR)
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[Collection] = None

    @property
    def client(self) -> chromadb.PersistentClient:
        """Lazy-loaded ChromaDB persistent client."""
        if self._client is None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    def get_collection(
        self,
        create_if_missing: bool = True,
        expected_dimension: Optional[int] = None,
        expected_model: Optional[str] = None
    ) -> Collection:
        """Retrieves or initializes the dedicated schema collection with compatibility checks."""
        if self._collection is not None:
            meta = self._collection.metadata or {}
            stored_dim = meta.get("dimension")
            if stored_dim and expected_dimension and stored_dim != expected_dimension:
                raise ChromaModelMismatchError(
                    f"ChromaDB collection '{self.collection_name}' has dimension {stored_dim}, "
                    f"but active provider requires dimension {expected_dimension}. Controlled re-indexing is required."
                )
            return self._collection

        client = self.client
        coll_metadata = {
            "hnsw:space": "cosine",
            "description": "FinTech Agent Schema Catalog RAG Index",
            "dimension": expected_dimension or settings.EMBEDDING_DIMENSION,
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "embedding_model": expected_model or settings.EMBEDDING_MODEL
        }

        # Check existing collection
        existing_names = [c.name for c in client.list_collections()]
        if self.collection_name in existing_names:
            col = client.get_collection(self.collection_name)
            meta = col.metadata or {}
            stored_dim = meta.get("dimension")
            if stored_dim and expected_dimension and stored_dim != expected_dimension:
                raise ChromaModelMismatchError(
                    f"ChromaDB collection '{self.collection_name}' has dimension {stored_dim}, "
                    f"but active provider requires dimension {expected_dimension}. Controlled re-indexing is required."
                )
            self._collection = col
            return self._collection

        if not create_if_missing:
            raise FileNotFoundError(f"ChromaDB collection '{self.collection_name}' does not exist.")

        self._collection = client.create_collection(
            name=self.collection_name,
            metadata=coll_metadata
        )
        logger.info(f"Created new ChromaDB collection '{self.collection_name}' at '{self.persist_dir}'")
        return self._collection

    def upsert_documents(
        self,
        documents: List[RAGDocument],
        embeddings: List[List[float]],
        schema_fingerprint: Optional[str] = None
    ) -> int:
        """
        Upserts schema documents and their embedding vectors idempotently.
        Repeated indexing of identical documents updates existing records without duplication.
        """
        if not documents:
            return 0
        if len(documents) != len(embeddings):
            raise ValueError(f"Document count ({len(documents)}) does not match embeddings count ({len(embeddings)})")

        dim = len(embeddings[0]) if embeddings else settings.EMBEDDING_DIMENSION
        col = self.get_collection(expected_dimension=dim)

        ids = [doc.id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas = [_sanitize_metadata(doc.metadata) for doc in documents]

        # ChromaDB batch upsert
        col.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )

        # Update collection metadata with latest schema fingerprint
        if schema_fingerprint:
            meta = dict(col.metadata or {})
            meta["schema_fingerprint"] = schema_fingerprint
            meta["dimension"] = dim
            # ChromaDB forbids passing 'hnsw:space' to col.modify() once created
            meta.pop("hnsw:space", None)
            col.modify(metadata=meta)

        logger.info(f"Upserted {len(documents)} schema documents into ChromaDB collection '{self.collection_name}'")
        return len(documents)

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Queries the vector index for nearest schema documents."""
        col = self.get_collection(expected_dimension=len(query_embedding))
        total_count = col.count()
        if total_count == 0:
            return []

        n_results = min(top_k, total_count)
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = col.query(**kwargs)

        output: List[Dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, doc_text, meta, dist in zip(ids, docs, metas, distances):
            # Compute cosine similarity from cosine distance (hnsw:space = "cosine"):
            # ChromaDB cosine distance = 1.0 - cosine_similarity
            if dist is not None:
                sim = max(0.0, min(1.0, round(1.0 - float(dist), 4)))
            else:
                sim = 1.0
            output.append({
                "id": doc_id,
                "content": doc_text,
                "metadata": meta,
                "distance": dist,
                "similarity": sim
            })
        return output

    def get_stats(self) -> Dict[str, Any]:
        """Returns collection inventory, document count, and persistence status."""
        try:
            col = self.get_collection(create_if_missing=False)
            count = col.count()
            meta = col.metadata or {}
            return {
                "status": "ready",
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "document_count": count,
                "metadata": meta,
                "schema_fingerprint": meta.get("schema_fingerprint"),
                "embedding_dimension": meta.get("dimension")
            }
        except Exception as exc:
            return {
                "status": "uninitialized",
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "document_count": 0,
                "error": str(exc)
            }

    def delete_stale_documents(self, active_ids: Set[str]) -> int:
        """Removes documents in ChromaDB whose IDs no longer exist in the active schema catalog."""
        col = self.get_collection()
        all_data = col.get()
        stored_ids = set(all_data.get("ids", []))
        stale_ids = list(stored_ids - active_ids)

        if stale_ids:
            col.delete(ids=stale_ids)
            logger.info(f"Removed {len(stale_ids)} stale documents from ChromaDB collection '{self.collection_name}'")
        return len(stale_ids)

    def reset_collection(self) -> None:
        """Safely clears only the dedicated schema collection without affecting other ChromaDB data."""
        client = self.client
        if self.collection_name in [c.name for c in client.list_collections()]:
            client.delete_collection(self.collection_name)
            self._collection = None
            logger.info(f"Reset ChromaDB collection '{self.collection_name}'")


chroma_store = ChromaSchemaStore()
