# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are banking operations, risk, fraud, and compliance analysts working in an internal academic/demonstration setting who need answers from banking records and recurring operational reports without writing MongoDB aggregation pipelines or waiting on data engineering tickets.

Secondary system roles:
- **Developer / administrator:** configures local Windows services, MongoDB read-only RBAC credentials, LLM/embedding providers, and fail-closed live-execution gates.
- **Scheduler runner:** single APScheduler background service reconciling and executing explicitly approved recurring jobs under lease control.

## Product Purpose

FinTech Agent turns plain-language banking questions and reporting requests into schema-grounded, deterministically validated, read-only MongoDB aggregation pipelines and explicit-approval recurring schedules. Success means analysts receive accurate, verifiable explanations, tabular results, and inspectable MQL pipelines from the synthetic banking dataset (`fintech_agent_db`, 19,120 documents) without risking database writes, unbounded queries, or unapproved automated jobs.

## Positioning

A sandboxed, deterministic-gated 9-node LangGraph NL-to-MongoDB workflow purpose-built for banking operations: it pairs ChromaDB vector schema retrieval (`chroma_data/`) and semantic result verification with recursive MQL AST policy validation, strict dual-database separation (`fintech_agent_db` read-only banking data vs `agent_metadata_db` metadata/schedules), SHA-256 preview-locked human approval for recurring APScheduler reports, and fail-closed live-execution gates (`PHASE6_LIVE_EXECUTION_ENABLED=False`, `PHASE7_SCHEDULER_ENABLED=False` by default).

## Operating Context

- **Runtime environment:** Local Windows 10/11 application (`start_project.bat`, `start_scheduler.bat`, `run_tests.bat`) serving a React 18 + Vite frontend (`localhost:5173`, proxying `/api` to `127.0.0.1:8001`), a FastAPI backend (`127.0.0.1:8001`), MongoDB (`localhost:27017`), and local ChromaDB persistence (`chroma_data/`).
- **Primary query workflow:** Analyst submits a natural-language question (up to 2,000 characters) -> deterministic Input Guardrail -> Intent Router (banking Q&A, query, query+schedule, schedule-only, clarification, or out-of-scope) -> Schema Retriever -> Query Synthesizer -> MQL Policy Validator -> Read-only Query Executor -> Result Verifier & bounded recovery (up to 3 attempts) -> Response Composer returning plain-language explanation, tabular data, and the validated pipeline.
- **Recurring report workflow:** Natural-language schedule request -> recurrence parsing (daily, weekly, monthly, or 5-field cron) in IANA timezones (default `Asia/Kolkata`) -> immutable dry-run preview (capped at 10 sample docs, next 3 projected fire times, SHA-256 pipeline hash, 15-minute expiry) -> explicit user approval -> durable job persisted in `agent_metadata_db.scheduled_jobs` with pause, resume, cancel, and `job_runs` history management.
- **Dynamic relative dates:** Relative windows (such as `$$DAYS_AGO_30`) stay dynamic and are resolved at scheduled run time in the configured IANA timezone rather than frozen at creation time.

## Capabilities and Constraints

- **9-node LangGraph + single APScheduler authority:** Scheduling is handled by one external APScheduler runner (`scheduler_runner.py`) using `scheduler_leases` for distributed lease coordination; do not introduce Celery, Redis, or a second scheduler.
- **Strict read-only banking data & MQL policy gate:** Write/admin operations and unsafe expressions (`$out`, `$merge`, `$where`, `$function`, `$accumulator`, `$eval`) are blocked; `$set`/`$unset` are validated contextually as aggregation stages; `$lookup.from` is validated against the 12 approved collections (`accounts`, `branches`, `cards`, `customers`, `employees`, `fraud_alerts`, `investments`, `kyc_documents`, `loans`, `merchants`, `support_tickets`, `transactions`).
- **Execution bounds:** Default `QUERY_TIMEOUT_MS=15000`, `RESULT_DOC_LIMIT=1000`, `MAX_MESSAGE_LENGTH=2000`, `MAX_CONVERSATION_HISTORY_TURNS=10`, terminal `$limit` validation (`<= 100` in current policy), and consecutive-failure auto-pause (3 failures) on scheduled jobs.
- **Fail-closed live gates (current state):** `PHASE6_LIVE_EXECUTION_ENABLED=False`, `PHASE7_SCHEDULER_ENABLED=False`, `PHASE7_LIVE_REGISTRATION_ENABLED=False`, and `MONGO_AUTH_ENABLED=False` by default for safe local demonstration.
- **Auth boundary (open product decision):** Backend schedule endpoints enforce HMAC-SHA256 Bearer tokens (`POST /api/v1/auth/token`) and server-side tenant isolation, while the current React client (`frontend/src/services/api.js`) operates in an unauthenticated local demo flow without a sign-in UI. Whether to expose analyst login/token acquisition in the web UI remains undecided.
- **Schema grounding constraint:** Financial terms must match verified fields in `fintech-agent/data/schema.json` and `BANKING_GLOSSARY.md` (for example, defaulted loan principal uses `loans.outstanding_amount`; do not invent unverified fields such as `days_past_due` or `overdue_amount`).

## Brand Commitments

- **Product identity:** Present the product as **FinTech Agent** (Banking Operations / Banking Intelligence Assistant).
- **Academic attribution:** Preserve `Team T11 · INT450` only as subtle secondary branding in the sidebar while dropping obsolete `Phase 2` and `INT450 LLM Shell` prototype labels.
- **Preserved trust commitments:** Always preserve strict read-only banking guardrails, explicit human approval before any scheduled report becomes active, and transparency of the exact validated MQL pipeline.
- **Synthetic-only truth:** All banking records and sample scenarios represent the local synthetic dataset (`fintech_agent_db`, 19,120 documents); never represent synthetic data as live production banking records or claim regulatory compliance certifications.

## Evidence on Hand

- **Synthetic banking dataset & schema:** `fintech-agent/data/schema.json`, `fintech-agent/data/exports/` (19,120 documents across 12 collections), `fintech-agent/data/test_questions.json`.
- **Domain terminology & prompt benchmarks:** `BANKING_GLOSSARY.md`, `SAMPLE_QUERIES.md`.
- **Architecture, requirements & verification:** `SYSTEM_ARCHITECTURE_UPDATED.md`, `PROJECT_REQUIREMENTS.md`, `FINAL_RUN_GUIDE.md`, `FINAL_PROJECT_ACCEPTANCE_REPORT.md`, `PHASE7_IMPLEMENTATION_REPORT.md`.
- **Application code:** `backend/app/`, `frontend/src/`.
- **Absences not to fabricate:** No real customers, bank logos, external testimonials, press mentions, production SLA guarantees, or real PII exist or may be invented in future surfaces.

## Product Principles

1. **Safety Before Convenience:** Enforce deterministic MQL policy validation, read-only banking isolation, and fail-closed live gates without workarounds.
2. **Explicit Approval Before Automation:** Never register or activate a recurring report until the user reviews the recurrence, timezone, upcoming fire times, dry-run preview, and validated pipeline and explicitly approves it.
3. **Verifiable Grounding Over Plausibility:** Anchor answers to verified schema collections and fields, surface truncation and empty-result states honestly, and expose the exact validated pipeline.
4. **Operational Banking Clarity:** Use crisp banking-operations and risk-analysis terminology in user-facing copy, free of academic course/team tags or raw implementation jargon where plain language serves better.
