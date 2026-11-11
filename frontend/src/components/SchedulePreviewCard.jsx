import React, { useState } from 'react';
import { Calendar, Clock, CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, Loader2, Sparkles } from 'lucide-react';
import { approveSchedule } from '../services/api';

export default function SchedulePreviewCard({ preview, onApproved }) {
  const [isApproving, setIsApproving] = useState(false);
  const [approvedJob, setApprovedJob] = useState(null);
  const [error, setError] = useState(null);
  const [showPipeline, setShowPipeline] = useState(false);

  if (!preview) return null;

  const handleApprove = async () => {
    setIsApproving(true);
    setError(null);
    try {
      const idempotencyKey = `ui-${preview.preview_id}-${Date.now()}`;
      const response = await approveSchedule(preview.preview_id, idempotencyKey);
      setApprovedJob(response);
      if (onApproved) {
        onApproved(response);
      }
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to approve schedule preview.');
    } finally {
      setIsApproving(false);
    }
  };

  const spec = preview.schedule_spec || {};
  const nextRuns = preview.next_run_times || [];

  return (
    <div className="mt-3 bg-gradient-to-br from-slate-900 to-slate-950 text-slate-100 rounded-xl border border-sky-500/30 p-4 shadow-lg text-xs font-sans max-w-xl">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-lg bg-sky-500/20 text-sky-400">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-semibold text-slate-100 text-sm">{preview.report_name || 'Scheduled Report'}</h4>
            <p className="text-[11px] text-sky-400 font-mono">
              Target: <span className="text-slate-300 font-medium">{preview.target_collection}</span>
            </p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-medium ${
          approvedJob ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
        }`}>
          {approvedJob ? 'ACTIVE' : 'PENDING APPROVAL'}
        </span>
      </div>

      {/* Recurrence & Next Runs */}
      <div className="py-3 space-y-2">
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase font-semibold">Recurrence</span>
            <span className="font-mono text-slate-200">{spec.recurrence_expression || 'Custom'}</span>
            {spec.cron_expression && (
              <span className="block text-[10px] text-slate-400 font-mono mt-0.5">({spec.cron_expression})</span>
            )}
          </div>
          <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase font-semibold">Timezone</span>
            <span className="font-mono text-slate-200">{spec.timezone || 'Asia/Kolkata'}</span>
            <span className="block text-[10px] text-slate-400 mt-0.5">IANA Standard</span>
          </div>
        </div>

        {/* Next Run Times */}
        <div className="bg-slate-800/40 p-2.5 rounded-lg border border-slate-800/80">
          <div className="flex items-center space-x-1.5 text-slate-300 text-[11px] font-semibold mb-1">
            <Clock className="w-3 h-3 text-sky-400" />
            <span>Upcoming Executions (Next 3)</span>
          </div>
          <ul className="space-y-1 font-mono text-[10px] text-slate-300">
            {nextRuns.length > 0 ? (
              nextRuns.map((timeStr, idx) => (
                <li key={idx} className="flex items-center space-x-1.5">
                  <span className="text-sky-400 font-bold">{idx + 1}.</span>
                  <span>{timeStr}</span>
                </li>
              ))
            ) : (
              <li className="text-slate-500">Not calculated</li>
            )}
          </ul>
        </div>

        {/* Pipeline Toggle */}
        <div>
          <button
            onClick={() => setShowPipeline(!showPipeline)}
            className="flex items-center space-x-1 text-[11px] text-sky-400 hover:text-sky-300 transition font-medium"
          >
            <span>{showPipeline ? 'Hide MQL Pipeline' : 'Inspect Validated MQL Pipeline'}</span>
            {showPipeline ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showPipeline && (
            <pre className="mt-1.5 p-2 bg-black/60 rounded text-[10px] font-mono text-emerald-400 max-h-40 overflow-y-auto border border-slate-800">
              {JSON.stringify(preview.approved_pipeline, null, 2)}
            </pre>
          )}
        </div>

        {/* Dry run sample */}
        {preview.dry_run_results && preview.dry_run_results.length > 0 ? (
          <div className="bg-slate-800/40 p-2 rounded-lg border border-slate-800">
            <span className="text-slate-400 text-[10px] uppercase font-semibold block mb-1">
              Sample Results ({preview.dry_run_results.length} records)
            </span>
            <pre className="p-1.5 bg-black/40 rounded text-[9px] font-mono text-slate-300 max-h-24 overflow-y-auto">
              {JSON.stringify(preview.dry_run_results, null, 2)}
            </pre>
          </div>
        ) : (
          <div className="flex items-center space-x-1.5 text-[10px] text-amber-300 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span>Execution preview gated pending native MongoDB RBAC authorization.</span>
          </div>
        )}
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-2 p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px]">
          {error}
        </div>
      )}

      {/* Action Footer */}
      <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
        <span className="text-[10px] text-slate-500 font-mono">
          ID: {preview.preview_id}
        </span>
        {approvedJob ? (
          <div className="flex items-center space-x-1.5 text-emerald-400 font-medium text-[11px]">
            <CheckCircle2 className="w-4 h-4" />
            <span>Job Activated ({approvedJob.job_id})</span>
          </div>
        ) : (
          <button
            onClick={handleApprove}
            disabled={isApproving}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 active:bg-sky-700 text-white rounded-lg font-medium transition disabled:opacity-50 shadow-sm"
          >
            {isApproving ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Approving...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3 h-3" />
                <span>Approve Schedule</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
