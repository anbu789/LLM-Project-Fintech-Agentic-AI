# FinTech Agent — Phase 5 Remaining Risks Report
## Known Limitations, Operational Boundaries & Prerequisites for Phase 6

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Date:** November 10, 2026  
**Status:** PHASE 5 BOUNDARIES SECURE | PHASE 6 PREREQUISITES DOCUMENTED  

---

## 1. Executive Summary

Phase 5 has successfully built and verified the schema retrieval, natural language query synthesis, and deterministic MQL validation pipeline. 

Because Phase 5 intentionally enforces zero database execution, the system is not yet executing queries or displaying real banking records. This report identifies remaining architectural risks, performance considerations, and prerequisites that must be addressed during Phase 6 (Read-Only Query Execution & Verification).

---

## 2. Identified Risks & Recommended Phase 6 Mitigations

### RISK-01: Aggregation Execution Timeouts on Large Collections
- **Severity:** HIGH
- **Description:** When Phase 6 begins executing aggregation pipelines against the `transactions` collection (10,000 documents) or multi-collection `$lookup` joins, unindexed queries could exceed acceptable response latencies.
- **Current Safeguard:** MongoDB cursor `maxTimeMS` enforcement is already present in `ReadOnlyCursorProxy` (`settings.QUERY_TIMEOUT_MS = 5000`).
- **Phase 6 Mitigation:**
  1. Ensure every pipeline executed in Node 6 explicitly sets `maxTimeMS` on `banking_db[target_col].aggregate(pipeline, maxTimeMS=settings.QUERY_TIMEOUT_MS)`.
  2. Implement request deadline budget checks before initiating execution.
  3. Validate that existing database indexes (e.g., `transactions.customer_id`, `accounts.customer_id`, `customers.city`) are leveraged by aggregation stages.

---

### RISK-02: Result Set Volume & Memory Exhaustion in Node 6
- **Severity:** MEDIUM
- **Description:** An aggregation pipeline returning thousands of documents could exhaust server memory, slow network serialization, or overwhelm the frontend UI.
- **Current Safeguard:** Node 4 injects `$limit: 100` by default; Node 5 enforces a recommended limit.
- **Phase 6 Mitigation:**
  1. In Node 6, enforce hard document limits (`settings.RESULT_DOC_LIMIT = 1000`).
  2. If the aggregation result exceeds the limit, truncate the result set and set `result_truncated: True` in `AgentState`.
  3. Provide UI notification in Node 8 indicating that results have been truncated for performance.

---

### RISK-03: Multi-Hop Complex `$lookup` Memory Constraints
- **Severity:** MEDIUM
- **Description:** Pipelines requiring 2 or 3 `$lookup` stages (e.g., `customers` -> `accounts` -> `transactions`) can trigger MongoDB aggregation memory limits (100MB limit per pipeline stage unless `allowDiskUse` is enabled).
- **Current Safeguard:** Node 5 limits `$lookup` stages to a maximum of 3 and requires verified schema relationships.
- **Phase 6 Mitigation:**
  1. Prohibit `allowDiskUse: True` in Node 6 to prevent arbitrary disk consumption by untrusted queries.
  2. Maintain strict `$match` filtering prior to `$lookup` stages to minimize document working sets.

---

### RISK-04: Handling Empty Result Sets (Result Verifier Node 7)
- **Severity:** LOW
- **Description:** A valid pipeline executed against `fintech_agent_db` may return zero documents (e.g., searching for active customers in a city with zero accounts).
- **Current Safeguard:** Node 7 is registered in LangGraph as `result_verifier_stub`.
- **Phase 6 Mitigation:**
  1. Implement Node 7 (`result_verifier.py`) to classify results into `VALID_WITH_DATA` or `VALID_EMPTY`.
  2. If `VALID_EMPTY` occurs due to over-restrictive filter criteria, provide helpful suggestions to the user (e.g., "No transactions found above ₹500,000 for this customer; would you like to search across all amounts?").

---

### RISK-05: Real LLM Provider Latency & Rate Limits
- **Severity:** LOW
- **Description:** When switching from `settings.LLM_PROVIDER = "mock"` to live providers (Gemini, Claude, GPT-4), external API latency (1–3 seconds) and potential HTTP 429 rate limits could impact user experience.
- **Current Safeguard:** Exponential backoff and retry logic in `LLMService` adapters; request deadline tracking.
- **Phase 6 Mitigation:**
  1. Maintain prompt brevity (schema catalog chunks bounded to 25 fields per collection).
  2. Ensure frontend displays clean loading and skeleton states during synthesis and execution.

---

## 3. Mandatory Phase 6 Prerequisites

Before enabling query execution in Node 6, the following conditions must be met:
1. **Authenticated Sandbox:** The read-only banking connection must use `fintech_readonly_user` with strictly the `read` role on `fintech_agent_db`.
2. **Proxy Protection:** All PyMongo calls must pass through `ReadOnlyDatabaseProxy` and `ReadOnlyCollectionProxy`.
3. **Execution Timeouts:** All calls must specify `maxTimeMS` natively.
4. **Zero Mutation Guarantee:** Database document count must remain 19,120 before and after every execution test.

---

## 4. Final Risk Verdict

```
PHASE 5 RISKS FULLY MITIGATED — ARCHITECTURE READY FOR PHASE 6 EXECUTION ENGINE.
```
