# FinTech Agent — Phase 5 Implementation Report
## Schema Retrieval, Natural Language to MongoDB Aggregation Pipeline & Deterministic MQL Validation

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Phase:** Phase 5 — Schema RAG, MQL Synthesis & Deterministic Policy Validation  
**Date:** November 10, 2026  
**Status:** COMPLETE — PHASE 5 READY FOR PHASE 6  

---

## 1. Executive Summary

Phase 5 extends the FinTech Agent from an intent-routed conversational agent into a schema-grounded, natural-language-to-MongoDB aggregation pipeline synthesizer with deterministic AST security validation.

In Phase 5, the LangGraph state machine activates three critical middle-tier nodes:
1. **Node 3 — Schema Retriever (`schema_retriever.py`):** Harnesses ChromaDB cosine semantic search and the canonical banking schema catalog to retrieve relevant collections, field inventories, allowed enum values, foreign key relationships, and unsupported business concept flags.
2. **Node 4 — Query Synthesizer (`query_synthesizer.py`):** Translates user natural language into structured read-only MongoDB aggregation pipelines. Implements a dual-path architecture: a deterministic mock synthesis engine covering all 18 banking query archetypes from `SAMPLE_QUERIES.md`, alongside a structured JSON system prompt for live LLM providers (Gemini, Claude, GPT-4).
3. **Node 5 — MQL Policy Validator (`mql_policy_validator.py`):** A zero-LLM deterministic security gate that validates candidate pipelines against an AST policy. Rejects mutating stages (`$out`, `$merge`), dangerous code execution operators (`$where`, `$function`, `$accumulator`), unauthorized collections, non-existent fields, unverified `$lookup` joins, and enforces structural limits (max 20 stages, max depth 10).
4. **Node 8 — Response Composer (`response_composer.py`):** Enhanced to present validated pipelines, plain-language explanations, validation error breakdowns, and unsupported concept notices, while explicitly certifying that database query execution has not occurred.

### Mandatory Phase 5 Boundary Verification
- **Zero Database Queries Executed:** PyMongo `aggregate()`, `find()`, or administrative commands were NEVER executed against `fintech_agent_db`.
- **Zero Document Mutations:** The live MongoDB database retains exactly 19,120 documents across all 12 collections (0 inserts, 0 updates, 0 deletes).
- **Nodes 6, 7, and 9 Preserved as Stubs:** Read-only query executor (Node 6), result verifier (Node 7), and scheduler (Node 9) remain registered stubs ready for future phases.
- **Full Regression Integrity:** 171/171 backend tests passing (100%), 8/8 frontend tests passing (100%), frontend production build verified.

---

## 2. Node 3: Schema Retriever Implementation

**Source File:** `backend/app/agent/nodes/schema_retriever.py`

### 2.1 Responsibilities
Node 3 bridges the intent router and query synthesizer by supplying verified schema metadata extracted from the schema catalog and ChromaDB vector store. It performs zero database operations.

### 2.2 Retrieval Workflow
1. **Query Extraction:** Reads `query_description` (if refined by Node 2) or `natural_language_query`.
2. **Vector Similarity Retrieval:** Invokes `schema_retriever.retrieve(query=search_query, top_k=5)` against the ChromaDB collection `fintech_schema_catalog_cosine`.
3. **Canonical Catalog Grounding:** Fetches rich collection definitions directly from the generated canonical catalog (`SchemaCatalog`):
   - Primary key fields
   - Field inventory with data types, descriptions, and allowed enum values
   - Relevant cross-collection foreign key relationships
4. **Unsupported Concept Shielding:** Inspects the query against `KNOWN_UNSUPPORTED_CONCEPTS` with regex word boundaries. Detects requests for non-existent concepts such as:
   - `loans.overdue_amount`
   - `loans.days_past_due` (DPD)
   - Delinquency buckets
   - Loan arrears
5. **Relationship Discovery:** Discovers valid foreign key links between identified collections (e.g., `customers.customer_id` <-> `accounts.customer_id`).
6. **State Population:** Populates `schema_context`, `collections_identified`, `schema_version`, and records audit trace entries.

---

## 3. Node 4: Query Synthesizer Implementation

**Source File:** `backend/app/agent/nodes/query_synthesizer.py`  
**Prompt File:** `backend/app/agent/prompts/query_synthesis.py`

