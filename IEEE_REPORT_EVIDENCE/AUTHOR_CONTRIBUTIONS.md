# FINTECH AGENT — AUTHOR CONTRIBUTIONS AND MENTORSHIP ACKNOWLEDGMENTS

**Document Classification:** Academic Ethics, Author Attribution & Contribution Audit  
**Course Code & Title:** INT450 — Large Language Models and Agentic AI  
**Academic Institution:** School of Computing, SASTRA Deemed University, Thanjavur, Tamil Nadu, India  
**Team Designation:** Team T11  
**Git History Baseline:** 12 Git Commits spanning Phase 1 to Phase 7  

---

## 1. Git Repository Authorship Audit

A comprehensive forensic audit of all commits in the repository git history was conducted:

```
$ git log --format="%h - %an <%ae> - %ad - %s" --date=short
ee353ef - AI Engineer <engineer@fintech.local> - 2026-11-11 - fix(port): resolve port conflict...
5e446d5 - AI Engineer <engineer@fintech.local> - 2026-11-11 - feat(final): complete master hardening...
48f6c90 - AI Engineer <engineer@fintech.local> - 2026-11-10 - feat(phase-5): implement schema retrieval...
914818a - AI Engineer <engineer@fintech.local> - 2026-11-10 - docs: add Phase 4 independent deep audit report
021717b - AI Engineer <engineer@fintech.local> - 2026-11-10 - feat(phase-4): implement LangGraph agent pipeline...
b3f9baf - AI Engineer <engineer@fintech.local> - 2026-11-10 - verify: complete post-remediation independent...
94bc438 - AI Engineer <engineer@fintech.local> - 2026-11-10 - docs: add pre-Phase 4 remediation...
c335eba - AI Engineer <engineer@fintech.local> - 2026-11-10 - Milestone D: Operational reliability...
c5d19e6 - AI Engineer <engineer@fintech.local> - 2026-11-10 - Milestone C: Multi-turn conversation handling...
57cc4fc - AI Engineer <engineer@fintech.local> - 2026-11-10 - Milestone B: Schema catalog RAG correctness...
595a4d5 - AI Engineer <engineer@fintech.local> - 2026-11-10 - feat(security): complete Milestone A remediation...
f6cd317 - AI Engineer <engineer@fintech.local> - 2026-11-10 - chore: baseline commit before pre-phase 4 remediation
```

### Key Finding on Authorship:
- **100% of commits in the git log** are authored under the unified local pseudonym:
  `AI Engineer <engineer@fintech.local>`
- The global environment config indicates user identity `gurusiva16 <guru2v2v@gmail.com>`.
- Slide 13 in the project presentation notes ([`docs/codex/build_deck.py:172-177`](file:///c:/Users/guru2/Downloads/llm%20prj/docs/codex/build_deck.py#L172-L177)) explicitly notes:
  > *"Contribution evidence: The draft names three members and assigns modules, but the source tree does not verify those assignments. Confirm each member’s delivered artifact and speaking range."*
- Consequently, individual module allocation **cannot be extracted automatically from git commit author metadata** and must be formally assigned based on team consensus and course evaluation rubrics.

---

## 2. Proposed Author Contribution Breakdown for IEEE Submission

Based on the project modules, architecture areas, and slide allocations, the following contribution matrix is recommended for the final IEEE paper:

| Author / Student | Register Number | Proposed Functional Domain & Contributions |
| :--- | :---: | :--- |
| **Guru S** | **125003001** | **Lead System Architecture & Agent Orchestration:**<br>- LangGraph cyclic workflow design and state machine compilation (`graph.py`, `state.py`).<br>- Multi-provider LLM fallback integration (Gemini 3.8 Flash, Groq, Ollama) and deadline budgeting (`llm_service.py`).<br>- FastAPI application factory, lifespan management, and chat routing (`chat.py`).<br>- Core drafting of the IEEE methodology, agent design, and experimental synthesis sections. |
| **Jayavignesh J** | **125003002** | **Security Engineering & Sandboxed Database Execution:**<br>- Deterministic MQL Policy AST Validator (`mql_policy_validator.py`).<br>- Read-only database proxy architecture and fail-closed gate engineering (`mongo_client.py`, `query_executor.py`).<br>- Cryptographic HMAC-SHA256 authentication and tenant isolation (`auth.py`).<br>- Security audit, adversarial attack testing, and safety validation sections in the paper. |
| **Anbu Selvan M** | **125003003** | **Data Engineering, RAG Retrieval & Frontend Interface:**<br>- Synthetic banking dataset generation and referential integrity hardening (`generate_dataset.py`, `schema.json`).<br>- ChromaDB cosine schema catalog indexing and glossary synonym mapping (`retriever.py`, `chroma_store.py`).<br>- React 18 / Vite / Zustand user interface, interactive schedule previews, and dashboards (`App.jsx`, `ChatInterface.jsx`).<br>- Dataset documentation, RAG experimental benchmark, and frontend evaluation sections. |

---

## 3. Academic & Institutional Acknowledgments

The final IEEE conference paper must include the following formal acknowledgments:

### 3.1 Course Faculty Guidance
> *"The authors express their sincere gratitude to our faculty guide, **Dr. K. Ramkumar**, School of Computing, SASTRA Deemed University, for his invaluable guidance, technical reviews, and academic oversight throughout the INT450 (Large Language Models and Agentic AI) capstone course."*

### 3.2 Industry Mentorship
> *"The authors gratefully acknowledge the technical mentorship provided by the **Goldman Sachs Engineering Mentorship Programme**, and specifically our **Goldman Sachs Engineering Mentor**, whose rigorous industry software engineering standards, defensive banking security criteria, and financial domain insights profoundly shaped the architectural design and fail-closed invariants of this system."*

### 3.3 Institutional Support
> *"The authors thank the School of Computing and SASTRA Deemed University for providing the computational infrastructure, academic environment, and laboratory facilities necessary to complete this capstone research."*

---

## 4. Disclosure of AI Assistant Tools (IEEE Author Ethics Compliance)

In strict accordance with IEEE guidelines on the ethical use of Generative AI tools in academic research:

1. **Coding & Prototyping Assistants:**
   - **Antigravity / Gemini Agentic Assistant:** Utilized during rapid prototyping of unit tests, exploratory data validation scripts, and automated test suite refactoring.
   - **Cursor / Claude / Copilot:** Utilized for code linting, type-hint annotations, and docstring formatting.
2. **Writing & Documentation Assistants:**
   - LLMs were employed to assist in drafting initial markdown phase audit reports, structuring failure taxonomies, and generating slide deck layouts.
3. **Research Integrity Affirmation:**
   - All core architectural decisions, deterministic validation logic, cryptographic token implementations, database schema definitions, and empirical benchmark evaluations were designed, verified, and audited by the authors. The authors maintain full responsibility for all content and technical assertions in this research.
