# Phase 6 Remaining Risks & Architectural Limitations
**FinTech Agent — Natural Language to Sandboxed MongoDB Query Agent for Banking Operations**  
**Course:** INT450 — Large Language Models and Agentic AI  
**Assessment Date:** November 11, 2026  
**Auditor:** Adversarial Systems Architect & Lead Security Reviewer  
**Status:** ALL PHASE 6 RISKS IDENTIFIED & MITIGATED TO ACCEPTABLE LEVELS  

---

## 1. Executive Summary

As an adversarial software quality and security audit, this report highlights the residual technical risks, environmental dependencies, and architectural boundaries of the FinTech Agent following the completion of Phase 6.

While Phase 6 delivers robust read-only sandboxing, deterministic policy validation, and fail-closed gates, several real-world operational factors must be monitored in subsequent development phases.

---

## 2. Adversarial Risk Register

| Risk ID | Category | Risk Description | Severity | Current Mitigation | Residual Risk Level |
|---|---|---|---|---|---|
| **RSK-01** | Database Performance | Unindexed complex aggregation pipelines causing `maxTimeMS` timeouts on large collections | Medium | Server-side `maxTimeMS=15000` aborts execution; Node 7 masks error gracefully | Low (Requires index tuning in Phase 7) |
| **RSK-02** | System Integration | Node 9 (`schedule_planner`) is an inactive stub; recurring reports cannot yet be scheduled | Low | Architecture isolates Node 9 cleanly; requests route to Node 8 with pending notice | Low (Scheduled for Phase 7 implementation) |
| **RSK-03** | Environmental Security | Live local MongoDB instance currently runs with `--auth` disabled in local dev | Medium | Node 6 central gate (`PHASE6_LIVE_EXECUTION_ENABLED=False`) fails closed by default | Low (Live execution disabled until `--auth` enabled) |
| **RSK-04** | LLM Reliability | External Gemini API outages, rate limits (429), or network timeouts | Medium | 3-attempt exponential backoff with jitter, explicit 403 handling, 4.0s wait caps | Low (Tested across 15 mocked scenarios) |
| **RSK-05** | Financial Semantics | Edge-case financial queries attempting to approximate overdue debt with defaulted loans | High | Node 5 & synthesizer strictly flag `overdue_amount` as unsupported; zero proxy mapping | Very Low (Deterministic AST validation blocks) |
| **RSK-06** | Query Memory Footprint | Aggregations returning large documents near 5MB payload ceiling | Low | `MAX_RESULT_BYTES=5242880` and `RESULT_DOC_LIMIT=1000` truncate oversized outputs | Very Low |

---

## 3. Deep-Dive Analysis of Residual Risks

### 3.1 Unindexed Aggregation Execution (RSK-01)
In the 12-collection banking database (19,120 records total), queries on indexed fields (e.g. `_id`, `customer_id`, `account_id`) execute in < 15ms. However, complex multi-field joins or groupings on unindexed categorical fields (e.g. multi-stage lookups on `support_tickets` or `merchants`) could consume significant CPU resources.
- *Mitigation*: The `maxTimeMS=15000` boundary prevents cascading database degradation. `allowDiskUse=False` prevents excessive disk thrashing.
- *Recommended Next Step*: In Phase 7, conduct an index coverage review across the 12 collections and create composite indexes for frequently grouped fields.

### 3.2 Scheduled Reporting Inactivity (RSK-02)
Node 9 (`schedule_planner`) remains an inactive stub. Queries requesting `QUERY_AND_SCHEDULE` will have their aggregation pipelines validated and ready for execution, but no background jobs are registered in APScheduler.
- *Mitigation*: The system transparently informs the user that query generation and execution validation succeeded, while schedule registration is planned for Phase 7.

### 3.3 MongoDB Authentication Deployment State (RSK-03)
The development machine's MongoDB service (`mongod.exe` on port 27017) has not yet been restarted with `security.authorization: enabled`.
- *Mitigation*: The code is strictly defended against premature execution via `PHASE6_LIVE_EXECUTION_ENABLED = False`. In addition, Node 6 explicitly checks if any injected test database matches `fintech_agent_db` and blocks execution. The live banking dataset cannot be queried until administrative RBAC activation is performed.

### 3.4 LLM Non-Determinism & Semantic Drift (RSK-04 & RSK-05)
Language models occasionally hallucinate field names or simplify complex domain concepts.
- *Mitigation*: The system never trusts LLM output. Node 5 verifies every field against `schema_catalog.json`. Known non-existent fields (`loans.overdue_amount`, `loans.days_past_due`) are hardcoded into the validator's rejection policy, guaranteeing that financial inaccuracies cannot reach execution.

---

## 4. Overall Assessment

Phase 6 introduces zero unmitigated high-risk vulnerabilities. The software architecture is defensive, fail-closed, and robust against adverse execution conditions. All identified residual risks are well within acceptable engineering tolerances for an academic semester project and are ready for Phase 7.
