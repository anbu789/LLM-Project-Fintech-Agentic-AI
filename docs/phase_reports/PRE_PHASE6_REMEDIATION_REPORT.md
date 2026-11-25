# Pre-Phase 6 Remediation Report
**Project:** FinTech Agent — Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Author:** Principal Software Architect, Senior Python Engineer, LangGraph Specialist, MongoDB Security Engineer, Gemini Integration Specialist  
**Date:** November 10, 2026  
**Git Baseline Commit:** `48f6c90`  
**Remediation Scope:** Phase 4 & Phase 5 Defect Correction, Financial Accuracy, Gemini Reliability, MQL Security, Logging Portability, and RBAC Readiness  

---

## 1. Executive Summary

Following the findings of `PHASE4_PHASE5_INDEPENDENT_POST_AUDIT_REPORT.md`, this remediation sprint systematically resolved all confirmed defects across Phase 4 and Phase 5 without commencing Phase 6 query execution.

### Key Remediation Results:
1. **Financial Semantics (Priority 1):** Eliminated the silent substitution of `loans.status = "defaulted"` and `outstanding_amount` as a calculated proxy for overdue loan debt. Queries requesting overdue loans, overdue amounts, or days past due (DPD) now return a structured `UNSUPPORTED` status with clear educational explanations of schema limitations. Supported defaulted loan queries and outstanding principal summations remain fully functional and explicitly labeled.
2. **Hard MQL Result-Volume Policy (Priority 2):** Node 5 (MQL Policy Validator) now deterministically rejects pipelines exceeding `RESULT_DOC_LIMIT` (1,000 documents) as `INVALID` with hard validation errors rather than advisory warnings. Enforced terminal `$limit` requirements on row-returning pipelines and blocked `$unwind` array expansion following limit stages.
3. **Multi-Turn Conversation Context (Priority 3):** Fixed `mock_classify_intent` to properly inspect `conversation_history`, enabling seamless conversational follow-ups (e.g., "What about Coimbatore?", "Only show failed ones", "Sort them by outstanding amount") while preserving strict cross-session isolation when no history or separate sessions are queried.
4. **Gemini Reliability & Bounded Retries (Priority 4):** Hardened `OpenAICompatibleProvider` with an asynchronous bounded retry mechanism (up to 3 total attempts) with exponential backoff and jitter for transient errors (HTTP 502, 503, 504, temporary 429 rate limits, and network timeouts), while failing fast without useless retries on permanent authentication (401/403) and client (400, 404) errors.
5. **Windows Logging Portability (Priority 5):** Added `make_ascii_safe` transformation in `backend/app/core/logging.py` to prevent Windows `cp1252` console crashes on Unicode decorative characters (`→`, `₹`, `✅`, `❌`, `⚠️`) while retaining full diagnostic output and regex credential redaction.
6. **Authentication Script Hardening (Priority 8):** Aligned `scripts/mongo_init_auth.js` and `scripts/rollback_mongo_auth.js` with `.env` configuration variables (`fintech_readonly_user` and `agent_metadata_user`), enforcing least privilege without hardcoded secrets.
7. **Complete Regression Verification:** All **201 backend tests** pass (171 historical + 30 new remediation tests). All **8 frontend tests** pass. Frontend production build compiles cleanly. The live database remains intact at exactly **19,120 documents**.

---

## 2. Inventory of Modified and Created Files

