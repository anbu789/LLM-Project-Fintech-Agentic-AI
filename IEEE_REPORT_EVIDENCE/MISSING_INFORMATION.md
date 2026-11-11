# FINTECH AGENT — MISSING INFORMATION AND MANUAL ACTION CHECKLIST

**Document Classification:** Academic Prerequisite Checklist & Author Action Items  
**Objective:** Identify every piece of technical or institutional information that cannot be inferred from repository code and must be manually provided by Team T11 before drafting the final IEEE conference paper.

---

## 1. Prioritized Missing Information Checklist

| # | Priority | Missing Item | Description & Why It Is Needed | Repository Finding | Required Action from Student Team |
| :-: | :---: | :--- | :--- | :--- | :--- |
| **1** | **CRITICAL** | **Individual Author Contributions** | Exact distribution of technical contributions for Section 15 / Author Contributions. | All 12 git commits were authored under `AI Engineer <engineer@fintech.local>`. Slide 13 notes contributions need confirmation. | Guru S, Jayavignesh J, and Anbu Selvan M must formally confirm their individual module responsibilities and percentages. |
| **2** | **CRITICAL** | **55-Question Gold Pipelines & Execution Script** | If the 90.9% (50/55) accuracy claim is to be made in the paper, reproducible execution evidence is required. | `test_questions.json` contains 55 questions and hints, but zero gold MQL queries and zero gold execution outputs. No runner script exists. | Provide an executable benchmark harness script, run the 55 queries against the live agent, capture raw JSON/CSV outputs, and recalculate actual accuracy. Alternatively, omit the claim. |
| **3** | **HIGH** | **Official GitHub Repository Remote URL** | IEEE papers standardly include a public code availability footnote or link. | `git remote -v` returned empty; the repository is currently a local standalone git tree. | Provide the public GitHub URL (e.g. `https://github.com/<team>/fintech-agent`) if code is to be published. |
| **4** | **HIGH** | **Industry Mentor Name & Affiliation Confirmation** | Formal acknowledgment in the IEEE paper. | Project documents state *"Guided by Goldman Sachs Engineering Mentor"* under the *"Goldman Sachs Engineering Mentorship Programme"*, without a personal name. | Check with the mentor whether their personal name and corporate title may be published in the IEEE acknowledgment section, or if the anonymous institutional program credit should be retained. |
| **5** | **MEDIUM** | **Target IEEE Conference Details** | Formatting, page limit, and citation style. | Course INT450 guidelines specify an IEEE conference format of up to 8 pages. | Confirm the specific conference name, track, submission deadline, and whether IEEE double-column LaTeX or Word format is requested. |
| **6** | **MEDIUM** | **Dense Embedding Benchmark Execution** | Evaluation of RAG with live `sentence-transformers` rather than mock embeddings. | ChromaDB index was evaluated with deterministic unit vectors via `MockEmbeddingProvider` to avoid downloading PyTorch/ONNX models during CI. | If dense transformer retrieval accuracy is to be reported, run `test_rag_benchmark_evaluation_metrics` with `EMBEDDING_PROVIDER="sentence-transformers"` and real weights. |
| **7** | **LOW** | **High-Resolution Interface Screenshots** | Visual figures for paper Section 5 / Frontend Workbench. | Slide images exist in `docs/inspect_slides/`, but high-resolution native browser screenshots of the live Chat and Schedules Dashboard should be captured. | Launch `start_project.bat` and capture two clean, high-DPI screenshots: (1) Main chat showing validated MQL pipeline and execution metrics; (2) Recurring report SchedulePreviewCard and Schedules drawer. |

---

## 2. Immediate Next Steps for the Team

1. **Review and approve the proposed Author Contribution matrix** in [`AUTHOR_CONTRIBUTIONS.md`](file:///c:/Users/guru2/Downloads/llm%20prj/IEEE_REPORT_EVIDENCE/AUTHOR_CONTRIBUTIONS.md).
2. **Decide whether to execute the 55-question benchmark:**
   - *Option A (Recommended for IEEE Academic Rigor):* Frame the 55 questions as an *Analytical Benchmark Catalogue* and report the verified 18-case RAG retrieval and synthesis evaluations.
   - *Option B (If 55-query accuracy is mandatory):* Develop a standalone benchmark runner script, execute the 55 queries, log the results, and generate genuine percentiles.
3. **Capture UI screenshots** from the local running web app on `http://localhost:5173`.
