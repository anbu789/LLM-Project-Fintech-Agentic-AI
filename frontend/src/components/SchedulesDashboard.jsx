import React, { useState, useEffect } from 'react';
import {
  Calendar,
  Clock,
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
} from 'lucide-react';
import {
  fetchSchedules,
  pauseSchedule,
  resumeSchedule,
  cancelSchedule,
  fetchScheduleRuns,
} from '../services/api';

export default function SchedulesDashboard({ isOpen, onClose }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionInProgress, setActionInProgress] = useState({});
  const [expandedRuns, setExpandedRuns] = useState({});
  const [runsLoading, setRunsLoading] = useState({});

  useEffect(() => {
    if (isOpen) {
      loadJobs();
    }
  }, [isOpen]);

  const loadJobs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSchedules();
      setJobs(data || []);
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to load scheduled reports.');
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async (jobId) => {
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await pauseSchedule(jobId);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to pause schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleResume = async (jobId) => {
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await resumeSchedule(jobId);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to resume schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const handleCancel = async (jobId) => {
    if (!window.confirm('Are you sure you want to permanently cancel this scheduled report?')) {
      return;
    }
    setActionInProgress((prev) => ({ ...prev, [jobId]: true }));
    try {
      await cancelSchedule(jobId);
      await loadJobs();
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to cancel schedule.');
    } finally {
      setActionInProgress((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  const toggleRuns = async (jobId) => {
    if (expandedRuns[jobId]) {
      setExpandedRuns((prev) => ({ ...prev, [jobId]: null }));
      return;
    }

    setRunsLoading((prev) => ({ ...prev, [jobId]: true }));
    try {
      const runs = await fetchScheduleRuns(jobId);
      setExpandedRuns((prev) => ({ ...prev, [jobId]: runs || [] }));
    } catch (err) {
      setError(typeof err === 'string' ? err : err.message || 'Failed to load run history.');
    } finally {
      setRunsLoading((prev) => ({ ...prev, [jobId]: false }));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl text-slate-100 overflow-hidden font-sans">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-sky-500/20 text-sky-400">
              <Calendar className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">Scheduled Banking Reports</h2>
              <p className="text-xs text-slate-400">Autonomous recurring MQL reports in agent_metadata_db</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={loadJobs}
              disabled={loading}
              className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
              title="Refresh schedules"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Error notification */}
        {error && (
          <div className="mx-6 mt-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Content body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading && jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin text-sky-400 mb-2" />
              <p className="text-sm">Loading scheduled reports...</p>
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-12 text-slate-400 space-y-2">
              <Calendar className="w-12 h-12 mx-auto text-slate-600 mb-2" />
              <h3 className="text-sm font-medium text-slate-300">No scheduled reports found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Ask the assistant to schedule queries (e.g. &ldquo;Generate loan delinquency report every Monday at 9 AM&rdquo;).
              </p>
            </div>
          ) : (
            jobs.map((job) => {
              const spec = job.schedule_spec || {};
              const inProgress = actionInProgress[job.job_id];
              const runs = expandedRuns[job.job_id];
              const loadingRuns = runsLoading[job.job_id];

              return (
                <div
                  key={job.job_id}
                  className="bg-slate-950/40 rounded-xl border border-slate-800 p-4 hover:border-slate-700/80 transition"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center space-x-2">
                        <h3 className="font-semibold text-sm text-slate-100">{job.report_name}</h3>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-medium ${
                            job.status === 'ACTIVE'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                              : job.status === 'PAUSED'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : job.status === 'CANCELLED'
                              ? 'bg-slate-700 text-slate-400 border border-slate-600'
                              : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          }`}
                        >
                          {job.status}
                        </span>
                        {job.consecutive_failures > 0 && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-rose-500/30 text-rose-200 border border-rose-500/50">
                            {job.consecutive_failures} Failures
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Collection: <span className="font-mono text-slate-300 font-medium">{job.target_collection}</span>
                        {' · '}
                        Recurrence: <span className="font-mono text-sky-400">{spec.recurrence_expression || 'Custom'}</span>
                        {' · '}
                        TZ: <span className="font-mono text-slate-400">{job.timezone || 'Asia/Kolkata'}</span>
                      </p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center space-x-2">
                      {job.status === 'ACTIVE' && (
                        <button
                          onClick={() => handlePause(job.job_id)}
                          disabled={inProgress}
                          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-400 text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50"
                        >
                          <Pause className="w-3.5 h-3.5" />
                          <span>Pause</span>
                        </button>
                      )}
                      {job.status === 'PAUSED' && (
                        <button
                          onClick={() => handleResume(job.job_id)}
                          disabled={inProgress}
                          className="px-2.5 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50"
                        >
                          <Play className="w-3.5 h-3.5" />
                          <span>Resume</span>
                        </button>
                      )}
                      {job.status !== 'CANCELLED' && (
                        <button
                          onClick={() => handleCancel(job.job_id)}
                          disabled={inProgress}
                          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-rose-950/60 text-slate-400 hover:text-rose-400 text-xs font-medium flex items-center space-x-1 transition disabled:opacity-50"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Cancel</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Timing & Metadata */}
                  <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] pt-3 border-t border-slate-800/80">
                    <div>
                      <span className="text-slate-500 block">Next Execution:</span>
                      <span className="font-mono text-slate-300 font-medium">
                        {job.next_run_at || 'None'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Last Run:</span>
                      <span className="font-mono text-slate-300">
                        {job.last_run_at || 'Never'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Job Identifier:</span>
                      <span className="font-mono text-slate-400 text-[10px]">{job.job_id}</span>
                    </div>
                  </div>

                  {/* Toggle Run History */}
                  <div className="mt-3 pt-2 border-t border-slate-800/60">
                    <button
                      onClick={() => toggleRuns(job.job_id)}
                      className="text-xs text-sky-400 hover:text-sky-300 flex items-center space-x-1 font-medium transition"
                    >
                      <History className="w-3.5 h-3.5" />
                      <span>{runs ? 'Hide Execution History' : 'View Execution History'}</span>
                      {runs ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>

                    {/* Run History List */}
                    {loadingRuns && (
                      <div className="py-2 text-xs text-slate-400 flex items-center space-x-1.5">
                        <RefreshCw className="w-3 h-3 animate-spin text-sky-400" />
                        <span>Loading execution runs...</span>
                      </div>
                    )}
                    {runs && (
                      <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
                        {runs.length === 0 ? (
                          <div className="text-[11px] text-slate-500 italic py-1">
                            No recorded executions yet.
                          </div>
                        ) : (
                          runs.map((r) => (
                            <div
                              key={r.run_id}
                              className="p-2 rounded bg-black/40 border border-slate-800/60 text-[11px] flex items-center justify-between font-mono"
                            >
                              <div className="flex items-center space-x-2">
                                {r.status === 'SUCCESS' ? (
                                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                ) : (
                                  <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                                )}
                                <span className="text-slate-300">{r.start_time}</span>
                                <span className="text-slate-500">({r.duration_ms}ms)</span>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className="text-slate-400">{r.result_row_count} records</span>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[9px] ${
                                    r.status === 'SUCCESS' ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'
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
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/60 text-xs text-slate-400 flex items-center justify-between">
          <span>Scheduled queries execute against MongoDB using bounded read-only constraints.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