### 3.1 Dual-Path Architecture
To satisfy rigorous offline testing and live LLM integration, Node 4 implements a dual-path design governed by `settings.LLM_PROVIDER`:

```
                 Incoming State (schema_context, query, history)
                                      |
                      [settings.LLM_PROVIDER == 'mock']
                                     / \
                                    /   \
                             (True)/     \(False)
                                  v       v
                       Deterministic     Structured Prompt &
                        Mock Engine       LLM JSON Generation
                                  \       /
                                   \     /
                                    v   v
                         Candidate Aggregation Pipeline
                          (Target Collection + Stages)
```

### 3.2 Canonical Banking Constraints Enforced
1. **Loan Balance vs. Overdue Debt:**
   - `loans.outstanding_amount` exists and is the sole principal balance field.
   - `loans.overdue_amount` and `loans.days_past_due` do NOT exist in the database.
   - When a user asks for overdue debts or default loans, the synthesizer maps to `status: "defaulted"` and uses `outstanding_amount` as the balance proxy.
   - `unsupported_concepts_identified` explicitly notes that overdue balance and DPD are absent.
2. **Strict Schema Grounding:** The synthesizer is barred from hallucinating collection names or column names.
3. **Bounded Pipelines:** Every unbounded search pipeline includes a `$limit` stage (capped at 100 for mock, max 1000 for LLM).

### 3.3 Coverage of 18 Banking Archetypes
The deterministic mock synthesizer covers all 18 representative banking queries from `SAMPLE_QUERIES.md`:
1. High-value customer balances (`accounts` + `$match` + `$sort`)
2. Customer search by city (`customers` + `$match` on `city` and `status`)
3. Customer accounts join (`accounts` + `$lookup` on `customers`)
4. Customer transactions history (`transactions` + `$match` on `customer_id`)
5. Failed transaction investigation (`transactions` + `$match: {status: 'failed'}`)
6. Top merchants by transaction volume (`transactions` + `$group` on `merchant_id` + `$sort`)
7. High-risk fraud alerts (`fraud_alerts` + `$match: {risk_level: 'high'}`)
8. Active loan portfolio (`loans` + `$match: {status: 'active', outstanding_amount: ...}`)
9. Defaulted loan audit / Overdue proxy (`loans` + `$match: {status: 'defaulted'}`)
10. Outstanding balance aggregate (`loans` + `$group: {_id: null, total: {$sum: '$outstanding_amount'}}`)
11. Support ticket backlog (`support_tickets` + `$match: {status: 'open'}`)
12. Pending KYC documents (`kyc_documents` + `$match: {verification_status: 'pending'}`)
13. Accounts count per branch (`accounts` + `$group: {_id: '$branch_id', count: {$sum: 1}}`)
14. Accounts per account type (`accounts` + `$group: {_id: '$account_type', count: {$sum: 1}}`)
15. Transactions by channel/mode (`transactions` + `$group` on `transaction_mode`)
16. Investments summary (`investments` + `$match: {status: 'active'}`)
17. Card status audit (`cards` + `$match: {status: 'blocked'}`)
18. Multi-turn contextual follow-up (embedding conversation history turns)

---

## 4. Node 5: MQL Policy Validator Implementation

**Source File:** `backend/app/agent/nodes/mql_policy_validator.py`

### 4.1 Zero-LLM Deterministic Policy Gate
Node 5 does NOT call an LLM. It performs static analysis of the candidate pipeline AST to ensure it complies strictly with banking security and schema boundaries.

### 4.2 Security Rules Enforced
| Category | Rule | Enforcement Mechanism |
|---|---|---|
| **Collection Allowlist** | Only canonical 12 collections allowed | Target collection checked against `CANONICAL_COLLECTIONS` set |
| **Stage Allowlist** | Read-only stages only | Approved: `$match`, `$project`, `$group`, `$sort`, `$limit`, `$skip`, `$unwind`, `$lookup`, `$count`, `$addFields`, `$set` |
| **Prohibited Stages** | Mutating stages strictly blocked | Explicit block on `$out`, `$merge` |
| **Prohibited Operators** | JavaScript code execution blocked | Explicit block on `$where`, `$function`, `$accumulator` |
| **Pipeline Length** | Max 20 stages | Checked against `settings.MAX_PIPELINE_STAGES` |
| **Expression Depth** | Max 10 levels of nesting | Recursive AST traversal with `_inspect_expression_depth()` |
| **Field Grounding** | All referenced fields must exist | Validated against catalog `fields` + `dynamic_scope_fields` |
| **Non-Existent Loans Fields** | Strict rejection of `overdue_amount` / `days_past_due` | Explicit zero-tolerance check on `loans` scope |
| **`$lookup` Verification** | Target must be canonical & related | `from` must be in catalog; foreign key must match verified relationships |
| **`$lookup` Keys** | `localField` and `foreignField` verified | Both keys verified to exist in respective collection schemas |
| **Dynamic Fields** | Computed fields registered in scope | Fields introduced by `$group`, `$project`, `$lookup as` tracked dynamically |

