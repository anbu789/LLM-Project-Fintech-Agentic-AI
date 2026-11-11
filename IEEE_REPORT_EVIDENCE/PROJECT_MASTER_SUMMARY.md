# FINTECH AGENT — MASTER PROJECT EVIDENCE AUDIT & SYSTEM SUMMARY
**Course:** INT450 — Large Language Models and Agentic AI  
**Institution:** School of Computing, SASTRA Deemed University, Thanjavur, Tamil Nadu, India  
**Team:** T11 (Fall / Academic Term 2026)  
**System Title:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Auditor Roles:** Principal Software Architect, Senior Python Engineer, LangGraph Specialist, MongoDB Security Auditor, LLM Systems Researcher & Academic Documentation Specialist  
**Audit Completion Date:** November 16, 2026  
**Repository Branch / Commit Baseline:** `master` @ `ee353ef` (with hardened working-tree multi-provider fallback & execution monitor updates)

---

## 1. Executive Summary: Implemented Reality vs. Documented Claims

This audit provides an exhaustive, evidence-based technical inventory of the FinTech Agent repository. Every statement of fact is grounded strictly in executable code, verified configurations, automated test suites, and empirical logs. 

### 1.1 What the System Actually Implements
The FinTech Agent is a **stateful, single-graph 9-node pipeline orchestrated with LangGraph (v1.2.20) and FastAPI (v0.162.2)**, fronted by a **React 18 / Vite / TailwindCSS / Zustand** web interface, backed by **ChromaDB (v1.5.9)** for schema grounding, and protected by **multi-tier deterministic defensive guardrails**.

1. **Deterministic Input Guardrail (Node 1):** Regex-enforced, LLM-free detection of empty input, message length overruns (>2,000 chars), prompt injection patterns (DAN mode, "ignore previous instructions"), credential exfiltration attempts, and destructive database commands (`drop`, `deleteMany`, `remove`).
2. **Request Intent Router (Node 2):** LLM-based classification into five discrete `RequestMode` categories (`QUERY_ONLY`, `QUERY_AND_SCHEDULE`, `SCHEDULE_ONLY`, `CLARIFICATION_REQUIRED`, `OUT_OF_SCOPE`) with safe fallback to clarification.
3. **ChromaDB Schema Retriever (Node 3):** Cosine vector search over 269 pre-indexed schema catalog chunks in `chroma_data` (`hnsw:space = cosine`), augmented with automated banking glossary expansion and regex shielding for unsupported loan concepts.
4. **MQL Query Synthesizer (Node 4):** Pydantic-validated candidate aggregation pipeline generation conforming to strictly retrieved schema chunks, with zero direct database connection.
5. **Deterministic MQL Policy Validator (Node 5):** AST traversal engine enforcing collection allowlists (12 canonical banking collections), stage allowlists (read-only stages only; explicit blocking of `$out`, `$merge`), operator allowlists (prohibiting `$where`, `$accumulator`, `$function`), schema field verification, foreign-key join verification, complexity limits (max 20 stages, max depth 10), and mandatory terminal `$limit` capping.
6. **Read-Only Query Executor (Node 6):** Sandboxed database execution layer with a 7-point fail-closed gate. Under default development configuration (`PHASE6_LIVE_EXECUTION_ENABLED=False`), live execution against the original banking database is intercepted with `GATE_BLOCKED`. Real aggregation execution is tested against isolated test fixtures (`state['test_db']`).
7. **Result Verifier & Recovery (Node 7):** Data sanitization (BSON `ObjectId`, `datetime`, exact `Decimal128` preservation), outcome classification (`VALID_WITH_DATA`, `VALID_EMPTY`, `RETRYABLE_ERROR`), and bounded retry loop back to executor for transient faults.
8. **Schedule Planner & Registrar (Node 8 in execution order / Node 9 in architecture):** Recurrence parsing (daily, weekly, monthly, cron), IANA timezone validation (`zoneinfo`), projection of next 3 execution timestamps via `APScheduler` (`CronTrigger`), dry-run preview generation, and preparation of immutable schedule previews for explicit user approval.
9. **Response Composer (Node 9 in execution order / Node 8 in architecture):** Final plain-language markdown response generation with pipeline explanation, execution metrics badge, and gate status notices.
10. **Multi-Provider LLM Fallback (Service Layer):** Resilient failover chain spanning **Google Gemini 3.8 Flash** (`gemini-3.8-flash`) as primary, failing over to **Groq GPT-OSS 120B** (`openai/gpt-oss-120b`), and **Local Ollama** (`hf.co/mradermacher/K2-Horizon-3.7B-i1-GGUF:Q3_K_M`), bounded by an absolute operation deadline (24.0s).
11. **Cryptographic Identity & Multi-Tenancy:** Zero caller-controlled headers; HMAC-SHA256 URL-safe Bearer tokens enforce tenant isolation across recurring schedules.

---

## 2. Quantitative Verification Status Summary

