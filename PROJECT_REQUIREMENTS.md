# FinTech Agent — Project Requirements

> **Project:** FinTech Agent: Natural Language to MongoDB Query Agent for Banking Operations  
> **Course:** INT450 — Large Language Models and Agentic AI  
> **Team:** T11 · SASTRA Deemed University  
> **Status:** Requirements baseline for implementation; features are targets until implemented and tested.

---

## 1. Project Overview

### 1.1 Problem

Banking operations, risk, fraud, and compliance analysts often need answers from banking data but may not know how to write MongoDB aggregation pipelines. They depend on developers for ad-hoc questions, and a generated query can be incorrect, inefficient, or unsafe if it is not checked.

### 1.2 Proposed solution

FinTech Agent lets an analyst ask a banking-data question in ordinary language. The system identifies the user's intent, retrieves relevant database schema information, generates a MongoDB aggregation pipeline, validates it, executes it with read-only database permissions, checks whether the result answers the question, and explains the result in plain language.

The system also supports approved recurring reports. A user can ask for a report to run on a schedule; the system previews the report and schedule, obtains explicit approval, stores the job in MongoDB, and lets a single APScheduler process execute it.

### 1.3 Primary user journey

1. The analyst asks a question in the chat interface.
2. Deterministic input checks run before the raw request is sent to an LLM.
3. The workflow classifies the request: query now, query and schedule, schedule only, clarification, or out of scope.
4. The schema retriever supplies relevant collections, fields, relationships, and observed types.
5. The LLM proposes a structured MongoDB aggregation pipeline.
6. A deterministic validator checks the pipeline and its cost/safety properties.
7. A read-only executor runs the approved pipeline with bounded execution and result limits.
8. A verifier checks semantic fit and may request a bounded correction.
9. The response composer returns an explanation, result table, and relevant query details.
10. For a scheduled request, the user reviews the schedule and explicitly approves registration.

---

## 2. Goals and Success Criteria

### 2.1 Product goals

- Make supported banking-data questions answerable without requiring the analyst to write MongoDB queries.
- Generate queries grounded in the actual database schema rather than guessed collection or field names.
- Prevent database writes through the query-execution path.
- Distinguish successful database execution from a semantically correct answer.
- Support clarification and follow-up questions where conversation context is needed.
- Enable users to create and manage approved recurring reports.
- Provide enough query, result, and execution transparency for a reviewer to understand what happened.

### 2.2 Initial measurable goals

These are project targets, not achieved results:

| Measure | Initial target / rule |
|---|---|
| Benchmark coverage | Maintain a versioned benchmark with 55 cases or another explicitly approved final count. |
| Answer quality | Target at least 80% correct query-and-result outcomes on the agreed benchmark. |
| Query safety | Zero prohibited writes to the banking database during the safety test suite. |
| Retry budget | Maximum of 3 correction attempts, shared across retry paths. |
| Query execution time | Initial MongoDB `maxTimeMS` default: 15,000 ms; make configurable. |
| Returned records | Application-level cap: 1,000 documents; indicate when results are truncated. |
| Schedule dry run | Return at most 10 sample documents for preview. |
| Response latency | Initial end-to-end target: approximately 20–30 seconds; measure P50 and P90. |

Do not report a target as achieved until the benchmark or test evidence exists. The previous architecture review recorded inconsistent preliminary baseline arithmetic; recalculate all benchmark figures from raw test logs before reporting them.

---

## 3. Users and Roles

### 3.1 Primary user

**Banking operations / risk analyst** — asks questions about the synthetic banking dataset, reviews results, and may schedule recurring reports.

### 3.2 System roles

- **Authenticated application user:** may submit questions and view only the data permitted by the implemented authorization model.
- **Scheduler service:** executes approved jobs using a service identity and rechecks job status and ownership before execution.
- **Developer / administrator:** configures the application, database credentials, model provider, and deployment.

### 3.3 Authorization limitation

If the MVP uses one shared synthetic banking dataset without row-level authorization, document that limitation clearly. Do not claim per-user isolation or production banking authorization unless deterministic controls and tests actually implement it. LLM-based classification must never be the only authorization control.

---

## 4. Functional Requirements

