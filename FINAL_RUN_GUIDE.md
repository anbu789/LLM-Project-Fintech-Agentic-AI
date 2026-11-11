# FINTECH AGENT — FINAL OPERATIONAL RUN GUIDE
**Course:** INT450 — Large Language Models and Agentic AI  
**Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Operating System:** Windows 10 / Windows 11 (PowerShell & Command Prompt)  
**Author:** Principal Software Architect & Application Deployment Specialist  

---

## 1. Prerequisites & Environment Setup

Ensure the following runtimes are installed on your Windows system:
1. **Python 3.12+ (64-bit):**
   - Virtual environment configured at: `.venv_clean\`
   - Python executable: `.\.venv_clean\Scripts\python.exe`
2. **Node.js 18+ and npm 9+:**
   - Command: `npm.cmd`
3. **MongoDB Community Server 7.0+:**
   - Listening locally at: `mongodb://localhost:27017`
   - Banking database: `fintech_agent_db` (19,120 documents across 12 collections)
   - Metadata database: `agent_metadata_db`
4. **Google Gemini API Key:**
   - Configured in `.env` as `GEMINI_API_KEY=...`

---

## 2. One-Click Automated Windows Launchers

The project includes three dedicated Windows batch scripts located in the root directory:

### 2.1 Start Complete Application: `start_project.bat`
Launches the FastAPI backend and React frontend concurrently in two dedicated Windows Command Prompt windows:
```cmd
start_project.bat
```
**What this script does:**
1. Verifies the existence of `.\.venv_clean\Scripts\python.exe`.
2. Verifies `npm` in the Windows system PATH.
3. Launches the FastAPI backend on port 8001 (`http://127.0.0.1:8001`).
4. Launches the React Vite frontend dev server on port 5173 (`http://localhost:5173`).
5. Verifies backend health on `http://127.0.0.1:8001/health` before reporting startup success.
6. Displays interactive service URLs and remains open for monitoring.

### 2.2 Run Full Regression Test Suite: `run_tests.bat`
Executes the full end-to-end verification pipeline:
```cmd
run_tests.bat
```
**What this script does:**
1. Runs all 323 backend pytest tests (`pytest backend/tests -v`).
2. Runs all 8 frontend vitest tests (`npm.cmd test -- --run`).
3. Runs the frontend production build (`npm.cmd run build`).
4. Reports pass/fail status with proper exit codes.

### 2.3 Start Background Scheduler Service: `start_scheduler.bat`
Launches the single APScheduler reconciliation authority:
```cmd
start_scheduler.bat
```
**What this script does:**
1. Performs a preflight check on `PHASE7_SCHEDULER_ENABLED`.
2. **Fail-Closed Gate Notice:** If `PHASE7_SCHEDULER_ENABLED=False`, safely explains that recurring queries are gated by default to protect live databases and exits cleanly.
3. If enabled, acquires the distributed database lease and begins reconciling active jobs.

---

## 3. Manual CLI Launch Instructions

If you prefer to start services individually from PowerShell or Command Prompt:

### 3.1 Launch FastAPI Backend API
Open a PowerShell terminal in the project root:
```powershell
.\.venv_clean\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload
```
- API Base: `http://127.0.0.1:8001`
- Swagger Interactive Documentation: `http://127.0.0.1:8001/docs`
- ReDoc Documentation: `http://127.0.0.1:8001/redoc`
- Health Check: `http://127.0.0.1:8001/health` or `http://127.0.0.1:8001/api/v1/health`

### 3.2 Launch React Frontend Web UI
Open a second terminal in the `frontend/` directory:
```powershell
cd frontend
npm.cmd run dev
```
- Frontend UI: `http://localhost:5173`

---

## 4. Cryptographic Authentication & Tenant Isolation

All schedule management operations require a cryptographically signed HMAC-SHA256 Bearer token.

