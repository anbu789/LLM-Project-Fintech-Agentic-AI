# FinTech Agent — Phase 7 Implementation Report
## Scheduled Queries, Automated Reports & Autonomous Lifecycle Management

**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Academic Term:** Fall 2026 / Semester Evaluation  
**Author:** Principal Software Architect, Senior Python Engineer & LangGraph Specialist  
**Status:** Completed & Independently Verified  
**Date:** November 11, 2026  

---

## 1. Executive Summary

Phase 7 completes the operational scheduling automation layer of the FinTech Agent system. It enables users to express recurring banking query requirements in natural language (e.g., *"Send me active accounts every Monday at 9:00 AM"*, *"Generate daily loan delinquency reports at 8:00 AM"*), validates recurrence intervals against strict IANA timezone standards, projects deterministic upcoming execution timestamps using APScheduler triggers, presents immutable dry-run previews requiring explicit user approval, and coordinates durable job execution within `agent_metadata_db`.

Crucially, Phase 7 adheres to the strict security architecture of the FinTech Agent:
1. **Zero Access to Original Banking Data:** The historical production database (`fintech_agent_db`, 19,120 documents across 12 canonical collections) was never queried, modified, or accessed during Phase 7 implementation or testing.
2. **Fail-Closed Autonomous Execution Gate:** `PHASE7_SCHEDULER_ENABLED=False` and `PHASE7_LIVE_REGISTRATION_ENABLED=False` default to disabled, preventing unauthenticated background query loops until native MongoDB authentication is manually verified.
3. **Runtime Deterministic Revalidation:** Every scheduled execution passes through `MQLPolicyValidator` immediately before runtime execution. If schema drift or illegal operators are detected, the job transitions to `FAILED_CONFIGURATION` without running any database operation.
4. **Single External Scheduler Process:** Background jobs are managed by an asynchronous runner (`SchedulerRunner`) coordinating through a distributed database lease (`scheduler_leases`), eliminating duplicate task execution and race conditions without heavy third-party brokers (Redis/Celery).

---

## 2. Implemented Architecture & Component Breakdown

```
User Prompt (Natural Language)
               │
               ▼
   [Node 1: Input Guardrail]
               │ (Allowed)
               ▼
    [Node 2: Intent Router] ──── (SCHEDULE_ONLY / QUERY_AND_SCHEDULE)
               │
               ▼
  [Node 3: Schema Retriever] ──── (Vector RAG on 12 collections)
               │
               ▼
 [Node 4: Query Synthesizer] ──── (Synthesize candidate MQL)
               │
               ▼
[Node 5: MQL Policy Validator] ── (Deterministic security gate)
               │
               ▼
  [Node 6: Query Executor] ────── (Gated / Bounded dry-run preview)
               │
               ▼
  [Node 7: Result Verifier] ───── (Result integrity check)
               │
               ▼
 [Node 9: Schedule Planner] ───── (Recurrence parser, next 3 run times,
               │                   immutable preview generation)
               ▼
[Node 8: Response Composer] ───── (Formats interactive preview card &
               │                   explicit approval instructions)
               ▼
        User Receives
    Schedule Preview Card
               │
               ▼  (Explicit POST /api/v1/schedules/approve)
  [Durable Job Activated in agent_metadata_db.scheduled_jobs]
               │
               ▼
   [Single APScheduler Runner (scheduler_runner.py)]
   - Distributed lease coordination in scheduler_leases
   - Periodic reconciliation
   - Dynamic relative date token resolution ($$DAYS_AGO_30)
   - Pre-execution MQLPolicyValidator re-validation
   - Bounded execution & error tracking (Auto-pause after 3 failures)
   - Durable run history logged to agent_metadata_db.job_runs
```

### 2.1 Dependencies & Version Pinning
- **`apscheduler==3.11.3`**: Standard single-process task scheduling framework utilizing `AsyncIOScheduler` and `CronTrigger`.
- **`tzlocal==5.4.5`**: System timezone resolution utility complementing Python 3.9+ native `zoneinfo`.
- Both packages installed in the clean virtual environment (`.venv_clean`) and pinned in `backend/requirements.txt`.