### 4.1 User interface and API

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-01 | Provide a conversational React interface. | A user can submit a question and see the corresponding response. |
| FR-02 | Provide FastAPI endpoints for chat/query operations. | Valid requests reach the agent workflow; invalid payloads receive structured errors. |
| FR-03 | Show answer text and structured result data. | Tabular results are readable and large results show truncation. |
| FR-04 | Show the generated MongoDB pipeline for transparency. | The displayed pipeline is the validated pipeline actually executed, not an unvalidated draft. |
| FR-05 | Show progress/status for long operations. | Frontend can receive request status or progress through the selected API mechanism. |

### 4.2 Intent, context, and schema understanding

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-06 | Run deterministic input guardrails before LLM-assisted routing. | Rejected or oversized input is not sent to the LLM. |
| FR-07 | Classify request modes. | Supported modes include query-only, query-plus-schedule, schedule-only, clarification, and out-of-scope. |
| FR-08 | Retrieve relevant schema context. | Retrieved collections and fields exist in the current schema catalog. |
| FR-09 | Ask for clarification when required details are missing. | Ambiguous requests do not silently invent filters, fields, or time ranges. |
| FR-10 | Support follow-up questions. | A follow-up can use prior conversational context; resumed state is revalidated. |

### 4.3 Query generation, validation, and execution

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-11 | Generate structured MongoDB aggregation pipelines. | Output parses into the expected structured representation and is grounded in retrieved schema. |
| FR-12 | Validate pipelines recursively. | Unknown collections, fields where schema validation is available, unsupported stages, and blocked expressions are rejected. |
| FR-13 | Enforce read-only execution. | Banking database credentials are read-only and write commands are not exposed through the query executor. |
| FR-14 | Apply query cost safeguards. | Enforce stage/depth/result/time limits and inspect query plans using `queryPlanner` where supported. |
| FR-15 | Execute the validated pipeline. | Only the validated pipeline is sent to MongoDB. |
| FR-16 | Verify semantic correctness. | The system distinguishes valid empty results from errors and checks whether the result addresses the user's intent. |
| FR-17 | Perform bounded self-correction. | Correctable errors may return to query generation within a shared maximum of 3 attempts and the request deadline. |
| FR-18 | Explain the result. | Response summarizes the result without claiming facts unsupported by the returned data. |

### 4.4 Scheduled reports

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-19 | Parse natural-language schedules. | Extract query/report intent, recurrence, local time, and IANA timezone. |
| FR-20 | Preview before registration. | Show report summary, recurrence, timezone, and next 3 run times derived from the registered trigger. |
| FR-21 | Require explicit approval. | No scheduled job is registered before user approval. |
| FR-22 | Persist job definitions. | MongoDB `scheduled_jobs` is the durable source of truth. |
| FR-23 | Execute scheduled jobs. | One APScheduler process reconciles active database jobs and runs approved work. |
| FR-24 | Manage jobs. | Authorized users can list, pause, resume, and cancel/delete their jobs. |
| FR-25 | Persist job history. | Each run records status and a result reference or error summary in `job_runs`. |
| FR-26 | Handle failures. | Failures are recorded, notifications are sent only through configured channels, and repeated failures can trigger configured auto-pause behavior. |
| FR-27 | Resolve relative date ranges at execution time. | “Last 30 days” is resolved using the run-time timestamp and configured IANA timezone, not frozen at schedule creation. |

---

## 5. Non-Functional Requirements

### Security and privacy

- Keep API keys, database credentials, JWT secrets, and email passwords outside source control.
- Keep all secrets on the backend; never return them to the frontend or include them in LLM prompts.
- Use a dedicated read-only identity for `fintech_agent_db`.
- Use a separate least-privilege identity for approved writes to `agent_metadata_db`.
- Do not send raw banking query results to an external LLM. Send only bounded, redacted summaries when semantic verification or response generation requires model input.
- Treat user input, retrieved schema text, database values, and tool output as untrusted content; they must not override system policy.
- Do not execute generated Python, shell commands, JavaScript, or arbitrary code as part of query generation.
- Do not claim row-level data isolation unless it exists and is tested.

### Reliability

- Use typed request/response models and structured errors.
- Apply request deadlines and a shared retry counter across every retry edge.
- Make scheduled-job reconciliation idempotent and prevent duplicate registrations.
- Revalidate stored pipelines at scheduled execution time; never trust a previously approved pipeline without rechecking current policy.

