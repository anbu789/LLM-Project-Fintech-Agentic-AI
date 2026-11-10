"""
FinTech Agent — Semantic Schema Retrieval Service
Performs semantic vector search over schema documents in ChromaDB, applies metadata filters,
expands cross-collection join paths, and identifies missing/unsupported financial concepts.
"""

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.embeddings.base import BaseEmbeddingProvider
from backend.app.embeddings.provider_factory import get_embedding_provider
from backend.app.rag.chroma_store import ChromaSchemaStore, chroma_store
from backend.app.schema.catalog_builder import SchemaCatalogBuilder, schema_catalog_builder
from backend.app.schema.models import SchemaCatalog


class RetrievedDocument(BaseModel):
    """Structured representation of an individual retrieved schema document."""
    id: str = Field(..., description="Document identifier")
    doc_type: str = Field(..., description="Document type: collection, field, relationship, glossary")
    content: str = Field(..., description="Document text content")
    collection: Optional[str] = Field(default=None, description="Associated collection name")
    field: Optional[str] = Field(default=None, description="Associated field name")
    similarity: float = Field(..., description="Calculated similarity score [0.0 - 1.0]")
    distance: float = Field(..., description="Vector distance in embedding space")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")


class RetrievalResult(BaseModel):
    """Complete structured response from the semantic schema retrieval service."""
    query: str = Field(..., description="Original user inquiry")
    relevant_collections: List[str] = Field(default_factory=list, description="Ranked list of relevant collection names")
    relevant_fields: List[Dict[str, Any]] = Field(default_factory=list, description="Relevant collection fields identified")
    relevant_relationships: List[Dict[str, Any]] = Field(default_factory=list, description="Discovered join relationships")
    retrieved_documents: List[RetrievedDocument] = Field(default_factory=list, description="Ranked document hits")
    unsupported_concepts: List[Dict[str, str]] = Field(default_factory=list, description="Warnings for concepts not in dataset")
    total_hits: int = Field(default=0, description="Total matching documents retrieved")