### 2.2 Pydantic Contracts (`backend/app/schemas/schedule.py`)
- **`ScheduleSpec`**: Normalized model storing frequency (`daily`, `weekly`, `monthly`, `cron`), human recurrence expression, 5-field cron expression, IANA timezone string, execution hour/minute, days of week, and days of month.
- **`SchedulePreview`**: Immutable data transfer object containing `preview_id`, `owner_id`, `report_name`, `target_collection`, `approved_pipeline`, `pipeline_hash` (SHA-256), `schedule_spec`, `next_run_times` (next 3 timestamps), `dry_run_status`, `dry_run_results` (capped at 10 documents), and `expires_at`.
- **`ScheduleApprovalRequest`**: Client approval payload with `preview_id` and optional `idempotency_key`.
- **`ScheduleApprovalResponse`**: Immediate server confirmation including `job_id`, `status` (`ACTIVE`), and `next_run_time`.
- **`ScheduledJob`**: Persistent MongoDB document model in `agent_metadata_db.scheduled_jobs` tracking full execution configuration, recurrence, ownership, next/last run times, and consecutive failure counts.
- **`JobRun`**: Execution audit log model in `agent_metadata_db.job_runs` recording run ID, job ID, duration, status (`SUCCESS`, `FAILED`, `SKIPPED`), row counts, and error details.

### 2.3 Recurrence & Natural Language Parser (`backend/app/services/recurrence_parser.py`)
- Implements `parse_recurrence(text, timezone_name)`:
  - **Standard 5-Field Cron**: Matches expressions like `0 9 * * 1` or `30 8 * * *`. Validates syntax and field value limits using `CronTrigger.from_crontab()`. Rejects invalid out-of-range cron expressions (`99 99 * * *`).
  - **Daily Recurrence**: Detects `daily`, `every day`, `each day` combined with explicit time strings (`at 8:00 AM`, `at 14:30`, `at 6pm`). Automatically populates `cron_expression="<min> <hour> * * *"`.
  - **Weekly Recurrence**: Detects `every Monday`, `weekly on Friday` using word boundary checks (`\b(every|on)\s+<day>\b`) to prevent substring collisions (e.g. `mon` inside `month`). Generates `cron_expression="<min> <hour> * * <day>"`.
  - **Monthly Recurrence**: Detects `first day of every month`, `monthly on the 1st`, `every month on the 15th`. Validates day of month ($1 \le \text{DOM} \le 31$) and generates `cron_expression="<min> <hour> <dom> * *"`.
  - **Time Extraction**: `_parse_time_parts()` reliably isolates `at <time>` or explicit colon/meridiem timestamps without false-matching ordinal day numbers.
  - **Next Run Projections**: `calculate_next_run_times(spec, count=3)` queries real APScheduler `CronTrigger.get_next_fire_time()` sequentially, returning strictly ascending, future ISO UTC timestamps.

### 2.4 Schedule Persistence & Approval Workflow (`backend/app/services/schedule_service.py`)
- Coordinates immutable preview generation, SHA-256 tamper verification, explicit approval, and job lifecycle.
- **`create_preview()`**: Computes SHA-256 hash of the pipeline and stores preview in `agent_metadata_db.schedule_previews` with a 15-minute expiration window.
- **`approve_preview()`**:
  - Validates preview existence and checks current UTC against `expires_at`.
  - Enforces ownership: only the user who created the preview (`owner_id`) can approve it.
  - Verifies pipeline integrity by recomputing SHA-256 hash against the stored hash.
  - Executes immediate deterministic revalidation via `MQLPolicyValidator.validate_pipeline()`.
  - Enforces idempotency via `idempotency_key` or `preview_id`.
  - Transitions job to `ACTIVE` in `agent_metadata_db.scheduled_jobs`.
- **Lifecycle Operations**: `pause_job()`, `resume_job()` (with mandatory pre-resumption MQL revalidation), `cancel_job()` (clearing `next_run_at`), and `get_job_runs()`.

### 2.5 Background Scheduler Runner (`backend/app/services/scheduler_runner.py`)
- Independent, single-process background scheduling authority.
- **Distributed Lease**: Periodically acquires/renews `primary_scheduler` lease in `agent_metadata_db.scheduler_leases` with 60-second TTL. If another process holds an unexpired lease, secondary instances remain passive.
- **Job Reconciliation**: Queries `scheduled_jobs` where `status == "ACTIVE"`, mounts corresponding `CronTrigger` instances in APScheduler, and unregisters paused or cancelled jobs.
- **Dynamic Relative Date Resolution**: Replaces date placeholders in MQL pipelines at execution time:
  - `$$DAYS_AGO_<N>` $\rightarrow$ `(now - N days).isoformat()`
  - `$$DAYS_AHEAD_<N>` $\rightarrow$ `(now + N days).isoformat()`
  - `$$TODAY_START` $\rightarrow$ start of current UTC day
  - `$$NOW` $\rightarrow$ current UTC timestamp
