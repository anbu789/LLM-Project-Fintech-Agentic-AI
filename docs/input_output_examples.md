# Input/Output Flow — Complete Examples

> **Project:** FinQuery AI Agent — Natural Language to MongoDB for Fintech  
> **Stack:** LangGraph · FastAPI · React · MongoDB · Redis · Celery  
> **Author:** Capstone Team | Guided by Goldman Sachs Engineering Mentor  
> **Version:** 1.0 | Last Updated: September 2026

---

## Table of Contents

1. [How Input Flows Through the System](#1-how-input-flows-through-the-system)
2. [The Agent State Object](#2-the-agent-state-object)
3. [Example 1 — Simple Lookup](#3-example-1--simple-lookup)
4. [Example 2 — Complex Aggregation](#4-example-2--complex-aggregation)
5. [Example 3 — Self-Correction in Action](#5-example-3--self-correction-in-action)
6. [Example 4 — Scheduling Request](#6-example-4--scheduling-request)
7. [Example 5 — Failed Query with Graceful Degradation](#7-example-5--failed-query-with-graceful-degradation)
8. [Example 6 — Multi-Turn Conversation](#8-example-6--multi-turn-conversation)
9. [The WebSocket Message Protocol](#9-the-websocket-message-protocol)
10. [API Endpoint Reference Table](#10-api-endpoint-reference-table)

---

## 1. How Input Flows Through the System

Every user message travels through a precisely ordered pipeline — from the React chat UI all the way to MongoDB and back. The diagram below captures every hop, every agent node, and every data transformation.

```mermaid
sequenceDiagram
    autonumber
    actor User as Business User
    participant React as React Chat UI
    participant WS as WebSocket /ws/chat
    participant API as FastAPI /api/chat
    participant LG as LangGraph Agent Orchestrator
    participant SR as schema_retriever Node
    participant QG as query_generator Node
    participant QV as query_validator Node
    participant EX as executor Node
    participant RV as result_validator Node
    participant RF as response_formatter Node
    participant SD as scheduler Node (conditional)
    participant MDB as MongoDB Atlas
    participant Redis as Redis Cache
    participant Celery as Celery Worker

    User->>React: Types natural language question
    React->>WS: Sends JSON message over WebSocket connection
    WS->>API: Forwards to POST /api/chat handler
    API->>Redis: Check query cache (TTL: 5 min)
    Redis-->>API: Cache MISS (or HIT skip to step 22)
    API->>LG: Invoke agent with AgentState payload

    Note over LG: LangGraph begins node traversal

    LG->>SR: schema_retriever node activated
    SR-->>WS: type thinking node schema_retriever
    WS-->>React: Streams thinking indicator
    SR->>MDB: Fetch schema embeddings for relevant collections
    MDB-->>SR: Schema metadata + field definitions
    SR-->>LG: Returns relevant_collections and schema_context

    LG->>QG: query_generator node activated
    QG-->>WS: type thinking node query_generator
    WS-->>React: Streams thinking indicator
    QG->>QG: LLM generates aggregation pipeline
    QG-->>LG: Returns pipeline and collection_name
    LG-->>WS: type query_ready with query JSON
    WS-->>React: Renders collapsible View Query panel

    LG->>QV: query_validator node activated
    QV->>QV: Validate syntax, fields, types
    alt Validation FAILS
        QV-->>LG: valid false, error message, retry_count+1
        LG->>QG: Re-invoke query_generator with error context
    else Validation PASSES
        QV-->>LG: valid true
    end

    LG->>EX: executor node activated
    EX-->>WS: type executing
    WS-->>React: Streams Running query indicator
    EX->>MDB: Execute aggregation pipeline
    MDB-->>EX: Raw cursor results (paginated)
    EX-->>LG: Returns raw_results, row_count, execution_time_ms

    LG->>RV: result_validator node activated
    RV->>RV: Check for empty results, anomalies
    alt Results SUSPICIOUS
        RV-->>LG: result_valid false with reason
        LG->>QG: Re-invoke with refinement hint
    else Results OK
        RV-->>LG: result_valid true
    end

    LG->>Redis: Cache results (key: hash of query + params)

    alt Scheduling intent detected
        LG->>SD: scheduler node activated
        SD->>MDB: Insert document into scheduled_jobs collection
        SD->>Celery: Register periodic task via beat schedule
        SD-->>LG: job_id and next_run returned
        LG-->>WS: type schedule_created with job_id and next_run
        WS-->>React: Shows scheduling confirmation banner
    end

    LG->>RF: response_formatter node activated
    RF->>RF: LLM formats results into natural language
    RF-->>LG: Returns answer_text, formatted_table, citations
    LG-->>API: Final AgentState returned
    API->>MDB: Persist to query_history collection
    API-->>WS: type answer with text, rows, and total
    WS-->>React: Renders answer text + sortable result table
    React-->>User: Displays full response with query panel
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| WebSocket instead of REST polling | Enables real-time streaming of each agent node's progress — users see "thinking" indicators per step |
| Redis query cache (5-min TTL) | Identical queries from multiple users skip the entire LangGraph pipeline, reducing LLM API cost |
| Conditional `scheduler` node | Only activated when scheduling intent is detected by `query_generator`; avoids unnecessary overhead |
| Retry loop between `query_validator` and `query_generator` | Enables self-correction without restarting the full pipeline; state is preserved across retries |
| `result_validator` after execution | Catches semantically wrong results (e.g., empty result on a collection with 500K records) that syntax validation cannot detect |

---

## 2. The Agent State Object

The `AgentState` TypedDict is the central data structure passed between every LangGraph node. It is initialized at the start of each agent invocation and mutated in place as nodes execute. Every field below is present for every run.

```python
from typing import TypedDict, Optional, List, Dict, Any, Literal
from datetime import datetime


class SchemaContext(TypedDict):
    """Schema metadata resolved by schema_retriever node."""
    collection_name: str              # Primary MongoDB collection for this query
    relevant_collections: List[str]   # All collections involved (including $lookup targets)
    fields: Dict[str, str]            # {field_name: bson_type} for primary collection
    sample_values: Dict[str, List]    # {field_name: [sample1, sample2, ...]} from schema probe
    join_hints: List[Dict[str, str]]  # [{from_col, local_field, foreign_field}] for $lookup


class ValidationResult(TypedDict):
    """Output of the query_validator node."""
    valid: bool                        # True if pipeline passed all validation checks
    errors: List[str]                  # List of validation error messages (empty if valid)
    warnings: List[str]                # Non-fatal warnings (e.g., missing index hint)
    validated_at: str                  # ISO-8601 timestamp of validation


class ExecutionResult(TypedDict):
    """Raw output from the executor node."""
    rows: List[Dict[str, Any]]         # Actual result documents (capped at 1000 for UI)
    total_count: int                   # Total matching documents (via $count facet)
    execution_time_ms: int             # Wall-clock time for the MongoDB aggregation
    explain_plan: Optional[Dict]       # MongoDB explain output (only in DEBUG mode)


class ScheduleConfig(TypedDict):
    """Extracted scheduling intent (populated only when user requests recurrence)."""
    cron_expression: str               # Standard 5-field cron (e.g., '0 9 * * 1' for Mon 9am)
    human_readable: str                # e.g., 'Every Monday at 9:00 AM'
    email_recipients: List[str]        # Email addresses extracted from user message
    report_format: Literal["csv", "json", "excel"]  # Default: "csv"
    timezone: str                      # IANA timezone (e.g., 'America/New_York'), default UTC


class AgentState(TypedDict):
    """
    Central state object passed between all LangGraph nodes.
    Initialized by FastAPI handler; mutated by each node in sequence.
    Persisted to query_history collection after completion.
    """

    # --- Identity & Session ---------------------------------------------------
    session_id: str
    # Unique session identifier; maps to a Redis key for conversation context.
    # Format: "sess_<uuid4>". Used to retrieve prior turns in multi-turn mode.

    user_id: str
    # Authenticated user's ID from JWT token.
    # Used for audit logging and personalized query history.

    query_id: str
    # Unique ID for this specific query invocation.
    # Format: "qry_<uuid4>". Stored as _id in query_history collection.

    conversation_history: List[Dict[str, str]]
    # [{role: "user"|"assistant", content: "..."}]
    # Full message history for this session. Used by query_generator
    # to resolve pronouns and implicit references in multi-turn conversation.

    # --- Input ----------------------------------------------------------------
    user_message: str
    # The raw natural language string typed by the user.
    # Example: "Show me all customers in New York with credit score above 750"

    # --- Schema Resolution (set by schema_retriever) -------------------------
    schema_context: Optional[SchemaContext]
    # Populated after schema_retriever runs. None until that node completes.

    schema_retrieval_confidence: float
    # 0.0-1.0 score indicating how confidently the agent mapped the question
    # to a collection. Below 0.4, the agent triggers graceful degradation.

    # --- Query Generation (set by query_generator) ---------------------------
    generated_pipeline: Optional[List[Dict[str, Any]]]
    # The MongoDB aggregation pipeline as a Python list of stage dicts.
    # Example: [{"$match": {...}}, {"$sort": {...}}, {"$limit": 100}]

    target_collection: Optional[str]
    # The MongoDB collection the pipeline runs against.
    # Example: "customers"

    scheduling_intent: Optional[ScheduleConfig]
    # Populated only if query_generator detects a scheduling request.
    # None for all non-scheduling queries.

    # --- Validation (set by query_validator) ---------------------------------
    validation_result: Optional[ValidationResult]
    # Output of query_validator. None until that node completes.

    # --- Execution (set by executor) -----------------------------------------
    execution_result: Optional[ExecutionResult]
    # Raw MongoDB query output. None until executor completes.

    # --- Result Validation (set by result_validator) -------------------------
    result_is_valid: bool
    # True if result_validator is satisfied with the result set.
    # False triggers a refinement loop back to query_generator.

    result_validation_note: Optional[str]
    # Human-readable explanation if result_is_valid is False.
    # Example: "Empty result on accounts collection (500K docs) is suspicious."

    # --- Retry Control -------------------------------------------------------
    retry_count: int
    # Number of query regeneration attempts so far. Starts at 0.
    # Pipeline halts and returns graceful error if retry_count >= MAX_RETRIES (3).

    correction_log: List[str]
    # Ordered list of corrections applied across retries.
    # Shown in UI as "Query was auto-corrected N time(s)" with expandable detail.
    # Example: ["Corrected field 'account_status' -> 'status'",
    #            "Refined value filter after empty result"]

    # --- Scheduling (set by scheduler node) ----------------------------------
    scheduled_job_id: Optional[str]
    # MongoDB ObjectId of the inserted scheduled_jobs document.
    # None for non-scheduling queries.

    # --- Response (set by response_formatter) --------------------------------
    final_answer: Optional[str]
    # The natural language response shown to the user in the chat panel.

    answer_citations: List[str]
    # Collection and field names referenced in the answer, shown as tags in UI.

    # --- Metadata & Telemetry ------------------------------------------------
    pipeline_start_time: str           # ISO-8601; set when agent is first invoked
    pipeline_end_time: Optional[str]   # ISO-8601; set when response_formatter completes
    total_latency_ms: Optional[int]    # End-to-end wall time for the full pipeline
    cache_hit: bool                    # True if result was served from Redis cache
    nodes_executed: List[str]          # Ordered list of nodes that actually ran
    error_message: Optional[str]       # Set if pipeline fails with an unrecoverable error
```

> [!NOTE]
> The `AgentState` TypedDict is defined in `agent/state.py` and imported by every LangGraph node. LangGraph automatically handles state merging between node outputs — each node only needs to return the fields it modifies.

---

## 3. Example 1 — Simple Lookup

### User Input

> **"Show me all customers in New York with credit score above 750"**

---

### Step 1 — `schema_retriever` Output

The node embeds the user query and performs a cosine similarity search against pre-computed schema embeddings stored in MongoDB Atlas Vector Search.

```
Selected Collection : customers
Confidence Score    : 0.94

Reason: Query mentions "customers" explicitly. "credit score" maps to
        field 'credit_score' (int32). "New York" maps to field 'state'
        (string) in customers.address subdocument.

Relevant Fields Identified:
  - address.state     -> string  (filter)
  - credit_score      -> int32   (filter)
  - customer_id       -> string  (output)
  - first_name        -> string  (output)
  - last_name         -> string  (output)
  - email             -> string  (output)
  - phone             -> string  (output)
  - risk_rating       -> string  (output)

No $lookup required (single collection query).
```

---

### Step 2 — Generated MongoDB Aggregation Pipeline

```json
[
  {
    "$match": {
      "address.state": "NY",
      "credit_score": { "$gt": 750 }
    }
  },
  {
    "$project": {
      "_id": 0,
      "customer_id": 1,
      "first_name": 1,
      "last_name": 1,
      "email": 1,
      "phone": 1,
      "credit_score": 1,
      "risk_rating": 1,
      "address.city": 1,
      "address.state": 1
    }
  },
  {
    "$sort": { "credit_score": -1 }
  },
  {
    "$limit": 1000
  }
]
```

> [!TIP]
> The pipeline uses `address.state` (dot notation for subdocument) rather than a top-level `state` field. The `schema_retriever` correctly identified this from the schema metadata, preventing a field-not-found error.

---

### Step 3 — Execution Result

**Query executed in 38 ms | Total matching documents: 2,847**

Sample of returned rows (first 3 shown):

| customer_id | first_name | last_name | email | credit_score | risk_rating | address.city |
|---|---|---|---|---|---|---|
| CUST-100423 | Margaret | Holloway | m.holloway@email.com | 821 | low | Manhattan |
| CUST-100891 | Rajesh | Patel | r.patel@email.com | 815 | low | Brooklyn |
| CUST-102341 | Diane | Kowalski | d.kowalski@email.com | 803 | low | Queens |
| ... | ... | ... | ... | ... | ... | ... |

---

### Step 4 — Validation

The `query_validator` node performed the following checks:

| Check | Status | Detail |
|---|---|---|
| Pipeline is valid BSON/JSON | Pass | All stage keys are valid aggregation operators |
| `$match` fields exist in schema | Pass | `address.state` and `credit_score` confirmed in `customers` schema |
| Comparison operator types match | Pass | `credit_score` is `int32`; `750` is an integer literal |
| No `$out` or `$merge` (read-only enforcement) | Pass | Pipeline is read-only |
| `$limit` present (safety guard) | Pass | `$limit: 1000` present |
| Result count > 0 | Pass | 2,847 rows returned |

**Validation passed on first attempt. `retry_count: 0`**

---

### Step 5 — `response_formatter` Output

```
Final Answer (shown in chat):

"I found 2,847 customers in New York (state: NY) with a credit score
above 750. They are sorted by credit score from highest to lowest.
The top result is Margaret Holloway in Manhattan with a score of 821.
All identified customers are rated as 'low' risk. The full list is
displayed in the table below — you can sort by any column or export
to CSV."

Citations: [customers] [credit_score] [address.state]
```

---

### Step 6 — What the UI Shows

```
+-------------------------------------------------------------------+
|  FinQuery AI                                             [Live]   |
+-------------------------------------------------------------------+
|                                                                   |
|  YOU  Show me all customers in New York with credit score         |
|       above 750                                          10:14 AM |
|                                                                   |
|  AI   I found 2,847 customers in New York (NY) with a credit      |
|       score above 750, sorted highest to lowest. The top result   |
|       is Margaret Holloway in Manhattan (score: 821, low risk).  |
|                                                         10:14 AM |
|                                                                   |
|       [v] View Query                                              |
|       [MongoDB pipeline JSON in syntax-highlighted block]         |
|                                                                   |
|  +----------------------------------------------------------------+
|  | customer_id  | first_name | credit_score | city     | risk    |
|  | CUST-100423  | Margaret   | 821          | Manhattan| low     |
|  | CUST-100891  | Rajesh     | 815          | Brooklyn | low     |
|  | CUST-102341  | Diane      | 803          | Queens   | low     |
|  | ... (2,844 more rows)                                          |
|  +----------------------------------------------------------------+
|       [Export CSV]  [Export Excel]     Showing 1-50 of 2,847     |
+-------------------------------------------------------------------+
```

---

## 4. Example 2 — Complex Aggregation

### User Input

> **"What is the total transaction volume per branch for the last 30 days, sorted by highest volume?"**

---

### Collections Involved

| Collection | Role | Join Key |
|---|---|---|
| `transactions` | Primary — contains transaction amounts and timestamps | `branch_id` |
| `branches` | Lookup target — provides branch name and region | `branch_id` -> `_id` |

The `schema_retriever` determined a `$lookup` was needed because the user asked for **branch names** (in `branches`) alongside **transaction totals** (in `transactions`).

---

### Generated Aggregation Pipeline

```json
[
  {
    "$match": {
      "transaction_date": {
        "$gte": { "$dateSubtract": {
          "startDate": "$$NOW",
          "unit": "day",
          "amount": 30
        }},
        "$lte": "$$NOW"
      },
      "status": "completed"
    }
  },
  {
    "$group": {
      "_id": "$branch_id",
      "total_volume": { "$sum": "$amount" },
      "transaction_count": { "$sum": 1 },
      "avg_transaction": { "$avg": "$amount" }
    }
  },
  {
    "$lookup": {
      "from": "branches",
      "localField": "_id",
      "foreignField": "_id",
      "as": "branch_info"
    }
  },
  {
    "$unwind": {
      "path": "$branch_info",
      "preserveNullAndEmptyArrays": false
    }
  },
  {
    "$project": {
      "_id": 0,
      "branch_id": "$_id",
      "branch_name": "$branch_info.branch_name",
      "region": "$branch_info.region",
      "total_volume": 1,
      "transaction_count": 1,
      "avg_transaction": { "$round": ["$avg_transaction", 2] }
    }
  },
  {
    "$sort": { "total_volume": -1 }
  },
  {
    "$limit": 100
  }
]
```

> [!NOTE]
> The `$group` is intentionally placed **before** `$lookup` to minimize the number of documents sent through the join — a MongoDB performance best practice. Grouping first reduces N documents to at most M branches before the lookup runs.

---

### Execution Result

**Query executed in 124 ms | Total branches with activity: 47**

| branch_name | region | total_volume ($) | transaction_count | avg_transaction ($) |
|---|---|---|---|---|
| Midtown Manhattan Branch | Northeast | 142,847,320.50 | 18,432 | 7,750.82 |
| Downtown Chicago Branch | Midwest | 98,234,110.75 | 14,219 | 6,909.15 |
| Beverly Hills Branch | West | 87,541,990.00 | 9,871 | 8,869.47 |
| Boston Financial District | Northeast | 76,102,445.25 | 12,045 | 6,318.90 |
| Atlanta Peachtree Branch | Southeast | 54,893,220.00 | 10,788 | 5,088.73 |
| ... | ... | ... | ... | ... |

---

### Natural Language Response

```
"Over the last 30 days, your top-performing branch by transaction volume
is the Midtown Manhattan Branch (Northeast region) with $142.8M across
18,432 completed transactions. The Beverly Hills Branch leads in average
transaction size at $8,869 per transaction, suggesting a high-net-worth
customer concentration. All 47 active branches are listed in the table
below, sorted from highest to lowest total volume."
```

---

## 5. Example 3 — Self-Correction in Action

### User Input

> **"Find all accounts where the account_status is inactive"**

> [!IMPORTANT]
> The actual field in the `accounts` collection is `status`, not `account_status`. The valid status values are: `active`, `closed`, `frozen`, `dormant`. There is no value `inactive`.

---

### Attempt 1 — Wrong Field Name

**`query_generator` produces:**

```json
[
  {
    "$match": {
      "account_status": "inactive"
    }
  },
  {
    "$project": {
      "_id": 0,
      "account_id": 1,
      "customer_id": 1,
      "account_type": 1,
      "account_status": 1,
      "balance": 1
    }
  }
]
```

**`query_validator` output:**

```
VALIDATION FAILED
Error: Field 'account_status' does not exist in the 'accounts' collection schema.

Valid fields for accounts collection:
  account_id      (string)
  customer_id     (string)
  account_type    (string)   -> values: ['checking', 'savings', 'money_market', 'cd']
  status          (string)   -> values: ['active', 'closed', 'frozen', 'dormant']
  balance         (decimal128)
  opened_date     (date)
  branch_id       (string)
  interest_rate   (double)
  credit_limit    (decimal128)

Suggestion: Did you mean 'status'? The user's term 'account_status'
            likely maps to the 'status' field.

retry_count: 0 -> 1
Correction logged: "Field 'account_status' does not exist. Correcting to 'status'."
```

---

### Attempt 2 — Correct Field, Wrong Value

**`query_generator` regenerates with correction context:**

```json
[
  {
    "$match": {
      "status": "closed"
    }
  },
  {
    "$project": {
      "_id": 0,
      "account_id": 1,
      "customer_id": 1,
      "account_type": 1,
      "status": 1,
      "balance": 1
    }
  },
  {
    "$limit": 1000
  }
]
```

**`query_validator` output:** Validation passed. Field `status` exists, value `closed` is a known enum value.

**`executor` runs query. Result: 4,821 rows returned. Execution time: 45ms**

**`result_validator` output:**

```
RESULT CONCERN FLAGGED
The user asked for 'inactive' accounts. The query only retrieved 'closed'
accounts (4,821 rows). However, the schema shows additional status values
that could semantically map to 'inactive': 'frozen' and 'dormant'.

The intent was likely: all non-active accounts (closed + frozen + dormant).

result_is_valid: false
Reason: "Query only captured one of three non-active status values.
         Refining to include 'frozen' and 'dormant' to fully match
         user intent for 'inactive'."

retry_count: 1 -> 2
Correction logged: "Refined value filter: 'inactive' -> $in ['closed', 'frozen', 'dormant']"
```

---

### Attempt 3 — Correct Field, Full Value Set

**`query_generator` produces final corrected pipeline:**

```json
[
  {
    "$match": {
      "status": { "$in": ["closed", "frozen", "dormant"] }
    }
  },
  {
    "$project": {
      "_id": 0,
      "account_id": 1,
      "customer_id": 1,
      "account_type": 1,
      "status": 1,
      "balance": 1,
      "opened_date": 1,
      "branch_id": 1
    }
  },
  {
    "$sort": { "status": 1, "opened_date": -1 }
  },
  {
    "$limit": 1000
  }
]
```

**`result_validator` output:** 12,450 rows returned. Result is plausible for a collection of 500K accounts (~2.5% non-active rate is realistic). Validation passed.

---

### Final Answer Shown to User

```
"I found 12,450 accounts that are not currently active. Since your
accounts collection uses the field 'status' (not 'account_status'),
and the term 'inactive' covers three status values in this system,
I included all of them:

  - Closed:  4,821 accounts
  - Dormant: 5,109 accounts
  - Frozen:  2,520 accounts

  Total non-active accounts: 12,450

Auto-corrected 2 time(s):
  1. Field name corrected: 'account_status' -> 'status'
  2. Value filter expanded: 'inactive' -> ['closed', 'frozen', 'dormant']"
```

**Correction banner in UI:**

```
+-------------------------------------------------------------------+
|  Query auto-corrected 2 time(s)   [View correction log v]        |
|                                                                   |
|  Correction 1: Field 'account_status' corrected to 'status'      |
|  Correction 2: Value filter expanded to cover all non-active      |
|                statuses: ['closed', 'frozen', 'dormant']          |
+-------------------------------------------------------------------+
```

---

## 6. Example 4 — Scheduling Request

### User Input

> **"Every Monday morning at 9am, give me a list of all high-risk customers (risk_rating = high) who had transactions over $10,000 last week. Email the report to riskteam@goldmanbank.com"**

---

### Step 1 — Agent Runs the Query Immediately First

Before registering the schedule, the agent executes the query for the **current week** so the user sees an immediate result. This confirms the query is correct before it is scheduled.

**Pipeline generated and executed:**

```json
[
  {
    "$lookup": {
      "from": "transactions",
      "localField": "customer_id",
      "foreignField": "customer_id",
      "as": "recent_transactions",
      "pipeline": [
        {
          "$match": {
            "transaction_date": {
              "$gte": {
                "$dateSubtract": {
                  "startDate": "$$NOW",
                  "unit": "day",
                  "amount": 7
                }
              }
            },
            "amount": { "$gt": 10000 },
            "status": "completed"
          }
        }
      ]
    }
  },
  {
    "$match": {
      "risk_rating": "high",
      "recent_transactions": { "$ne": [] }
    }
  },
  {
    "$project": {
      "_id": 0,
      "customer_id": 1,
      "first_name": 1,
      "last_name": 1,
      "email": 1,
      "phone": 1,
      "risk_rating": 1,
      "credit_score": 1,
      "recent_transactions.transaction_id": 1,
      "recent_transactions.amount": 1,
      "recent_transactions.transaction_date": 1,
      "recent_transactions.transaction_type": 1,
      "transaction_count": { "$size": "$recent_transactions" },
      "total_transaction_value": { "$sum": "$recent_transactions.amount" }
    }
  },
  {
    "$sort": { "total_transaction_value": -1 }
  }
]
```

**Immediate result: 38 high-risk customers found this week.**

---

### Step 2 — Scheduling Intent Detection

The `query_generator` node extracts the scheduling intent into a structured JSON object:

```json
{
  "scheduling_intent": {
    "detected": true,
    "cron_expression": "0 9 * * 1",
    "human_readable": "Every Monday at 9:00 AM",
    "timezone": "America/New_York",
    "email_recipients": ["riskteam@goldmanbank.com"],
    "report_format": "csv",
    "report_subject_template": "Weekly High-Risk Customer Transaction Report - {date}",
    "query_description": "High-risk customers with transactions > $10,000 in the past 7 days"
  }
}
```

---

### Step 3 — `scheduled_jobs` Document Created

The `scheduler` node inserts the following document into the `scheduled_jobs` MongoDB collection:

```json
{
  "_id": "JOB-7f3a9c21-e4b1-4d8a-b2f3-9c1e5d7a3f8b",
  "job_id": "JOB-001",
  "created_by_user_id": "usr_4421",
  "created_at": "2026-09-03T13:28:00Z",
  "status": "active",

  "schedule": {
    "cron_expression": "0 9 * * 1",
    "human_readable": "Every Monday at 9:00 AM",
    "timezone": "America/New_York",
    "next_run_at": "2026-09-07T09:00:00-05:00"
  },

  "query": {
    "original_user_message": "Every Monday morning at 9am, give me a list of all high-risk customers (risk_rating = high) who had transactions over $10,000 last week. Email the report to riskteam@goldmanbank.com",
    "target_collection": "customers",
    "pipeline": [
      {
        "$lookup": {
          "from": "transactions",
          "localField": "customer_id",
          "foreignField": "customer_id",
          "as": "recent_transactions",
          "pipeline": [
            {
              "$match": {
                "transaction_date": {
                  "$gte": {
                    "$dateSubtract": {
                      "startDate": "$$NOW",
                      "unit": "day",
                      "amount": 7
                    }
                  }
                },
                "amount": { "$gt": 10000 },
                "status": "completed"
              }
            }
          ]
        }
      },
      { "$match": { "risk_rating": "high", "recent_transactions": { "$ne": [] } } },
      {
        "$project": {
          "_id": 0,
          "customer_id": 1,
          "first_name": 1,
          "last_name": 1,
          "email": 1,
          "risk_rating": 1,
          "transaction_count": { "$size": "$recent_transactions" },
          "total_transaction_value": { "$sum": "$recent_transactions.amount" }
        }
      },
      { "$sort": { "total_transaction_value": -1 } }
    ]
  },

  "notification": {
    "type": "email",
    "recipients": ["riskteam@goldmanbank.com"],
    "subject_template": "Weekly High-Risk Customer Transaction Report - {run_date}",
    "body_template": "Please find attached the weekly report of high-risk customers with transactions exceeding $10,000 in the past 7 days. Report generated on {run_date} at {run_time}. Total customers flagged: {row_count}.",
    "attachment_format": "csv",
    "attachment_filename_template": "high_risk_report_{run_date}.csv"
  },

  "execution_history": [],
  "run_count": 0,
  "last_run_at": null,
  "last_run_status": null,
  "error_count": 0
}
```

---

### Step 4 — Chat Confirmation to User

```
+-------------------------------------------------------------------+
|  Report Scheduled Successfully                                    |
|                                                                   |
|  Schedule:  Every Monday at 9:00 AM (America/New_York)            |
|  Next Run:  Monday, September 7, 2026 at 9:00 AM ET              |
|  Recipient: riskteam@goldmanbank.com                              |
|  Format:    CSV attachment                                        |
|  Job ID:    JOB-001    [Pause]  [Delete]                          |
+-------------------------------------------------------------------+

Today's result (preview - 38 customers flagged this week):

| customer_id  | first_name | last_name | risk_rating | total_txn_value |
| CUST-298411  | Victor     | Marchetti | high        | $847,230.00     |
| CUST-187342  | Sandra     | Okonkwo   | high        | $512,880.00     |
| CUST-334512  | Thomas     | Beaumont  | high        | $398,140.00     |
| ... (35 more rows)                                                |
```

---

### Step 5 — Monday 9:00 AM: Celery Task Execution

```
[2026-09-07 09:00:00 ET] celery.beat  -> Triggering task: finquery.jobs.run_scheduled_query
[2026-09-07 09:00:00 ET] Task ID: task-abc-123 | Job ID: JOB-001

Step 1: Load job document from MongoDB   OK  (12ms)
Step 2: Reconstruct aggregation pipeline OK  (2ms)
Step 3: Execute pipeline against MongoDB OK  (189ms) -> 41 customers flagged
Step 4: Serialize results to CSV         OK  (34ms)  -> high_risk_report_2026-09-07.csv (87 KB)
Step 5: Compose email via SMTP relay     OK  (21ms)
Step 6: Send email to recipients         OK  (340ms) -> riskteam@goldmanbank.com
Step 7: Update scheduled_jobs document   OK  (8ms)
Step 8: Insert record into audit_logs    OK  (5ms)

Total task duration: 611ms | Status: SUCCESS
```

---

### Step 6 — The Email That Gets Sent

```
FROM:    finquery-noreply@goldmanbank.com
TO:      riskteam@goldmanbank.com
SUBJECT: Weekly High-Risk Customer Transaction Report - 2026-09-07

Dear Risk Team,

Please find attached the weekly report of high-risk customers with
transactions exceeding $10,000 in the past 7 days.

  Report Date:       Monday, September 7, 2026
  Report Time:       9:00 AM ET
  Customers Flagged: 41
  Report Period:     August 31 - September 7, 2026

This report was automatically generated by the FinQuery AI Agent.
To modify or cancel this schedule, log in to the FinQuery dashboard
and navigate to Scheduled Reports > JOB-001.

This is an automated message. Do not reply to this email.
Goldman Sachs | FinQuery AI Platform | Internal Use Only

[ATTACHMENT]: high_risk_report_2026-09-07.csv (87 KB)
  Columns: customer_id, first_name, last_name, email, phone,
           risk_rating, credit_score, transaction_count,
           total_transaction_value, last_transaction_date
```

---

### Step 7 — Updated `scheduled_jobs` Document After First Run

```json
{
  "_id": "JOB-7f3a9c21-e4b1-4d8a-b2f3-9c1e5d7a3f8b",
  "job_id": "JOB-001",
  "status": "active",

  "schedule": {
    "cron_expression": "0 9 * * 1",
    "next_run_at": "2026-09-14T09:00:00-05:00"
  },

  "execution_history": [
    {
      "run_number": 1,
      "ran_at": "2026-09-07T09:00:00-05:00",
      "status": "success",
      "rows_returned": 41,
      "execution_time_ms": 611,
      "email_delivered": true,
      "attachment_size_bytes": 89088,
      "celery_task_id": "task-abc-123"
    }
  ],

  "run_count": 1,
  "last_run_at": "2026-09-07T09:00:00-05:00",
  "last_run_status": "success",
  "error_count": 0
}
```

---

## 7. Example 5 — Failed Query with Graceful Degradation

### User Input

> **"Show me quantum risk correlation matrix for derivative exposure"**

---

### Agent Processing Steps

**`schema_retriever` attempt:**

```
Embedding query: "quantum risk correlation matrix derivative exposure"

Cosine similarity scores against all 12 collections:
  risk_events      : 0.31
  investments      : 0.28
  market_data      : 0.26
  transactions     : 0.19
  accounts         : 0.11
  (all others)     : < 0.10

Highest confidence: 0.31 (risk_events)
Threshold for proceeding: 0.40

CONFIDENCE BELOW THRESHOLD
schema_retrieval_confidence: 0.31 < 0.40

Cannot confidently map query to any collection.
Triggering graceful degradation path.
```

**`query_generator` skipped. `executor` skipped. `result_validator` skipped.**

**`response_formatter` invoked directly with degradation flag.**

---

### Response Shown to User

```
+-------------------------------------------------------------------+
|  I wasn't able to answer that question                            |
+-------------------------------------------------------------------+

I understood your request as relating to "quantum risk correlation" and
"derivative exposure," but I couldn't map this to any data in our MongoDB
collections with enough confidence to generate a reliable query.

Here's why:
  - Our system stores risk data in the 'risk_events' collection, which
    covers credit risk, fraud flags, and compliance events — but does not
    include derivative instruments or quantum risk models.
  - Correlation matrices and quantitative derivative analytics are
    typically computed by specialized risk engines (e.g., OpenGamma,
    Numerix) outside the scope of this platform's data.

What I CAN help you with in the risk domain:

  - "Show me all high-risk customers by risk_rating"
  - "List risk events flagged in the last 7 days"
  - "Which accounts have the highest credit risk score?"
  - "Show me fraud-flagged transactions above $50,000 this month"
  - "What is the risk event breakdown by type for Q3 2026?"

Would you like to try one of these, or rephrase your original question?
```

> [!NOTE]
> The graceful degradation path is triggered at the `schema_retriever` node level (confidence < 0.40) and short-circuits the rest of the pipeline. The `response_formatter` is invoked directly with `degradation=True` and `degradation_reason` fields set in the `AgentState`.

---

## 8. Example 6 — Multi-Turn Conversation

Multi-turn conversation works by persisting `conversation_history` in the `AgentState` and in Redis under the `session_id` key. Each new turn appends to the history and the `query_generator` node uses the full context to resolve pronouns and implicit references.

---

### Turn 1

**User says:**
> *"How many customers do we have in California?"*

**Agent executes:**
```json
[
  { "$match": { "address.state": "CA" } },
  { "$count": "california_customers" }
]
```

**Result:** `{ "california_customers": 8432 }`

**Agent responds:**
> *"There are **8,432 customers** in California (state: CA)."*

**Conversation history after Turn 1:**
```json
[
  {
    "role": "user",
    "content": "How many customers do we have in California?"
  },
  {
    "role": "assistant",
    "content": "There are 8,432 customers in California (state: CA).",
    "metadata": {
      "collection": "customers",
      "filter": { "address.state": "CA" },
      "count": 8432
    }
  }
]
```

---

### Turn 2

**User says:**
> *"Of those, how many have credit score above 800?"*

> [!NOTE]
> "Of those" is an implicit reference. The `query_generator` resolves "those" to California customers by reading `conversation_history[-1].metadata.filter` and merging it with the new condition.

**Agent executes:**
```json
[
  {
    "$match": {
      "address.state": "CA",
      "credit_score": { "$gt": 800 }
    }
  },
  {
    "$count": "california_high_credit_customers"
  }
]
```

**Result:** `{ "california_high_credit_customers": 1205 }`

**Agent responds:**
> *"Of the 8,432 California customers, **1,205** have a credit score above 800. That's approximately **14.3%** of your California customer base."*

**Conversation history after Turn 2:**
```json
[
  {
    "role": "user",
    "content": "How many customers do we have in California?"
  },
  {
    "role": "assistant",
    "content": "There are 8,432 customers in California.",
    "metadata": {
      "collection": "customers",
      "filter": { "address.state": "CA" },
      "count": 8432
    }
  },
  {
    "role": "user",
    "content": "Of those, how many have credit score above 800?"
  },
  {
    "role": "assistant",
    "content": "Of the 8,432 California customers, 1,205 have a credit score above 800 (14.3%).",
    "metadata": {
      "collection": "customers",
      "filter": { "address.state": "CA", "credit_score": { "$gt": 800 } },
      "count": 1205
    }
  }
]
```

---

### Turn 3

**User says:**
> *"Schedule this as a monthly report"*

> [!NOTE]
> "This" refers to the most recent query (Turn 2 pipeline and filters). The agent reuses the last `generated_pipeline` from conversation history metadata.

**Agent resolves scheduling intent:**
```json
{
  "cron_expression": "0 9 1 * *",
  "human_readable": "On the 1st of every month at 9:00 AM",
  "query_description": "California customers with credit score above 800",
  "reused_pipeline_from_turn": 2
}
```

**`scheduled_jobs` document created:**
```json
{
  "job_id": "JOB-002",
  "created_by_user_id": "usr_4421",
  "schedule": {
    "cron_expression": "0 9 1 * *",
    "human_readable": "1st of every month at 9:00 AM",
    "timezone": "UTC",
    "next_run_at": "2026-10-01T09:00:00Z"
  },
  "query": {
    "original_user_message": "How many customers do we have in California with credit score above 800?",
    "target_collection": "customers",
    "pipeline": [
      { "$match": { "address.state": "CA", "credit_score": { "$gt": 800 } } },
      { "$count": "california_high_credit_customers" }
    ]
  },
  "notification": {
    "type": "in_app",
    "recipients": ["usr_4421"]
  },
  "run_count": 0
}
```

**Agent responds:**
> *"Done! I've scheduled a monthly report for California customers with a credit score above 800. It will run on the **1st of every month at 9:00 AM UTC**, starting **October 1, 2026**. You'll receive an in-app notification with the updated count each month. (Job ID: JOB-002)"*

---

## 9. The WebSocket Message Protocol

All real-time communication between the FastAPI backend and the React frontend occurs over a single persistent WebSocket connection established at `/ws/chat`. Messages are JSON objects with a mandatory `type` discriminator field.

### Message Flow Sequence for a Typical Query

**Client sends to server:**
```json
{
  "type": "user_message",
  "session_id": "sess_f1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
  "message": "What is the total transaction volume per branch for the last 30 days?"
}
```

**Server streams back (one message per node, sent progressively):**

```json
{ "type": "thinking", "node": "schema_retriever", "message": "Identifying relevant collections..." }
```
```json
{ "type": "thinking", "node": "query_generator", "message": "Generating MongoDB aggregation pipeline..." }
```
```json
{
  "type": "query_ready",
  "query": [
    { "$match": { "transaction_date": { "$gte": "..." }, "status": "completed" } },
    { "$group": { "_id": "$branch_id", "total_volume": { "$sum": "$amount" } } },
    { "$lookup": { "from": "branches", "localField": "_id", "foreignField": "_id", "as": "branch_info" } },
    { "$sort": { "total_volume": -1 } }
  ],
  "collection": "transactions",
  "estimated_complexity": "medium"
}
```
```json
{ "type": "thinking", "node": "query_validator", "message": "Validating pipeline syntax and field names..." }
```
```json
{ "type": "executing", "message": "Running query against MongoDB Atlas...", "collection": "transactions" }
```
```json
{
  "type": "result",
  "rows": [
    { "branch_name": "Midtown Manhattan Branch", "region": "Northeast", "total_volume": 142847320.50, "transaction_count": 18432 },
    { "branch_name": "Downtown Chicago Branch",  "region": "Midwest",   "total_volume": 98234110.75,  "transaction_count": 14219 },
    { "branch_name": "Beverly Hills Branch",     "region": "West",      "total_volume": 87541990.00,  "transaction_count": 9871  }
  ],
  "total": 47,
  "execution_time_ms": 124,
  "columns": ["branch_name", "region", "total_volume", "transaction_count", "avg_transaction"]
}
```
```json
{
  "type": "answer",
  "text": "Over the last 30 days, your top-performing branch by transaction volume is the Midtown Manhattan Branch (Northeast) with $142.8M across 18,432 completed transactions...",
  "citations": ["transactions", "branches"],
  "corrections": [],
  "query_id": "qry_9d8c7b6a-e5f1-4c2d-b3a0-8e7f6d5c4b3a"
}
```

### Full Message Type Reference

| Message Type | Direction | Key Payload Fields | When Sent |
|---|---|---|---|
| `user_message` | Client to Server | `session_id`, `message` | User submits a question |
| `thinking` | Server to Client | `node`, `message` | Each LangGraph node starts executing |
| `query_ready` | Server to Client | `query` (pipeline JSON), `collection`, `estimated_complexity` | After `query_generator` completes |
| `validation_error` | Server to Client | `errors[]`, `attempt_number` | When `query_validator` fails |
| `correction_applied` | Server to Client | `correction_description`, `attempt_number` | When self-correction is triggered |
| `executing` | Server to Client | `message`, `collection` | When `executor` starts MongoDB call |
| `result` | Server to Client | `rows[]`, `total`, `execution_time_ms`, `columns[]` | After executor returns results |
| `result_suspicious` | Server to Client | `reason` | When `result_validator` flags anomaly |
| `answer` | Server to Client | `text`, `citations[]`, `corrections[]`, `query_id` | After `response_formatter` completes |
| `schedule_created` | Server to Client | `job_id`, `next_run`, `human_readable`, `cron_expression` | After `scheduler` node inserts job |
| `schedule_paused` | Server to Client | `job_id` | After user pauses a job |
| `schedule_deleted` | Server to Client | `job_id` | After user deletes a job |
| `error` | Server to Client | `code`, `message`, `recoverable` | On unrecoverable pipeline failure |
| `cache_hit` | Server to Client | `query_id`, `cached_at` | When result served from Redis |
| `ping` | Client to Server | *(none)* | Heartbeat every 30 seconds |
| `pong` | Server to Client | `server_time` | Response to ping |

### Special Error Message Example

```json
{
  "type": "error",
  "code": "SCHEMA_CONFIDENCE_TOO_LOW",
  "message": "I couldn't confidently map your question to any collection in the database. Confidence score: 0.31. Threshold: 0.40.",
  "recoverable": false,
  "suggestions": [
    "Show me all high-risk customers by risk_rating",
    "List risk events flagged in the last 7 days"
  ]
}
```

### Self-Correction WebSocket Stream

When the self-correction loop fires, the client receives this sequence of messages:

```json
{ "type": "validation_error",   "errors": ["Field 'account_status' does not exist in 'accounts'"], "attempt_number": 1 }
```
```json
{ "type": "correction_applied", "correction_description": "Field 'account_status' corrected to 'status'", "attempt_number": 1 }
```
```json
{ "type": "result_suspicious",  "reason": "Only 'closed' accounts returned; 'frozen' and 'dormant' also match 'inactive' intent" }
```
```json
{ "type": "correction_applied", "correction_description": "Value filter expanded: 'inactive' -> $in ['closed','frozen','dormant']", "attempt_number": 2 }
```

### Schedule Confirmation Message

```json
{
  "type": "schedule_created",
  "job_id": "JOB-001",
  "cron_expression": "0 9 * * 1",
  "next_run": "2026-09-07T09:00:00-05:00",
  "human_readable": "Every Monday at 9:00 AM (America/New_York)",
  "email_recipients": ["riskteam@goldmanbank.com"],
  "report_format": "csv"
}
```

---

## 10. API Endpoint Reference Table

All REST endpoints are prefixed with `/api/v1`. All endpoints except `/api/auth/login` require a valid JWT Bearer token in the `Authorization` header.

| Method | Endpoint | Description | Auth Required | Request Body | Response |
|---|---|---|---|---|---|
| `POST` | `/api/auth/login` | Authenticate user; returns JWT access token and refresh token | No | `{username, password}` | `{access_token, refresh_token, expires_in}` |
| `POST` | `/api/chat` | Submit a natural language query (non-WebSocket fallback; for testing only) | Yes | `{session_id, message}` | `{answer, query, rows, total, query_id}` |
| `GET` | `/api/jobs` | List all scheduled jobs for the authenticated user | Yes | — | `{jobs: [{job_id, status, schedule, query_description, run_count, next_run_at}]}` |
| `POST` | `/api/jobs` | Create a new scheduled job directly via REST | Yes | `{pipeline, collection, schedule, notification}` | `{job_id, created_at, next_run_at}` |
| `DELETE` | `/api/jobs/{id}` | Permanently delete a scheduled job and deregister from Celery beat | Yes | — | `{deleted: true, job_id}` |
| `PATCH` | `/api/jobs/{id}/pause` | Toggle a job between `active` and `paused` states | Yes | `{paused: true or false}` | `{job_id, status, next_run_at or null}` |
| `GET` | `/api/history` | List recent query history for the authenticated user (paginated) | Yes | Query params: `?page=1&limit=20&session_id=...` | `{queries: [...], total, page, pages}` |
| `GET` | `/api/history/{id}` | Retrieve full detail of a single past query including pipeline and raw results | Yes | — | Full `AgentState` snapshot as JSON |
| `WebSocket` | `/ws/chat` | Primary real-time bidirectional channel for the chat interface | Yes (token in query param: `?token=...`) | See WebSocket Protocol section | Streaming JSON messages |

### Request/Response Examples

**`POST /api/auth/login`**

```bash
curl -X POST https://finquery.goldmanbank.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "john.doe@goldmanbank.com", "password": "••••••••"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "user_id": "usr_4421",
    "name": "John Doe",
    "role": "analyst",
    "branch_id": "BR-NYC-001"
  }
}
```

**`GET /api/history?page=1&limit=5`**

```bash
curl https://finquery.goldmanbank.com/api/history?page=1&limit=5 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

```json
{
  "queries": [
    {
      "query_id": "qry_9d8c7b6a-e5f1-4c2d-b3a0-8e7f6d5c4b3a",
      "user_message": "What is the total transaction volume per branch for the last 30 days?",
      "final_answer": "Over the last 30 days, your top-performing branch is Midtown Manhattan...",
      "ran_at": "2026-09-03T13:14:22Z",
      "execution_time_ms": 124,
      "row_count": 47,
      "retry_count": 0,
      "cache_hit": false
    }
  ],
  "total": 142,
  "page": 1,
  "limit": 5,
  "pages": 29
}
```

**`PATCH /api/jobs/JOB-001/pause`**

```bash
curl -X PATCH https://finquery.goldmanbank.com/api/jobs/JOB-001/pause \
  -H "Authorization: Bearer ..." \
  -H "Content-Type: application/json" \
  -d '{"paused": true}'
```

```json
{
  "job_id": "JOB-001",
  "status": "paused",
  "paused_at": "2026-09-03T14:00:00Z",
  "next_run_at": null,
  "message": "Job JOB-001 has been paused. No further executions will occur until resumed."
}
```

> [!TIP]
> All API responses include a `X-Request-ID` response header for distributed tracing. Include this ID in any bug reports or support requests. Errors follow the RFC 7807 Problem Details format with `type`, `title`, `status`, `detail`, and `instance` fields.

> [!CAUTION]
> The `DELETE /api/jobs/{id}` endpoint is **irreversible**. The scheduled job document is soft-deleted (marked `status: "deleted"`) in MongoDB for audit trail purposes, but the Celery beat schedule entry is permanently removed. Deleted jobs cannot be re-activated.

---

*Document End — FinQuery AI Agent | Input/Output Examples v1.0*
