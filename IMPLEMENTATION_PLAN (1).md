# FinTech Agent — Implementation Plan

> **Purpose:** Practical build sequence for the FinTech Agent. Complete phases in order and use the completion gates before moving to the next phase. This is a plan, not evidence that the work is already implemented.

---

## Development Rules

- Use `SYSTEM_ARCHITECTURE_UPDATED.md` as the technical source of truth.
- Keep the development dataset separate from the benchmark-scale dataset.
- Do not invent fields; `schema.json` and real MongoDB documents decide what exists.
- Do not add Redis/Celery to the MVP without a demonstrated requirement.
- Keep all banking query execution read-only.
- Test each phase before beginning the next one.
- Maintain a working application at the end of every phase.

## Phase 1 — Repository, Environment, and Banking Data

**Outcome:** A reproducible project environment with a populated and inspected MongoDB banking database.

### Tasks

1. Create the Git repository and root folder structure.
2. Choose and pin supported Python and Node.js versions.
3. Create backend and frontend dependency manifests and lockfiles.
4. Configure `.gitignore`, `.env.example`, and local `.env` handling.
5. Create or connect to MongoDB and create `fintech_agent_db`.
6. Create the 12 planned banking collections: `branches`, `employees`, `merchants`, `customers`, `accounts`, `transactions`, `cards`, `loans`, `kyc_documents`, `support_tickets`, `fraud_alerts`, and `investments`.
7. Generate/import synthetic data using a reproducible seed.
8. Verify relationships and BSON types between collections.
9. Build `schema.json` from actual collections/documents, including nested fields, observed types, optional fields, categorical values, relationship keys, and indexes.
10. Record actual document counts with MongoDB count operations; do not reuse unverified reference counts as live facts.
11. Create a dedicated read-only MongoDB user for the banking database.
12. Create a separate metadata database/user for application-owned writes.

### Deliverables

- Working local MongoDB environment.
- Reproducible dataset generator or import procedure.
- `schema.json` generated from real data.
- Verified relationship/index report.
- `.env.example` and `.gitignore`.

### Completion gate

- [ ] All planned collections exist.
- [ ] Sample documents can be queried manually.
- [ ] Document counts are measured and recorded.
- [ ] Relationship keys and BSON types are checked.
- [ ] Read-only credentials cannot write to banking collections.
- [ ] Metadata credentials cannot perform unnecessary banking-data writes.

---

## Phase 2 — Backend, Frontend, and LLM Connectivity

**Outcome:** A basic end-to-end application shell where a user can send a message and receive a model response.

### Tasks

1. Initialize FastAPI and Uvicorn.
2. Add Pydantic request/response models and structured error responses.
3. Initialize React 18 with Vite and the selected styling approach.
4. Build the chat page and basic message history UI.
5. Implement a health-check endpoint and a chat endpoint.
6. Add a configurable LLM provider adapter; keep provider/model IDs in environment/configuration.
7. Verify API key loading on the backend only.
8. Add request IDs and structured logs with secrets and sensitive values redacted.
9. Connect the frontend to the backend and display model responses.
10. Add progress streaming only if required by the agreed UI; use the architecture's REST/WebSocket approach consistently.

### Deliverables

- FastAPI service starts locally.
- React interface starts locally.
- Backend can call the selected LLM provider.
- User can send a test prompt and view the response.

### Completion gate

- [ ] Backend and frontend run from documented commands.
- [ ] Missing/invalid API keys fail with a clear configuration error.
- [ ] No credentials are included in frontend bundles, logs, or Git.
- [ ] Request/response schemas and error handling are tested.

---

## Phase 3 — Schema Catalogue and RAG Retrieval

**Outcome:** The agent can retrieve the actual banking schema relevant to a user question.

### Tasks

1. Define a canonical schema document format from `schema.json`.
2. Include collection purpose, fields, BSON types, nested paths, optionality, categorical values, indexes, and verified relationships.
3. Split schema content into useful retrieval chunks; preserve collection and field identifiers in metadata.
4. Choose and configure an embedding provider/model.
5. Create a ChromaDB persistent collection for schema vectors.
6. Implement an offline indexing command that rebuilds the vector index from a versioned schema catalogue.
7. Implement a retrieval service that returns relevant collection/field descriptions and relationship context.
8. Add schema-version and embedding-model metadata to the index.
9. Add tests for expected collection/field retrieval using the sample query catalogue.
10. Add an index rebuild procedure; do not make an in-memory cache the source of truth.

### Deliverables

- Versioned schema catalogue.
- ChromaDB schema index.
- Schema-indexing command.
- Retrieval API/module and retrieval tests.

### Completion gate

- [ ] For representative prompts, retrieved collections and fields are relevant.
- [ ] Retrieved field names match `schema.json` exactly.
- [ ] Unknown collections/fields are not invented.
- [ ] Index can be rebuilt reproducibly after schema changes.

