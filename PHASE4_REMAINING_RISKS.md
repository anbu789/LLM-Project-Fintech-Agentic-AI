# FinTech Agent — Phase 4 Remaining Risks & Future Scope
## Open Limitations, Technical Debt, and Phase 5 Readiness

**Course:** INT450 — Large Language Models and Agentic AI  
**Author:** Senior Backend Engineer & LLM Systems Architect  
**Date:** November 10, 2026  
**Milestone:** Post-Phase 4 Risk Assessment  

---

## 1. Overview

While Phase 4 has successfully implemented the LangGraph state machine, Node 1 (Input Guardrail), and Node 2 (Request Intent Router), several functional areas remain intentionally unimplemented in accordance with the strict single-phase milestone scope.

This document inventories all remaining risks, operational assumptions, and architectural prerequisites for **Phase 5 (Schema Retrieval & MQL Pipeline Synthesis)** and **Phase 6 (Execution, Verification & Recovery)**.

---

## 2. Inventory of Remaining Risks

### Risk 1: Future-Phase Stubs Lack Functional Query Capabilities
- **Risk Description:** Nodes 3–7 and Node 9 are currently registered as safe stubs. While this fulfills Phase 4 criteria by proving graph topology and isolation, users submitting valid data queries (`QUERY_ONLY`) receive an informational placeholder acknowledging intent rather than real banking data.
- **Severity:** Informational (Expected by Design in Phase 4).
- **Remediation Plan for Phase 5:**
  - Implement Node 3 (`schema_retriever.py`) to connect ChromaDB schema chunks using the Phase 3 vector store.
  - Implement Node 4 (`query_synthesizer.py`) to generate read-only MongoDB aggregation pipelines.
  - Implement Node 5 (`mql_policy_validator.py`) with recursive stage inspection and operator allowlists.

### Risk 2: Real Neural LLM Evaluation Pending Production Keys
- **Risk Description:** Automated test suites utilize `MockLLMProvider` (`LLM_PROVIDER=mock`) for deterministic classification. While mock tests verify regex guardrails, routing paths, and Pydantic validation, the semantic accuracy of complex natural language classification using live models (e.g., Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro) has not been benchmarked with live network traffic in CI.
- **Severity:** Medium.
- **Mitigation in Place:**
  - `BaseLLMProvider` and structured JSON prompting are fully implemented in `intent_classification.py`.
  - Pydantic validation guarantees that any live LLM output that deviates from the schema triggers conservative fallback (`CLARIFICATION_REQUIRED`).
- **Remediation Plan for Phase 5:**
  - Execute a live provider verification run once dedicated API credentials with sufficient quota are configured.

### Risk 3: MongoDB Server-Side Authentication Disabled in Development
- **Risk Description:** MongoDB is currently running with `ALLOW_UNAUTHENTICATED_DEV=True` without native server-side authentication (`MONGO_AUTH_ENABLED=False`). While PyMongo client-level write blocking (`ReadOnlyCollectionProxy`) strictly prevents mutations, defense-in-depth requires native MongoDB role-based access control.
- **Severity:** Low (in local development); High (in production).
- **Mitigation in Place:**
  - `config.py` enforces fail-fast crashes if `APP_ENV=production` is run without `MONGO_AUTH_ENABLED=True` and distinct dual-database credentials.
  - Scripts `scripts/mongo_init_auth.js` have been audited to require explicit non-empty environment passwords.
- **Remediation Plan:**
  - Prior to production deployment, enable `--auth` on the MongoDB daemon and provision separate `banking_readonly_user` and `metadata_app_user` accounts.

### Risk 4: Context Window Limits on Extended Multi-Turn Conversations
- **Risk Description:** The system persists full conversation history in `agent_metadata_db.conversations`. In Node 2, the prompt builder includes the last 2 turns (4 messages), and `BaseLLMProvider` applies a sliding window of `MAX_CONVERSATION_HISTORY_TURNS * 2 = 20` messages. Very long conversations with extensive follow-up questions might lose earlier context if topics shift frequently.
- **Severity:** Low.
- **Mitigation in Place:**
  - The 20-message sliding window is standard for operational banking analytics sessions.
  - Frontend provides a "New Chat" button to reset the session context cleanly.

---

## 3. Phase 5 Readiness Matrix

| Architectural Component | Phase 4 State | Phase 5 Prerequisite | Readiness Verdict |
| :--- | :--- | :--- | :---: |
| **Agent StateGraph** | 9 nodes registered & compiled | Ready for Node 3 & 4 implementation | **READY** |
| **AgentState TypedDict** | Fully defined (Section 10) | State schema matches all phase needs | **READY** |
| **Input Guardrail (Node 1)** | Fully operational & tested | Protects entry into Phase 5 nodes | **READY** |
| **Intent Router (Node 2)** | Fully operational & tested | Directs `QUERY_ONLY` to Node 3 | **READY** |
| **Schema Catalog & Vector RAG** | Built & validated in Phase 3 | Ready for Node 3 integration | **READY** |
| **Read-Only Mongo Proxy** | Hardened in Pre-Phase 4 | Ready for sandboxed query execution | **READY** |
| **API Chat Route** | Fully integrated with graph | Ready for pipeline response payload | **READY** |

---

## 4. Final Phase 4 Recommendation

**VERDICT: COMPLETE — PHASE 4 READY FOR PHASE 5.**

The system is secure, stable, and architecturally aligned. Development may proceed directly to Phase 5: Schema Retrieval & MongoDB Aggregation Pipeline Synthesis.
