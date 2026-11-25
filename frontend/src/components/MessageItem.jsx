import React, { useMemo, useState } from 'react';
import { Bot, User, Clock, AlertCircle, ChevronDown, ChevronUp, Code2, RotateCcw, Terminal } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import SchedulePreviewCard from './SchedulePreviewCard';
import QueryResultTable from './QueryResultTable';

const ERROR_CATEGORY_LABELS = {
  provider_timeout: 'Provider Timeout',
  client_timeout: 'Client Timeout',
  backend_timeout: 'Backend Gateway Timeout',
  provider_error: 'Provider Error',
  backend_http_error: 'Backend HTTP Error',
  network_error: 'Network Failure',
  validation_error: 'Validation Error',
  auth_error: 'Authentication Error',
};

const getErrorLabel = (errorCategory, errorCode) => {
  if (errorCategory && ERROR_CATEGORY_LABELS[errorCategory]) {
    return ERROR_CATEGORY_LABELS[errorCategory];
  }
  if (errorCode === 'PROVIDER_TIMEOUT') return 'Provider Timeout';
  if (errorCode === 'CLIENT_TIMEOUT') return 'Client Timeout';
  if (errorCode === 'REQUEST_TIMEOUT') return 'Backend Gateway Timeout';
  if (errorCode === 'NETWORK_ERROR') return 'Network Failure';
  return null;
};

/**
 * Sanitizes internal phase numbers and engineering labels from normal customer-facing query output.
 * Replaces them with clear, professional banking terminology:
 * - "Read-only query execution"
 * - "Database query executed successfully"
 */
export function sanitizeCustomerFacingText(text) {
  if (!text || typeof text !== 'string') return text;

  let sanitized = text;

  // Replace headers with customer-friendly execution descriptions
  sanitized = sanitized.replace(/✅ \*\*Query Executed Successfully\*\* \((?:Phase 6|Database query executed successfully|Read-only query execution)\)/gi, '✅ **Database query executed successfully** (Read-only query execution)');
  sanitized = sanitized.replace(/✅ \*\*Query Executed Successfully\*\* \(Phase 6\)/gi, '✅ **Database query executed successfully** (Read-only query execution)');
  sanitized = sanitized.replace(/✅ \*\*Query Executed Successfully\*\*/gi, '✅ **Database query executed successfully**');
  sanitized = sanitized.replace(/⚠️ \*\*Query Executed \(Results Capped\)\*\* \(Phase 6\)/gi, '⚠️ **Database query executed (Results capped)** (Read-only query execution)');
  sanitized = sanitized.replace(/❌ \*\*Query Execution Failed\*\* \(Phase 6\)/gi, '❌ **Database query execution failed** (Read-only query execution)');

  // Replace validated pipeline headers
  sanitized = sanitized.replace(/✅ \*\*Query Understood & Validated\*\* \((?:Phase 5\/6 — Pipeline Validated|Phase 5 — Read-only query execution plan validated|Phase 5)\)/gi, '✅ **Query Understood & Validated** (Read-only query execution — Pipeline Validated)');
  sanitized = sanitized.replace(/📋 \*\*Scheduled Report Preview\*\* \(Phase 7 — Awaiting Explicit Approval\)/gi, '📋 **Scheduled Report Preview** (Awaiting Explicit Approval)');
  sanitized = sanitized.replace(/✅ \*\*Query Understood & Validated \(Schedule Request Pending\)\*\* \(Phase 5\)/gi, '✅ **Query Understood & Validated (Schedule Request Pending)** (Read-only query execution)');

  // Clean remaining parenthetical internal phase labels in general prose
  sanitized = sanitized.replace(/\(Phase 6\)/gi, '(Read-only query execution)');
  sanitized = sanitized.replace(/\(Phase 5\)/gi, '(Read-only query plan)');
  sanitized = sanitized.replace(/\(Phase 7\)/gi, '(Scheduled report)');

  // Clean gate configuration notices in customer view
  sanitized = sanitized.replace(/\(`?PHASE6_LIVE_EXECUTION_ENABLED=False`?\)/gi, '(live execution gated)');
  sanitized = sanitized.replace(/pending manual activation of MongoDB RBAC authentication/gi, 'pending administrative authorization');

  return sanitized;
}