---

## Phase 4 — Input Guardrail, Intent Routing, and Conversation State

**Outcome:** The workflow knows what the user wants and which path to take, while rejecting unsafe input before model use.

### Tasks

1. Create the LangGraph typed state definition.
2. Implement **Node 1 — Input Guardrail** as deterministic code before any LLM-assisted router.
3. Enforce request size/format limits and pre-check prohibited or unsupported requests.
4. Implement **Node 2 — Request Intent Router** with structured output.
5. Support modes: query-only, query-plus-schedule, schedule-only, clarification-required, and out-of-scope.
6. Add deterministic authorization checks outside the LLM.
7. Add clarification prompts for ambiguous business terms, unspecified metrics, and missing filters.
8. Persist/resume conversation state with an authenticated session-derived thread identifier if checkpointing is implemented.
9. Revalidate resumed state; never trust stale state as authorization.
10. Add tests for normal, ambiguous, malicious, oversized, and out-of-scope prompts.

### Deliverables

- LangGraph workflow shell with typed state.
- Input guardrail and intent-router nodes.
- Conversation/clarification handling.
- Intent and guardrail test suite.

### Completion gate

- [ ] Deterministic guardrail runs before LLM routing.
- [ ] Correct request mode is produced for sample cases.
- [ ] Ambiguous prompts trigger clarification instead of guessed fields/values.
- [ ] LLM classification cannot grant authorization.
- [ ] Prompt-injection text cannot change safety policy.

---

## Phase 5 — Query Synthesis and MQL Policy Validation

**Outcome:** The agent generates a structured MongoDB aggregation pipeline and a deterministic validator can accept or reject it.

### Tasks

1. Implement **Node 3 — Schema Retriever** in the graph using the Phase 3 retrieval service.
2. Implement **Node 4 — Query Synthesizer** using the selected LLM provider and structured output.
3. Require the prompt to include only relevant verified schema context and explicit query policy.
4. Implement **Node 5 — MQL Policy Validator** as recursive structural validation over dictionaries/lists; do not use Python AST parsing for MongoDB pipeline validation.
5. Validate one recognized operator per pipeline stage and recursively inspect nested expressions/pipelines.
6. Validate collection names and `$lookup.from` against the approved collection allowlist.
7. Block prohibited stages such as `$out` and `$merge`, and blocked expressions such as `$where`, `$function`, `$accumulator`, and `$eval` according to the policy.
8. Distinguish read-only aggregation `$set`/`$unset` stages from update/delete commands.
9. Enforce maximum stage count, nested pipeline depth, result cap, and other configurable complexity limits.
10. Add query-plan risk inspection using `explain` with `queryPlanner`; treat `COLLSCAN`/unbounded lookups as risk signals.
11. Add a bounded retry route with a shared maximum of 3 correction attempts and a total request deadline.
12. Store validated and rejected pipeline samples in the test artefacts with sensitive literals redacted.

### Deliverables

- Query synthesis node.
- Recursive MQL policy validator.
- Collection/field allowlist checks.
- Query broadness/plan safeguards.
- Validator unit tests and sample pipeline corpus.

### Completion gate

- [ ] Generated pipelines conform to the structured schema.
- [ ] Valid benchmark pipelines pass.
- [ ] Destructive operations and blocked operators fail closed.
- [ ] Aggregation `$set` is not confused with update commands.
- [ ] Unknown collections and invalid joins are rejected.
- [ ] Retry count and request deadline are enforced across all retry edges.

---

## Phase 6 — Read-only Execution, Result Verification, and Response UI

**Outcome:** A user receives a trustworthy answer backed by an executed, validated query.

### Tasks

1. Implement **Node 6 — Read-only Query Executor** with the dedicated read-only MongoDB identity.
2. Execute only the exact pipeline object that passed validation; do not regenerate or mutate it between validation and execution.
3. Apply `maxTimeMS` (initial architecture default 15,000 ms) and an application result cap (initial default 1,000 documents).
4. Implement **Node 7 — Result Verifier and Recovery**.
5. Distinguish database errors, validation failures, legitimate empty results, and semantic mismatch.
6. Verify result shape and whether the result addresses the original user intent.
7. Send only bounded/redacted result summaries to an external LLM when necessary; avoid sending raw banking records.
8. Implement **Node 8 — Response Composer**.
9. Display plain-language summary, result table, truncation indicator, and validated pipeline.
10. Preserve conversation state for meaningful follow-up questions.
11. Add audit/query history records in `agent_metadata_db`, with no unnecessary sensitive values.
12. Add end-to-end tests that compare actual results with independent gold results.

### Deliverables

- Read-only query executor.
- Result verifier and response composer.
- UI result table and pipeline display.
- Query history/audit behaviour.
- End-to-end regression tests.

