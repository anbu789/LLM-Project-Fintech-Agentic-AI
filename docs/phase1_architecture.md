# Phase 1 — Schema Design & System Architecture

> **Project:** FinQuery AI — Natural Language MongoDB Intelligence Agent  
> **Domain:** Fintech / Banking Analytics  
> **Stack:** LangGraph · FastAPI · React · MongoDB Atlas · Redis · Celery · APScheduler  
> **Document Version:** 1.0  
> **Last Updated:** 2026-09-03  

---

> [!IMPORTANT]
> This document is the **single source of truth** for Phase 1 of the FinQuery AI capstone project. All team members must review this document before writing any code. Changes to the schema or architecture must be reflected here first.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [MongoDB Schema — Entity Relationship Diagram](#2-mongodb-schema--entity-relationship-diagram)
3. [Collection Definitions](#3-collection-definitions)
4. [LangGraph Agent Pipeline](#4-langgraph-agent-pipeline)
5. [System Architecture](#5-system-architecture)
6. [Full Project Folder Structure](#6-full-project-folder-structure)
7. [Technology Breakdown](#7-technology-breakdown)
8. [Data Flow Narrative](#8-data-flow-narrative)
9. [Key Design Decisions](#9-key-design-decisions)

---

## 1. Project Overview

**FinQuery AI** is an end-to-end intelligent query agent for a banking analytics platform. A user types a plain-English question such as:

> *"Show me the top 10 customers by outstanding loan amount in Mumbai who have an active investment portfolio"*

The system then:
1. Understands the question using an LLM (Gemini / GPT-4o)
2. Retrieves the MongoDB schema context dynamically
3. Generates a MongoDB Aggregation Pipeline
4. Validates the pipeline syntax and semantics before execution
5. Executes the query against MongoDB Atlas
6. Validates the result for anomalies and correctness
7. Self-corrects if validation fails (up to 3 retry attempts)
8. Formats and returns a structured, human-readable response
9. Optionally schedules the query as a recurring Celery job (e.g., *"run this every Monday at 9 AM"*)

> [!NOTE]
> The agent is built as a **stateful graph** using LangGraph, where each processing step is a node with typed inputs and outputs. This allows precise control over retries, branching, and tracing.

---

## 2. MongoDB Schema — Entity Relationship Diagram

The system uses **12 MongoDB collections**. Although MongoDB is document-oriented, the logical relationships between collections are maintained via reference fields (similar to foreign keys in RDBMS), which the LLM agent understands through schema metadata.

```mermaid
erDiagram
    customers {
        string customer_id PK
        string name
        string email
        string phone
        date dob
        string gender
        string kyc_status
        float risk_rating
        int credit_score
        string country
        string city
        string occupation
        float annual_income
        int account_count
        bool is_active
        datetime created_at
        datetime updated_at
        string referral_code
        string preferred_language
        string segment
    }

    branches {
        string branch_id PK
        string branch_name
        string branch_code
        string city
        string state
        string country
        string region
        string address
        string phone
        string manager_id FK
        datetime opened_at
        bool is_active
        int total_accounts
        int total_loans
        float total_deposits
        int atm_count
        int staff_count
        float monthly_revenue
        string branch_type
    }

    employees {
        string employee_id PK
        string name
        string email
        string department
        string role
        string branch_id FK
        string manager_id FK
        date hire_date
        bool is_active
        string phone
        string region
        float performance_rating
        int client_count
        string specialization
        string salary_band
        array certifications
        date last_review_date
        int leave_balance
        string shift
    }

    accounts {
        string account_id PK
        string customer_id FK
        string account_type
        float balance
        string currency
        string branch_id FK
        string status
        datetime opened_at
        datetime closed_at
        float interest_rate
        float overdraft_limit
        bool is_joint
        string joint_holder_id
        datetime last_transaction_at
        float monthly_avg_balance
        string tier
        string manager_id FK
        string product_code
        string iban
        string swift_code
    }

    transactions {
        string transaction_id PK
        string account_id FK
        string customer_id FK
        string type
        float amount
        string currency
        string channel
        string merchant_category
        string merchant_name
        string status
        datetime initiated_at
        datetime settled_at
        string reference_no
        string description
        float balance_after
        string country
        string city
        bool is_flagged
        string flag_reason
        float processing_fee
        float exchange_rate
        string batch_id
    }

    loans {
        string loan_id PK
        string customer_id FK
        string account_id FK
        string loan_type
        float principal_amount
        float outstanding_amount
        float interest_rate
        int tenure_months
        float emi_amount
        datetime disbursed_at
        date due_date
        string status
        string collateral_type
        float collateral_value
        int credit_score_at_disbursal
        string manager_id FK
        string branch_id FK
        int late_payment_count
        datetime last_payment_at
        float penalty_amount
    }

    investments {
        string investment_id PK
        string customer_id FK
        string account_id FK
        string asset_class
        string symbol
        float quantity
        float avg_buy_price
        float current_price
        float market_value
        float unrealized_pnl
        float realized_pnl
        datetime invested_at
        datetime last_updated_at
        string broker_code
        string sector
        string country
        string currency
        bool is_locked
        date maturity_date
        string risk_category
    }

    market_data {
        string record_id PK
        string symbol
        date date
        float open
        float high
        float low
        float close
        float volume
        float adjusted_close
        float market_cap
        float pe_ratio
        float dividend_yield
        float beta
        string sector
        string exchange
        string currency
        string data_source
        bool is_holiday
        float week_52_high
        float week_52_low
    }

    risk_events {
        string event_id PK
        string customer_id FK
        string account_id FK
        string transaction_id FK
        string event_type
        string severity
        datetime detected_at
        datetime resolved_at
        string status
        string assigned_to FK
        string rule_triggered
        string description
        string action_taken
        string false_positive_reason
        string model_version
        float confidence_score
    }

    audit_logs {
        string log_id PK
        string user_id
        string user_type
        string action
        string collection_name
        string document_id
        datetime timestamp
        string ip_address
        string device_info
        object old_values
        object new_values
        string status
        string session_id
        string request_id
        int duration_ms
    }

    scheduled_jobs {
        string job_id PK
        string created_by
        string job_name
        string description
        string query_collection
        array query_pipeline
        string cron_expression
        datetime next_run_at
        datetime last_run_at
        string status
        string output_format
        object output_config
        int run_count
        int success_count
        int failure_count
        datetime created_at
        string last_error
    }

    query_history {
        string history_id PK
        string user_id
        string natural_language_query
        array generated_pipeline
        string collection_used
        int execution_time_ms
        int result_row_count
        int correction_attempts
        string final_status
        datetime created_at
        object agent_trace
        int feedback_rating
        string error_message
    }

    customers ||--o{ accounts : "holds"
    customers ||--o{ transactions : "makes"
    customers ||--o{ loans : "borrows"
    customers ||--o{ investments : "owns"
    customers ||--o{ risk_events : "triggers"
    accounts ||--o{ transactions : "contains"
    accounts ||--o{ loans : "linked_to"
    accounts ||--o{ investments : "funds"
    accounts ||--o{ risk_events : "flagged_in"
    transactions ||--o{ risk_events : "generates"
    branches ||--o{ accounts : "hosts"
    branches ||--o{ loans : "originates"
    branches ||--o{ employees : "employs"
    employees ||--o{ employees : "manages"
    employees ||--o{ branches : "manages"
    employees ||--o{ accounts : "manages"
    employees ||--o{ loans : "approves"
    employees ||--o{ risk_events : "investigates"
    investments }o--|| market_data : "references"
```

> [!NOTE]
> MongoDB does not enforce foreign key constraints natively. All cross-collection references (FK fields) are **logical references** maintained by application logic. The LangGraph agent learns these relationships from the schema metadata stored in Redis cache.

---

## 3. Collection Definitions

A quick-reference table of all 12 collections, their primary purpose, estimated document volume, and key indexed fields.

| # | Collection | Purpose | Est. Documents | Key Indexes |
|---|-----------|---------|---------------|-------------|
| 1 | `customers` | Core customer master record | 100,000 | `customer_id`, `email`, `kyc_status`, `segment` |
| 2 | `accounts` | Bank accounts per customer | 180,000 | `account_id`, `customer_id`, `branch_id`, `status` |
| 3 | `transactions` | All financial transactions | 5,000,000+ | `transaction_id`, `account_id`, `customer_id`, `initiated_at`, `is_flagged` |
| 4 | `loans` | Loan disbursals and repayments | 60,000 | `loan_id`, `customer_id`, `status`, `due_date` |
| 5 | `investments` | Customer investment portfolio | 120,000 | `investment_id`, `customer_id`, `symbol`, `asset_class` |
| 6 | `market_data` | Daily OHLCV and fundamentals | 2,000,000+ | `symbol`, `date`, `exchange` (compound) |
| 7 | `risk_events` | Fraud, AML, KYC breach flags | 40,000 | `event_id`, `customer_id`, `severity`, `status`, `detected_at` |
| 8 | `employees` | Bank staff and hierarchy | 5,000 | `employee_id`, `branch_id`, `department`, `role` |
| 9 | `branches` | Physical branch metadata | 500 | `branch_id`, `branch_code`, `city`, `country` |
| 10 | `audit_logs` | System-level audit trail | 10,000,000+ | `user_id`, `timestamp`, `action`, `collection_name` |
| 11 | `scheduled_jobs` | Celery/APScheduler job configs | 10,000 | `job_id`, `created_by`, `status`, `next_run_at` |
| 12 | `query_history` | Agent query + trace logs | 500,000+ | `history_id`, `user_id`, `created_at`, `final_status` |

### 3.1 Enum Values Summary

| Collection | Field | Allowed Values |
|-----------|-------|---------------|
| `customers` | `kyc_status` | `pending`, `verified`, `rejected`, `expired` |
| `customers` | `segment` | `retail`, `premium`, `corporate`, `wealth` |
| `accounts` | `account_type` | `savings`, `current`, `investment`, `loan` |
| `accounts` | `tier` | `silver`, `gold`, `platinum` |
| `transactions` | `type` | `debit`, `credit`, `transfer`, `fee` |
| `transactions` | `channel` | `mobile`, `atm`, `branch`, `online` |
| `transactions` | `status` | `completed`, `pending`, `failed`, `reversed` |
| `loans` | `loan_type` | `personal`, `home`, `auto`, `business` |
| `loans` | `status` | `active`, `closed`, `defaulted`, `npa` |
| `investments` | `asset_class` | `equity`, `bond`, `mutual_fund`, `etf` |
| `risk_events` | `event_type` | `fraud`, `aml`, `unusual_pattern`, `kyc_breach` |
| `risk_events` | `severity` | `low`, `medium`, `high`, `critical` |
| `risk_events` | `status` | `open`, `investigating`, `resolved`, `false_positive` |
| `branches` | `branch_type` | `urban`, `rural`, `semi-urban` |
| `audit_logs` | `user_type` | `customer`, `employee`, `agent`, `admin` |
| `scheduled_jobs` | `status` | `active`, `paused`, `deleted` |
| `scheduled_jobs` | `output_format` | `email`, `csv`, `webhook`, `in-app` |
| `query_history` | `final_status` | `success`, `failed` |

> [!TIP]
> When generating synthetic data with Faker, always constrain random values to these enum sets. The `generate_*.py` scripts in `data_generation/` should import a shared `ENUMS` constant dictionary to keep values consistent across all collections.

---

## 4. LangGraph Agent Pipeline

The core intelligence of the system is a **stateful directed graph** built with LangGraph. Each node is a Python function that reads from and writes to a shared `AgentState` TypedDict. Conditional edges implement the retry and self-correction logic.

```mermaid
flowchart TD
    START(["🟢 START\nUser NL Query Received"])

    SR["📋 schema_retriever\n─────────────────\nFetch relevant collection\nschemas from Redis cache.\nInject field names, types,\nenums, and relationships\ninto state context."]

    QG["🧠 query_generator\n─────────────────\nLLM generates MongoDB\naggregation pipeline JSON\nbased on NL query +\nschema context."]

    QV{"🔍 query_validator\n─────────────────\nValidate pipeline:\n• Syntax check\n• Stage order check\n• Field existence check\n• Type compatibility\nIs pipeline valid?"}

    QC["🔧 query_corrector\n─────────────────\nLLM receives:\n• Original query\n• Faulty pipeline\n• Validation error\nGenerates corrected\npipeline. retry_count++"]

    RETRY_CHECK{"⚠️ retry_count < 3?"}

    QE["⚙️ query_executor\n─────────────────\nExecute pipeline against\nMongoDB Atlas via PyMongo.\nCapture result docs,\nexecution time, row count."]

    EX_ERR{"❌ Execution\nError?"}

    RV{"✅ result_validator\n─────────────────\nValidate results:\n• Empty result check\n• Anomaly detection\n• Numeric range sanity\n• Cross-field consistency\nResult suspicious?"}

    RC["🩺 result_corrector\n─────────────────\nLLM re-examines query\nvs result. Suggests\nfilter or pipeline\nadjustment. Re-executes."]

    RF["📝 response_formatter\n─────────────────\nFormat result as:\n• Markdown table\n• Summary narrative\n• Chart-ready JSON\nAdd pipeline explanation\nfor transparency."]

    SCHED_CHECK{"🗓️ Schedule\nRequested?"}

    JS["⏰ job_scheduler_node\n─────────────────\nParse cron expression\nfrom NL. Register job\nin scheduled_jobs.\nTrigger Celery beat update."]

    FAIL(["🔴 FAIL\nReturn error message\n+ partial trace\nto user"])

    END(["🏁 END\nReturn structured\nresponse to FastAPI"])

    START --> SR
    SR --> QG
    QG --> QV

    QV -- "✅ Valid" --> QE
    QV -- "❌ Invalid" --> RETRY_CHECK

    RETRY_CHECK -- "Yes, retry" --> QC
    RETRY_CHECK -- "No, max retries hit" --> FAIL
    QC --> QV

    QE -- "✅ Success" --> RV
    QE -- "❌ Error" --> EX_ERR
    EX_ERR -- "retry_count < 3" --> QG
    EX_ERR -- "max retries" --> FAIL

    RV -- "✅ Looks good" --> RF
    RV -- "⚠️ Suspicious" --> RC
    RC --> RF

    RF --> SCHED_CHECK
    SCHED_CHECK -- "Yes" --> JS
    SCHED_CHECK -- "No" --> END
    JS --> END

    style START fill:#22c55e,color:#fff,stroke:#16a34a
    style END fill:#3b82f6,color:#fff,stroke:#1d4ed8
    style FAIL fill:#ef4444,color:#fff,stroke:#b91c1c
    style QV fill:#f59e0b,color:#fff,stroke:#d97706
    style RV fill:#f59e0b,color:#fff,stroke:#d97706
    style RETRY_CHECK fill:#f59e0b,color:#fff,stroke:#d97706
    style EX_ERR fill:#f59e0b,color:#fff,stroke:#d97706
    style SCHED_CHECK fill:#8b5cf6,color:#fff,stroke:#6d28d9
    style JS fill:#8b5cf6,color:#fff,stroke:#6d28d9
```

### 4.1 Agent State Definition

The `AgentState` is a `TypedDict` shared across all nodes. Every node reads what it needs and writes back its outputs:

```python
# backend/app/agent/state.py
from typing import TypedDict, Optional, List, Any
from datetime import datetime

class AgentState(TypedDict):
    # ── Input ─────────────────────────────────────────────
    user_id: str
    natural_language_query: str
    session_id: str

    # ── Schema Context ────────────────────────────────────
    schema_context: str          # JSON string of relevant collections
    collections_identified: List[str]

    # ── Query Generation ──────────────────────────────────
    generated_pipeline: Optional[List[dict]]
    target_collection: Optional[str]
    retry_count: int             # increments on each correction attempt

    # ── Validation ────────────────────────────────────────
    validation_status: str       # "valid" | "invalid" | "pending"
    validation_errors: List[str]

    # ── Execution ─────────────────────────────────────────
    raw_results: Optional[List[dict]]
    execution_time_ms: int
    result_row_count: int
    execution_error: Optional[str]

    # ── Result Validation ─────────────────────────────────
    result_valid: bool
    result_issues: List[str]

    # ── Response ──────────────────────────────────────────
    formatted_response: Optional[str]
    chart_data: Optional[dict]
    pipeline_explanation: Optional[str]

    # ── Scheduling ────────────────────────────────────────
    schedule_requested: bool
    cron_expression: Optional[str]
    job_id: Optional[str]

    # ── Tracing ───────────────────────────────────────────
    agent_trace: List[dict]      # step-by-step log for query_history
    final_status: str            # "success" | "failed"
    error_message: Optional[str]
```

### 4.2 Node Responsibilities

| Node | LLM Involved | MongoDB Touch | Key Output |
|------|-------------|--------------|-----------|
| `schema_retriever` | ❌ No | ✅ Read schema cache | `schema_context`, `collections_identified` |
| `query_generator` | ✅ Yes | ❌ No | `generated_pipeline`, `target_collection` |
| `query_validator` | ❌ No (rule-based) | ❌ No | `validation_status`, `validation_errors` |
| `query_corrector` | ✅ Yes | ❌ No | `generated_pipeline` (corrected), `retry_count++` |
| `query_executor` | ❌ No | ✅ Execute pipeline | `raw_results`, `execution_time_ms` |
| `result_validator` | ✅ Yes (light) | ❌ No | `result_valid`, `result_issues` |
| `result_corrector` | ✅ Yes | ✅ Re-execute | `raw_results` (corrected) |
| `response_formatter` | ✅ Yes | ❌ No | `formatted_response`, `chart_data` |
| `job_scheduler_node` | ✅ Yes (cron parse) | ✅ Write `scheduled_jobs` | `job_id` |

> [!IMPORTANT]
> The `retry_count` field in `AgentState` is the **global retry counter** shared across both `query_corrector` (syntax failures) and execution retry loops. It must be reset to `0` at the start of each new query session. Max retries = **3** for query correction, **2** for execution errors.

---

## 5. System Architecture

### 5.1 High-Level Architecture Diagram

```mermaid
graph TB
    subgraph CLIENT["🖥️  CLIENT LAYER"]
        UI["⚛️ React Frontend\n──────────────\nChat Interface\nQuery Display\nResult Table\nJobs Dashboard\nWebSocket client"]
    end

    subgraph API["🚀  API LAYER — FastAPI"]
        CHAT_EP["/api/chat\nPOST — stream NL query"]
        JOBS_EP["/api/jobs\nCRUD for scheduled jobs"]
        HIST_EP["/api/history\nQuery run history"]
        AUTH_EP["/api/auth\nJWT authentication"]
        WS["WebSocket /ws/session_id\nStreaming agent updates"]
    end

    subgraph AGENT["🧠  AGENT LAYER — LangGraph"]
        GRAPH["LangGraph StatefulGraph\n──────────────────────\nschema_retriever\nquery_generator\nquery_validator\nquery_corrector\nquery_executor\nresult_validator\nresult_corrector\nresponse_formatter\njob_scheduler_node"]
        LLM["☁️  LLM Provider\nGemini Pro / GPT-4o"]
        GRAPH <-->|"prompt / completion"| LLM
    end

    subgraph CACHE["⚡  CACHE LAYER — Redis"]
        R1["Schema Cache\nTTL: 1 hour"]
        R2["Session Store\nJWT + WebSocket state"]
        R3["Celery Broker\nTask queue messages"]
        R4["Celery Result Backend\nTask execution results"]
    end

    subgraph WORKER["⚙️  WORKER LAYER — Celery + APScheduler"]
        CELERY["Celery Worker\n──────────────\nExecute scheduled jobs\nRun aggregation pipelines"]
        BEAT["Celery Beat\n──────────────\nCron-based job triggers\nDynamic job registration"]
        DELIVERY["Delivery Module\n──────────────\nEmail / CSV / Webhook\nIn-app notifications"]
        CELERY --- BEAT
        CELERY --- DELIVERY
    end

    subgraph DB["🍃  DATA LAYER — MongoDB Atlas"]
        M1["Primary Collections\n──────────────\ncustomers · accounts\ntransactions · loans\ninvestments · market_data"]
        M2["Operational Collections\n──────────────\nrisk_events · employees\nbranches · audit_logs\nscheduled_jobs · query_history"]
    end

    UI <-->|"HTTPS REST + WebSocket"| API
    API --> AGENT
    AGENT -->|"read/write"| DB
    AGENT -->|"cache schema"| CACHE
    API <-->|"JWT sessions"| CACHE
    WORKER <-->|"broker / results"| CACHE
    WORKER <-->|"execute pipelines"| DB
    API <-->|"job management"| WORKER

    style CLIENT fill:#1e3a5f,color:#e2e8f0,stroke:#2563eb
    style API fill:#1a3a2a,color:#e2e8f0,stroke:#16a34a
    style AGENT fill:#3b1a5f,color:#e2e8f0,stroke:#7c3aed
    style CACHE fill:#5f3a1a,color:#e2e8f0,stroke:#d97706
    style WORKER fill:#1a3a3a,color:#e2e8f0,stroke:#0891b2
    style DB fill:#3a1a1a,color:#e2e8f0,stroke:#dc2626
```

### 5.2 Request Lifecycle (Sequence)

```mermaid
sequenceDiagram
    actor User
    participant React as ⚛️ React
    participant FastAPI as 🚀 FastAPI
    participant Redis as ⚡ Redis
    participant LangGraph as 🧠 LangGraph
    participant MongoDB as 🍃 MongoDB Atlas
    participant LLM as ☁️ LLM API

    User->>React: Types NL query
    React->>FastAPI: POST /api/chat
    FastAPI->>Redis: Check session / rate limit
    Redis-->>FastAPI: Session valid
    FastAPI->>LangGraph: invoke_agent(state)

    Note over LangGraph: Node: schema_retriever
    LangGraph->>Redis: GET schema collections
    Redis-->>LangGraph: Cached schema JSON

    Note over LangGraph: Node: query_generator
    LangGraph->>LLM: Prompt NL + schema to pipeline
    LLM-->>LangGraph: MongoDB Aggregation JSON

    Note over LangGraph: Node: query_validator
    LangGraph->>LangGraph: Validate pipeline rule-based

    Note over LangGraph: Node: query_executor
    LangGraph->>MongoDB: db.collection.aggregate
    MongoDB-->>LangGraph: Result documents

    Note over LangGraph: Node: result_validator
    LangGraph->>LLM: Validate result sanity
    LLM-->>LangGraph: Validation verdict

    Note over LangGraph: Node: response_formatter
    LangGraph->>LLM: Format as Markdown + chart JSON
    LLM-->>LangGraph: Formatted response

    LangGraph->>MongoDB: Insert query_history doc
    LangGraph-->>FastAPI: AgentState final
    FastAPI-->>React: JSON response streamed via WS
    React-->>User: Display result table + pipeline
```

> [!TIP]
> The FastAPI endpoint streams intermediate agent updates to the React frontend via **WebSocket**. This means the user sees "Retrieving schema…", "Generating query…", "Executing…" status messages in real time — providing excellent UX for long-running queries against large collections.

---

## 6. Full Project Folder Structure

> [!NOTE]
> Every file below has a one-line description of its purpose. Files marked `[Phase 2]` are scaffolded now but implemented later.

```
llm-prj/
│
├── backend/                          # Python backend (FastAPI + LangGraph + Celery)
│   │
│   ├── app/
│   │   │
│   │   ├── main.py                   # FastAPI app factory: registers routers, CORS, lifespan events
│   │   ├── config.py                 # Pydantic BaseSettings: loads all env vars from .env
│   │   │
│   │   ├── agent/                    # LangGraph agent package
│   │   │   │
│   │   │   ├── graph.py              # Builds and compiles the LangGraph StateGraph with all nodes and edges
│   │   │   ├── state.py              # AgentState TypedDict definition shared by all graph nodes
│   │   │   │
│   │   │   ├── nodes/                # One Python module per LangGraph node
│   │   │   │   ├── __init__.py       # Exports all node functions for graph.py to import cleanly
│   │   │   │   ├── schema_retriever.py   # Fetches collection schemas from Redis; injects into state context
│   │   │   │   ├── query_generator.py    # Calls LLM with NL query + schema to produce aggregation pipeline JSON
│   │   │   │   ├── query_validator.py    # Rule-based validator: stage order, field existence, type checks
│   │   │   │   ├── query_corrector.py    # Calls LLM with error context to regenerate corrected pipeline
│   │   │   │   ├── query_executor.py     # Executes pipeline via PyMongo; captures timing and row count
│   │   │   │   ├── result_validator.py   # Calls LLM to detect anomalous, empty, or inconsistent results
│   │   │   │   ├── result_corrector.py   # Re-adjusts pipeline or filter based on result anomaly feedback
│   │   │   │   ├── response_formatter.py # Formats raw docs into Markdown table, narrative, and chart JSON
│   │   │   │   └── job_scheduler_node.py # Parses cron from NL, writes to scheduled_jobs, notifies Celery Beat
│   │   │   │
│   │   │   └── prompts/              # LLM prompt templates
│   │   │       ├── __init__.py       # Exports all prompt templates
│   │   │       ├── query_generation_prompt.py    # System + user prompt for MongoDB pipeline generation
│   │   │       ├── result_validation_prompt.py   # Prompt asking LLM to sanity-check result documents
│   │   │       └── response_format_prompt.py     # Prompt instructing LLM to format results as Markdown
│   │   │
│   │   ├── scheduler/                # Celery + APScheduler integration
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py         # Celery application instance; broker and backend from config.py
│   │   │   ├── tasks.py              # Celery task definitions: run_scheduled_query(), send_report()
│   │   │   ├── beat_schedule.py      # APScheduler integration; dynamically loads jobs from scheduled_jobs
│   │   │   └── delivery.py           # Output delivery: email (SMTP), CSV export, webhook POST, in-app
│   │   │
│   │   ├── db/                       # Database layer
│   │   │   ├── __init__.py
│   │   │   ├── mongo_client.py       # Singleton PyMongo/Motor async client; connection pool management
│   │   │   ├── schema_cache.py       # Introspects MongoDB collections; serialises schema to Redis with TTL
│   │   │   └── models.py             # Pydantic v2 models for request/response validation
│   │   │
│   │   └── api/                      # FastAPI route handlers
│   │       ├── __init__.py
│   │       ├── chat.py               # POST /api/chat — accepts NL query, invokes LangGraph, streams response
│   │       ├── jobs.py               # CRUD routes for scheduled_jobs: list, create, pause, delete, trigger
│   │       ├── history.py            # GET /api/history — paginated query history with filter and feedback
│   │       └── auth.py               # POST /api/auth/login, /refresh, /logout — JWT-based stateless auth
│   │
│   ├── data_generation/              # Synthetic data seeders (one script per collection)
│   │   ├── __init__.py
│   │   ├── config.py                 # Shared Faker instance, ENUMS dict, MongoDB connection for seeders
│   │   ├── generate_customers.py     # Generates 100,000 realistic customer documents using Faker
│   │   ├── generate_branches.py      # Generates 500 branch documents with geographic distribution
│   │   ├── generate_employees.py     # Generates 5,000 employee docs with self-referential manager hierarchy
│   │   ├── generate_accounts.py      # Generates accounts linked to existing customer_ids and branch_ids
│   │   ├── generate_transactions.py  # Generates 5M+ transaction docs with realistic debit/credit patterns
│   │   ├── generate_loans.py         # Generates loan docs with EMI schedules and NPA simulation
│   │   ├── generate_investments.py   # Generates investment portfolio docs with market-linked prices
│   │   ├── generate_market_data.py   # Generates 2M+ OHLCV records for 100 symbols over 5 years
│   │   ├── generate_risk_events.py   # Generates fraud/AML events linked to flagged transactions
│   │   ├── generate_audit_logs.py    # Generates system audit log entries for all CRUD operations
│   │   └── run_all.py                # Master seeder: runs all generators in dependency order with progress bars
│   │
│   ├── tests/                        # Automated test suite
│   │   ├── __init__.py
│   │   ├── test_agent_nodes.py       # Unit tests for each LangGraph node function in isolation
│   │   ├── test_query_validator.py   # Edge-case tests for the rule-based pipeline validator
│   │   ├── test_api_endpoints.py     # Integration tests for all FastAPI routes using TestClient
│   │   ├── test_celery_tasks.py      # Tests for Celery task execution and delivery logic
│   │   └── conftest.py               # Pytest fixtures: mock MongoDB, mock Redis, mock LLM responses
│   │
│   ├── requirements.txt              # All Python dependencies pinned to exact versions
│   ├── .env.example                  # Template for environment variables (no secrets committed)
│   └── Dockerfile                    # Multi-stage Docker build for the FastAPI + Celery service
│
├── frontend/                         # React (Vite) frontend application
│   │
│   ├── src/
│   │   │
│   │   ├── components/               # Reusable UI components
│   │   │   ├── ChatInterface.jsx     # Main chat UI: text input, send button, message history display
│   │   │   ├── QueryDisplay.jsx      # Collapsible panel showing the generated MongoDB pipeline JSON
│   │   │   ├── ResultTable.jsx       # Dynamic table rendering query results with sort and CSV export
│   │   │   └── JobsDashboard.jsx     # Dashboard to view, create, pause, and delete scheduled jobs
│   │   │
│   │   ├── pages/                    # Top-level route pages
│   │   │   ├── Home.jsx              # Landing page with ChatInterface as the primary content area
│   │   │   └── Scheduler.jsx         # Dedicated page for the JobsDashboard and job creation wizard
│   │   │
│   │   ├── hooks/                    # Custom React hooks
│   │   │   ├── useWebSocket.js       # Manages WebSocket connection lifecycle and message streaming state
│   │   │   └── useQueryHistory.js    # Fetches and caches paginated query history from /api/history
│   │   │
│   │   ├── services/                 # API client modules
│   │   │   ├── api.js                # Axios instance with JWT interceptors and base URL configuration
│   │   │   └── jobsApi.js            # Typed API functions for all /api/jobs CRUD operations
│   │   │
│   │   ├── store/                    # Zustand global state management
│   │   │   └── appStore.js           # Global store: auth state, current query, WebSocket messages
│   │   │
│   │   └── App.jsx                   # Root component: React Router setup, auth guard, layout wrapper
│   │
│   ├── public/
│   │   └── favicon.svg               # FinQuery AI logo/favicon
│   │
│   ├── index.html                    # Vite HTML entry point
│   ├── vite.config.js                # Vite build config: proxy /api to FastAPI in dev mode
│   ├── tailwind.config.js            # Tailwind CSS configuration with custom fintech color palette
│   └── package.json                  # Node.js dependencies and npm scripts (dev, build, preview)
│
├── docs/                             # Project documentation
│   ├── phase1_architecture.md        # THIS FILE — Schema design and system architecture
│   ├── phase2_agent_implementation.md   # [Phase 2] LangGraph node implementation guide
│   ├── phase3_api_and_frontend.md       # [Phase 3] API design and React component guide
│   ├── phase4_scheduling_delivery.md    # [Phase 4] Celery job scheduling implementation
│   └── sample_queries.md             # 50 example NL queries with expected pipeline outputs
│
├── docker-compose.yml                # Orchestrates: FastAPI, Celery worker, Celery beat, Redis, MongoDB
├── .gitignore                        # Excludes .env, __pycache__, node_modules, .venv, etc.
└── README.md                         # Project overview, quickstart guide, and team member directory
```

> [!WARNING]
> **Never commit `.env` to Git.** Use `.env.example` as the template and share actual secrets via a secure channel (e.g., 1Password, team vault). The `.gitignore` already excludes `.env`, but be explicitly careful when using `git add .` on the `backend/` directory.

---

## 7. Technology Breakdown

> [!IMPORTANT]
> Every team member should understand **all** technologies at a conceptual level, even if they primarily use only a subset. This table maps each tool to its exact role in this project.

| # | Technology | Version | What It Is | Role in THIS Project | Primary User |
|---|-----------|---------|-----------|---------------------|-------------|
| 1 | **MongoDB Atlas** | 7.x | Fully managed cloud NoSQL document database | Stores all 12 collections. The agent executes LLM-generated aggregation pipelines against it. Atlas free-tier cluster used for dev and testing. | Backend + Data Team |
| 2 | **LangGraph** | 0.2.x | Library for building stateful, multi-step LLM agent workflows as directed graphs | Defines the 9-node agent pipeline. Manages state transitions, conditional branching (retry logic), and cycle detection for self-correction loops. | Agent Team |
| 3 | **LangChain** | 0.3.x | Framework providing LLM abstractions, prompt templates, and tool integrations | Used for `ChatPromptTemplate`, LLM chain construction, and JSON output parsers. LangGraph is built on top of LangChain. | Agent Team |
| 4 | **FastAPI** | 0.115.x | Modern async Python web framework with automatic OpenAPI docs | Exposes REST API and WebSocket endpoint for streaming. Acts as bridge between React frontend and the LangGraph agent. | Backend Team |
| 5 | **Celery** | 5.4.x | Distributed task queue for async and periodic job execution in Python | Executes scheduled query jobs asynchronously. When user says "run this every Monday", Celery worker picks it from Redis queue and runs it on schedule. | Scheduler Team |
| 6 | **Redis** | 7.x | In-memory key-value store used as cache, message broker, and session store | Three roles: (1) Schema cache for agent speed, (2) Celery task broker, (3) Celery result backend. Also stores JWT session data. | Backend + Scheduler |
| 7 | **APScheduler** | 3.10.x | Advanced Python job scheduling library with cron, interval, and date triggers | Integrated with Celery Beat for **dynamic** job scheduling — new `scheduled_jobs` docs are picked up at runtime without server restart. | Scheduler Team |
| 8 | **React** | 18.x | JavaScript UI library for building component-based web interfaces | Provides chat interface, query result display, pipeline viewer, and scheduled jobs dashboard. Communicates via Axios REST and native WebSocket. | Frontend Team |
| 9 | **Docker / Compose** | 27.x / 2.x | Container platform for packaging applications and dependencies | `docker-compose.yml` runs all services (FastAPI, Celery worker, Celery beat, Redis, local MongoDB) in isolated containers. | DevOps / All |
| 10 | **PyMongo** | 4.8.x | Official synchronous Python driver for MongoDB | Used in `query_executor.py` and all `data_generation/` scripts. Agent calls `db[collection].aggregate(pipeline)` via PyMongo. | Backend + Data |
| 11 | **Motor** | 3.5.x | Async Python driver for MongoDB (non-blocking wrapper over PyMongo) | Used in FastAPI async route handlers for non-blocking DB writes to `query_history` and reads from `scheduled_jobs`. | Backend Team |
| 12 | **Pydantic** | 2.x | Data validation library using Python type annotations | All API request/response schemas are Pydantic models. `config.py` uses `BaseSettings` to validate and load env variables from `.env`. | Backend + Agent |
| 13 | **python-dotenv** | 1.x | Loads environment variables from `.env` files into `os.environ` | Used during local development so that `MONGO_URI`, `OPENAI_API_KEY`, `REDIS_URL` etc. are available to `config.py` without being hardcoded. | All |
| 14 | **Faker** | 30.x | Python library for generating realistic fake data | Powers all 10 `generate_*.py` scripts. Generates realistic names, emails, financial amounts, dates, and geodata for 100K+ customers and millions of transactions. | Data Team |
| 15 | **Vite** | 5.x | Next-generation JavaScript bundler and dev server | Bundles and serves the React frontend. In dev mode, proxies `/api/*` to FastAPI (port 8000) to avoid CORS issues. | Frontend Team |
| 16 | **Tailwind CSS** | 3.x | Utility-first CSS framework | Styles all React components with a professional fintech dark-mode color palette. Provides responsive layout for chat and dashboard views. | Frontend Team |
| 17 | **Zustand** | 4.x | Lightweight global state management for React | Manages auth tokens, current query state, and incoming WebSocket messages globally across all components without prop-drilling. | Frontend Team |
| 18 | **Axios** | 1.x | Promise-based HTTP client for the browser | Used in `services/api.js` with JWT Bearer token interceptors for all REST calls to FastAPI. Handles token refresh on 401 responses automatically. | Frontend Team |
| 19 | **pytest** | 8.x | Python testing framework | Runs unit and integration tests. Used with `pytest-asyncio` for async FastAPI tests and `mongomock` for mocking MongoDB in unit tests. | All |
| 20 | **uvicorn** | 0.30.x | ASGI server for running FastAPI in production | Serves the FastAPI application both in Docker and locally. Configured with multiple workers in production for concurrency. | Backend / DevOps |

---

## 8. Data Flow Narrative

### 8.1 Simple Query Flow (No Scheduling)

```
User types: "What is the average credit score of defaulted loan customers in Delhi?"

1. React → POST /api/chat → FastAPI (chat.py)
2. FastAPI creates AgentState, calls LangGraph graph.invoke()
3. schema_retriever: identifies [loans, customers], fetches schema from Redis
4. query_generator: LLM produces:
   [
     { "$lookup": { "from": "customers", "localField": "customer_id",
                    "foreignField": "customer_id", "as": "cust" }},
     { "$unwind": "$cust" },
     { "$match": { "status": "defaulted", "cust.city": "Delhi" }},
     { "$group": { "_id": null,
                   "avg_credit_score": { "$avg": "$cust.credit_score" }}}
   ]
5. query_validator: checks $lookup fields exist → VALID
6. query_executor: runs against loans collection → [{ "avg_credit_score": 612.4 }]
7. result_validator: single result, numeric in realistic range → OK
8. response_formatter: "The average credit score of customers with defaulted
   loans in Delhi is 612.4 (based on 1,243 records)."
9. query_history: logged with pipeline, timing, trace
10. FastAPI → React (via WS stream) → User sees result
```

### 8.2 Scheduled Query Flow

```
User types: "Email me the top 5 NPA loans every Monday at 9 AM IST"

1. LangGraph executes once immediately (steps 1-8 above)
2. job_scheduler_node:
   - LLM parses "every Monday at 9 AM IST" → cron: "0 9 * * 1" (Asia/Kolkata)
   - Writes document to scheduled_jobs collection:
     { job_name: "Top 5 NPA Loans", cron: "0 9 * * 1",
       output_format: "email", output_config: { to: "user@bank.com" }}
   - Notifies Celery Beat via Redis signal
3. APScheduler (beat_schedule.py) picks up new job from scheduled_jobs
4. Every Monday 9 AM: Celery Beat fires → Celery Worker runs run_scheduled_query()
5. Worker re-executes pipeline against MongoDB
6. delivery.py sends formatted result as email via SMTP/SendGrid
7. Updates: last_run_at, run_count, success_count in scheduled_jobs
```

---

## 9. Key Design Decisions

### 9.1 Why LangGraph over a simple LLM chain?

| Aspect | Simple Chain | LangGraph |
|--------|-------------|-----------|
| Retry logic | Manual if/else | Built-in conditional edges |
| State management | Pass vars manually | Typed `AgentState` auto-propagated |
| Observability | Print statements | Full step-by-step trace in state |
| Parallelism | Sequential only | Parallel nodes possible (Phase 2) |
| Debuggability | Hard | LangSmith integration out of box |

### 9.2 Why MongoDB over PostgreSQL for a fintech system?

> [!NOTE]
> MongoDB is chosen here specifically because **the project itself is about teaching an LLM to understand and query it**. The flexible schema allows the AI agent to learn from introspected metadata rather than a rigid DDL. In a production bank, both SQL and NoSQL would coexist.

- **Aggregation Pipelines** are stage-based, making them easier to generate and validate programmatically than complex SQL JOINs.
- **Schema flexibility** allows documents to have variable fields (e.g., `collateral_type` only relevant for secured loans), which the LLM must learn to handle gracefully.
- **MongoDB Atlas** provides a free-tier cluster for academic projects, vector search for future phases, and Atlas Charts for visualization.

### 9.3 Why Celery + APScheduler (not just APScheduler alone)?

| Concern | APScheduler Alone | Celery + APScheduler |
|--------|------------------|---------------------|
| Distributed execution | Single process | Multiple workers across machines |
| Job result storage | In-memory | Redis / MongoDB backend |
| Retry on failure | Manual | Built-in Celery retry mechanism |
| Monitoring | None | Flower dashboard |
| Horizontal scale | Cannot | Add workers with `celery -A app worker` |

### 9.4 Schema Caching Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│  schema_retriever node                                          │
│                                                                 │
│  1. Identify relevant collections from NL query (LLM-lite)     │
│  2. For each collection:                                        │
│     a. Check Redis: GET schema:{collection_name}                │
│     b. HIT  → use cached JSON (TTL: 3600s)                     │
│     c. MISS → introspect MongoDB (sample 100 docs)             │
│              → infer field types, enums, ranges                 │
│              → SET Redis with TTL                               │
│  3. Inject combined schema JSON into AgentState.schema_context  │
└─────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> The schema cache TTL is set to **1 hour** by default. If you modify collection schemas during development (add/remove fields in seeders), manually flush the Redis cache with `redis-cli FLUSHDB` or call the admin endpoint `DELETE /api/admin/schema-cache` to force fresh introspection.

---

## Appendix A — Environment Variables

| Variable | Example Value | Required By | Purpose |
|---------|-------------|------------|--------|
| `MONGO_URI` | `mongodb+srv://user:pass@cluster.mongodb.net` | Backend, Celery | MongoDB Atlas connection string |
| `MONGO_DB_NAME` | `finquery_db` | Backend, Celery | Target database name |
| `REDIS_URL` | `redis://localhost:6379/0` | Backend, Celery | Redis connection string |
| `OPENAI_API_KEY` | `sk-...` | Agent | OpenAI GPT-4o access |
| `GEMINI_API_KEY` | `AIza...` | Agent | Google Gemini Pro access |
| `LLM_PROVIDER` | `gemini` | Agent | Selects which LLM backend to use |
| `JWT_SECRET_KEY` | `your-secret-key-here` | FastAPI auth | JWT token signing secret |
| `JWT_ALGORITHM` | `HS256` | FastAPI auth | JWT signing algorithm |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery | Task broker (separate Redis DB) |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Celery | Job result storage |
| `SMTP_HOST` | `smtp.sendgrid.net` | Delivery | Email sending for scheduled reports |
| `SMTP_PORT` | `587` | Delivery | SMTP port |
| `SMTP_USER` | `apikey` | Delivery | SendGrid API key username |
| `SMTP_PASS` | `SG....` | Delivery | SendGrid API key |
| `SCHEMA_CACHE_TTL` | `3600` | schema_cache.py | Redis TTL for schema in seconds |
| `MAX_RETRY_ATTEMPTS` | `3` | Agent | Max query correction retries |
| `CORS_ORIGINS` | `http://localhost:5173` | FastAPI | Allowed CORS origins |

---

## Appendix B — MongoDB Index Recommendations

> [!IMPORTANT]
> Create these indexes in MongoDB Atlas before running any benchmarks. Missing indexes on high-volume collections (`transactions`, `audit_logs`, `market_data`) will cause full collection scans and timeouts on the agent's aggregation queries.

```javascript
// transactions — most queried collection
db.transactions.createIndex({ account_id: 1, initiated_at: -1 })
db.transactions.createIndex({ customer_id: 1, type: 1 })
db.transactions.createIndex({ is_flagged: 1, initiated_at: -1 })
db.transactions.createIndex({ merchant_category: 1, amount: -1 })

// customers
db.customers.createIndex({ email: 1 }, { unique: true })
db.customers.createIndex({ kyc_status: 1, segment: 1 })
db.customers.createIndex({ country: 1, city: 1, segment: 1 })

// accounts
db.accounts.createIndex({ customer_id: 1, status: 1 })
db.accounts.createIndex({ branch_id: 1, tier: 1 })

// loans
db.loans.createIndex({ customer_id: 1, status: 1 })
db.loans.createIndex({ due_date: 1, status: 1 })

// market_data
db.market_data.createIndex({ symbol: 1, date: -1 }, { unique: true })

// risk_events
db.risk_events.createIndex({ customer_id: 1, severity: 1, status: 1 })
db.risk_events.createIndex({ detected_at: -1 })

// query_history
db.query_history.createIndex({ user_id: 1, created_at: -1 })

// audit_logs — TTL index to auto-delete logs older than 2 years
db.audit_logs.createIndex({ timestamp: 1 }, { expireAfterSeconds: 63072000 })
```

---

*End of Phase 1 — Schema Design & System Architecture*  
*Next: [Phase 2 — LangGraph Node Implementation](phase2_agent_implementation.md)*
