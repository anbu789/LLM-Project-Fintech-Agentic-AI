# FINTECH AGENT — COMPREHENSIVE FAILURE TAXONOMY AND ROOT CAUSE ANALYSIS

**Document Classification:** Defect Analysis, Fault Invariant Tracking & System Hardening  
**Audit Scope:** Real Observed Historical Defects, Verified Remediations, and Remaining Edge-Case Risks  
**Source Evidence:**
- Pre-Phase 4 Audit: [`PRE_PHASE4_REMEDIATION_REPORT.md`](file:///c:/Users/guru2/Downloads/llm%20prj/PRE_PHASE4_REMEDIATION_REPORT.md)
- Pre-Phase 6 Semantics Report: [`PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md`](file:///c:/Users/guru2/Downloads/llm%20prj/PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md)
- Multi-Provider Fallback Report: [`MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md`](file:///c:/Users/guru2/Downloads/llm%20prj/MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md)
- Execution Event Telemetry: [`logs/execution_events.jsonl`](file:///c:/Users/guru2/Downloads/llm%20prj/logs/execution_events.jsonl)
- Automated Test Suite: [`backend/tests/`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/tests/)

---

## 1. Executive Summary

In a safety-critical banking environment, system reliability is defined by how gracefully the architecture handles failures. The FinTech Agent codebase reflects extensive iterative failure remediation across its development lifecycle. 

This document establishes a formal taxonomy of **12 critical failure categories**, distinguishing between **empirically observed and remediated defects** and **residual theoretical risks**.

---

## 2. Taxonomy of Observed Failures and Implemented Remediations

### Category 1: Hallucinated Schema Fields in RAG Catalog
- **Incident / Test ID:** Audit Defect AUD-01 (`PRE_PHASE4_REMEDIATION_REPORT.md`)
- **Observed Behavior:** RAG glossary mapper mapped colloquial terms to non-existent fields: `kyc_documents.doc_type`, `fraud_alerts.severity`, and `merchants.merchant_category`.
- **Expected Behavior:** Every mapped field must exist in `fintech-agent/data/schema.json`.
- **Actual Failure:** Downstream synthesis produced pipelines that failed database execution because MongoDB returned empty fields or rejected queries.
- **Root Cause:** Manual drafting of `glossary_mapper.py` without programmatic cross-validation against authoritative JSON schema.
- **Responsible Component:** Node 3 (Schema Retriever) & `glossary_mapper.py`.
- **Remediation Implemented:** Corrected mappings to `kyc_documents.document_type`, `fraud_alerts.risk_score`, and `merchants.category`. Implemented automated validator `validate_glossary_against_schema()`.
- **Verifying Automated Test:** `backend/tests/test_pre_phase4_remediation.py::test_glossary_fields_match_schema_json`.
- **Residual Risk:** Schema changes without running the automated drift test could re-introduce drift.

---

### Category 2: Vector Space Inversion and Alphabetical Sorting Distortion
- **Incident / Test ID:** Audit Defect AUD-02 & AUD-03 (`PRE_PHASE4_REMEDIATION_REPORT.md`)
- **Observed Behavior:** ChromaDB initialized with Euclidean $L_2$ distance rather than cosine similarity; collections sorted alphabetically: `collections_found = sorted(list(collections_found))`.
- **Expected Behavior:** Target collections ranked strictly by semantic similarity score.
- **Actual Failure:** A query strongly targeting `transactions` ranked `accounts` first simply because "a" precedes "t" in ASCII order, causing Node 4 to synthesize queries against the wrong collection.
- **Root Cause:** Flawed post-processing grouping in `retriever.py`.
- **Responsible Component:** Node 3 (`backend/app/rag/retriever.py`).
- **Remediation Implemented:** Pinned ChromaDB collection metadata to `{"hnsw:space": "cosine"}`; bounded cosine similarity to $[0.0, 1.0]$; sorted collections by descending aggregate similarity score.
- **Verifying Automated Test:** `backend/tests/test_pre_phase4_remediation.py::test_retriever_ranking_preserves_vector_similarity`.
- **Residual Risk:** None. Verified deterministic.

---

### Category 3: Financial Semantic Distortion — Overdue Arrears vs. Default Principal
- **Incident / Test ID:** Defect FS-01 (`PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md`)
- **Observed Behavior:** When asked for "overdue loans" or "overdue amounts", the agent synthesized `{"$match": {"status": "defaulted"}}` and summed `outstanding_amount`.
- **Expected Behavior:** Recognize that `overdue_amount` (past-due installments) does not exist in `loans.json` and refuse to substitute unamortized principal balance.
- **Actual Failure:** Overstated overdue customer liabilities by up to 6,000%, conflating remaining 20-year mortgage principal with 2 months of missed EMI payments.
- **Root Cause:** Naive keyword proxying in prompt templates without domain credit risk boundaries.
- **Responsible Component:** Node 2, Node 4, and Node 5.
- **Remediation Implemented:** Built regex word-boundary interceptors for `overdue_amount`, `days_past_due`, `dpd`, `arrears`. Node 5 rejects any pipeline attempting to proxy overdue debt. Response Composer returns an explicit `UNSUPPORTED` explanation.
- **Verifying Automated Test:** `backend/tests/test_pre_phase6_remediation.py::test_financial_semantics_overdue_amount_unsupported`.
- **Residual Risk:** Analysts may still want to calculate arrears; requires dataset schema expansion in future iterations.

---

### Category 4: Cloud LLM Outages & HTTP 503 Service Unavailable
- **Incident / Test ID:** Incident INC-LLM-503 (`MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md`)
- **Observed Behavior:** Google Gemini 3.8 Flash returned intermittent HTTP 503 Service Unavailable and socket read timeouts under rapid sequential queries.
- **Expected Behavior:** High-availability query handling without user-facing 500 errors.
- **Actual Failure:** Whole chat request crashed with HTTP 500 Internal Server Error.
- **Root Cause:** Cloud API capacity throttles and lack of secondary provider fallback.
- **Responsible Component:** Service Layer (`backend/app/services/llm_service.py`).
- **Remediation Implemented:** Implemented `FallbackProviderManager` with 3-tier cascade: Gemini 3.8 Flash -> Groq GPT-OSS 120B -> Local Ollama K2-Horizon 3.7B. Governed by shared 24.0s operation deadline budget.
- **Verifying Automated Test:** `backend/tests/test_multi_provider_fallback.py::test_fallback_gemini_fails_groq_succeeds`.
- **Residual Risk:** If all three providers fail or internet connection drops without local Ollama running, request terminates with controlled HTTP 503.

---

### Category 5: Caller-Controlled Identity Spoofing & Schedule Tampering
- **Incident / Test ID:** Security Vulnerability SEC-01 (`FINAL_SECURITY_AUDIT_REPORT.md`)
- **Observed Behavior:** Endpoints in `schedules.py` accepted an arbitrary caller-supplied `X-User-ID` header to identify schedule owners.
- **Expected Behavior:** Identity must be cryptographically asserted and immutable.
- **Actual Failure:** A malicious operator could submit `X-User-ID: victim_analyst` to list, delete, or pause another analyst's recurring compliance schedules.
- **Root Cause:** Prototype authentication shortcut without token verification.
- **Responsible Component:** `backend/app/core/auth.py` and `backend/app/api/routes/schedules.py`.
- **Remediation Implemented:** Implemented HMAC-SHA256 URL-safe Bearer tokens. Added `_verify_ownership` check that compares token `sub` claim against stored `owner_id`. If caller supplies a conflicting `X-User-ID`, request is rejected with HTTP 403 Forbidden.
- **Verifying Automated Test:** `backend/tests/test_final_audit_hardening.py::test_task1_identity_spoofing_token_mismatch_rejected`.
- **Residual Risk:** Secret key (`JWT_SECRET_KEY`) must be kept confidential and rotated in production.

---

### Category 6: Distributed Scheduler Duplicate Execution Race Conditions
- **Incident / Test ID:** Concurrency Defect CONC-01 (`PHASE7_IMPLEMENTATION_REPORT.md`)
- **Observed Behavior:** In a multi-worker deployment (e.g. 4 Uvicorn workers), each worker's internal scheduler fired the same recurring job simultaneously.
- **Expected Behavior:** Exactly-once execution for every scheduled trigger time.
- **Actual Failure:** 4 duplicate database queries executed and 4 duplicate run records logged.
- **Root Cause:** Independent in-memory APScheduler instances without distributed coordination.
- **Responsible Component:** `backend/app/services/scheduler_runner.py`.
- **Remediation Implemented:** Distributed atomic lease in `agent_metadata_db.scheduler_leases` using MongoDB `find_one_and_update` with fencing tokens and a 30-second TTL heartbeat. Only the lease holder can trigger job executions.
- **Verifying Automated Test:** `backend/tests/test_final_audit_hardening.py::test_task2_scheduler_lease_collision_denial`.
- **Residual Risk:** Database latency exceeding 30s could cause temporary lease handover.

---

### Category 7: Timezone DST and Month-End Scheduling Anomalies
- **Incident / Test ID:** Edge Case EC-01 & EC-02 (`FINAL_TEST_REPORT.md`)
- **Observed Behavior:** Recurring queries scheduled for "the 31st of every month" threw unhandled datetime exceptions in February, April, June, September, and November. Daylight Saving Time transitions (Spring Forward / Fall Back) skipped or duplicated runs.
- **Expected Behavior:** Deterministic date coalescing and unambiguous UTC projection.
- **Actual Failure:** Unhandled runtime crash in background scheduler.
- **Root Cause:** Naive datetime arithmetic (`dt.replace(day=31)`).
- **Responsible Component:** `backend/app/services/recurrence_parser.py`.
- **Remediation Implemented:** Coalescing month-end dates to the last valid day of the month (e.g., Feb 28/29, Apr 30). Used standard IANA timezones via `zoneinfo` and APScheduler `CronTrigger` which natively accounts for fold and transition offsets.
- **Verifying Automated Test:** `backend/tests/test_final_audit_hardening.py::test_task3_month_end_recurrence`, `test_task3_timezone_dst_spring_forward`.
- **Residual Risk:** None. Handled mathematically.

---

### Category 8: Lossy Decimal128 BSON Precision Conversion
- **Incident / Test ID:** Data Integrity Defect DI-01 (`test_phase6_execution.py`)
- **Observed Behavior:** Converting MongoDB `Decimal128` financial values using standard Python `float(val)` introduced IEEE 754 floating-point rounding errors (e.g., ₹1,00,000.10 -> 100000.10000000001).
- **Expected Behavior:** Exact decimal representation for monetary balances.
- **Actual Failure:** Subtle rounding drift in account balances and loan totals.
- **Root Cause:** Standard JSON serializer fallback to `float`.
- **Responsible Component:** Node 7 (`backend/app/agent/nodes/result_verifier.py:_sanitize_doc`).
- **Remediation Implemented:** Custom recursive sanitizer preserving exact `Decimal(str(val))` strings without float casting.
- **Verifying Automated Test:** `backend/tests/test_phase6_execution.py::test_result_verifier_decimal128_preservation`.
- **Residual Risk:** None. Financial precision preserved.

---

### Category 9: Unbounded Aggregation Memory Exhaustion ($unwind after $limit)
- **Incident / Test ID:** MQL Policy Defect MQL-04 (`test_phase5_query_pipeline.py`)
- **Observed Behavior:** Synthesized pipelines placed `$limit` before `$unwind` and `$lookup`, or omitted terminal limits entirely.
- **Expected Behavior:** Strictly bounded execution memory footprint.
- **Actual Failure:** An early `$limit` followed by `$unwind` on a large transactions array can explode in memory, bypassing the intended row limit.
- **Root Cause:** LLM synthesizer arranging stages in arbitrary sequence.
- **Responsible Component:** Node 5 (`backend/app/agent/nodes/mql_policy_validator.py`).
- **Remediation Implemented:** Validator deterministically rejects any pipeline containing `$unwind` after a `$limit`. Mandates terminal `$limit <= 100` for all non-scalar queries.
- **Verifying Automated Test:** `backend/tests/test_pre_phase6_remediation.py::test_mql_unwind_after_limit_rejected`.
- **Residual Risk:** None. Enforced by deterministic AST check.

---

### Category 10: Case-Sensitive Status Value Hallucinations
- **Incident / Test ID:** Synthesis Defect SYN-02 (`generate_dataset.py` v1 -> v2)
- **Observed Behavior:** Prompts generated `{"status": "Active"}` with uppercase 'A', matching 0 records because MongoDB strings are case-sensitive.
- **Expected Behavior:** Status queries match actual database enum values.
- **Actual Failure:** Valid queries returned empty results (`VALID_EMPTY`) instead of records.
- **Root Cause:** Inconsistent casing across initial dataset generation scripts and schema.
- **Responsible Component:** Dataset generator & Query Synthesizer.
- **Remediation Implemented:** Standardized every status field across all 12 collections to strictly lowercase (`active`, `inactive`, `closed`, `defaulted`, `blocked`). Updated query synthesis prompt to inject lowercase enum rules.
- **Verifying Automated Test:** `backend/tests/test_phase5_query_pipeline.py::test_synthesizer_uses_lowercase_status`.
- **Residual Risk:** User explicitly typing uppercase in search strings handled via regex normalization.

---

### Category 11: Accidental Live Execution Against Banking Data
- **Incident / Test ID:** Safety Defect SEC-03 (`FINAL_PROJECT_ACCEPTANCE_REPORT.md`)
- **Observed Behavior:** Running test suites could accidentally issue write or drop commands against the local `fintech_agent_db`.
- **Expected Behavior:** Zero database mutations under any circumstance.
- **Actual Failure:** Risk of corrupting the 19,120 baseline benchmark records.
- **Root Cause:** Direct unshielded connection strings in test fixtures.
- **Responsible Component:** `backend/app/agent/nodes/query_executor.py`.
- **Remediation Implemented:** Central 7-point fail-closed gate. Under `PHASE6_LIVE_EXECUTION_ENABLED=False`, all live executions return `GATE_BLOCKED`. Tests execute exclusively against in-memory `mock_db` or isolated test collections.
- **Verifying Automated Test:** `backend/tests/test_phase1_readiness.py::test_protected_assets_remain_unmodified`.
- **Residual Risk:** Zero. All 19,120 documents remain verified untouched.

---

### Category 12: In-Flight Request Cancellation & Prompt Leakage
- **Incident / Test ID:** Frontend Defect UI-05 (`frontend/src/test/ChatApp.test.jsx`)
- **Observed Behavior:** When a user cancelled a query or switched conversation threads while an LLM call was in flight, the aborted query's prompt leaked into the newly selected conversation input box.
- **Expected Behavior:** Clean abort with prompt preserved only in the originating session.
- **Actual Failure:** Confusion and accidental cross-thread prompt submission.
- **Root Cause:** Shared global state in Zustand store without thread-bound abort tracking.
- **Responsible Component:** `frontend/src/store/useChatStore.js`.
- **Remediation Implemented:** Added thread-specific `AbortController` tracking. Switching threads calls `abort()` on the active request and clears thread-local staging prompts.
- **Verifying Automated Test:** `frontend/src/test/ChatApp.test.jsx::17. Switching conversations aborts an in-flight request without leaking its prompt across threads`.
- **Residual Risk:** None. Verified in Vitest.