### Performance and scale

- Bound query time, result count, pipeline depth, and lookup complexity.
- Inspect MongoDB query plans with `queryPlanner` for risk signals; do not use `executionStats` as a supposedly non-executing preflight.
- Separate development data from benchmark-scale data.
- Record actual document counts, index sizes, database size, and latency before making scale claims.

### Maintainability

- Pin tested dependency versions.
- Keep LLM provider and embedding provider configurable.
- Keep schema catalog versioned and recoverable independently of caches.
- Keep requirements, schema, tests, and implementation documentation synchronized.

---

## 6. Data Requirements

### 6.1 Banking database

Database: `fintech_agent_db`  
Currency / locale reference: INR and India (`en_IN`)  
Date-range reference from the original dataset description: 2010–2026; verify actual generated records before relying on it.

The 12 planned banking collections are:

| Collection | Purpose | Key fields / indexes documented in architecture |
|---|---|---|
| `branches` | Physical bank branches | `branch_id` (unique), `city`, `state` |
| `employees` | Bank staff and hierarchy | `employee_id` (unique), `branch_id`, `department` |
| `merchants` | Payment destination merchants | `merchant_id` (unique), `merchant_category` |
| `customers` | Customer master records | `customer_id` (unique), `kyc_status`, `risk_category` |
| `accounts` | Bank accounts per customer | `account_id` (unique), `customer_id`, `branch_id`, `status` |
| `transactions` | Financial transactions | `transaction_id` (unique), `account_id`, `customer_id`, `transaction_date`, `status` |
| `cards` | Debit and credit cards | `card_id` (unique), `customer_id`, `account_id` |
| `loans` | Loan disbursals and repayments | `loan_id` (unique), `customer_id`, `status`, `sanctioning_branch_id` |
| `kyc_documents` | KYC identity documents | `kyc_id` (unique), `customer_id` |
| `support_tickets` | Customer support tickets | `ticket_id` (unique), `customer_id`, `priority` |
| `fraud_alerts` | Fraud and suspicious activity flags | `alert_id` (unique), `transaction_id`, `customer_id` |
| `investments` | Investment portfolio records | `investment_id` (unique), `customer_id` |

**Schema rule:** These are documented key fields, not a substitute for the actual `schema.json`. Verify all fields, BSON types, optionality, nested paths, and relationship keys against the generated documents. In particular, do not assume `loans.days_past_due` or `loans.overdue_amount` exists until verified.

### 6.2 Metadata database

Database: `agent_metadata_db`  
Collections: `query_history`, `scheduled_jobs`, `job_runs`.

The metadata database stores application history and scheduled-job state. The banking query executor must not need write permissions to the banking database.

### 6.3 Data volume references

The current architecture document lists development reference counts that sum to 19,120 documents. These counts are not verified live counts. The benchmark scale plan proposes approximately 500,000 records for selected high-volume collections, subject to feasibility. Generate and verify the actual counts before publishing them.

---

## 7. LangGraph Workflow Requirements

The target workflow has **nine nodes**. The scheduler itself is an external service, not a tenth LangGraph node.

1. **Input Guardrail** — deterministic input checks before LLM use.
2. **Request Intent Router** — classify supported request mode.
3. **Schema Retriever** — retrieve relevant schema and relationship context from ChromaDB.
4. **Query Synthesizer** — generate structured MongoDB aggregation.
5. **MQL Policy Validator** — recursively validate stage/operator policy and query constraints.
6. **Read-only Query Executor** — execute only validated pipelines.
7. **Result Verifier and Recovery** — distinguish errors, legitimate empty results, and semantic mismatch; apply bounded recovery.
8. **Response Composer** — present answer, result table, and validated pipeline details.
9. **Schedule Planner and Registrar** — prepare schedule specification, perform bounded dry run, show preview, and register only after approval.

Do not describe these nine workflow nodes as nine independent autonomous agents. Some nodes are deterministic software components within one stateful workflow.

---

## 8. Safety Policy Baseline

### 8.1 Prohibited database operations

The query execution path must not provide database write or administrative operations such as insert, update, replace, delete, drop, database creation/deletion, index mutation, or collection rename.

### 8.2 Blocked aggregation features

