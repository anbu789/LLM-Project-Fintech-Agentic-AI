# FINTECH AGENT — TECHNICAL IMPLEMENTATION AND RUNTIME ENVIRONMENT EVIDENCE

**Document Classification:** Software Engineering, Dependency Pinning & Deployment Environment Audit  
**Configuration Sources:**
- Python Specification: [`.python-version`](file:///c:/Users/guru2/Downloads/llm%20prj/.python-version), [`backend/requirements.txt`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/requirements.txt)
- Node.js Specification: [`.nvmrc`](file:///c:/Users/guru2/Downloads/llm%20prj/.nvmrc), [`frontend/package.json`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/package.json)
- Environment Defaults: [`.env.example`](file:///c:/Users/guru2/Downloads/llm%20prj/.env.example)
- Production Launcher: [`start_project.bat`](file:///c:/Users/guru2/Downloads/llm%20prj/start_project.bat), [`scripts/start_fintech_agent.ps1`](file:///c:/Users/guru2/Downloads/llm%20prj/scripts/start_fintech_agent.ps1)

---

## 1. Verified Software Dependency Manifest

The following tables document the exact software versions installed and verified in the active development runtime:

### 1.1 Backend Dependency Manifest (Python 3.12 Runtime)
*Verified via `.venv_clean/Scripts/python.exe -m pip list`*

| Package Category | Package Name | Pinned Version in Runtime | Manifest Constraint (`requirements.txt`) | Role in Architecture |
| :--- | :--- | :---: | :--- | :--- |
| **Agent Orchestration** | `langgraph` | **1.2.20** | Unpinned transitive | Cyclic StateGraph orchestration engine |
| | `langgraph-checkpoint` | **4.3.1** | Unpinned transitive | State checkpointing and memory management |
| | `langgraph-sdk` | **0.4.14** | Unpinned transitive | Graph compilation and serialization |
| | `langchain-core` | **1.7.7** | Unpinned transitive | Core prompt and message contracts |
| | `langsmith` | **0.14.17** | Unpinned transitive | Observability tracing primitives |
| **API & Server** | `fastapi` | **0.162.2** | `>=0.110.0,<1.0.0` | Asynchronous REST API framework |
| | `uvicorn` | **0.54.0** | `>=0.28.0,<1.0.0` | ASGI production application server |
| | `starlette` | **1.10.0** | Transitive | Underlying ASGI routing and middleware |
| **Database & Drivers** | `pymongo` | **4.19.0** | `>=4.6.0,<5.0.0` | Official MongoDB Python driver |
| | `chromadb` | **1.5.9** | `>=0.5.0` | In-process persistent vector database |
| **Data Validation** | `pydantic` | **2.14.3** | `>=2.7.0,<3.0.0` | Data modeling and schema validation |
| | `pydantic-settings` | **2.16.2** | `>=2.2.0,<3.0.0` | Environment settings management |
| **Task Scheduling** | `APScheduler` | **3.11.3** | `>=3.10.4,<4.0.0` | Single-process recurring job scheduler |
| | `tzlocal` | **5.4.5** | Transitive | Local system timezone discovery |
| **HTTP & Networking** | `httpx` | **0.28.1** | `>=0.27.0,<1.0.0` | Async HTTP client for LLM provider adapters |
| **Testing & CI** | `pytest` | **8.4.2** | `>=8.0.0,<9.0.0` | Python test runner framework |
| | `pytest-asyncio` | **1.4.1.post1**| `>=0.23.0` | Asynchronous test execution plugin |
| **Synthetic Data** | `Faker` | **40.52.0** | `>=24.0.0` | Indian locale (`en_IN`) data synthesis |

### 1.2 Frontend Dependency Manifest (Node.js Runtime)
*Verified via `frontend/package.json` and `npm list`*

| Package Category | Package Name | Installed Version | Role in Architecture |
| :--- | :--- | :---: | :--- |
| **Core Framework** | `react` | **18.3.1** | Component view layer |
| | `react-dom` | **18.3.1** | DOM renderer |
| **Build & Bundler** | `vite` | **5.3.1** (5.4.21 at build) | Development server & Rollup production bundler |
| **Styling & Icons** | `tailwindcss` | **3.4.4** | Utility-first responsive CSS styling |
| | `lucide-react` | **0.400.0** | Clean, accessible vector UI icons |
| **State & Network** | `zustand` | **4.5.2** | Centralized client state store (`useChatStore.js`) |
| | `axios` | **1.7.0** | Promise-based HTTP client with 40s timeout |
| **Content Rendering**| `react-markdown` | **10.1.0** | Safe AST-based Markdown renderer |
| | `remark-gfm` | **4.0.1** | GitHub Flavored Markdown plugin (tables, task lists) |
| **Testing** | `vitest` | **4.1.12** | Fast Vite-native unit test runner |
| | `@testing-library/react` | **16.3.3** | React component interaction testing harness |

---

## 2. Hardware and Host System Environment

Hardware profile captured directly from host WMI / CIM instrumentation:

| Hardware / OS Parameter | Verified Host Specification |
| :--- | :--- |
| **Operating System** | **Microsoft Windows 11 Home / Pro (win32, x64)** |
| **Processor (CPU)** | **13th Gen Intel(R) Core(TM) i5-13420H** |
| **CPU Architecture** | 8 Physical Cores (4 Performance + 4 Efficient), 12 Logical Processors |
| **Base Clock / Turbo** | 2.10 GHz base, up to 4.60 GHz turbo |
| **Installed RAM** | **16.0 GB DDR5 RAM** |
| **Graphics (GPU)** | Intel(R) UHD Graphics (Integrated, Host-Managed) |
| **Python Binary Path** | `c:\Users\guru2\Downloads\llm prj\.venv_clean\Scripts\python.exe` (v3.12.3) |
| **Node.js Binary Path** | `C:\Program Files\nodejs\node.exe` (v25.6.0) |
| **Local MongoDB Engine** | MongoDB Community Server **v8.0.6** (Listening on `127.0.0.1:27017`) |

---

## 3. Launch Procedures and Operational Runbook

The application is configured to run on Windows systems via automated batch and PowerShell scripts:

### 3.1 Network Port Configuration
To resolve potential local port conflicts with other development services, FinTech Agent is pinned to:
- **Backend API Server:** Port **`8001`** (`http://127.0.0.1:8001`)
- **Frontend Vite Server:** Port **`5173`** (`http://localhost:5173`)
- **Vite Reverse Proxy:** Automatically forwards `/api/*` requests from `5173` to `http://localhost:8001/api/*`

### 3.2 Launch Procedure
1. **Automated Launch:** Run `start_project.bat` or `scripts/start_fintech_agent.ps1`.
   The script:
   - Verifies MongoDB connection on port 27017.
   - Activates Python virtual environment `.venv_clean`.
   - Starts FastAPI with Uvicorn: `uvicorn backend.app.main:app --host 127.0.0.1 --port 8001`.
   - Polls `GET http://127.0.0.1:8001/api/v1/health` until HTTP 200 is confirmed.
   - Starts Vite development server: `npm run dev` in `frontend/`.
   - Opens default browser to `http://localhost:5173`.
2. **Termination:** Run `scripts/stop_fintech_agent.ps1` to cleanly terminate background Uvicorn and Vite processes.

---

## 4. Required Environment Variables Configuration

The application reads configuration through `pydantic-settings` from `.env`. All sensitive credentials are sanitized below:

| Environment Variable | Configured Value (Sanitized) | Purpose & Description |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Runtime environment mode |
| `PORT` | `8001` | Backend HTTP port |
| `MONGO_URI` | `mongodb://localhost:27017/` | Connection string for MongoDB server |
| `MONGO_BANKING_DB` | `fintech_agent_db` | Read-only banking database name (19,120 docs) |
| `MONGO_METADATA_DB` | `agent_metadata_db` | Application metadata DB (sessions, schedules) |
| `LLM_PROVIDER` | `gemini` | Primary LLM provider |
| `LLM_MODEL` | `gemini-3.8-flash` | Primary cloud model identifier |
| `LLM_API_KEY` | `<REDACTED_SET>` | Google AI Studio Gemini API key |
| `GROQ_API_KEY` | `<REDACTED_SET>` | Secondary fallback Groq Cloud API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq fallback model identifier |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible endpoint |
| `LOCAL_LLM_ENABLED` | `true` | Enable local Ollama fallback |
| `LOCAL_LLM_PROVIDER` | `ollama` | Local provider name |
| `LOCAL_LLM_MODEL` | `hf.co/mradermacher/K2-Horizon-3.7B-i1-GGUF:Q3_K_M` | Local quantized GGUF model tag |
| `LOCAL_LLM_BASE_URL` | `http://127.0.0.1:11434` | Ollama loopback server endpoint |
| `LLM_FALLBACK_ENABLED`| `true` | Enable automated multi-provider failover chain |
| `LLM_FALLBACK_ORDER` | `groq,ollama` | Secondary provider priority order |
| `PHASE6_LIVE_EXECUTION_ENABLED` | `false` | Fail-closed gate: blocks live execution on banking DB |
| `PHASE7_SCHEDULER_ENABLED` | `false` | Fail-closed gate: blocks autonomous background loop |
| `QUERY_TIMEOUT_MS` | `15000` | Server-side MongoDB aggregation timeout (15s) |
| `RESULT_DOC_LIMIT` | `1000` | Absolute ceiling on returned database records |
| `MAX_PIPELINE_STAGES` | `20` | AST limit on aggregation pipeline length |

---

## 5. Git Remote and Repository Baseline

Inspection of the local repository configuration (`git remote -v`) reveals:
- **Configured Remotes:** `None` (Local standalone git repository).
- **Current Branch:** `master`
- **Latest Commit Hash:** `ee353efb32ecb1ad3c49adaae58722654f83edae`
- **Latest Commit Message:** `fix(port): resolve port conflict by configuring FinTech Agent to port 8001, add health endpoint, and verify backend readiness in launcher`
- **Working Tree State:** Contains untracked and modified files representing the multi-provider fallback engine (`MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md`), execution monitor (`backend/app/core/execution_monitor.py`), and enhanced Vitest test suites.