export const MARKDOWN_COMPONENTS = {
  h1: ({ node, ...props }) => <h1 className="text-lg font-semibold text-slate-900 mt-4 mb-2 first:mt-0 tracking-tight max-w-[68ch]" {...props} />,
  h2: ({ node, ...props }) => <h2 className="text-base font-semibold text-slate-900 mt-3.5 mb-1.5 first:mt-0 tracking-tight max-w-[68ch]" {...props} />,
  h3: ({ node, ...props }) => <h3 className="text-sm font-semibold text-slate-900 mt-3 mb-1 first:mt-0 max-w-[68ch]" {...props} />,
  h4: ({ node, ...props }) => <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-700 mt-2.5 mb-1 first:mt-0 max-w-[68ch]" {...props} />,
  p: ({ node, ...props }) => <p className="mb-2.5 last:mb-0 leading-relaxed text-slate-800 max-w-[68ch]" {...props} />,
  ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-2.5 last:mb-0 space-y-1 text-slate-800 max-w-[68ch]" {...props} />,
  ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-2.5 last:mb-0 space-y-1 text-slate-800 max-w-[68ch]" {...props} />,
  li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
  strong: ({ node, ...props }) => <strong className="font-semibold text-slate-900" {...props} />,
  blockquote: ({ node, ...props }) => (
    <blockquote className="border border-fintech-200 bg-fintech-50/70 px-3.5 py-2 my-2.5 rounded-lg text-slate-700 italic max-w-[68ch]" {...props} />
  ),
  hr: ({ node, ...props }) => <hr className="my-3.5 border-slate-200" {...props} />,
  a: ({ node, ...props }) => (
    <a className="text-fintech-700 underline underline-offset-2 hover:text-fintech-800 font-medium" {...props} />
  ),
  table: ({ node, ...props }) => (
    <div className="max-w-full overflow-x-auto my-3 border border-slate-200/90 rounded-xl bg-white shadow-card">
      <table className="min-w-full divide-y divide-slate-200 text-xs tabular-nums" {...props} />
    </div>
  ),
  thead: ({ node, ...props }) => <thead className="bg-slate-50/95 text-slate-800 font-semibold border-b border-slate-200" {...props} />,
  th: ({ node, ...props }) => <th className="px-3.5 py-2.5 text-left font-semibold text-slate-800 whitespace-nowrap" {...props} />,
  td: ({ node, ...props }) => <td className="px-3.5 py-2 border-t border-slate-100 text-slate-700 align-top" {...props} />,
  pre: ({ node, ...props }) => (
    <pre className="markdown-pre max-w-full bg-fintech-950 text-slate-100 p-3.5 rounded-xl overflow-x-auto text-xs my-2.5 font-mono leading-relaxed border border-fintech-800/70 shadow-card" {...props} />
  ),
  code: ({ node, className, children, ...props }) => (
    <code
      className={`bg-fintech-50 text-fintech-800 border border-fintech-200/80 px-1.5 py-0.5 rounded font-mono text-xs ${className || ''}`}
      {...props}
    >
      {children}
    </code>
  ),
};

/**
 * Detects and extracts MongoDB query results from the customer-facing message markdown.
 * Returns null if no query result block exists (e.g. clarification, blocked, error, empty).
 */