### 4.1 Step 1: Obtain a Token
Send a `POST` request to `/api/v1/auth/token`:
```bash
curl -X POST "http://127.0.0.1:8001/api/v1/auth/token" \
     -H "Content-Type: application/json" \
     -d "{\"user_id\": \"alice\", \"role\": \"analyst\"}"
```
**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSIsInJvbGUiOiJhbGFseXN0IiwiZXhwIjoxNzk0NDA5MjAwfQ.xxxxxx",
  "token_type": "bearer",
  "user_id": "alice",
  "role": "analyst",
  "expires_in": 3600
}
```

### 4.2 Step 2: Use Token in Requests
Pass the token in the `Authorization` header:
```bash
curl -X GET "http://127.0.0.1:8001/api/v1/schedules" \
     -H "Authorization: Bearer <access_token>"
```

### 4.3 Step 3: Identity Spoofing Protection (Verified)
If a user attempts to spoof another user's identity:
```bash
curl -X GET "http://127.0.0.1:8001/api/v1/schedules" \
     -H "Authorization: Bearer <alice_token>" \
     -H "X-User-ID: bob"
```
**Response:** `HTTP 403 Forbidden`
```json
{
  "detail": "Identity spoofing violation: Asserted user 'bob' does not match authenticated token principal 'alice'."
}
```

---

## 5. End-to-End Query & Scheduling Workflow

### 5.1 Ad-Hoc Banking Query Example
Ask natural language questions in the web interface or via `POST /api/v1/chat`:
- *"Show total balance of active accounts by account type"*
- *"List top 5 transactions with amount greater than 50000"*
- *"Find all defaulted loans and sum their outstanding principal"*

The agent executes the 8-node LangGraph:
1. Validates prompt safety (Node 1).
2. Classifies intent as `BANKING_QUERY` (Node 2).
3. Retrieves relevant schema fields and relationships (Node 3).
4. Synthesizes a canonical MQL aggregation pipeline with Gemini (Node 4).
5. Deterministically validates the pipeline against AST policies (Node 5).
6. Executes query or validates execution readiness (Node 6).
7. Verifies and formats the output data (Node 7).
8. Composes structured Markdown tables and metrics (Node 8).

### 5.2 Scheduled Report Workflow Example
Ask to schedule a recurring report:
- *"Schedule daily report of high-value transactions at 9am"*

The agent routes to Node 9 (`schedule_planner`), parses recurrence, and generates an immutable schedule preview:
1. Preview displays upcoming run times (Next 3 runs in IANA timezone).
2. Previews require explicit approval before activation (`approve <preview_id>`).
3. Once approved, the job is persisted to `agent_metadata_db.scheduled_jobs` with status `ACTIVE`.

---

## 6. Fail-Closed Security Configuration

By default, all live database execution and autonomous background jobs are gated:
```ini
# Safe Defaults in .env
PHASE6_LIVE_EXECUTION_ENABLED=False
PHASE7_SCHEDULER_ENABLED=False
PHASE7_LIVE_REGISTRATION_ENABLED=False
MONGO_AUTH_ENABLED=False
```

### Demonstration vs Live Execution Distinction:
- **Demonstration Mode (Default):** Natural language queries and schedules are synthesized, fully validated, and previewed. Live execution is safely gated with `GATE_BLOCKED`.
- **Live Mode:** Requires native MongoDB authentication enabled (`security.authorization: enabled` in `mongod.cfg`), user `fintech_analyst_user` provisioned, and canary test verified before setting `PHASE6_LIVE_EXECUTION_ENABLED=True`.

---

## 7. Troubleshooting & Common Issues

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| `Address already in use: 8001` | Another process is occupying port 8001 | Run `netstat -ano \| findstr :8001` in PowerShell and terminate the conflicting PID with `taskkill /PID <pid> /F`. |
| `Address already in use: 5173` | Vite server already running | Vite will automatically offer port 5174, or terminate the existing Node process. |
| `HTTP 401 Unauthorized` | Missing or expired Bearer token | Call `POST /api/v1/auth/token` to acquire a fresh 1-hour access token. |
| `HTTP 403 Forbidden` | Identity mismatch or tenant access denial | Ensure `X-User-ID` matches the token claim `sub`, or omit `X-User-ID` header. |
| `GATE_BLOCKED` | Live execution gate is closed | Normal and expected in demonstration mode. |
