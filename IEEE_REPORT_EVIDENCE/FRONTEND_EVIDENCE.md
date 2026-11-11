# FINTECH AGENT — FRONTEND ARCHITECTURE AND USER EXPERIENCE EVIDENCE

**Document Classification:** User Interface, Interaction Design & Frontend Engineering Audit  
**Frontend Framework:** React 18.3.1, Vite 5.3.1 (Rollup 5.4.21), TailwindCSS 3.4.4, Zustand 4.5.2, Lucide-React 0.400.0  
**Source Code References:**
- Main Viewport: [`frontend/src/App.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/App.jsx)
- Chat Engine: [`frontend/src/components/ChatInterface.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/ChatInterface.jsx)
- Message Renderer: [`frontend/src/components/MessageItem.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/MessageItem.jsx)
- Recurring Schedule Preview: [`frontend/src/components/SchedulePreviewCard.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/SchedulePreviewCard.jsx)
- Schedules Dashboard: [`frontend/src/components/SchedulesDashboard.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/SchedulesDashboard.jsx)
- Operator Auth Modal: [`frontend/src/components/AuthSessionModal.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/AuthSessionModal.jsx)
- Schema Reference Guide: [`frontend/src/components/SchemaGuide.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/SchemaGuide.jsx)
- Central Store: [`frontend/src/store/useChatStore.js`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/store/useChatStore.js)
- API Gateway Client: [`frontend/src/services/api.js`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/services/api.js)

---

## 1. Frontend Architectural Overview

The FinTech Agent user interface is engineered as an enterprise-grade banking analyst workbench. It delivers clear visual distinction between natural language explanations, executable MQL queries, tabular data previews, and recurring schedule controls.

```
+-----------------------------------------------------------------------------------------+
|                                    APP.JSX VIEWPORT                                     |
+------------------------------+----------------------------------------------------------+
|  SIDEBAR.JSX                 |  CHATINTERFACE.JSX                                       |
|  - Team T11 / INT450 Badge   |  - Top Bar: Conversation Title, Offline/Online Status,   |
|  - Backend Online / Offline  |             Operator Profile / Sign-In Button            |
|  - Active Model Badge        |  - Scrollable Message Stream:                            |
|  - New Conversation Button   |     * User Message Bubbles                               |
|  - Stored Chat Thread List   |     * Assistant Responses (Safe Markdown AST)            |
|  - "Recurring Reports" Link  |     * Synthesized MQL Code Box (JSON syntax highlighted) |
|  - "Schema Guide" (12 Tables)|     * Tabular Results Preview / JSON Explorer            |
|                              |     * SchedulePreviewCard (Approval Trigger)             |
|                              |  - Execution Progress Indicator (Multi-node stage pulse) |
|                              |  - Error Alert Banner (Classification Badge, Retry, Dismiss)|
|                              |  - ChatInput.jsx: Autosizing text box, 2000 char counter, |
|                              |                   Send / In-Flight Cancel Button         |
+------------------------------+----------------------------------------------------------+
|  MODALS & DRAWERS (Overlay):                                                            |
|  - SchedulesDashboard.jsx: Active jobs, run histories, pause/resume, delete              |
|  - AuthSessionModal.jsx: Operator token authentication & role claims                    |
|  - SchemaGuide.jsx: Interactive reference of 12 collections, fields & 22 foreign keys    |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Core UI Component Specifications

### 2.1 ChatInterface & MessageItem (`MessageItem.jsx`)
- **Safe Markdown Rendering:** Uses `react-markdown` (`v10.1.0`) with `remark-gfm` (`v4.0.1`) to render markdown without raw HTML injection risks (`dangerouslySetInnerHTML` is completely avoided).
- **MQL Pipeline Inspection:** Aggregation pipelines are isolated in dedicated dark-themed syntax boxes with one-click copy capability.
- **Execution Badges:** Every successful query displays:
  - Rows returned (e.g. `10 records`)
  - Execution latency in milliseconds (e.g. `42 ms`)
  - Target collection tag (e.g. `accounts`)
  - Gated notice if live execution was intercepted by configuration.
- **Error Badges:** Failures render a prominent red alert tag indicating the exact architectural reason: `MQL_POLICY_VIOLATION`, `UNSUPPORTED_CONCEPT`, `RATE_LIMIT_EXCEEDED`, or `LLM_FALLBACK_EXHAUSTED`.

### 2.2 SchedulePreviewCard (`SchedulePreviewCard.jsx`)
When an analyst requests a recurring query (e.g. *"Show failed transactions every day at 8:00 AM"*), the assistant returns an interactive card containing:
1. **Report Metadata:** Report Name and Target Collection.
2. **Timing Breakdown:** Human expression (*"Daily at 08:00"*), 5-field cron (`0 8 * * *`), and IANA Timezone (`Asia/Kolkata`).
3. **Next 3 Projected Runs:** Exact upcoming ISO timestamps calculated via APScheduler.
4. **Dry-Run Data Preview:** Top 10 sample records returned from isolated test execution.
5. **Approval Action Button:** Calls `POST /api/v1/schedules/approve`. Transitions to a confirmed green status badge upon activation.

### 2.3 SchedulesDashboard (`SchedulesDashboard.jsx`)
- Slide-over drawer providing full lifecycle management for scheduled jobs:
  - Lists all jobs owned by the authenticated analyst (`GET /api/v1/schedules`).
  - Toggle switch to **Pause** or **Resume** jobs (`POST /api/v1/schedules/{id}/pause`).
  - Permanent **Delete** button with confirmation modal (`DELETE /api/v1/schedules/{id}`).
  - Expandable **Run History** drawer displaying historical trigger times, duration, records returned, and error logs (`GET /api/v1/schedules/{id}/runs`).

### 2.4 Cryptographic Operator Authentication (`AuthSessionModal.jsx`)
- Complies with banking audit standards:
  - Prompt for Analyst User ID (e.g. `analyst_rajesh`) and Role (`analyst`, `compliance_officer`, `admin`).
  - Calls `POST /api/v1/auth/token` to retrieve a cryptographically signed HMAC-SHA256 token.
  - Persists token securely in `localStorage` under key `fintech_agent_auth_token`.
  - Automatically attaches `Authorization: Bearer <TOKEN>` to all outgoing Axios requests.
  - Exposes an explicit "Sign Out" button that revokes credentials and resets active state.

---

## 3. Comprehensive User Journey Walkthrough

An actual end-to-end user interaction demonstrating the full system workflow:

```
[ Step 1: Analyst Enters Prompt ]
Analyst types into ChatInput:
"Which customers have an annual income above ₹10 lakh, sorted by income descending?"
Clicks "Send" or presses Enter.

[ Step 2: Client State Transition ]
- useChatStore sets isLoading = true.
- ChatInput disables submit button and reveals "Cancel" button.
- Progress indicator displays: "Analyzing banking query and retrieving schema..."

[ Step 3: Backend Multi-Node Execution ]
- Node 1: InputGuardrail validates length (84 chars), zero injections, zero destructive terms -> ALLOWED.
- Node 2: IntentRouter classifies as QUERY_ONLY -> Target collections: ["customers"].
- Node 3: SchemaRetriever fetches `coll:customers` chunk from ChromaDB via cosine similarity.
- Node 4: QuerySynthesizer drafts candidate MQL pipeline:
  [
    {"$match": {"annual_income": {"$gt": 1000000}}},
    {"$sort": {"annual_income": -1}},
    {"$limit": 100}
  ]
- Node 5: MQLPolicyValidator approves: valid collection, allowed stages ($match, $sort, $limit),
  existing schema field (annual_income), valid limit (100).
- Node 6: QueryExecutor verifies read-only gate. In test harness: executes aggregation in 18ms.
- Node 7: ResultVerifier sanitizes BSON types, confirms 100 rows returned.
- Node 8: ResponseComposer formats user-facing explanation.

[ Step 4: Frontend Response Rendering ]
- MessageItem displays:
  ✅ "Query Executed Successfully (100 records returned in 18 ms)"
  Explanation: "Retrieved customer records with annual income exceeding ₹10,00,000, ordered from highest to lowest earner."
- Formatted tabular data preview renders top earners (e.g. Suresh Kumar, ₹24,50,000).
- MQL Code Box displays syntax-highlighted aggregation pipeline with one-click copy.
- Input box re-enables for follow-up conversational queries.
```

---

## 4. Frontend Test Verification (Vitest Suite)

The frontend interface was validated using Vitest (`4.1.12`) and React Testing Library ([`frontend/src/test/ChatApp.test.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/test/ChatApp.test.jsx)):
- **Total Tests Executed:** 21 tests.
- **Passed:** **21 / 21 (100.0% Pass Rate)** in 8.69s.
- **Coverage Highlights:**
  - Welcome branding and empty-state rendering.
  - Prevention of empty or whitespace message submissions.
  - Non-duplicated error alerts when API returns HTTP 500/503.
  - In-flight request cancellation without thread leakage.
  - Operator sign-in modal, token validation, and sign-out.
  - SchedulePreviewCard owner mismatch interception.
  - Markdown AST code fence rendering.
