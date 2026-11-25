# FinTech Agent — Phase 7 Remaining Risks & Mitigation Strategies
## Residual Risk Assessment, Environmental Factors & Operational Safeguards

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Academic Term:** Fall 2026 / Semester Evaluation  
**Assessment Date:** November 11, 2026  

---

## 1. Executive Summary

This document provides a transparent, rigorous accounting of residual operational and environmental risks following the completion of Phase 7 (Scheduled Queries and Automated Reports). Every identified risk has an active mitigation strategy or a deterministic architectural safeguard.

---

## 2. Risk Registry & Detailed Analysis

### Risk 1: Unprovisioned Native MongoDB Authentication in Active Process
- **Category:** Infrastructure / Security Gate
- **Severity:** High (if unguarded)
- **Current State:**
  - The currently running local `mongod` process on `127.0.0.1:27017` is running with native authorization disabled (`security.authorization: disabled`).
  - Neither `fintech_readonly` on `fintech_agent_db` nor `fintech_metadata_rw` on `agent_metadata_db` has been created in the running server.
- **Architectural Safeguard:**
  - **Triple Fail-Closed Execution Gate:** In `backend/app/agent/nodes/query_executor.py` and `scheduler_runner.py`, `check_live_execution_readiness()` strictly checks `settings.PHASE6_LIVE_EXECUTION_ENABLED`, `settings.MONGO_AUTH_ENABLED`, and `settings.MONGO_NATIVE_AUTH_VERIFIED`.
  - Unless all three flags are explicitly `True` and verified, live database query execution is unconditionally blocked and replaced with safe simulation/gated notices.
- **Mitigation Procedure:**
  - Follow the step-by-step checklist in `PHASE7_EXECUTION_READINESS.md`: execute `mongo_init_auth.js`, update `mongod.cfg`, restart the service, and verify via `verify_mongo_auth.py`.

---

### Risk 2: Gemini API Quota Exhaustion on Background Automated Jobs
- **Category:** External Provider Dependency
- **Severity:** Very Low (Eliminated by Design)
- **Analysis:**
  - Could scheduled reports fail during the night if external LLM provider quotas are exhausted?
- **Architectural Safeguard:**
  - **Zero LLM Dependency at Execution Time:** The FinTech Agent architecture completely decouples natural language understanding from query execution.
  - The Gemini LLM is used **only once** during the initial conversational turn to synthesize the aggregation pipeline.
  - Once approved by the user, the persistent job stores the exact, validated MongoDB aggregation pipeline.
  - At runtime, `SchedulerRunner` resolves dynamic relative date tokens and executes the query directly against MongoDB through `query_executor_node` without making any LLM calls.
  - Therefore, scheduled reporting operations are 100% resilient to Gemini outages, rate limits, or quota exhaustion.

---

### Risk 3: Memory Pressure on High-Volume Aggregation Queries
- **Category:** Database Performance / Resource Contention
- **Severity:** Low
- **Analysis:**
  - Complex `$group` or `$lookup` pipelines over 100,000+ documents could exceed MongoDB's in-memory sort limit (100MB).
- **Architectural Safeguard:**
  - `allowDiskUse=False` prevents uncontrolled spillover to disk.
  - `maxTimeMS=15000` enforces a strict 15-second execution deadline on every aggregation.
  - `MQLPolicyValidator` enforces that unbounded aggregation pipelines include an explicit terminal `$limit` stage (capped at `settings.RESULT_DOC_LIMIT = 1000`).
  - Foreign key lookups are restricted to 1:1 relationships verified against single-field unique indexes (`PHASE6_VERIFIED_INDEX_EVIDENCE.json`), preventing multiplicative Cartesian joins.

---

### Risk 4: Daylight Saving Time (DST) Jitter in International Timezones
- **Category:** Scheduling Precision
- **Severity:** Very Low
- **Analysis:**
  - Ambiguities during autumn/spring clock changes (e.g. `America/New_York` repeated or skipped hours).
- **Architectural Safeguard:**
  - `validate_iana_timezone()` mandates valid IANA timezone identifiers (e.g. `Asia/Kolkata`, `UTC`, `America/New_York`).
  - Next-run calculations rely on APScheduler's native `CronTrigger`, which leverages Python's standard `zoneinfo` engine to resolve DST offsets accurately across fire times.

---

### Risk 5: Growth of Historical Audit Logs in `job_runs`
- **Category:** Database Capacity
- **Severity:** Low
- **Analysis:**
  - Over months of recurring executions, `agent_metadata_db.job_runs` will accumulate records.
- **Mitigation Procedure:**
  - Provision a MongoDB TTL index on `start_time` for the `job_runs` collection:
    ```javascript
    use agent_metadata_db;
    db.job_runs.createIndex({ "start_time": 1 }, { expireAfterSeconds: 7776000 }); // 90 days
    ```

---

## 3. Summary Risk Matrix

| Risk Description | Inherent Severity | Residual Severity | Key Mitigation |
| :--- | :---: | :---: | :--- |
| **Unprovisioned MongoDB Auth** | High | Negligible | Fail-closed execution gate (`PHASE6_LIVE_EXECUTION_ENABLED=False`) |
| **Gemini Outage / Rate Limits** | High | None | Scheduled execution requires zero LLM API calls |
| **Database Memory Exhaustion** | Medium | Negligible | Strict 15s deadline, no disk spill, enforced terminal `$limit` |
| **Schema Drift over Time** | High | Negligible | Deterministic `MQLPolicyValidator` re-validation prior to every run |
| **Lease Collision in Multi-Node** | Medium | Negligible | Atomic `find_one_and_update` on `scheduler_leases` collection |
| **Runaway Failure Retries** | Medium | Negligible | Automatic circuit-breaker pause (`AUTO_PAUSED`) after 3 failures |

---

## 4. Conclusion

All residual risks are thoroughly addressed through fail-closed controls, zero-LLM runtime decoupling, pre-execution validation, and resource limits. The system is safe, stable, and ready for deployment under authentication.