The initial policy blocks `$out` and `$merge` stages, and blocks expression operators `$where`, `$function`, `$accumulator`, and `$eval`. This is a baseline policy and must be reviewed against the exact benchmark needs.

**Important:** Aggregation `$set` is a read-only transformation stage. It is not equivalent to a database update command. Validate the context of the operator rather than banning the string `$set` everywhere. Apply the same context-aware distinction to `$unset`.

### 8.3 Query cost safeguards

Initial architecture defaults:

- MongoDB `maxTimeMS`: 15,000 ms.
- Application result cap: 1,000 documents, with truncation indicator.
- Schedule dry-run cap: 10 documents.
- Maximum correction attempts: 3, shared across retries.
- Initial end-to-end deadline target: 20–30 seconds, configurable.

Also enforce maximum stage count and nested-pipeline depth; validate `$lookup.from` against approved collections; detect broad queries, `COLLSCAN`, and potentially unbounded joins; use `explain` with `queryPlanner` for preflight signals. Ask for clarification or explicit confirmation for expensive or overly broad queries.

---

## 9. Scheduling Requirements

- Use APScheduler for the MVP, with one scheduler process.
- Use MongoDB `scheduled_jobs` as the durable source of truth; APScheduler's in-memory jobs are reconciled from it.
- Do not add Celery Beat or a second scheduler as a competing scheduling authority.
- A schedule-only request must still retrieve schema, generate and validate the report pipeline, perform a bounded dry run, and pass verification before approval.
- Show report summary, human-readable recurrence, IANA timezone, and the next 3 run times.
- Require an explicit approval action before persisting an active job.
- Store run status and result references in `job_runs`.
- Re-check job status and owner before every run; revalidate the stored pipeline before execution.
- Support list, pause, resume, and cancel/delete operations with owner checks.
- Resolve relative date windows at each execution using the current run timestamp and job timezone.
- Email delivery is optional and must use a verified/authorized recipient address and configured provider credentials.

---

## 10. Out of Scope for the Initial MVP

- Any write/update/delete operation against the banking dataset.
- Real production banking or personally identifiable customer data.
- Mobile application frontend.
- Model fine-tuning.
- Distributed job execution infrastructure such as Celery/Redis before a measured need exists.
- Claims of production-grade regulatory compliance or row-level customer authorization without implementation and evidence.

---

## 11. Acceptance Checklist

The project is ready for a first complete demonstration when all applicable checks below pass:

- [ ] User can submit a natural-language query from the React interface.
- [ ] FastAPI validates and routes the request.
- [ ] Deterministic input guardrail runs before LLM routing.
- [ ] Intent router selects the correct supported path or asks for clarification.
- [ ] Schema retriever returns real collection/field definitions.
- [ ] Query generator emits a structured aggregation pipeline.
- [ ] Recursive validator rejects prohibited or malformed pipelines.
- [ ] MongoDB query user has read-only permissions on banking data.
- [ ] Query executor runs only the validated pipeline with time/result limits.
- [ ] Legitimate empty results are not treated as failures.
- [ ] Result verifier detects semantic mismatch and applies bounded correction.
- [ ] UI displays an explanation, result table, and validated pipeline.
- [ ] Scheduling preview requires explicit approval.
- [ ] Scheduler persists jobs and run history in MongoDB and avoids duplicates.
- [ ] Scheduled queries are revalidated at execution time.
- [ ] Benchmark results are computed from raw, reproducible test logs.
- [ ] Documentation distinguishes implemented features from planned features.

---

## 12. Open Decisions to Finalize

These choices are intentionally not hardcoded in this requirements document:

1. LLM provider and exact model ID.
2. Embedding provider/model.
3. Local MongoDB versus MongoDB Atlas deployment target.
4. Authentication provider and exact role model.
5. Whether email delivery is included in the MVP demo.
6. Actual final benchmark size and dataset scale.
7. Final set of approved aggregation stages based on the benchmark.

Update this section when a decision is made. Keep the architecture, `.env.example`, tests, and implementation aligned with the chosen values.

---

## 13. Source of Truth

Use `SYSTEM_ARCHITECTURE_UPDATED.md` as the primary technical architecture reference. This file defines product-level requirements and acceptance conditions; it does not claim that any requirement has already been implemented.