class SchemaRetriever:
    """Retrieves relevant database schema information for natural language banking questions."""

    KNOWN_UNSUPPORTED_CONCEPTS = {
        "overdue_amount": {
            "concept": "overdue_amount",
            "warning": "The 'overdue_amount' field does NOT exist in the loans collection. Use 'loans.outstanding_amount' with status = 'defaulted' or check 'loans.next_due_date'."
        },
        "days_past_due": {
            "concept": "days_past_due",
            "warning": "The 'days_past_due' (DPD) field does NOT exist in the loans collection. Evaluate overdue status using 'loans.status' = 'defaulted' or relative date calculations on 'loans.next_due_date'."
        },
        "dpd": {
            "concept": "days_past_due",
            "warning": "The 'days_past_due' (DPD) field does NOT exist in the loans collection."
        }
    }

    def __init__(
        self,
        store: ChromaSchemaStore = chroma_store,
        catalog_builder: SchemaCatalogBuilder = schema_catalog_builder,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
    ):
        self.store = store
        self.catalog_builder = catalog_builder
        self._provider = embedding_provider
        self._catalog: Optional[SchemaCatalog] = None

    @property
    def embedding_provider(self) -> BaseEmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    @property
    def catalog(self) -> SchemaCatalog:
        if self._catalog is None:
            self._catalog = self.catalog_builder.load_catalog()
        return self._catalog

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        doc_types: Optional[List[str]] = None,
        collection_filter: Optional[str] = None
    ) -> RetrievalResult:
        """
        Executes semantic schema retrieval for a natural-language query.
        Returns relevant collections, fields, relationships, and warnings.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return RetrievalResult(query=query)

        k = top_k or settings.RETRIEVAL_TOP_K
        provider = self.embedding_provider

        # 1. Generate query embedding
        query_embedding = provider.embed_text(cleaned_query)

        # 2. Build ChromaDB filter
        where_filter: Optional[Dict[str, Any]] = None
        if doc_types and len(doc_types) == 1 and collection_filter:
            where_filter = {
                "$and": [
                    {"doc_type": {"$eq": doc_types[0]}},
                    {"collection": {"$eq": collection_filter}}
                ]
            }
        elif doc_types and len(doc_types) == 1:
            where_filter = {"doc_type": {"$eq": doc_types[0]}}
        elif collection_filter:
            where_filter = {"collection": {"$eq": collection_filter}}

        # Fetch more candidates to allow relationship expansion and deduplication
        fetch_k = max(k * 2, 10)
        raw_hits = self.store.query(
            query_embedding=query_embedding,
            top_k=fetch_k,
            where_filter=where_filter
        )

        # 3. Process and filter documents
        retrieved_docs: List[RetrievedDocument] = []
        collections_found: Set[str] = set()
        fields_found: List[Dict[str, Any]] = []
        seen_field_keys: Set[str] = set()

        # Hybrid entity extraction: identify collections explicitly mentioned in the query
        import re
        tokens = set(re.findall(r"\w+", cleaned_query.lower()))
        col_keywords = {
            "branch": "branches", "branches": "branches",
            "employee": "employees", "employees": "employees", "staff": "employees",
            "merchant": "merchants", "merchants": "merchants", "vendor": "merchants",
            "customer": "customers", "customers": "customers", "client": "customers",
            "account": "accounts", "accounts": "accounts",
            "transaction": "transactions", "transactions": "transactions", "txn": "transactions",
            "card": "cards", "cards": "cards",
            "loan": "loans", "loans": "loans",
            "kyc": "kyc_documents",
            "ticket": "support_tickets", "tickets": "support_tickets",
            "alert": "fraud_alerts", "fraud": "fraud_alerts",
            "investment": "investments", "investments": "investments"
        }
        for token in tokens:
            if token in col_keywords:
                collections_found.add(col_keywords[token])

        for hit in raw_hits:
            meta = hit.get("metadata", {})
            doc_type = meta.get("doc_type", "unknown")

            # In-memory filter for multiple doc_types if specified
            if doc_types and doc_type not in doc_types:
                continue

            col = meta.get("collection")
            if col and col != "general":
                collections_found.add(col)

            f_name = meta.get("field")
            if col and f_name:
                f_key = f"{col}.{f_name}"
                if f_key not in seen_field_keys:
                    seen_field_keys.add(f_key)
                    fields_found.append({
                        "collection": col,
                        "field": f_name,
                        "data_type": meta.get("data_type", "unknown"),
                        "is_primary_key": meta.get("is_primary_key", False),
                        "is_foreign_key": meta.get("is_foreign_key", False)
                    })

            doc = RetrievedDocument(
                id=hit["id"],
                doc_type=doc_type,
                content=hit["content"],
                collection=col,
                field=f_name,
                similarity=hit["similarity"],
                distance=hit["distance"],
                metadata=meta
            )
            retrieved_docs.append(doc)

        # 4. Multi-collection join expansion
        discovered_relationships: List[Dict[str, Any]] = []
        if len(collections_found) > 1:
            cat = self.catalog
            for rel in cat.relationships:
                if rel.from_collection in collections_found and rel.to_collection in collections_found:
                    discovered_relationships.append({
                        "from": f"{rel.from_collection}.{rel.from_field}",
                        "to": f"{rel.to_collection}.{rel.to_field}",
                        "cardinality": rel.relationship_type,
                        "description": rel.description
                    })

        # 5. Unsupported concept inspection
        unsupported: List[Dict[str, str]] = []
        q_lower = cleaned_query.lower()
        for term, info in self.KNOWN_UNSUPPORTED_CONCEPTS.items():
            if term.replace("_", " ") in q_lower or term in q_lower:
                unsupported.append(info)

        # Limit returned documents to requested top_k
        final_docs = retrieved_docs[:k]

        return RetrievalResult(
            query=cleaned_query,
            relevant_collections=sorted(list(collections_found)),
            relevant_fields=fields_found[:k],
            relevant_relationships=discovered_relationships,
            retrieved_documents=final_docs,
            unsupported_concepts=unsupported,
            total_hits=len(final_docs)
        )


schema_retriever = SchemaRetriever()
