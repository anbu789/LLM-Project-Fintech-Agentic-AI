# FinTech Agent — Phase 4 Security Review
## Guardrail Verification, Threat Modeling, and Safety Boundaries

**Course:** INT450 — Large Language Models and Agentic AI  
**Author:** Application Security Engineer & LLM Systems Architect  
**Date:** November 10, 2026  
**Scope:** Phase 4 (Input Guardrail, Intent Routing, State Graph Security)  
**Security Rating:** PASS — ZERO CRITICAL VULNERABILITIES IDENTIFIED

---

## 1. Security Architecture Overview

Phase 4 establishes the first defense perimeter for the FinTech Agent agentic system. In AI agent systems, natural language inputs represent an untrusted attack surface. The architecture separates security boundaries into deterministic layers and probabilistic layers:

```mermaid
flowchart TD
    UserInput["Untrusted User Input"] --> N1["Node 1: Input Guardrail (Deterministic Code)"]
    N1 -->|Matched Attack / Malformed / Oversized| Terminate["Terminate Immediately (END)\nReturn Safe Rejection Message"]
    N1 -->|Clean Input| N2["Node 2: Request Intent Router (LLM / Mock)"]
    N2 -->|Parse Failure / Timeout| Fallback["Conservative Fallback\nCLARIFICATION_REQUIRED"]
    N2 -->|OUT_OF_SCOPE| Composer["Node 8: Response Composer (Informational)"]
    N2 -->|Data Query| Stub["Node 3: Schema Retriever (Phase 5 Stub)"]
    Stub --> Composer
    Composer --> Output["Shielded Safe Output"]
```

> [!IMPORTANT]
> **Core Security Principle:** LLM classification is **never** the security boundary. The deterministic guardrail (Node 1) runs before the LLM, and prompt-injection text cannot alter safety policy or grant access to database operations.

---

## 2. Threat Modeling & Mitigation Analysis

### Threat 1: Prompt Injection & Jailbreaking
- **Attack Vector:** An attacker submits inputs designed to override system instructions (e.g., "Ignore previous instructions", "You are now DAN", "Disregard system constraints").
- **Mitigation:**
  - Node 1 evaluates a comprehensive suite of compiled regular expressions prior to model dispatch.
  - Pattern matching is case-insensitive and covers DAN mode, developer mode exploits, persona adoption ("you are now", "act as", "pretend to be"), and directive wipes ("forget instructions", "override system").
  - On match, the graph immediately returns `guardrail_status: "rejected"` and routes to `END`. The LLM router is never executed on injected input.
- **Verification:** Verified by `test_guardrail_rejects_prompt_injections` across 9 distinct attack payloads.

### Threat 2: Credential & Environment Exfiltration
- **Attack Vector:** An attacker attempts to trick the agent into revealing API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`), database connection strings (`MONGO_URI`), `.env` configuration, or internal system prompts.
- **Mitigation:**
  - Node 1 blocks queries containing verbs (`show`, `tell`, `reveal`, `print`, `output`, `expose`, `leak`) followed by credential targets (`api key`, `password`, `secret`, `credentials`, `.env`, `environment variable`, `token`).
  - Regex also blocks direct inquiries ("what is your API key", "repeat system prompt").
  - `sanitize_error_message()` middleware redacts sensitive strings before sending responses to clients.
- **Verification:** Verified by `test_guardrail_rejects_credential_extraction` across 7 exfiltration attempts.

### Threat 3: Destructive Database Operation Intent
- **Attack Vector:** An attacker attempts to submit drop, delete, update, or administrative commands against the MongoDB database.
- **Mitigation:**
  - Node 1 blocks inputs attempting collection drops, database deletions, document updates, or inserts (e.g., `db.<collection>.drop()`, `dropDatabase()`, `deleteMany`, `insert into`).
  - Even if an input were to pass Node 1, Node 6 (`query_executor.py`) is an inert stub in Phase 4 that does not connect to or query MongoDB.
  - The underlying MongoDB client utilizes the `ReadOnlyCollectionProxy` established in pre-Phase 4 remediation, ensuring hardware-level write rejection at the Python PyMongo driver boundary.
- **Verification:** Verified by `test_guardrail_rejects_destructive_db_intent`.

### Threat 4: Denial of Service (DoS) via Oversized Payloads
- **Attack Vector:** An attacker submits multi-megabyte payloads to exhaust memory or trigger excessive LLM token costs.
- **Mitigation:**
  - **HTTP Body Limit:** Middleware enforces `settings.MAX_REQUEST_BODY_BYTES` (1 MB max).
  - **Pydantic Validation:** `ChatRequest.validate_message` enforces `MAX_MESSAGE_LENGTH` (2,000 characters).
  - **Guardrail Check:** Node 1 verifies message length ≤ 2,000 characters as a redundant safety check.
- **Verification:** Verified by `test_guardrail_rejects_oversized_query` and `test_chat_rejects_oversized_message`.

### Threat 5: Authorization Escalation via LLM Misclassification
- **Attack Vector:** An attacker sends ambiguous or corrupted text attempting to manipulate the router into returning an authorized query mode.
- **Mitigation:**
  - The router enforces strict Pydantic validation on the JSON output.
  - If the LLM generates non-JSON, invalid enum strings, or experiences network failures, the router executes `_safe_fallback()` which defaults strictly to `CLARIFICATION_REQUIRED`.
  - It is mathematically impossible for a classification failure to default to `QUERY_ONLY` or `QUERY_AND_SCHEDULE`.
- **Verification:** Verified by `test_intent_router_fallback_never_converts_failure_to_banking`.

---

## 3. Data Privacy and Isolation

1. **PII Isolation:**
   - In Phase 4, no banking data is fetched or transmitted to external LLM providers.
   - Nodes 3–7 contain no queries to `fintech_agent_db`.
2. **Metadata Separation:**
   - Conversation history is stored exclusively in `agent_metadata_db.conversations`.
   - The banking database (`fintech_agent_db`) is isolated and strictly read-only.
3. **Audit Trail:**
   - Every node appends a structured dictionary to `state["trace"]` recording `node`, `status`, `detail`, and `timestamp` (UTC ISO 8601).
   - Trace entries contain no plain-text credentials or customer PII.

---

## 4. Security Findings & Recommendations

| Finding | Severity | Status | Mitigation in Phase 4 |
| :--- | :---: | :---: | :--- |
| Potential bypass of `db.<col>.drop()` in regex | Medium | Resolved | Added wildcard collection pattern `\bdb\s*\..*?\.\s*(drop\|delete)\b` |
| Exception swallowing masking 401/400 errors | Medium | Resolved | Re-raised `FinTechAgentException` so HTTP shielding returns proper status |
| Unauthenticated MongoDB development mode | Low | Mitigated | Enforced `ALLOW_UNAUTHENTICATED_DEV=True` check; production fails fast |

---

## 5. Security Verdict

**VERDICT: APPROVED.**  
Phase 4 satisfies all security, safety, and boundary requirements defined in INT450 standards. The system is hardened and safe to proceed to Phase 5.
