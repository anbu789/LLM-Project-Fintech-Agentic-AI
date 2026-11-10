"""
FinTech Agent — Retrieval Evaluation Engine
Evaluates schema retrieval accuracy, collection recall, and relationship discovery
against a benchmark derived from SAMPLE_QUERIES.md.
"""

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from backend.app.rag.retriever import SchemaRetriever, schema_retriever


class EvaluationTestCase(BaseModel):
    """An individual evaluation test case with ground-truth expected schema entities."""
    id: str
    query: str
    category: str
    expected_collections: List[str]
    expected_fields: List[str] = Field(default_factory=list)
    expected_relationships: List[str] = Field(default_factory=list)
    unsupported_concepts: List[str] = Field(default_factory=list)


# 10 Representative Test Cases Grounded in SAMPLE_QUERIES.md
BENCHMARK_TEST_CASES: List[EvaluationTestCase] = [
    EvaluationTestCase(
        id="Q01_CUST_LOC",
        query="Show customers from Chennai",
        category="Single Collection Filter",
        expected_collections=["customers"],
        expected_fields=["city", "customer_id"]
    ),
    EvaluationTestCase(
        id="Q02_TXN_AMT",
        query="Find transactions above ₹10,000",
        category="Numeric Range Filter",
        expected_collections=["transactions"],
        expected_fields=["amount", "transaction_id"]
    ),
    EvaluationTestCase(
        id="Q03_CUST_ACTIVE_LOANS",
        query="Show customers with active loans",
        category="Multi-Collection Relationship",
        expected_collections=["customers", "loans"],
        expected_fields=["customer_id", "status"],
        expected_relationships=["loans.customer_id->customers.customer_id"]
    ),
    EvaluationTestCase(
        id="Q04_ACC_CUST_CITY",
        query="Find accounts belonging to customers in Coimbatore",
        category="Multi-Collection Join",
        expected_collections=["accounts", "customers"],
        expected_fields=["customer_id", "city"],
        expected_relationships=["accounts.customer_id->customers.customer_id"]
    ),
    EvaluationTestCase(
        id="Q05_CARDS_EXPIRING",
        query="Show credit cards expiring this month",
        category="Date & Synonyms",
        expected_collections=["cards"],
        expected_fields=["expiry_date", "card_type"]
    ),
    EvaluationTestCase(
        id="Q06_MERCHANTS_TXN",
        query="Find merchants with high transaction volumes",
        category="Aggregation Across Entities",
        expected_collections=["merchants", "transactions"],
        expected_fields=["merchant_id", "amount"],
        expected_relationships=["transactions.merchant_id->merchants.merchant_id"]
    ),
    EvaluationTestCase(
        id="Q07_BRANCH_EMP",
        query="Show employees working at a particular branch",
        category="Hierarchy & Branch Join",
        expected_collections=["employees", "branches"],
        expected_fields=["branch_id", "employee_id"],
        expected_relationships=["employees.branch_id->branches.branch_id"]
    ),
    EvaluationTestCase(
        id="Q08_KYC_DOCS",
        query="Find KYC documents belonging to customers",
        category="Customer Compliance",
        expected_collections=["kyc_documents", "customers"],
        expected_fields=["customer_id", "doc_type"],
        expected_relationships=["kyc_documents.customer_id->customers.customer_id"]
    ),
    EvaluationTestCase(
        id="Q09_LOAN_BALANCE",
        query="Show outstanding loan balances",
        category="Banking Terminology",
        expected_collections=["loans"],
        expected_fields=["outstanding_amount"]
    ),
    EvaluationTestCase(
        id="Q10_OVERDUE_ABSENT",
        query="Find overdue loans with days past due and overdue amount",
        category="Unsupported Concepts Shielding",
        expected_collections=["loans"],
        expected_fields=["status", "outstanding_amount"],
        unsupported_concepts=["days_past_due", "overdue_amount"]
    )
]


