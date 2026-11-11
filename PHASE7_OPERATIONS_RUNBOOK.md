# FinTech Agent — Phase 7 Operations Runbook
## Production Administration, Scheduler Runner Management & Troubleshooting Guide

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Academic Term:** Fall 2026 / Semester Evaluation  
**Audience:** System Administrators, DevOps Engineers & Site Reliability Engineers  
**Date:** November 11, 2026  

---

## 1. System Architecture & Process Topography

The FinTech Agent production environment operates with two coordinated backend processes:

```
┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
│        Process A: FastAPI API        │     │    Process B: Scheduler Runner       │
│      (uvicorn backend.app.main:app)  │     │   (python -m ...scheduler_runner)    │
├──────────────────────────────────────┤     ├──────────────────────────────────────┤
│ - Handles conversational user chat   │     │ - Single background APScheduler      │
│ - Node 1-9 LangGraph execution       │     │ - Acquires/renews distributed lease  │
│ - Preview generation & approval      │     │ - Periodically reconciles jobs       │
│ - REST management endpoints          │     │ - Executes scheduled aggregations    │
└──────────────────┬───────────────────┘     └──────────────────┬───────────────────┘
                   │                                            │
                   ▼                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           agent_metadata_db                                       │
│  - schedule_previews: Ephemeral approval previews (TTL 15 min)                    │
│  - scheduled_jobs: Persistent recurring report configurations                     │
│  - job_runs: Complete historical audit trail of all executions                    │
│  - scheduler_leases: Atomic lease coordinates single scheduler authority          │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Service Management Procedures

### 2.1 Starting the API Server
```powershell
# From project root in clean virtual environment
.\.venv_clean\Scripts\Activate.ps1
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2.2 Starting the Background Scheduler Runner
```powershell
# In a separate dedicated process / service
.\.venv_clean\Scripts\Activate.ps1
python -m backend.app.services.scheduler_runner
```

### 2.3 Checking Scheduler Process Status
Inspect the distributed lease in MongoDB:
```javascript
use agent_metadata_db;
db.scheduler_leases.find({ lease_name: "primary_scheduler" }).pretty();
```
*Expected Output:*
```json
{
  "_id": "...",
  "lease_name": "primary_scheduler",
  "instance_id": "sched_PROD-SRV-01_a1b2c3d4",
  "acquired_at": "2026-11-11T12:00:00Z",
  "expires_at": "2026-11-11T12:01:00Z"
}
```
If `expires_at` is in the future, the scheduler authority is healthy and renewing normally.

---

## 3. Scheduled Job Lifecycle Administration

All job lifecycle operations can be performed via REST API or MongoDB shell.

### 3.1 Listing Active Jobs
```bash
curl -X GET "http://localhost:8000/api/v1/schedules" \
     -H "X-User-ID: analyst_1"
```

### 3.2 Pausing a Scheduled Report
```bash
curl -X POST "http://localhost:8000/api/v1/schedules/job_12345/pause" \
     -H "X-User-ID: analyst_1"
```

### 3.3 Resuming a Paused Report
```bash
curl -X POST "http://localhost:8000/api/v1/schedules/job_12345/resume" \
     -H "X-User-ID: analyst_1"
```
*Note:* The resume endpoint triggers mandatory pre-resumption MQL validation. If the underlying schema has drifted, resumption is rejected.

### 3.4 Cancelling a Scheduled Report
```bash
curl -X POST "http://localhost:8000/api/v1/schedules/job_12345/cancel" \
     -H "X-User-ID: analyst_1"
```

### 3.5 Viewing Run History
```bash
curl -X GET "http://localhost:8000/api/v1/schedules/job_12345/runs?limit=20" \
     -H "X-User-ID: analyst_1"
```

---

## 4. Incident Response & Troubleshooting

### 4.1 Job Enters `AUTO_PAUSED` Status
- **Symptom:** Job status changes from `ACTIVE` to `AUTO_PAUSED`. No upcoming run times scheduled.
- **Root Cause:** The job experienced 3 consecutive execution failures (`consecutive_failures >= 3`).
- **Remediation:**
  1. Inspect the error logs in `job_runs`:
     ```javascript
     use agent_metadata_db;
     db.job_runs.find({ job_id: "job_12345", status: "FAILED" }).sort({ start_time: -1 }).limit(3).pretty();
     ```
  2. Verify database connectivity, authentication status, and query limits.
  3. Once the underlying cause is resolved, issue a resume call via `POST /api/v1/schedules/{job_id}/resume`. This resets `consecutive_failures` to 0.

### 4.2 Job Enters `FAILED_CONFIGURATION` Status
- **Symptom:** Job status flips to `FAILED_CONFIGURATION` during scheduled execution.
- **Root Cause:** Node 5 `MQLPolicyValidator` detected schema drift immediately before execution (e.g., a field used in the query was renamed or deleted).
- **Remediation:**
  1. Check the exact error message:
     ```javascript
     db.scheduled_jobs.find({ job_id: "job_12345" }, { last_error: 1, pipeline_template: 1 });
     ```
  2. Inform the report owner that the canonical schema has evolved.
  3. The user must submit a revised query in chat to generate a fresh, validated preview and approve the new job.

### 4.3 Stale Scheduler Lease / Split-Brain Recovery
- **Symptom:** The scheduler runner crashes ungracefully (e.g. host reboot) and the new process cannot acquire the lease immediately.
- **Behavior:** The lease has a strict 60-second TTL (`expires_at = now + 60s`). Within 60 seconds, the expired lease is automatically reclaimed by any active instance without manual intervention.
- **Emergency Force Release:** If necessary, manually clear the lease record:
  ```javascript
  use agent_metadata_db;
  db.scheduler_leases.deleteOne({ lease_name: "primary_scheduler" });
  ```

---

## 5. Security & Audit Guidelines

1. **Never grant write access to banking data:** The background scheduler process must ONLY connect with `fintech_readonly` credentials to `fintech_agent_db`.
2. **Rotate Metadata DB Credentials:** Periodically update `fintech_metadata_rw` passwords in `.env` following corporate secrets management policies.
3. **Monitor `job_runs` Table Size:** Implement a 90-day TTL index on `agent_metadata_db.job_runs.start_time` in high-throughput deployments to prevent unbounded collection growth.