export function extractResultsBlock(text) {
  if (!text || typeof text !== 'string') return null;

  // Regex matches Results Preview or Results followed by a json code block
  const pattern = /(?:(?:\*{1,2}|#{1,4}\s*)?Results?(?:\s+Preview)?:?(?:\*{1,2})?)\s*```(?:json)?\s*([\s\S]*?)\s*```/i;
  const match = text.match(pattern);
  if (!match) return null;

  try {
    const rawJson = match[1].trim();
    const parsed = JSON.parse(rawJson);
    const rows = Array.isArray(parsed)
      ? parsed
      : typeof parsed === 'object' && parsed !== null
      ? [parsed]
      : null;
    if (!rows || rows.length === 0) return null;

    // Guard: Verify this is not an MQL aggregation pipeline specification (e.g. [{ $match: ... }])
    const isMqlPipeline = rows.some(
      (r) => r && typeof r === 'object' && Object.keys(r).some((k) => k.startsWith('$'))
    );
    if (isMqlPipeline) return null;

    const preText = text.slice(0, match.index).trim();
    const postText = text.slice(match.index + match[0].length).trim();

    // Extract total count and execution time from preText if available
    const metricsMatch = preText.match(/Execution Metrics:\s*(\d+)\s*records?\s*(?:returned)?(?:\s*in\s*([\d.]+)\s*ms)?/i);
    const totalCount = metricsMatch ? parseInt(metricsMatch[1], 10) : rows.length;
    const executionTimeMs = metricsMatch && metricsMatch[2] ? parseFloat(metricsMatch[2]) : null;

    // Extract target collection from preText if available
    const colMatch = preText.match(/Target Collection:\*{0,2}\s*`?([a-zA-Z0-9_]+)`?/i);
    const targetCollection = colMatch ? colMatch[1] : null;

    return {
      preText,
      postText,
      rows,
      totalCount,
      executionTimeMs,
      targetCollection,
    };
  } catch {
    return null;
  }
}

/**
 * Derives internal phase and LangGraph node details for developer diagnostics.
 */
function getDeveloperPhaseInfo(message) {
  const text = message.rawText || message.text || '';
  if (message.schedulePreview || text.includes('Phase 7') || text.includes('Scheduled Report Preview')) {
    return {
      phase: 'Phase 7 — Recurring Schedule Planning & Registration',
      primaryNode: 'schedule_planner (Node 9)',
      mode: 'SCHEDULE_PREVIEW',
      description: 'APScheduler recurrence parsing, dry-run preview generation, and explicit approval gating.',
    };
  }
  if (text.includes('Query Executed Successfully') || text.includes('Phase 6') || text.includes('Execution Metrics:')) {
    return {
      phase: 'Phase 6 — Read-Only Database Execution',
      primaryNode: 'query_executor (Node 6)',
      mode: 'LIVE_EXECUTION',
      description: 'Authenticated read-only MongoDB execution with maxTimeMS timeout and bounded result cursor.',
    };
  }
  if (message.pipelineSpec || text.includes('Pipeline Validated') || text.includes('Phase 5')) {
    return {
      phase: 'Phase 5 — Deterministic MQL Policy Validation',
      primaryNode: 'mql_policy_validator (Node 5)',
      mode: 'VALIDATION_ONLY',
      description: 'AST policy validator enforcing canonical schema, read-only operators, and stage limits.',
    };
  }
  return {
    phase: 'Phase 4 — Conversational Routing & Guardrails',
    primaryNode: 'request_intent_router (Node 2)',
    mode: 'CONVERSATIONAL',
    description: 'Input guardrails, intent classification, and schema grounding.',
  };
}

export default function MessageItem({ message, onRetry, isLoading }) {
  const isUser = message.role === 'user';
  const isError = message.isError;
  const [showPipeline, setShowPipeline] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const hasStandalonePipeline =
    !isUser &&
    !isError &&
    !message.schedulePreview &&
    Array.isArray(message.pipelineSpec) &&
    message.pipelineSpec.length > 0;

  const diagInfo = !isUser && !isError ? getDeveloperPhaseInfo(message) : null;
  const customerFacingText = !isUser && !isError ? sanitizeCustomerFacingText(message.text) : message.text;
  const resultData = useMemo(
    () => (!isUser && !isError ? extractResultsBlock(customerFacingText) : null),
    [isUser, isError, customerFacingText]
  );

  return (
    <div className={`flex w-full py-2.5 px-1 sm:px-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-full sm:max-w-3xl min-w-0 gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-white shadow-sm ${
            isUser ? 'bg-fintech-800' : isError ? 'bg-rose-600' : 'bg-fintech-600'
          }`}
        >
          {isUser ? <User className="w-4 h-4" /> : isError ? <AlertCircle className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
        </div>

        {/* Bubble & Metadata */}
        <div className="flex flex-col space-y-1.5 min-w-0 flex-1">
          <div
            className={`rounded-2xl px-4 py-3.5 text-sm leading-relaxed shadow-card min-w-0 ${
              isUser
                ? 'bg-fintech-700 text-white rounded-tr-sm'
                : isError
                ? 'bg-rose-50/90 text-rose-900 border border-rose-200 rounded-tl-sm'
                : 'bg-white text-slate-800 border border-slate-200/90 rounded-tl-sm'
            }`}
          >
            {isUser ? (
              <div className="whitespace-pre-wrap break-words">{message.text}</div>
            ) : isError ? (
              <div className="space-y-2.5">
                {getErrorLabel(message.errorCategory, message.errorCode) && (
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-rose-700">
                    {getErrorLabel(message.errorCategory, message.errorCode)}
                  </div>
                )}
                <div className="whitespace-pre-wrap break-words text-rose-900 font-medium">{message.text}</div>
                <div className="flex flex-wrap items-center gap-2">
                  {message.errorCode && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-rose-100 text-rose-900 border border-rose-200 font-medium">
                      {message.errorCode}
                    </span>
                  )}
                  {message.failedPrompt && onRetry && (
                    <button
                      type="button"
                      onClick={() => onRetry(message.id, message.failedPrompt)}
                      disabled={isLoading}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-rose-100 text-rose-800 border border-rose-300 text-xs font-semibold transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 shadow-card"
                    >
                      <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Retry Query</span>
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-800 leading-relaxed break-words min-w-0">
                {resultData ? (
                  <div className="space-y-2.5">
                    {resultData.preText && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                        {resultData.preText}
                      </ReactMarkdown>
                    )}
                    <QueryResultTable
                      rows={resultData.rows}
                      totalCount={resultData.totalCount}
                      executionTimeMs={resultData.executionTimeMs}
                      targetCollection={resultData.targetCollection || message.selectedCollection}
                    />
                    {resultData.postText && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                        {resultData.postText}
                      </ReactMarkdown>
                    )}
                  </div>
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                    {customerFacingText}
                  </ReactMarkdown>
                )}
              </div>
            )}

            {/* Standalone Validated MQL Pipeline Drawer & Developer Diagnostics Bar */}
            {!isUser && !isError && (
              <div className="mt-3.5 pt-3 border-t border-slate-200/90">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {hasStandalonePipeline && (
                      <button
                        type="button"
                        onClick={() => setShowPipeline((v) => !v)}
                        aria-expanded={showPipeline}
                        className="inline-flex items-center space-x-1.5 text-xs font-semibold text-fintech-700 hover:text-fintech-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 rounded-md px-1.5 py-1 hover:bg-fintech-50/70 transition"
                      >
                        <Code2 className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>{showPipeline ? 'Hide Validated MQL Pipeline' : 'Inspect Validated MQL Pipeline'}</span>
                        {showPipeline ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setShowDiagnostics((v) => !v)}
                      aria-expanded={showDiagnostics}
                      className="inline-flex items-center space-x-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 rounded-md px-1.5 py-1 hover:bg-slate-100 transition"
                    >
                      <Terminal className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
                      <span>{showDiagnostics ? 'Hide Diagnostics' : 'Developer Diagnostics'}</span>
                      {showDiagnostics ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px] font-mono">
                    {message.selectedCollection && (
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-800 border border-slate-200 font-medium">
                        {message.selectedCollection}
                      </span>
                    )}
                    {message.validationStatus && (
                      <span
                        className={`px-2 py-0.5 rounded-md border font-semibold ${
                          message.validationStatus === 'passed'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : 'bg-amber-50 text-amber-800 border-amber-200'
                        }`}
                      >
                        MQL: {message.validationStatus}
                      </span>
                    )}
                  </div>
                </div>

                {/* Pipeline Drawer Content */}
                {hasStandalonePipeline && showPipeline && (
                  <div className="mt-2.5 space-y-2">
                    {message.queryExplanation && (
                      <p className="text-xs text-slate-700 bg-slate-50 border border-slate-200/80 rounded-lg px-3 py-2 max-w-[68ch]">
                        {message.queryExplanation}
                      </p>
                    )}
                    <pre className="max-w-full bg-fintech-950 text-emerald-300 p-3.5 rounded-xl overflow-x-auto text-xs font-mono max-h-56 border border-fintech-800/70 shadow-card">
                      {JSON.stringify(message.pipelineSpec, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Developer Diagnostics Content */}
                {showDiagnostics && diagInfo && (
                  <div className="mt-2.5 p-3.5 bg-slate-900 text-slate-100 rounded-xl text-xs font-mono space-y-3 border border-slate-800 shadow-card">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <div className="flex items-center space-x-2 text-slate-200 font-semibold">
                        <Terminal className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                        <span>Developer Diagnostics &amp; Audit Trace</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-emerald-300 border border-slate-700">
                        {diagInfo.mode}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span className="text-slate-400">Internal Execution Phase:</span>
                        <div className="text-emerald-400 font-medium mt-0.5">{diagInfo.phase}</div>
                      </div>
                      <div>
                        <span className="text-slate-400">Primary LangGraph Node:</span>
                        <div className="text-cyan-300 font-medium mt-0.5">{diagInfo.primaryNode}</div>
                      </div>
                    </div>

                    <div>
                      <span className="text-slate-400 text-[11px]">LangGraph Node Architecture Sequence:</span>
                      <div className="flex flex-wrap items-center gap-1 mt-1 text-[10px]">
                        {[
                          '1. input_guardrail',
                          '2. request_intent_router',
                          '3. schema_retriever',
                          '4. query_synthesizer',
                          '5. mql_policy_validator',
                          '6. query_executor (Phase 6)',
                          '7. result_verifier',
                          '8. response_composer',
                          '9. schedule_planner (Phase 7)',
                        ].map((step, idx) => (
                          <span key={idx} className="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-slate-700">
                            {step}
                          </span>
                        ))}
                      </div>
                    </div>

                    {Array.isArray(message.trace) && message.trace.length > 0 && (
                      <div>
                        <span className="text-slate-400 text-[11px]">Runtime Audit Trace ({message.trace.length} steps):</span>
                        <div className="mt-1 max-h-36 overflow-y-auto space-y-1 bg-slate-950 p-2 rounded border border-slate-800 text-[10px]">
                          {message.trace.map((t, idx) => (
                            <div key={idx} className="flex items-start justify-between gap-2 border-b border-slate-900/60 pb-1 last:border-0">
                              <span className="text-cyan-400 font-semibold">{t.node || `step-${idx + 1}`}</span>
                              <span className="text-slate-300 truncate max-w-[240px]">{t.status || t.detail || 'completed'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-[10px] text-slate-400 border-t border-slate-800 pt-2 flex flex-wrap items-center justify-between gap-2">
                      <span>Monitor: Terminal 2 event stream (<code className="text-emerald-400 font-mono">tail_monitor.py</code>)</span>
                      <span>Request ID: {message.requestId || 'n/a'}</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Interactive Schedule Preview Card */}
            {!isUser && message.schedulePreview && (
              <SchedulePreviewCard preview={message.schedulePreview} />
            )}
          </div>

          {/* Metadata badges for Assistant */}
          {!isUser && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-600 px-1 font-mono tabular-nums">
              {message.provider && (
                <span className="bg-white border border-slate-200/90 text-slate-700 px-2 py-0.5 rounded-md shadow-card">
                  {message.provider}:{message.model}
                </span>
              )}
              {message.requestId && (
                <span className="text-slate-600">id:{message.requestId}</span>
              )}
              {message.latencyMs != null && (
                <>
                  <span className="text-slate-300" aria-hidden="true">·</span>
                  <span className="text-slate-600">{message.latencyMs}ms</span>
                </>
              )}
              {message.timestamp && (
                <>
                  <span className="text-slate-300" aria-hidden="true">·</span>
                  <span className="inline-flex items-center space-x-1 text-slate-600">
                    <Clock className="w-3 h-3" aria-hidden="true" />
                    <span>{message.timestamp}</span>
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