class RetrievalEvaluationRunner:
    """Executes benchmark queries, computes retrieval metrics, and formats evaluation reports."""

    def __init__(self, retriever: SchemaRetriever = schema_retriever):
        self.retriever = retriever

    def run_evaluation(self, test_cases: Optional[List[EvaluationTestCase]] = None, top_k: int = 5) -> Dict[str, Any]:
        """Runs evaluation over test cases and aggregates precision, recall, and MRR."""
        cases = test_cases or BENCHMARK_TEST_CASES
        total_cases = len(cases)

        collection_hits = 0
        relationship_hits = 0
        total_multi_cases = 0
        unsupported_concept_hits = 0
        total_unsupported_cases = 0

        reciprocal_ranks: List[float] = []
        precisions: List[float] = []
        recalls: List[float] = []

        case_results: List[Dict[str, Any]] = []

        for case in cases:
            res = self.retriever.retrieve(case.query, top_k=top_k)
            retrieved_collections = set(res.relevant_collections)
            expected_collections = set(case.expected_collections)

            # Collection Recall: fraction of expected collections found
            found_expected_cols = expected_collections.intersection(retrieved_collections)
            col_recall = len(found_expected_cols) / len(expected_collections) if expected_collections else 1.0
            recalls.append(col_recall)

            if len(found_expected_cols) > 0:
                collection_hits += 1

            # Precision@K: fraction of retrieved documents relevant to expected collections
            relevant_docs_count = sum(
                1 for doc in res.retrieved_documents
                if doc.collection in expected_collections or doc.doc_type == "glossary"
            )
            prec = relevant_docs_count / len(res.retrieved_documents) if res.retrieved_documents else 0.0
            precisions.append(prec)

            # MRR: Rank of first document matching expected collection
            rr = 0.0
            for rank, doc in enumerate(res.retrieved_documents, start=1):
                if doc.collection in expected_collections:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

            # Relationship discovery check for multi-collection queries
            if case.expected_relationships:
                total_multi_cases += 1
                found_rels = {f"{r['from']}->{r['to']}" for r in res.relevant_relationships}
                if any(exp in found_rels for exp in case.expected_relationships):
                    relationship_hits += 1

            # Unsupported concept shielding check
            if case.unsupported_concepts:
                total_unsupported_cases += 1
                flagged = {c["concept"] for c in res.unsupported_concepts}
                if any(u in flagged for u in case.unsupported_concepts):
                    unsupported_concept_hits += 1

            case_results.append({
                "id": case.id,
                "query": case.query,
                "category": case.category,
                "expected_collections": case.expected_collections,
                "retrieved_collections": res.relevant_collections,
                "precision": round(prec, 4),
                "recall": round(col_recall, 4),
                "reciprocal_rank": round(rr, 4),
                "top_retrieved_ids": [doc.id for doc in res.retrieved_documents[:3]],
                "discovered_relationships": [r["from"] + "->" + r["to"] for r in res.relevant_relationships],
                "unsupported_warnings": [w["concept"] for w in res.unsupported_concepts]
            })

        avg_precision = round(sum(precisions) / total_cases, 4) if total_cases else 0.0
        avg_recall = round(sum(recalls) / total_cases, 4) if total_cases else 0.0
        mrr = round(sum(reciprocal_ranks) / total_cases, 4) if total_cases else 0.0
        col_hit_rate = round(collection_hits / total_cases, 4) if total_cases else 0.0
        rel_hit_rate = round(relationship_hits / total_multi_cases, 4) if total_multi_cases else 1.0
        unsupported_shield_rate = round(unsupported_concept_hits / total_unsupported_cases, 4) if total_unsupported_cases else 1.0

        return {
            "total_test_cases": total_cases,
            "metrics": {
                "precision_at_k": avg_precision,
                "recall_at_k": avg_recall,
                "mean_reciprocal_rank_mrr": mrr,
                "collection_retrieval_hit_rate": col_hit_rate,
                "relationship_discovery_rate": rel_hit_rate,
                "unsupported_concept_shield_rate": unsupported_shield_rate
            },
            "embedding_provider": self.retriever.embedding_provider.provider_name,
            "embedding_model": self.retriever.embedding_provider.model_name,
            "case_results": case_results
        }


evaluation_runner = RetrievalEvaluationRunner()