| Area / Investigation | Claimed in Documents | Verified Repository Reality | Evidence Classification |
| :--- | :--- | :--- | :--- |
| **Banking Dataset Size** | "~18,700 documents" (`README_DATASET.md`) | Exactly **19,120 documents** across 12 collections in `fintech-agent/data/exports/json/` | `VERIFIED` |
| **Original Data Immutability** | Zero writes to banking data | All 19,120 documents remain 100% unmodified across all test runs | `VERIFIED` |
| **Backend Test Suite** | 129 -> 205 -> 304 -> 323 passing | **368 tests collected & passing** across 17 test modules in `backend/tests/` | `VERIFIED` |
| **Frontend Test Suite** | 8 component tests passing | **21 unit/integration tests passing** in `frontend/src/test/ChatApp.test.jsx` (Vitest) | `VERIFIED` |
| **RAG Retrieval Quality** | Unverified / 78% token reduction | 18 banking test cases evaluated: 100% hit rate, 97.22% Recall@5, 90.74% MRR (`PRE_PHASE4_RAG_EVALUATION.md`) | `VERIFIED` (Mock Embeddings) |
| **MQL Synthesis Validity** | 18 archetypes validated | 18 representative banking archetypes pass all 5 validation criteria (`PHASE5_RAG_AND_QUERY_EVALUATION.md`) | `VERIFIED` |
| **55-Question Accuracy** | **90.9% (50/55) Agent vs 61.8% (34/55) Baseline** | **Not independently verifiable**. No gold query outputs or benchmark execution scripts exist in repo. | `REPORTED_NOT_VERIFIED` |
| **Self-Correction Convergence** | 75.0% (9/12) | **Not independently verifiable**. Denominator and execution logs are absent. | `REPORTED_NOT_VERIFIED` |
| **Latency P50 / P90** | P50: 2.4s, P90: 3.2s | **Not independently verifiable**. Historical design estimates, not measured benchmark percentiles. | `REPORTED_NOT_VERIFIED` |
| **Native MongoDB Auth** | Production-grade RBAC | Script `scripts/mongo_init_auth.js` exists, but `MONGO_AUTH_ENABLED=False` in current runtime | `BLOCKED_BY_CONFIGURATION` |
| **Live Database Execution** | Sandboxed live query execution | Fail-closed gate `PHASE6_LIVE_EXECUTION_ENABLED=False` blocks live execution against banking DB | `BLOCKED_BY_CONFIGURATION` |
| **Scheduled Background Runs** | Autonomous Celery/APScheduler | Single-runner APScheduler implemented, but `PHASE7_SCHEDULER_ENABLED=False` in active runtime | `BLOCKED_BY_CONFIGURATION` |

---

## 3. Core Evidence Findings for the IEEE Conference Paper

1. **Agent Workflow vs. Autonomous Agents:** The system is **NOT** a collection of independent multi-agent entities. It is a single, deterministic-governed state machine implemented with LangGraph's cyclic `StateGraph`. The paper must accurately describe it as a **"Deterministic-Guarded Multi-Stage Agentic Workflow"**.
2. **Defensive Architecture is the Core Novelty:** The primary academic contribution is the **defense-in-depth isolation between untrusted LLM outputs and the underlying database**. Even if the LLM hallucinates malicious syntax, the deterministic AST validator (Node 5) and the 7-stage fail-closed execution gate (Node 6) make data exfiltration or modification structurally impossible.
3. **The Financial Semantics Discovery:** A major empirical contribution is the identification and formal remediation of retail credit risk ambiguity: distinguishing **Remaining Principal Balance** (`outstanding_amount`) from **Contractual Default** (`status: "defaulted"`) and **Overdue Debt / Arrears** (`overdue_amount`, `days_past_due` — which do not exist in the schema). The agent safely rejects overdue arrears queries rather than returning misleading financial balances.
4. **Multi-Provider Fault Tolerance:** The live system incorporates a 3-tier fallback hierarchy (Gemini 3.8 Flash -> Groq 120B -> Local Ollama) to eliminate single-point-of-failure cloud outages, bounded within a 24-second request deadline.
5. **Academic Honesty Requirement:** The paper must report the verified 368 backend unit/integration tests and the 18-case RAG/synthesis benchmark, while clearly qualifying the 55-question natural language benchmark as an evaluation catalog whose full execution harness remains an open milestone.

---

## 4. Evidence Package Directory Structure

The complete evidence audit is distributed across the following dedicated documents in `IEEE_REPORT_EVIDENCE/`:

```
IEEE_REPORT_EVIDENCE/
├── PROJECT_MASTER_SUMMARY.md              # (This document) Executive overview and verified reality
├── TEAM_INFORMATION.md                   # Team identity, academic context, faculty, and problem statement
├── ARCHITECTURE_EVIDENCE.md              # 9-node LangGraph topology, routing rules, and Mermaid diagram
├── DATASET_AND_RAG_EVIDENCE.md           # 12 collections, 19,120 documents, ChromaDB vector store
├── LLM_AND_QUERY_GENERATION_EVIDENCE.md  # Multi-provider fallback, prompts, and JSON output schemas
├── SECURITY_AND_LIMITATIONS_EVIDENCE.md  # Guardrails, MQL policy AST, fail-closed gates, and limitations
├── SCHEDULING_EVIDENCE.md                # Recurrence parsing, APScheduler triggers, and approval flow
├── IMPLEMENTATION_EVIDENCE.md            # Tech stack, pinned versions, hardware specs, and run procedures
├── EVALUATION_EVIDENCE.md                # Benchmark investigation, 18-case RAG, and arithmetic verification
├── FAILURE_ANALYSIS.md                   # Systematic taxonomy of observed vs theoretical failures
├── FRONTEND_EVIDENCE.md                  # React/Vite UI architecture, state management, and user journey
├── AUTHOR_CONTRIBUTIONS.md               # Git audit, contributor allocation, and mentor acknowledgments
├── CONTRADICTION_REGISTER.md             # Prioritized register of 12 documented vs implemented conflicts
├── MISSING_INFORMATION.md                # Action items and data required from the student team
├── IEEE_REPORT_DATA.json                 # Machine-readable structured evidence for IEEE drafting
├── VERIFIED_RESULTS.json                 # Verified experimental benchmark data
└── VERIFIED_RESULTS.csv                  # Tabular export of verified experimental results
```