### 4.3 Validation Output Contract
Returns `MQLValidationResult` supporting both object attribute and dictionary access:
```python
val_res.is_valid            # bool
val_res.validation_status   # "VALID" | "INVALID"
val_res.validation_errors   # List[str]
val_res.validation_warnings # List[str]
val_res.approved_pipeline   # List[Dict[str, Any]] or None
val_res.query_plan_summary  # Summary dict (target, stages, lookups)
val_res.referenced_fields   # List of all extracted field references
```

---

## 5. LangGraph Pipeline Integration & State Transitions

**Source File:** `backend/app/agent/graph.py`

### 5.1 Active Execution Topology
The compiled LangGraph StateGraph executes as follows:

```
[START]
   │
   ▼
[input_guardrail] (Node 1)
   │
   ├── (rejected) ──────────────────────────────────────────┐
   ▼ (allowed)                                              │
[intent_router] (Node 2)                                    │
   │                                                        │
   ├── (OUT_OF_SCOPE / CLARIFICATION_REQUIRED) ──────────┐  │
   ▼ (QUERY_ONLY / QUERY_AND_SCHEDULE)                    │  │
[schema_retriever] (Node 3)                               │  │
   │                                                      │  │
   ▼                                                      │  │
[query_synthesizer] (Node 4)                              │  │
   │                                                      │  │
   ▼                                                      │  │
[mql_policy_validator] (Node 5)                           │  │
   │                                                      │  │
   ▼                                                      │  │
[response_composer] (Node 8) <────────────────────────────┘  │
   │                                                         │
   ▼                                                         │
 [END] <─────────────────────────────────────────────────────┘
```

Nodes 6 (Query Executor), 7 (Result Verifier), and 9 (Schedule Planner) remain registered in the StateGraph registry as future-phase stubs. They are not connected into the active execution path during Phase 5.

---

## 6. Node 8: Response Composer Enhancements

**Source File:** `backend/app/agent/nodes/response_composer.py`

Node 8 assembles user-facing responses tailored to Phase 5:
- **Validated Pipelines:** Emits formatted JSON pipeline within a markdown code block, collection identifier, natural language explanation, validation summary, and an explicit notice:
  > *In accordance with Phase 5 boundaries, database query execution has NOT occurred (scheduled for Phase 6).*
- **Invalid Pipelines:** Outlines specific validation policy errors and instructs the user how to refine the query.
- **Unsupported Concepts:** Explains why requested concepts are unsupported and presents canonical proxies.
- **Conversational Queries:** Preserves greetings, clarification requests, and out-of-scope guidance.

---

## 7. API Contract Updates

**Source Files:** `backend/app/schemas/chat.py`, `backend/app/api/routes/chat.py`

The `POST /api/v1/chat` endpoint populates Phase 5 metadata in `ChatResponse`:
```json
{
  "success": true,
  "status": "success",
  "conversation_id": "conv-123",
  "request_id": "req-abc",
  "message": "✅ Query Understood & Validated (Phase 5)...",
  "response": "✅ Query Understood & Validated (Phase 5)...",
  "provider": "mock",
  "model": "mock-banking-llm",
  "latency_ms": 24.5,
  "intent": "QUERY_ONLY",
  "request_mode": "QUERY_ONLY",
  "guardrail_status": "allowed",
  "pipeline_spec": [
    {"$match": {"status": "active"}},
    {"$limit": 100}
  ],
  "selected_collection": "loans",
  "validation_status": "passed",
  "query_explanation": "Filtered loans where status is 'active'.",
  "trace": [...]
}
```

---

## 8. Final Verdict

```
COMPLETE — PHASE 5 READY FOR PHASE 6.
```
All Phase 5 requirements have been completely fulfilled, verified with 171 passing backend tests, 8 passing frontend tests, zero database mutations, and comprehensive deterministic MQL policy validation.
