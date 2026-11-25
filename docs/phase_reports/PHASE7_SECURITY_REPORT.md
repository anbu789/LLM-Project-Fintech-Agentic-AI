# FinTech Agent — Phase 7 Security Architecture & Threat Model Report
## Comprehensive Application Security, Tenant Isolation, Tamper Resistance & Autonomous Safety Gates

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Academic Term:** Fall 2026 / Semester Evaluation  
**Security Status:** Audited, Hardened & Independently Verified  
**Date:** November 11, 2026  

---

## 1. Security Architecture Overview

Autonomous and scheduled agent systems introduce novel security challenges compared to simple interactive chat systems. Unbounded recurring execution, prompt injection through schedule names, tampering with approved queries, schema drift over time, and runaway failure loops represent significant risks if not defended against.

Phase 7 of the FinTech Agent establishes a **10-tier defense-in-depth security model** protecting banking operations and metadata assets:

```
[Threat Boundary 1: API & Client Requests]
  - Strict Pydantic input sanitization (message length ≤ 2000, conversation_id alphanumeric regex)
  - In-memory sliding window rate limiting (ChatRateLimiter: max 30 req/min)
  - Ownership enforcement (X-User-ID matching on all schedule endpoints)

[Threat Boundary 2: LangGraph Agent Safety]
  - Node 1: Input Guardrail blocks prompt injections, SQLi, MQLi, and non-banking domains
  - Node 2: Intent Router strictly classifies request modes

[Threat Boundary 3: Pipeline Synthesis & MQL Validation]
  - Node 4: Schema grounding strictly bounded to retrieved catalog
  - Node 5: MQLPolicyValidator blocks all destructive operators ($out, $merge, $writeConcern, etc.),
            JavaScript execution ($where, $function), system namespaces ($cmd), and enforces terminal $limit

[Threat Boundary 4: Scheduling Approval Gate]
  - Node 9: Previews remain unapproved (status: PENDING_APPROVAL, schedule_approved: False)
  - SHA-256 Pipeline Hashing: Tamper detection rejects modified pipelines upon approval
  - TTL Expiration: Previews expire after 15 minutes
  - Idempotency: Prevents double-scheduling via client idempotency keys

[Threat Boundary 5: Durable Metadata Storage]
  - Scheduled jobs and execution history stored strictly in agent_metadata_db
  - ZERO write privileges to fintech_agent_db

[Threat Boundary 6: Scheduler Runner & Execution Safety]
  - Single-Process Distributed Lease: scheduler_leases collection prevents multi-instance execution storms
  - Pre-Execution Runtime Revalidation: MQLPolicyValidator re-evaluates pipeline immediately before fire
  - Schema Drift Defense: Invalidated queries transition to FAILED_CONFIGURATION without executing
  - Dynamic Date Token Resolution: Safe, structured parsing ($$DAYS_AGO_30) without eval()
  - Failure Circuit Breaker: Auto-pauses job (AUTO_PAUSED) after 3 consecutive failures
  - Fail-Closed Feature Gates: Background runner disabled by default (PHASE7_SCHEDULER_ENABLED=False)
```

---

## 2. Threat Analysis & Countermeasures

### 2.1 Threat 1: Autonomous Unapproved Scheduling
- **Risk:** An LLM hallucinations or adversarial prompt might automatically schedule a recurring report without the human user's knowledge or consent.
- **Countermeasure:** Node 9 enforces that `schedule_approved` is unconditionally `False` during graph execution. The system creates an immutable `SchedulePreview` stored in `agent_metadata_db.schedule_previews`. No job can be registered or executed until the human user submits an explicit authenticated `POST /api/v1/schedules/approve` request.

### 2.2 Threat 2: Pipeline Tampering & Parameter Manipulation
- **Risk:** An attacker intercepts or modifies the approved pipeline between preview generation and approval, substituting a malicious aggregation pipeline.
- **Countermeasure:** When a preview is generated, `ScheduleService.compute_pipeline_hash()` computes a SHA-256 checksum over the serialized JSON representation of the pipeline stages. Upon approval, the server recomputes the hash from the stored pipeline and compares it with `preview.pipeline_hash`. If any stage, key, or value has been tampered with, approval is aborted with `ScheduleServiceError("Pipeline integrity verification failed: pipeline hash mismatch")`.