### Completion gate

- [ ] Only validated read-only pipelines reach MongoDB.
- [ ] Database write attempts result in zero banking-data writes.
- [ ] Empty results are reported as valid empty results when appropriate.
- [ ] Results are compared with gold outputs on benchmark cases.
- [ ] False-success cases are identified and reduced.
- [ ] UI distinguishes answer, data, and errors clearly.

---

## Phase 7 — Scheduled Queries and Automated Reports

**Outcome:** Users can preview, approve, and manage recurring banking reports.

### Tasks

1. Implement **Node 9 — Schedule Planner and Registrar**.
2. Parse natural-language recurrence into a structured schedule specification.
3. Use IANA timezone names; do not silently assume a timezone when it materially affects the schedule.
4. For schedule-only requests, still retrieve schema, synthesize/validate the pipeline, run a bounded dry run (maximum 10 records), and verify the result.
5. Show report summary, recurrence, timezone, and next 3 run times calculated from the actual registered APScheduler trigger.
6. Require explicit user approval before storing an active job.
7. Persist approved job definitions in MongoDB `scheduled_jobs`.
8. Run one APScheduler process that periodically reconciles in-memory jobs with the MongoDB source of truth.
9. Recheck job status/owner and revalidate stored MQL at execution time.
10. Persist each execution outcome and result reference/error summary in `job_runs`.
11. Support list, pause, resume, and cancel/delete operations with owner checks.
12. Resolve relative date windows at run time.
13. Add configurable failure notifications and auto-pause after the configured consecutive failure threshold.
14. Add email delivery only after a verified recipient and provider configuration are available.
15. Add idempotency and duplicate-registration tests.

### Deliverables

- Schedule parser and preview UI.
- Approval flow.
- MongoDB-backed job registry and run history.
- One APScheduler service and reconciliation logic.
- Job management APIs/UI and scheduler tests.

### Completion gate

- [ ] No job is registered without explicit approval.
- [ ] Next 3 run times match the real APScheduler trigger.
- [ ] Restart/reconciliation restores active jobs without duplicates.
- [ ] Ownership is checked for every job operation and run.
- [ ] Stored pipelines are revalidated before scheduled execution.
- [ ] Relative date ranges move with the execution date.
- [ ] Pause/resume/cancel and failure handling are tested.

---

## Phase 8 — Benchmarking, Security Review, Deployment, and Demo

**Outcome:** The full application is reproducibly tested and ready for evaluation/demo.

### Tasks

1. Finalize the benchmark set and denominator; keep stable question IDs.
2. Create independent gold pipelines/results using the fixed dataset.
3. Run all six evaluation tiers: basic filters, aggregation, multi-collection lookups, temporal analytics, adversarial/security, and scheduling/job management.
4. Measure query execution accuracy, pipeline validity, semantic correctness, result equivalence, recovery rate, false-success rate, retrieval accuracy, safety rejection, zero-write safety, P50/P90 latency, token use, schedule correctness, and schedule reliability.
5. Recalculate all percentages from raw run logs; explain exclusions and denominators.
6. Generate benchmark-scale data only after development tests pass; preserve relationship integrity and verify counts/indexes.
7. Conduct a security review of credentials, logs, prompt injection, query validation, data permissions, job ownership, and secret handling.
8. Add monitoring, meaningful error messages, and operational runbooks.
9. Deploy frontend/backend/database according to selected hosting plan.
10. Prepare demo scenarios covering simple query, follow-up, multi-collection query, refusal, empty result, and scheduled report.
11. Update documentation to distinguish completed, partial, and future capabilities.

### Deliverables

- Reproducible benchmark report.
- Security/test report.
- Deployed demo or documented local demo environment.
- Final architecture and operating instructions.
- Demonstration script.

### Completion gate

- [ ] All benchmark cases have stable IDs and gold expectations.
- [ ] Results are reproducible from the recorded dataset/version.
- [ ] Security negative tests pass.
- [ ] No unsupported implementation claims remain in documentation.
- [ ] Demo setup works from a clean checkout using the documented steps.

---

## Cross-Phase Definition of Done

A phase is complete only when:

1. Its deliverables exist in the repository.
2. Automated tests for the phase pass.
3. Manual verification steps are recorded where automation is not practical.
4. `.env.example`, README, architecture, and relevant requirements are updated.
5. No secrets, personal banking data, or generated credentials are committed.
6. The agent report lists changed files, commands run, test results, known limitations, and next blockers.

## Suggested MVP Cut Line

The first complete conversational agent is achieved after **Phase 6**. Phase 7 adds scheduled reports. Phase 8 makes the system measurable, safer to demonstrate, and deployable. Do not delay the first end-to-end query demonstration until every advanced scheduling feature is complete.
