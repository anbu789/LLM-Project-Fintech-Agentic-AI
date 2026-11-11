# FINTECH AGENT — SCHEDULED QUERIES AND RECURRENCE AUTOMATION EVIDENCE

**Document Classification:** Scheduling Engine, Concurrency Coordination & Lifecycle Management  
**Implementation Framework:** APScheduler (v3.11.3), `zoneinfo` (Python 3.9+ standard library), `tzlocal` (v5.4.5)  
**Source Code References:**
- Node 9 Planner: [`backend/app/agent/nodes/schedule_planner.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/nodes/schedule_planner.py)
- Recurrence Parser & Triggers: [`backend/app/services/recurrence_parser.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/services/recurrence_parser.py)
- Schedule Service & Previews: [`backend/app/services/schedule_service.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/services/schedule_service.py)
- Asynchronous Runner & Leases: [`backend/app/services/scheduler_runner.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/services/scheduler_runner.py)
- REST Endpoints: [`backend/app/api/routes/schedules.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/api/routes/schedules.py)
- Pydantic Contracts: [`backend/app/schemas/schedule.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/schemas/schedule.py)

---

## 1. Natural Language Recurrence Parsing Engine

The recurrence parser (`backend/app/services/recurrence_parser.py`) translates unstructured human timing constraints into strict cron specifications:

### 1.1 Supported Recurrence Grammars
1. **Daily Schedules:**
   - Expressions: *"daily at 9:00 AM"*, *"every day at 18:30"*, *"every morning at 8:00 AM"*
   - Mapping: `frequency = "daily"`, `hour = 9`, `minute = 0`, `cron = "0 9 * * *"`
2. **Weekly Schedules:**
   - Expressions: *"every Monday at 9:00 AM"*, *"weekly on Friday at 5:00 PM"*
   - Mapping: `frequency = "weekly"`, `day_of_week = "mon"`, `hour = 9`, `minute = 0`, `cron = "0 9 * * 1"`
3. **Monthly Schedules:**
   - Expressions: *"1st of every month at 10:00 AM"*, *"monthly on the 15th at noon"*
   - Mapping: `frequency = "monthly"`, `day_of_month = 1`, `hour = 10`, `minute = 0`, `cron = "0 10 1 * *"`
4. **Custom 5-Field Cron:**
   - Expressions: `"0 0 * * 1-5"` (weekdays at midnight)
   - Validated against standard 5-part cron syntax with field boundary checking (0-59, 0-23, 1-31, 1-12, 0-6).

### 1.2 IANA Timezone Validation
- Timezone strings are validated using Python's native `zoneinfo.ZoneInfo`:
  ```python
  def validate_iana_timezone(tz_name: str) -> str:
      try:
          ZoneInfo(tz_name)
          return tz_name
      except ZoneInfoNotFoundError:
          raise ValueError(f"Invalid IANA timezone '{tz_name}'. Example valid timezones: 'Asia/Kolkata', 'UTC', 'America/New_York'.")
  ```
- Default fallback timezone: `Asia/Kolkata` (`settings.SCHEDULER_TIMEZONE`).

### 1.3 Next Run Time Calculation
Next execution timestamps are computed directly via APScheduler's `CronTrigger`:
```python
def calculate_next_run_times(spec: ScheduleSpec, count: int = 3) -> List[str]:
    trigger = CronTrigger.from_crontab(spec.cron_expression, timezone=ZoneInfo(spec.timezone))
    now = datetime.now(ZoneInfo(spec.timezone))
    run_times = []
    current = now
    for _ in range(count):
        nxt = trigger.get_next_fire_time(None, current)
        if not nxt: break
        run_times.append(nxt.isoformat())
        current = nxt
    return run_times
```

---

## 2. Human-in-the-Loop Approval Workflow

In banking compliance, autonomous agent execution must never register recurring background jobs without explicit human verification:

```
User Prompt: "Send me active accounts every Monday at 9:00 AM"
                         │
                         ▼
           [LangGraph Workflow Execution]
                         │
                         ▼
     [Node 9: SchedulePlanner Generates Preview]
     - Validates recurrence & IANA timezone
     - Computes next 3 execution times
     - Bounded dry-run preview (top 10 rows)
     - Stores immutable preview in agent_metadata_db.schedule_previews
     - Sets schedule_approved = False
                         │
                         ▼
     [ResponseComposer Renders SchedulePreviewCard]
     - Displays Cron, Timezone, 3 Run Times, Data Preview
     - Renders "Approve Schedule" Action Button
                         │
                         ▼
         User Clicks "Approve Schedule"
                         │
                         ▼
[POST /api/v1/schedules/approve]
     - Authenticates Caller Bearer Token (HMAC-SHA256)
     - Verifies token principal matches preview owner_id
     - Verifies preview has not expired (TTL: 24 hours)
     - Validates idempotency key (prevents double activation)
     - Registers active job in agent_metadata_db.scheduled_jobs
                         │
                         ▼
[Job Status: ACTIVE -> Managed by SchedulerRunner]
```

---

## 3. Distributed Lease and Concurrency Control

To guarantee zero duplicate executions when multiple application replicas or processes run, `backend/app/services/scheduler_runner.py` uses an atomic database lease:

### 3.1 Distributed Lease Specification (`scheduler_leases`)
- **Collection:** `agent_metadata_db.scheduler_leases`
- **Lease Duration:** 30 seconds (`settings.SCHEDULER_LEASE_SECONDS`).
- **Heartbeat:** Active runner refreshes lease every 10 seconds.
- **Atomic Acquisition:** Implemented via `find_one_and_update` with conditional timestamp check (`lease_expires_at < now`).
- **Fencing Token:** Monotonically increasing sequence number prevents stale master process writes after network partitions.

### 3.2 Dynamic Relative Date Resolution
Banking reports frequently require dynamic temporal windows (e.g. *"transactions in the last 30 days"*). Storing hardcoded timestamps would result in stale data during future recurring runs.
The scheduler runner introduces dynamic MQL tokens:
- `$$DAYS_AGO_30`: Evaluated at execution runtime to `datetime.now(timezone.utc) - timedelta(days=30)`.
- `$$START_OF_MONTH`: Evaluated to the 1st day of the current month at 00:00:00 UTC.
- Evaluated cleanly prior to preflight MQL policy validation.

### 3.3 Security Invariants During Background Execution
1. **Pre-Execution AST Recheck:** Before firing, the runner passes the stored pipeline through `MQLPolicyValidator`. If schema drift has made a field invalid, the job immediately enters `FAILED_CONFIGURATION` without executing.
2. **Pipeline Integrity SHA-256 Check:** The runner computes the SHA-256 hash of the pipeline and verifies it matches `pipeline_hash` signed at approval time.
3. **Consecutive Failure Circuit Breaker:** If a recurring job experiences 3 consecutive failures (`consecutive_failures >= 3`), the runner automatically transitions the job to `PAUSED` and logs an incident event.

---

## 4. Operational Status: Tested vs. Gated

| Capability | Automated Test Module | Verification Result | Live Execution Gate Status |
| :--- | :--- | :---: | :---: |
| **Recurrence Parsing (Daily/Weekly/Monthly)** | `test_phase7_scheduling.py` | **PASSED** (100%) | Functional in unit/mock runs |
| **DST Spring Forward / Fall Back Transitions** | `test_final_audit_hardening.py` | **PASSED** (100%) | Functional in unit runs |
| **Leap Year (Feb 29) Recurrence** | `test_final_audit_hardening.py` | **PASSED** (100%) | Functional in unit runs |
| **Month-End (31st to 30th/28th) Coalescing** | `test_final_audit_hardening.py` | **PASSED** (100%) | Functional in unit runs |
| **Distributed Lease Acquisition & Collision** | `test_final_audit_hardening.py` | **PASSED** (100%) | Functional with metadata DB |
| **Cryptographic Identity Verification** | `test_final_audit_hardening.py` | **PASSED** (100%) | Fully active in API routes |
| **Dynamic Date Token Resolution** | `test_phase7_scheduling.py` | **PASSED** (100%) | Functional in test harness |
| **Live Background Execution Loop** | — | — | **BLOCKED BY CONFIGURATION** (`PHASE7_SCHEDULER_ENABLED=False`) |
