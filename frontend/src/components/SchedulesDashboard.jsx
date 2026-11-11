import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Calendar,
  Play,
  Pause,
  XCircle,
  RefreshCw,
  X,
  History,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  KeyRound,
} from 'lucide-react';
import {
  fetchSchedules,
  pauseSchedule,
  resumeSchedule,
  cancelSchedule,
  fetchScheduleRuns,
} from '../services/api';
import { useChatStore } from '../store/useChatStore';

const formatScheduleTime = (isoString, fallback = 'None') => {
  if (!isoString) return fallback;
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return String(isoString);
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const STATUS_FILTERS = ['ALL', 'ACTIVE', 'PAUSED', 'CANCELLED'];

export default function SchedulesDashboard({ isOpen, onClose }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isAuthError, setIsAuthError] = useState(false);
  const [actionInProgress, setActionInProgress] = useState({});
  const [confirmCancelId, setConfirmCancelId] = useState(null);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [expandedRuns, setExpandedRuns] = useState({});
  const [runsLoading, setRunsLoading] = useState({});

  const authUser = useChatStore((s) => s.authUser);
  const openAuthModal = useChatStore((s) => s.openAuthModal);

  const dialogRef = useRef(null);
  const closeBtnRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      setConfirmCancelId(null);
      loadJobs();
      const rafId = typeof window !== 'undefined' && window.requestAnimationFrame
        ? window.requestAnimationFrame(() => closeBtnRef.current?.focus())
        : null;
      return () => {
        if (rafId) window.cancelAnimationFrame(rafId);
      };
    } else if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen, authUser?.user_id]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const loadJobs = async () => {
    setLoading(true);
    setError(null);
    setIsAuthError(false);
    try {
      const data = await fetchSchedules();
      setJobs(data || []);
    } catch (err) {
      const authFailed = err?.status === 401 || err?.error_code === 'AUTH_REQUIRED';
      setIsAuthError(authFailed);
      setError(typeof err === 'string' ? err : err?.message || 'Failed to load scheduled reports.');
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async (jobId) => {
    setError(null);
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await pauseSchedule(jobId);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err?.message || 'Failed to pause schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleResume = async (jobId) => {
    setError(null);
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await resumeSchedule(jobId);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err?.message || 'Failed to resume schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleConfirmCancel = async (jobId) => {
    setError(null);
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await cancelSchedule(jobId);
      setConfirmCancelId(null);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err?.message || 'Failed to cancel schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const loadRunsForJob = async (jobId) => {
    setError(null);
    setRunsLoading((prev) => ({ ...prev, [jobId]: true }));
    try {
      const runs = await fetchScheduleRuns(jobId);
      setExpandedRuns((prev) => ({ ...prev, [jobId]: runs || [] }));
    } catch (err) {
      setError(typeof err === 'string' ? err : err?.message || 'Failed to load run history.');
    } finally {
      setRunsLoading((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const toggleRuns = async (jobId) => {
    if (expandedRuns[jobId]) {
      setExpandedRuns((prev) => ({ ...prev, [jobId]: null }));
      return;
    }
    await loadRunsForJob(jobId);
  };

  const counts = useMemo(() => {
    const map = { ALL: jobs.length, ACTIVE: 0, PAUSED: 0, CANCELLED: 0 };
    for (const j of jobs) {
      if (map[j.status] !== undefined) map[j.status] += 1;
    }
    return map;
  }, [jobs]);

  const filteredJobs = useMemo(() => {
    if (statusFilter === 'ALL') return jobs;
    return jobs.filter((j) => j.status === statusFilter);
  }, [jobs, statusFilter]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-fintech-950/60 backdrop-blur-[2px] p-3 sm:p-4 animate-modal-enter"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="schedules-dialog-title"
        aria-describedby="schedules-dialog-desc"
        className="bg-white border border-slate-200 rounded-2xl w-full max-w-4xl max-h-[88vh] flex flex-col shadow-panel text-slate-900 overflow-hidden font-sans"
      >
        {/* Header */}
        <div className="px-4 sm:px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-3 bg-fintech-25/90">
          <div className="flex items-center space-x-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-fintech-100/90 border border-fintech-200 text-fintech-700 flex items-center justify-center shrink-0">
              <Calendar className="w-5 h-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 id="schedules-dialog-title" className="text-base font-semibold tracking-tight text-slate-900 truncate">
                Scheduled Banking Reports
              </h2>
              <p id="schedules-dialog-desc" className="text-xs text-slate-600 truncate">
                Explicitly approved recurring queries · Read-only validated MQL
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-1.5 shrink-0">
            <button
              type="button"
              onClick={loadJobs}
              disabled={loading}
              className="min-w-[36px] min-h-[36px] inline-flex items-center justify-center p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-white border border-transparent hover:border-slate-200 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
              title="Refresh schedules"
              aria-label="Refresh schedules"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              ref={closeBtnRef}
              type="button"
              onClick={onClose}
              aria-label="Close scheduled reports modal"
              className="min-w-[36px] min-h-[36px] inline-flex items-center justify-center p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-white border border-transparent hover:border-slate-200 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Status filter tabs */}
        {jobs.length > 0 && (
          <div className="px-4 sm:px-6 py-2.5 border-b border-slate-200 bg-white flex flex-wrap items-center gap-2">
            {STATUS_FILTERS.map((status) => {
              const active = statusFilter === status;
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => setStatusFilter(status)}
                  aria-pressed={active}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono font-medium border transition tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 ${
                    active
                      ? 'bg-fintech-700 text-white border-fintech-700 shadow-sm'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:border-fintech-300 hover:bg-fintech-25'
                  }`}
                >
                  {status} ({counts[status] || 0})
                </button>
              );
            })}
          </div>
        )}

        {/* Error notification */}
        {error && (
          <div role="alert" className="mx-4 sm:mx-6 mt-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center space-x-2 min-w-0 flex-1">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" aria-hidden="true" />
              <span className="font-medium break-words">{error}</span>
            </div>
            <div className="flex items-center space-x-2 shrink-0">
              {isAuthError && (
                <button
                  type="button"
                  onClick={openAuthModal}
                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md bg-rose-700 hover:bg-rose-800 text-white font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                >
                  <KeyRound className="w-3 h-3" aria-hidden="true" />
                  <span>Sign In</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setIsAuthError(false);
                }}
                aria-label="Dismiss schedule error"
                className="text-rose-700 hover:text-rose-900 p-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Content body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 bg-slate-50/75">
          {loading && jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-600">
              <RefreshCw className="w-8 h-8 animate-spin text-fintech-600 mb-2" aria-hidden="true" />
              <p className="text-sm font-medium">Loading scheduled reports...</p>
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-12 px-4 rounded-xl border border-dashed border-slate-300 bg-white text-slate-600 space-y-2">
              <div className="w-11 h-11 rounded-xl bg-fintech-50 border border-fintech-200 text-fintech-600 flex items-center justify-center mx-auto mb-2">
                <Calendar className="w-5 h-5" aria-hidden="true" />
              </div>
              <h3 className="text-sm font-semibold text-slate-800">No scheduled reports found</h3>
              <p className="text-xs text-slate-600 max-w-sm mx-auto leading-relaxed">
                Ask the assistant to schedule queries (e.g. &ldquo;Generate the customer KYC-status count report every Monday at 9 AM&rdquo;).
              </p>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="text-center py-10 text-slate-600 text-xs bg-white rounded-xl border border-slate-200">
              No scheduled reports with status <span className="font-mono font-semibold">{statusFilter}</span>.
            </div>
          ) : (
            filteredJobs.map((job) => {
              const spec = job.schedule_spec || {};
              const inProgress = actionInProgress[job.job_id];
              const isConfirmingCancel = confirmCancelId === job.job_id;
              const runs = expandedRuns[job.job_id];
              const loadingRuns = runsLoading[job.job_id];

              return (
                <div
                  key={job.job_id}
                  className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden hover:border-fintech-200 transition tabular-nums"
                >
                  <div className="p-4 flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-sm text-slate-900 tracking-tight">{job.report_name}</h3>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold border ${
                            job.status === 'ACTIVE'
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                              : job.status === 'PAUSED'
                              ? 'bg-amber-50 text-amber-800 border-amber-300'
                              : job.status === 'CANCELLED'
                              ? 'bg-slate-100 text-slate-700 border-slate-300'
                              : 'bg-rose-50 text-rose-800 border-rose-300'
                          }`}
                        >
                          {job.status}
                        </span>
                        {job.consecutive_failures > 0 && (
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-800 border border-rose-300">
                            {job.consecutive_failures} Failures
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                        Collection: <span className="font-mono text-slate-900 font-medium">{job.target_collection}</span>
                        {' · '}
                        Recurrence: <span className="font-mono text-fintech-700 font-medium">{spec.recurrence_expression || 'Custom'}</span>
                        {' · '}
                        TZ: <span className="font-mono text-slate-700">{job.timezone || 'Asia/Kolkata'}</span>
                      </p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center space-x-2 shrink-0">
                      {job.status === 'ACTIVE' && (
                        <button
                          type="button"
                          onClick={() => handlePause(job.job_id)}
                          disabled={inProgress}
                          className="min-h-[34px] px-3 py-1.5 rounded-lg bg-white hover:bg-amber-50 text-amber-800 border border-slate-200 hover:border-amber-300 text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                        >
                          <Pause className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>Pause</span>
                        </button>
                      )}
                      {job.status === 'PAUSED' && (
                        <button
                          type="button"
                          onClick={() => handleResume(job.job_id)}
                          disabled={inProgress}
                          className="min-h-[34px] px-3 py-1.5 rounded-lg bg-fintech-600 hover:bg-fintech-700 text-white text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                        >
                          <Play className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>Resume</span>
                        </button>
                      )}
                      {job.status !== 'CANCELLED' && !isConfirmingCancel && (
                        <button
                          type="button"
                          onClick={() => setConfirmCancelId(job.job_id)}
                          disabled={inProgress}
                          className="min-h-[34px] px-3 py-1.5 rounded-lg bg-white hover:bg-rose-50 text-slate-700 hover:text-rose-800 border border-slate-200 hover:border-rose-300 text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                        >
                          <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
                          <span>Cancel</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* In-modal cancel confirmation bar */}
                  {isConfirmingCancel && (
                    <div
                      role="alertdialog"
                      aria-label={`Confirm cancelling ${job.report_name}`}
                      className="mx-4 mb-3 p-3 rounded-lg bg-rose-50 border border-rose-200 flex flex-wrap items-center justify-between gap-2 text-xs text-rose-900"
                    >
                      <span className="font-medium">
                        Permanently cancel <span className="font-semibold">{job.report_name}</span>? Future scheduled runs will stop.
                      </span>
                      <div className="flex items-center space-x-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setConfirmCancelId(null)}
                          disabled={inProgress}
                          className="px-2.5 py-1.5 rounded-md bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                        >
                          Keep Schedule
                        </button>
                        <button
                          type="button"
                          onClick={() => handleConfirmCancel(job.job_id)}
                          disabled={inProgress}
                          className="px-2.5 py-1.5 rounded-md bg-rose-700 hover:bg-rose-800 text-white font-semibold transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                        >
                          {inProgress ? 'Cancelling...' : 'Confirm Cancel'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Hairline Timing & Metadata Strip */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 text-xs border-t border-slate-200 bg-slate-50/45">
                    <div className="px-4 py-2.5">
                      <span className="text-slate-600 block text-[11px] font-medium">Next Execution</span>
                      <span className="font-mono text-slate-900 font-semibold block mt-0.5">
                        {formatScheduleTime(job.next_run_at, 'None')}
                      </span>
                    </div>
                    <div className="px-4 py-2.5">
                      <span className="text-slate-600 block text-[11px] font-medium">Last Run</span>
                      <span className="font-mono text-slate-800 block mt-0.5">
                        {formatScheduleTime(job.last_run_at, 'Never')}
                      </span>
                    </div>
                    <div className="px-4 py-2.5">
                      <span className="text-slate-600 block text-[11px] font-medium">Job Identifier</span>
                      <span className="font-mono text-slate-700 text-[11px] break-all block mt-0.5">{job.job_id}</span>
                    </div>
                  </div>

                  {/* Toggle Run History */}
                  <div className="px-4 py-2.5 border-t border-slate-200 bg-white">
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => toggleRuns(job.job_id)}
                        aria-expanded={Boolean(runs)}
                        className="text-xs text-fintech-700 hover:text-fintech-900 flex items-center space-x-1 font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 rounded px-1 py-0.5"
                      >
                        <History className="w-3.5 h-3.5" aria-hidden="true" />
                        <span>{runs ? 'Hide Execution History' : 'View Execution History'}</span>
                        {runs ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                      {runs && (
                        <button
                          type="button"
                          onClick={() => loadRunsForJob(job.job_id)}
                          disabled={loadingRuns}
                          aria-label={`Refresh runs for ${job.report_name}`}
                          className="text-[11px] font-medium text-slate-600 hover:text-fintech-800 flex items-center space-x-1 rounded px-1.5 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                        >
                          <RefreshCw className={`w-3 h-3 ${loadingRuns ? 'animate-spin' : ''}`} aria-hidden="true" />
                          <span>Refresh Runs</span>
                        </button>
                      )}
                    </div>

                    {/* Run History List */}
                    {loadingRuns && (
                      <div className="py-2 text-xs text-slate-600 flex items-center space-x-1.5">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-fintech-600" aria-hidden="true" />
                        <span>Loading execution runs...</span>
                      </div>
                    )}
                    {runs && (
                      <div className="mt-2.5 max-h-48 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100 bg-slate-50/40">
                        {runs.length === 0 ? (
                          <div className="text-xs text-slate-600 italic py-2.5 px-3">
                            No recorded executions yet.
                          </div>
                        ) : (
                          runs.map((r) => (
                            <div
                              key={r.run_id}
                              className="px-3 py-2 text-xs flex flex-wrap items-center justify-between gap-2 font-mono bg-white"
                            >
                              <div className="flex items-center space-x-2">
                                {r.status === 'SUCCESS' ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" aria-hidden="true" />
                                ) : (
                                  <AlertCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" aria-hidden="true" />
                                )}
                                <span className="text-slate-800">{formatScheduleTime(r.start_time, r.start_time)}</span>
                                <span className="text-slate-600">({r.duration_ms}ms)</span>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className="text-slate-700">{r.result_row_count} records</span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                    r.status === 'SUCCESS' ? 'text-emerald-800 bg-emerald-50 border border-emerald-200' : 'text-rose-800 bg-rose-50 border border-rose-200'
                                  }`}
                                >
                                  {r.status}
                                </span>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-4 sm:px-6 py-3 border-t border-slate-200 bg-white text-xs text-slate-600 flex items-center justify-between gap-3">
          <span>Scheduled reports re-validate MQL policy before each run under bounded read-only limits.</span>
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 shrink-0"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
