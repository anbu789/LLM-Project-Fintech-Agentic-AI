import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Calendar, Clock, CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, Loader2, ShieldCheck, Table2, Code2, KeyRound, RefreshCw } from 'lucide-react';
import { approveSchedule } from '../services/api';
import { useChatStore } from '../store/useChatStore';

const formatDisplayDate = (isoString) => {
  if (!isoString) return 'Not specified';
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return String(isoString);
  return parsed.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
};

const formatCellValue = (value) => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  return String(value);
};

export default function SchedulePreviewCard({ preview, onApproved }) {
  const [isApproving, setIsApproving] = useState(false);
  const [approvedJob, setApprovedJob] = useState(null);
  const [error, setError] = useState(null);
  const [authErrorFlag, setAuthErrorFlag] = useState(false);
  const [showPipeline, setShowPipeline] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  const persistedApproval = useChatStore((s) =>
    preview?.preview_id ? s.approvedPreviews[preview.preview_id] : null
  );
  const markPreviewApproved = useChatStore((s) => s.markPreviewApproved);
  const authUser = useChatStore((s) => s.authUser);
  const openAuthModal = useChatStore((s) => s.openAuthModal);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isChatLoading = useChatStore((s) => s.isLoading);

  const idempotencyKeyRef = useRef(null);
  useEffect(() => {
    if (preview?.preview_id) {
      idempotencyKeyRef.current = `ui-${preview.preview_id}-${Math.random().toString(36).slice(2, 10)}`;
    }
  }, [preview?.preview_id]);

  const dryRunRows = Array.isArray(preview?.dry_run_results) ? preview.dry_run_results : [];
  const tableColumns = useMemo(() => {
    const cols = [];
    for (const row of dryRunRows.slice(0, 10)) {
      if (row && typeof row === 'object' && !Array.isArray(row)) {
        for (const key of Object.keys(row)) {
          if (!cols.includes(key)) cols.push(key);
        }
      }
    }
    return cols;
  }, [dryRunRows]);

  if (!preview) return null;

  const effectiveApprovedJob = approvedJob || persistedApproval || null;
  const isCachedApproval = !approvedJob && Boolean(persistedApproval);
  const parsedExpiry = preview.expires_at ? Date.parse(preview.expires_at) : NaN;
  const isExpired = !effectiveApprovedJob && !Number.isNaN(parsedExpiry) && parsedExpiry <= Date.now();
  const hasOwnerMismatch = Boolean(
    !effectiveApprovedJob && authUser?.user_id && preview.owner_id && preview.owner_id !== authUser.user_id
  );
  const needsAuthPrompt = Boolean(!effectiveApprovedJob && !authUser && preview.owner_id);

  const handleApprove = async () => {
    if (isExpired) {
      setError('This schedule preview has expired. Please request a fresh preview.');
      setAuthErrorFlag(false);
      return;
    }
    if (hasOwnerMismatch) {
      setError(
        `This schedule preview belongs to '${preview.owner_id}', which differs from signed-in operator '${authUser.user_id}'.`
      );
      setAuthErrorFlag(false);
      return;
    }
    setIsApproving(true);
    setError(null);
    setAuthErrorFlag(false);
    try {
      const key =
        idempotencyKeyRef.current ||
        (idempotencyKeyRef.current = `ui-${preview.preview_id}-${Math.random().toString(36).slice(2, 10)}`);
      const response = await approveSchedule(preview.preview_id, key);
      setApprovedJob(response);
      markPreviewApproved(preview.preview_id, response);
      if (onApproved) {
        onApproved(response);
      }
    } catch (err) {
      const isAuthFailure = err?.status === 401 || err?.error_code === 'AUTH_REQUIRED';
      setAuthErrorFlag(isAuthFailure);
      setError(typeof err === 'string' ? err : err?.message || 'Failed to approve schedule preview.');
    } finally {
      setIsApproving(false);
    }
  };

  const spec = preview.schedule_spec || {};
  const nextRuns = preview.next_run_times || [];
  const dryRunStatus = preview.dry_run_status;

  const renderEmptyDryRunNotice = () => {
    if (dryRunStatus === 'SUCCESS_EMPTY') {
      return {
        tone: 'bg-slate-100 text-slate-800 border-slate-300',
        iconTone: 'text-slate-600',
        message: 'Dry-run executed successfully and matched 0 records for this preview criteria.',
      };
    }
    if (dryRunStatus === 'EXECUTION_GATE_BLOCKED' || dryRunStatus === 'NOT_PERMITTED') {
      return {
        tone: 'bg-amber-50 text-amber-900 border-amber-200',
        iconTone: 'text-amber-700',
        message: 'Live dry-run execution is currently disabled on the server. Review the MQL pipeline before approving.',
      };
    }
    return {
      tone: 'bg-amber-50 text-amber-900 border-amber-200',
      iconTone: 'text-amber-700',
      message: dryRunStatus
        ? `Dry-run sample unavailable (status: ${dryRunStatus}).`
        : 'Dry-run sample unavailable.',
    };
  };

  return (
    <div className="mt-3.5 bg-white text-slate-800 rounded-xl border border-fintech-200/90 shadow-card overflow-hidden text-xs font-sans max-w-2xl">
      {/* Ticket Header Band */}
      <div className="px-4 py-3 bg-fintech-25/90 border-b border-slate-200 flex items-start sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-fintech-100/90 border border-fintech-200 text-fintech-700 flex items-center justify-center shrink-0">
            <Calendar className="w-4 h-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-slate-900 text-sm tracking-tight truncate">
              {preview.report_name || 'Scheduled Report'}
            </h4>
            <p className="text-xs text-slate-600 font-mono truncate mt-0.5">
              Target: <span className="text-fintech-800 font-semibold">{preview.target_collection}</span>
              {preview.owner_id && (
                <span>
                  {' '}
                  · Owner: <span className="text-slate-800 font-semibold">{preview.owner_id}</span>
                </span>
              )}
            </p>
          </div>
        </div>
        <span
          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold shrink-0 border ${
            effectiveApprovedJob
              ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
              : isExpired
              ? 'bg-rose-50 text-rose-800 border-rose-300'
              : 'bg-amber-50 text-amber-800 border-amber-300'
          }`}
        >
          {approvedJob ? 'ACTIVE' : isCachedApproval ? 'APPROVED (SESSION)' : isExpired ? 'EXPIRED' : 'PENDING APPROVAL'}
        </span>
      </div>

      {/* Hairline Spec Ledger Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 bg-white border-b border-slate-200 tabular-nums text-xs">
        <div className="px-4 py-2.5">
          <span className="text-slate-600 block text-[11px] uppercase font-semibold tracking-wider">Recurrence</span>
          <span className="font-mono text-slate-900 font-semibold block mt-0.5">
            {spec.recurrence_expression || 'Custom'}
          </span>
          {spec.cron_expression && (
            <span className="block text-[11px] text-slate-600 font-mono mt-0.5">({spec.cron_expression})</span>
          )}
        </div>
        <div className="px-4 py-2.5">
          <span className="text-slate-600 block text-[11px] uppercase font-semibold tracking-wider">Timezone</span>
          <span className="font-mono text-slate-900 font-semibold block mt-0.5">
            {spec.timezone || 'Asia/Kolkata'}
          </span>
          <span className="block text-[11px] text-slate-600 mt-0.5">IANA Standard</span>
        </div>
      </div>

      {/* Ticket Body Well */}
      <div className="p-4 bg-slate-50/55 space-y-3 tabular-nums">
        {/* Next Run Times */}
        <div className="bg-white rounded-lg border border-slate-200/90 overflow-hidden">
          <div className="px-3 py-2 bg-slate-50/80 border-b border-slate-200/80 flex items-center space-x-1.5 text-slate-800 text-xs font-semibold">
            <Clock className="w-3.5 h-3.5 text-fintech-600 shrink-0" aria-hidden="true" />
            <span>Upcoming Executions (Next 3)</span>
          </div>
          <ul className="divide-y divide-slate-100 font-mono text-xs text-slate-700">
            {nextRuns.length > 0 ? (
              nextRuns.map((timeStr, idx) => (
                <li key={idx} className="px-3 py-1.5 flex items-center space-x-2">
                  <span className="text-fintech-700 font-bold w-4 shrink-0">{idx + 1}.</span>
                  <span>{timeStr}</span>
                </li>
              ))
            ) : (
              <li className="px-3 py-2 text-slate-600">Not calculated</li>
            )}
          </ul>
        </div>

        {/* Pipeline Toggle */}
        <div className="rounded-lg border border-slate-200/90 bg-white overflow-hidden">
          <button
            type="button"
            onClick={() => setShowPipeline(!showPipeline)}
            className="w-full px-3 py-2 flex items-center justify-between text-xs text-fintech-700 hover:text-fintech-900 hover:bg-fintech-25 transition font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
          >
            <span>{showPipeline ? 'Hide MQL Pipeline' : 'Inspect Validated MQL Pipeline'}</span>
            {showPipeline ? <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" /> : <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />}
          </button>
          {showPipeline && (
            <pre className="p-3 bg-fintech-950 text-xs font-mono text-emerald-300 max-h-44 overflow-auto border-t border-slate-200">
              {JSON.stringify(preview.approved_pipeline, null, 2)}
            </pre>
          )}
        </div>

        {/* Dry run sample */}
        {dryRunRows.length > 0 ? (
          <div className="bg-white rounded-lg border border-slate-200/90 overflow-hidden">
            <div className="px-3 py-2 bg-slate-50/80 border-b border-slate-200/80 flex items-center justify-between gap-2">
              <span className="text-slate-700 text-[11px] uppercase font-semibold tracking-wider">
                Sample Results ({dryRunRows.length} {dryRunRows.length === 1 ? 'record' : 'records'})
              </span>
              {tableColumns.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowRawJson((v) => !v)}
                  className="inline-flex items-center space-x-1 text-[11px] font-semibold text-fintech-700 hover:text-fintech-900 bg-white border border-slate-200 hover:border-fintech-300 hover:bg-fintech-25 rounded-md px-2 py-0.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                >
                  {showRawJson ? (
                    <>
                      <Table2 className="w-3 h-3" aria-hidden="true" />
                      <span>View Table</span>
                    </>
                  ) : (
                    <>
                      <Code2 className="w-3 h-3" aria-hidden="true" />
                      <span>View Raw JSON</span>
                    </>
                  )}
                </button>
              )}
            </div>
            {!showRawJson && tableColumns.length > 0 ? (
              <div className="max-h-48 overflow-auto">
                <table className="min-w-full divide-y divide-slate-200 text-xs tabular-nums">
                  <thead className="bg-slate-50/90 text-slate-800 sticky top-0 border-b border-slate-200">
                    <tr>
                      {tableColumns.map((col) => (
                        <th key={col} className="px-2.5 py-1.5 text-left font-mono font-semibold whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {dryRunRows.map((row, rowIdx) => (
                      <tr key={rowIdx} className="hover:bg-fintech-25/70 transition-colors">
                        {tableColumns.map((col) => (
                          <td key={col} className="px-2.5 py-1.5 text-slate-700 whitespace-nowrap font-mono">
                            {formatCellValue(row?.[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <pre className="p-3 bg-fintech-950 text-xs font-mono text-slate-100 max-h-44 overflow-auto">
                {JSON.stringify(dryRunRows, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          (() => {
            const notice = renderEmptyDryRunNotice();
            return (
              <div className={`flex items-start space-x-2 text-xs p-2.5 rounded-lg border ${notice.tone}`}>
                <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${notice.iconTone}`} aria-hidden="true" />
                <span>{notice.message}</span>
              </div>
            );
          })()
        )}

        {isExpired && (
          <div className="flex items-start space-x-2 text-xs text-rose-900 bg-rose-50 p-2.5 rounded-lg border border-rose-200">
            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" aria-hidden="true" />
            <span>Preview expired on {formatDisplayDate(preview.expires_at)}. Request a fresh schedule preview to approve.</span>
          </div>
        )}

        {needsAuthPrompt && !isExpired && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-fintech-900 bg-fintech-50 p-2.5 rounded-lg border border-fintech-200">
            <div className="flex items-center space-x-2 min-w-0">
              <KeyRound className="w-4 h-4 shrink-0 text-fintech-700" aria-hidden="true" />
              <span>
                Sign in to obtain a Bearer token matching schedule preview ownership before approving.
              </span>
            </div>
            <button
              type="button"
              onClick={openAuthModal}
              className="px-2.5 py-1 rounded-md bg-fintech-700 hover:bg-fintech-800 text-white font-semibold shrink-0 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              Sign In
            </button>
          </div>
        )}

        {hasOwnerMismatch && !isExpired && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-amber-900 bg-amber-50 p-2.5 rounded-lg border border-amber-200">
            <div className="flex items-start space-x-2 min-w-0 flex-1">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-700 mt-0.5" aria-hidden="true" />
              <span>
                Preview owner is <span className="font-mono font-semibold">{preview.owner_id}</span>, while your session is signed in as{' '}
                <span className="font-mono font-semibold">{authUser.user_id}</span>. Regenerate the preview under your session to approve.
              </span>
            </div>
            {preview.natural_language_query && (
              <button
                type="button"
                disabled={isChatLoading}
                onClick={() => sendMessage(preview.natural_language_query)}
                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md bg-amber-800 hover:bg-amber-900 text-white font-semibold shrink-0 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600"
              >
                <RefreshCw className="w-3 h-3" aria-hidden="true" />
                <span>Regenerate as {authUser.user_id}</span>
              </button>
            )}
          </div>
        )}

        {/* Error display */}
        {error && (
          <div role="alert" className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs font-medium flex flex-wrap items-center justify-between gap-2">
            <span>{error}</span>
            {authErrorFlag && (
              <button
                type="button"
                onClick={openAuthModal}
                className="px-2.5 py-1 rounded-md bg-rose-700 hover:bg-rose-800 text-white text-[11px] font-semibold shrink-0 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
              >
                Sign In
              </button>
            )}
          </div>
        )}
      </div>

      {/* Sticky Ticket Action Footer */}
      <div className="px-4 py-3 bg-white border-t border-slate-200 flex flex-wrap items-center justify-between gap-2.5">
        <div className="text-[11px] text-slate-600 font-mono space-y-0.5">
          <div>ID: {preview.preview_id}</div>
          {preview.expires_at && (
            <div className={isExpired ? 'text-rose-700 font-semibold' : 'text-slate-600'}>
              Expires: {formatDisplayDate(preview.expires_at)}
            </div>
          )}
        </div>
        {effectiveApprovedJob ? (
          <div className="flex items-center space-x-1.5 text-emerald-800 font-semibold text-xs bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg">
            <CheckCircle2 className="w-4 h-4 text-emerald-700 shrink-0" aria-hidden="true" />
            <span>
              {isCachedApproval
                ? `Approved in session (${effectiveApprovedJob.job_id})`
                : `Job Activated (${effectiveApprovedJob.job_id})`}
            </span>
          </div>
        ) : (
          <button
            type="button"
            onClick={handleApprove}
            disabled={isApproving || isExpired || hasOwnerMismatch}
            className="h-9 flex items-center space-x-1.5 px-3.5 bg-fintech-600 hover:bg-fintech-700 active:bg-fintech-800 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
          >
            {isApproving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                <span>Approving...</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Approve Schedule</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