### 2.3 Threat 3: Tenant / Ownership Impersonation
- **Risk:** User B approves, inspects, pauses, resumes, or cancels User A's scheduled banking reports or views User A's report execution history.
- **Countermeasure:** Every schedule preview and durable job document contains an immutable `owner_id`. All schedule endpoints (`/api/v1/schedules/*`) extract the authenticated identity via `get_current_user_id` (`X-User-ID` header) and verify exact ownership matching. Cross-user operations raise `ScheduleOwnershipError` and return `HTTP 403 Forbidden`.

### 2.4 Threat 4: Schema Drift & Stale Approved Pipelines
- **Risk:** A query approved weeks ago becomes invalid because an underlying collection field is deprecated, renamed, or modified. Running the stale pipeline could result in unexpected behavior or resource exhaustion.
- **Countermeasure:** Approved pipelines are **never permanently trusted**. Immediately before each scheduled execution fire, `SchedulerRunner.execute_scheduled_job()` invokes `MQLPolicyValidator.validate_pipeline()`. If the pipeline references any field not present in the current schema or violates current security policies, execution is aborted, the job status is transitioned to `FAILED_CONFIGURATION`, and an audit record is logged in `job_runs`.

### 2.5 Threat 5: Runaway Resource Exhaustion & Denial of Service
- **Risk:** A scheduled job fails due to an upstream database issue or network partition, and continually retries indefinitely, overloading the database.
- **Countermeasure:** `SchedulerRunner` tracks `consecutive_failures` on each job document. If a job fails 3 consecutive times (`PHASE7_FAILURE_THRESHOLD=3`), the scheduler automatically transitions the job to `AUTO_PAUSED`, halts future executions, and notifies operations via logs. Resuming an auto-paused job requires explicit manual action via `POST /api/v1/schedules/{job_id}/resume`, which triggers mandatory pipeline revalidation.

### 2.6 Threat 6: Concurrency Storms & Duplicate Execution
- **Risk:** In horizontally scaled or containerized deployments, multiple backend instances run background schedulers, leading to duplicate simultaneous executions of the same recurring report.
- **Countermeasure:** `SchedulerRunner` coordinates through a distributed database lease in `agent_metadata_db.scheduler_leases`. The primary instance acquires a lease with a 60-second TTL. If secondary instances detect an unexpired lease held by another instance ID, their background schedulers remain completely passive.

### 2.7 Threat 7: Unsafe Code Execution via Dynamic Dates
- **Risk:** Resolving relative dates (e.g. "past 30 days") through `eval()` or string interpolation exposes the system to code execution.
- **Countermeasure:** Dynamic date tokens (`$$DAYS_AGO_<N>`, `$$DAYS_AHEAD_<N>`, `$$TODAY_START`, `$$NOW`) are parsed using strict regular expressions (`\$\$DAYS_AGO_(\d+)`), converted to standard Python integer offsets, and computed using Python's `datetime` and `timedelta` libraries before JSON deserialization. No dynamic evaluation or arbitrary string substitution is ever permitted.

---

## 3. Fail-Closed Deployment Gate Summary

| Configuration Setting | Default Value | Security Impact |
| :--- | :--- | :--- |
| `PHASE6_LIVE_EXECUTION_ENABLED` | `False` | Blocks any query execution against `fintech_agent_db` until native auth is active |
| `PHASE7_SCHEDULER_ENABLED` | `False` | Prevents background scheduler loop from running in development |
| `PHASE7_LIVE_REGISTRATION_ENABLED` | `False` | Prevents automated registration of live jobs against unverified clusters |
| `PHASE7_DRY_RUN_RESULT_LIMIT` | `10` | Caps preview data sets to 10 records maximum |
| `PHASE7_FAILURE_THRESHOLD` | `3` | Automatically pauses runaway failing scheduled jobs |
| `SCHEDULER_TIMEZONE` | `"Asia/Kolkata"` | Standard IANA timezone enforcement across all trigger calculations |

---

## 4. Security Verification Conclusion

Phase 7 maintains the strongest security posture across the entire application lifecycle. The scheduled query subsystem is completely isolated from original banking data, protects against parameter tampering and schema drift, enforces strict ownership boundaries, and safely prevents denial of service.