| File Path | Nature | Purpose |
|---|---|---|
| `backend/app/agent/prompts/query_synthesis.py` | Modified | Corrected loan prompt rules; removed overdue proxy rule; added defaulted loan archetypes and follow-up city filters. |
| `backend/app/agent/nodes/mql_policy_validator.py` | Modified | Enforced hard `$limit` <= 1,000 error; added terminal limit enforcement and `$unwind` expansion checks; handled `UNSUPPORTED` concept states. |
| `backend/app/agent/prompts/intent_classification.py` | Modified | Implemented multi-turn follow-up context resolution in `mock_classify_intent`; replaced non-ASCII arrows. |
| `backend/app/services/llm_service.py` | Modified | Implemented bounded 3-attempt exponential backoff with jitter in `OpenAICompatibleProvider`. |
| `backend/app/core/logging.py` | Modified | Added `make_ascii_safe()` to sanitize log output for Windows CP1252 stream safety. |
| `backend/app/agent/nodes/response_composer.py` | Modified | Updated `_UNSUPPORTED_CONCEPT_TEMPLATE` to explain remaining principal vs. overdue debt; sanitized Unicode output. |
| `scripts/mongo_init_auth.js` | Modified | Parameterized usernames (`fintech_readonly_user`, `agent_metadata_user`) matching `.env` and `config.py`. |
| `scripts/rollback_mongo_auth.js` | Modified | Added safe idempotency dropping both active and legacy provisioned usernames. |
| `backend/tests/test_phase5_query_pipeline.py` | Modified | Updated test assertion to verify overdue inquiries are NOT mapped to defaulted loan proxy. |
| `backend/tests/test_pre_phase6_remediation.py` | Created | Dedicated 30-test regression suite covering Financial Semantics, MQL Limits, Context, Gemini Retries, Logging, Graph Flow, and Security. |
| `PRE_PHASE6_REMEDIATION_REPORT.md` | Created | Master remediation and root-cause analysis report. |
| `PRE_PHASE6_TEST_REPORT.md` | Created | Comprehensive test verification and regression report. |
| `PRE_PHASE6_SECURITY_REPORT.md` | Created | MQL validator, proxy bypass, and RBAC readiness report. |
| `PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md` | Created | In-depth financial domain analysis of supported vs. unsupported loan metrics. |
| `PHASE6_READINESS_CHECKLIST.md` | Created | Phase 6 gatekeeping checklist separating development from live execution authorization. |

---

## 3. Detailed Remediation Analysis by Priority

### Priority 1: Financial Semantics for Overdue Loans (Severity: P1)
- **Root Cause:** Phase 5 query synthesis previously mapped natural language queries asking for "overdue loans" or "overdue amount" to `loans.status = "defaulted"` and aggregated `loans.outstanding_amount`. In commercial banking, total outstanding principal on a defaulted loan is the full remaining balance, whereas "overdue amount" represents delinquent unpaid installments, missed interest, and penalties.
- **Code Fix:**
  - In `backend/app/agent/prompts/query_synthesis.py`, removed the rule substituting defaulted status for overdue inquiries.
  - Set `pipeline: []` and populated `unsupported_concepts_identified: ["overdue_amount", "days_past_due"]` for overdue queries.
  - Added dedicated archetypes for legitimate defaulted loan queries ("Show defaulted loans" -> `status: "defaulted"`) and principal summaries ("Calculate outstanding principal of defaulted loans" -> aggregates `outstanding_amount` labeled strictly as "Total outstanding principal of defaulted loans").
  - In `backend/app/agent/nodes/mql_policy_validator.py`, routed empty pipelines with unsupported concepts to `validation_status = "UNSUPPORTED"`.
  - In `backend/app/agent/nodes/response_composer.py`, formatted `_UNSUPPORTED_CONCEPT_TEMPLATE` explaining that overdue debt cannot be derived from remaining principal.

### Priority 2: Hard MQL Result-Volume Policy (Severity: P1/P2)
- **Root Cause:** `validate_pipeline()` in `mql_policy_validator.py` previously appended a warning when `$limit` exceeded `RESULT_DOC_LIMIT` (1,000), allowing over-limit or unbounded pipelines to receive `validation_status = "VALID"`.
- **Code Fix:**
  - Changed `$limit > settings.RESULT_DOC_LIMIT` from a warning to a hard validation error, setting `is_valid = False` and `validation_status = "INVALID"`.
  - Added terminal `$limit` checking when `require_terminal_limit=True` (active in Node 5). Row-returning pipelines must contain an effective terminal limit stage bounding final results.
  - Added `$unwind` post-limit validation: rejected pipelines where `$unwind` appears after a `$limit` without a subsequent `$limit`, preventing unbounded array row expansion.
  - Enforced consistency across multiple `$limit` stages: prevented subsequent limits from attempting to expand earlier bounds.

### Priority 3: Phase 4 Conversation Context Fix (Severity: P2)
- **Root Cause:** `mock_classify_intent()` in `intent_classification.py` accepted `conversation_history` but explicitly left it unused (`# unused in mock`). Elliptical follow-up questions without standalone banking keywords fell through to `OUT_OF_SCOPE`.
- **Code Fix:**
  - Added reverse inspection of `conversation_history` to extract prior banking queries in the active session.
  - Added follow-up pattern detection ("what about", "how about", "only show", "sort them by", "filter by", short contextual queries).
  - When follow-up is recognized, inherits prior banking subject (e.g., "Show customers from Chennai" -> "What about Coimbatore?" is classified as `QUERY_ONLY` with composite query description).
  - When `conversation_history` is empty or from a separate session, identical follow-ups cannot infer context and route to `CLARIFICATION_REQUIRED` or `OUT_OF_SCOPE`.