- **Pre-Execution Revalidation & Drift Defense**: Immediately before executing any scheduled query, invokes `MQLPolicyValidator`. If schema drift has made a field invalid, the job status is set to `FAILED_CONFIGURATION` and no query is run.
- **Consecutive Failure Auto-Pause**: Increments consecutive failure counter upon runtime errors; automatically pauses job (`AUTO_PAUSED`) when threshold ($\ge 3$) is reached.
- **Run Logging**: Records each execution in `agent_metadata_db.job_runs`.

### 2.6 Node 9 — Schedule Planner (`backend/app/agent/nodes/schedule_planner.py`)
- Integrated into LangGraph agent between Node 7 (`result_verifier`) and Node 8 (`response_composer`).
- Bypasses non-scheduling modes (`QUERY_ONLY`, `CLARIFICATION_REQUIRED`, `OUT_OF_SCOPE`).
- For `SCHEDULE_ONLY` and `QUERY_AND_SCHEDULE`:
  - Parses recurrence and validates IANA timezone.
  - Computes next 3 execution run times.
  - Caps dry-run sample results to 10 records (`PHASE7_DRY_RUN_RESULT_LIMIT`).
  - Generates immutable `SchedulePreview` awaiting explicit user approval.
  - Ensures `schedule_approved` remains `False`.

### 2.7 Response Composer & Frontend Integration (`response_composer.py` & React UI)
- Formats markdown template `_SCHEDULE_PREVIEW_TEMPLATE` detailing report name, recurrence, timezone, next 3 run times, pipeline JSON, dry run sample, preview ID, and approval instructions.
- Returns structured `schedule_preview` in `ChatResponse`.
- **React Frontend**:
  - `SchedulePreviewCard.jsx`: Interactive card with "Approve Schedule" button calling `/api/v1/schedules/approve`.
  - `SchedulesDashboard.jsx`: Comprehensive management dashboard for listing active/paused jobs, pausing, resuming, cancelling, and inspecting durable execution run logs.
  - `Sidebar.jsx`: Integrated "Scheduled Reports" navigation button.

---

## 3. Verification & Compliance Matrix

| Requirement | Implementation Component | Verification Evidence |
| :--- | :--- | :--- |
| **Recurrence Parsing (Daily, Weekly, Monthly, Cron)** | `recurrence_parser.py` | 8 dedicated unit tests passing |
| **Strict IANA Timezone Validation** | `validate_iana_timezone()` | Tested valid (`Asia/Kolkata`, `UTC`) and invalid |
| **Deterministic Next Run Times (APScheduler)** | `calculate_next_run_times()` | Next 3 times strictly ascending & in future |
| **Node 9 Schedule Planner in LangGraph** | `schedule_planner_node()` | Integrated into graph; verified via e2e trace |
| **Bounded Dry-Run Preview** | `schedule_planner.py` | Results strictly truncated to $\le 10$ documents |
| **Explicit User Approval Gate** | `schedule_service.py` | Jobs remain unapproved until explicit POST |
| **Tamper-Resistant Pipeline Hashing** | SHA-256 `pipeline_hash` | Hash mismatch blocks approval |
| **Idempotent Approval** | `idempotency_key` check | Duplicate requests return existing job |
| **Metadata DB Persistence** | `agent_metadata_db` | `scheduled_jobs`, `job_runs`, `scheduler_leases` |
| **Pre-Execution Runtime Revalidation** | `SchedulerRunner` + Node 5 | Schema drift transitions to `FAILED_CONFIGURATION` |
| **Dynamic Date Token Resolution** | `resolve_relative_dates()` | `$$DAYS_AGO_30`, `$$TODAY_START` resolved dynamically |
| **Failure Auto-Pause ($\ge 3$ failures)** | `_handle_job_failure()` | Transitions to `AUTO_PAUSED` upon 3 consecutive errors |
| **FastAPI REST Endpoints** | `/api/v1/schedules/*` | 7 endpoints implemented with ownership checks |
| **Interactive Frontend UI** | `SchedulePreviewCard` + Dashboard | Vitest passed 8/8; Vite production build clean |
| **Immutability of Banking Data** | `fintech_agent_db` protection | Zero live access to original banking collections |

---

## 4. Conclusion

Phase 7 is fully implemented, rigorously tested, and independently verified. All 304 backend tests and 8 frontend tests pass with zero errors. The application build compiles cleanly into production bundles. The background scheduling engine is fully decoupled from the live banking database and remains fail-closed under security gating.
