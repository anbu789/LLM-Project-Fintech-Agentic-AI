# INT450 Final Project Presentation — notes

## Slide-wise speaking points and timing

1. **FinTech Agent** — 0:35. Introduce the project, team and academic context. Frame it as a natural-language interface to synthetic banking data.
2. **Problem definition** — 0:55. Explain why analysts need help translating cross-collection questions into MongoDB aggregation queries. Use the benchmark example.
3. **Objectives and scope** — 0:55. Distinguish dataset and evaluation-plan artifacts from a verified running system. Point out the implementation evidence still needed.
4. **Why an agent workflow?** — 0:55. Explain how separate schema, generation, validation, execution and answer stages improve inspectability.
5. **Data and knowledge sources** — 0:55. Cover synthetic Faker data, the 12 collections, schema/integrity metadata and the 55-question benchmark.
6. **System architecture** — 1:05. Trace the documented flow; identify the lower retry loop and safety boundary. This is an architecture design, not a deployed system screenshot.
7. **Agent stages and tools** — 0:55. Describe each documented stage and its expected input/output. Clarify these are workflow responsibilities, not independently verified agent implementations.
8. **One request, end to end** — 1:05. Walk through Q11 and the illustrative `$match`/`$sort` pipeline. State that it is not a captured runtime output.
9. **Safety and verification** — 0:55. Present the proposed code-enforced gates, but do not claim verified guarantees absent validator code and test results.
10. **Implementation and demo plan** — 0:55. If application code is available, demonstrate a normal, tricky and refusal case. Otherwise explicitly call this a planned walkthrough.
11. **Evaluation methodology** — 0:55. Explain the 55 questions and five levels, then describe reproducible run logging and semantic scoring.
12. **Results and failure analysis** — 0:55. State what evidence exists and what is missing. Do not reuse draft numerical claims as project results without source logs.
13. **Report alignment and contributions** — 0:50. Align terminology and citations with the final report; ask each member to confirm their delivered module and presentation range.
14. **Conclusion and next steps** — 0:35. Summarize the verified project foundation and next evidence needed, then invite questions.

**Planned speaking time:** approximately 12:30, leaving about 2:30 of the 15-minute slot for a live demo. Q&A: 5 minutes.

## Items to confirm before presenting

- The provided `fintech-agent/` folder contains dataset generation, validation, schema and benchmark files, but no application runtime, agent source, evaluation harness or run logs. Confirm whether those artifacts are in another repository and update the slides with verifiable implementation evidence.
- The benchmark metadata defines 55 questions; no run output, gold result set, baseline or held-out split was supplied. Do not present draft claims such as 90.9% accuracy, 3.2-second P90, 75% recovery, 100% zero-write rate, or baseline comparisons as measured results until corroborated.
- The dataset README says “~18,700” documents, while the listed default per-collection sizes sum to 18,120. Treat the total as approximate or compute it from a generated database snapshot.
- Confirm whether schema RAG, ChromaDB, Redis, FastAPI, LangGraph, MongoDB deployment, scheduling, AST validation, `explain()` gating, UI and live demo are implemented; the available source files do not establish these.
- Confirm the team member names, registration numbers, individual contributions and slide ownership.
- The IEEE project report and report bibliography were not supplied; align citations and architecture naming with the final report before delivery.
- Confirm whether the scheduled-job flow is implemented. Current slides state that it is described in design materials, not verified code.

## Source basis

Prepared from the workspace's dataset README, generator/validation scripts, `schema.json`, `test_questions.json`, project design documents, the supplied template, and prior deck drafts. Claims in prior drafts were treated as unverified where corresponding implementation or evaluation evidence was unavailable.