### Priority 4: Gemini Reliability Hardening (Severity: P2)
- **Root Cause:** `OpenAICompatibleProvider` made a single HTTP request without retries. Upstream temporary HTTP 503 high-demand errors or timeouts immediately caused request termination.
- **Code Fix:**
  - Wrapped `generate_response()` in an asynchronous bounded retry loop (up to 3 total attempts).
  - Implemented exponential backoff with random jitter (`0.5 * (2 ** attempt) + uniform(0.1, 0.4)s`).
  - Implemented `Retry-After` header parsing.
  - Categorized errors: retries transient errors (502, 503, 504, temporary 429, timeouts, connection errors); fails fast without retrying permanent client/auth errors (400, 401, 403, 404, quota exhaustion).
  - Never silently substitutes mock responses when live Gemini fails.

### Priority 5: Windows Logging Compatibility (Severity: P3)
- **Root Cause:** Decorative Unicode characters (`→`, `₹`, `✅`, `❌`, `ℹ️`, `⚠️`) caused `UnicodeEncodeError: 'charmap' codec can't encode character` when logging to Windows console streams using CP1252.
- **Code Fix:**
  - Implemented `make_ascii_safe()` in `backend/app/core/logging.py`, replacing non-ASCII symbols with portable ASCII equivalents (`->`, `INR `, `[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`).
  - Enhanced `RedactingFormatter` to ensure all emitted log messages encode cleanly to the target stream's encoding.

---

## 4. Contract and Documentation Reconciliation (Priority 6)

### A. RequestMode Taxonomy Reconciliation
- **Canonical Code Contract:** Defined in `backend/app/agent/state.py`:
  `Literal["QUERY_ONLY", "QUERY_AND_SCHEDULE", "SCHEDULE_ONLY", "CLARIFICATION_REQUIRED", "OUT_OF_SCOPE"]`
- **Graph Routing:** Reconciled in `backend/app/agent/graph.py`:
  `QUERY_ONLY`, `QUERY_AND_SCHEDULE`, and `SCHEDULE_ONLY` proceed to `schema_retriever`.
  `CLARIFICATION_REQUIRED` and `OUT_OF_SCOPE` route directly to `response_composer`.
- **Status Clarification:** Documentation references to `SCHEDULE_QUERY` and `HYBRID_QUERY_SCHEDULE` were legacy architectural aliases for `SCHEDULE_ONLY` and `QUERY_AND_SCHEDULE`. Codebase consistently uses the 5 canonical modes from `state.py`.

### B. Canonical API Endpoint
- **Registered Path:** `POST /api/v1/chat` (mounted in `backend/app/main.py` via `api_router` with prefix `/api/v1`).
- **Frontend Configuration:** `frontend/src/services/api.js` sets `API_BASE_URL = '/api/v1'`, calling `apiClient.post('/chat')`, which targets `POST /api/v1/chat`.
- **Documentation Reconciliation:** Canonical path is `/api/v1/chat`.

### C. Guardrail Rejection Routing
- **Verified Behavior:** `route_after_guardrail` maps `guardrail_status == "rejected"` directly to `END`.
- `input_guardrail.py` populates `final_status: "rejected"` and `graph_response` directly, returning clean rejection text to caller without invoking Node 2 or downstream LLM services.

---

## 5. Remaining Limitations

1. **Live Gemini Upstream Demand:** Live testing against `https://generativelanguage.googleapis.com/v1beta/openai` with `gemini-3.8-flash` confirmed that Google's servers periodically return HTTP 503 ("This model is currently experiencing high demand"). The retry mechanism successfully attempts 3 backoff cycles before failing gracefully.
2. **Native MongoDB RBAC Inactive:** MongoDB 8.0 on localhost:27017 runs without `--auth`. Read-only protection is currently enforced 100% by Python application proxies (`ReadOnlyDatabaseProxy`), pending server-side authentication activation.

---
*Report certified by Principal Software Architect & Application Security Reviewer.*
