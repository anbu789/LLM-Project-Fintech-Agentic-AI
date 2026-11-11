import React, { useEffect } from 'react';
import { MessageSquarePlus, ShieldCheck, Bot, Cpu, Calendar, X, Trash2, RefreshCw, AlertCircle, KeyRound, LogOut } from 'lucide-react';

export default function Sidebar({
  isOpen = false,
  onClose,
  onNewChat,
  onOpenSchedules,
  backendStatus,
  onRetryHealth,
  activeModel,
  conversations,
  currentId,
  onSelectConv,
  onDeleteConv,
  authUser = null,
  onOpenAuthModal,
  onSignOut,
}) {
  useEffect(() => {
    if (!isOpen || !onClose) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const statusMeta =
    backendStatus === 'online'
      ? {
          label: 'Connected',
          color: 'text-emerald-300',
          icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />,
        }
      : backendStatus === 'offline'
      ? {
          label: 'Offline',
          color: 'text-rose-300',
          icon: <AlertCircle className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />,
        }
      : {
          label: 'Checking...',
          color: 'text-amber-300',
          icon: <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" aria-hidden="true" />,
        };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-fintech-950/50 backdrop-blur-[1px] md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        aria-label="Conversation history and controls"
        className={`fixed inset-y-0 left-0 z-40 w-72 shrink-0 bg-fintech-900 text-fintech-50 flex flex-col h-full border-r border-fintech-800/90 transition-transform duration-200 ease-out md:static md:translate-x-0 ${
          isOpen ? 'translate-x-0 shadow-panel md:shadow-none' : '-translate-x-full'
        }`}
      >
        {/* Branding */}
        <div className="px-4 py-3.5 border-b border-fintech-800/80 flex items-center justify-between gap-2">
          <div className="flex items-center space-x-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-fintech-500 to-fintech-700 ring-1 ring-white/15 flex items-center justify-center text-white shadow-sm shrink-0">
              <Bot className="w-5 h-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h1 className="font-semibold text-white tracking-tight text-sm leading-tight truncate">FinTech Agent</h1>
              <p className="text-[11px] text-fintech-100/90 mt-0.5 truncate">Banking Operations Analytics</p>
              <p className="text-[10px] font-mono text-fintech-200/80 mt-0.5 truncate">Team T11 · INT450</p>
            </div>
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close navigation sidebar"
              className="md:hidden p-2 rounded-lg text-fintech-200 hover:text-white hover:bg-fintech-800 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Actions */}
        <div className="p-3 border-b border-fintech-800/75 space-y-2">
          <button
            type="button"
            onClick={onNewChat}
            className="w-full h-9 flex items-center justify-center space-x-2 px-3.5 bg-fintech-600 hover:bg-fintech-500 active:bg-fintech-700 text-white rounded-lg text-xs font-semibold transition shadow-sm ring-1 ring-inset ring-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200"
          >
            <MessageSquarePlus className="w-4 h-4 shrink-0" aria-hidden="true" />
            <span>New Conversation</span>
          </button>
          <button
            type="button"
            onClick={onOpenSchedules}
            className="w-full h-9 flex items-center justify-center space-x-2 px-3.5 bg-fintech-800/75 hover:bg-fintech-800 text-fintech-100 hover:text-white rounded-lg text-xs font-medium transition border border-fintech-700/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200"
          >
            <Calendar className="w-3.5 h-3.5 text-fintech-200 shrink-0" aria-hidden="true" />
            <span>Scheduled Reports</span>
          </button>
        </div>

        {/* Navigation / Conversation List */}
        <div className="flex-1 overflow-y-auto sidebar-scroll px-3 py-3 space-y-1">
          <div className="px-2 pb-1.5 flex items-center justify-between">
            <span className="text-[11px] font-semibold tracking-wider text-fintech-200 uppercase">
              Conversations
            </span>
            {conversations.length > 0 && (
              <span className="text-[10px] font-mono text-fintech-200/85 tabular-nums px-1.5 py-0.5 rounded bg-fintech-800/80 border border-fintech-700/60">
                {conversations.length}
              </span>
            )}
          </div>
          {conversations.length === 0 ? (
            <div className="text-xs text-fintech-200/80 px-3 py-5 mx-1 rounded-lg border border-dashed border-fintech-800 bg-fintech-950/35 text-center leading-relaxed">
              No previous conversations in this session.
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`group flex items-center gap-1 rounded-lg border transition ${
                  conv.id === currentId
                    ? 'bg-fintech-800/95 text-white font-medium border-fintech-600/60 shadow-sm'
                    : 'text-fintech-100/90 border-transparent hover:bg-fintech-800/55 hover:text-white'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelectConv(conv.id)}
                  aria-current={conv.id === currentId ? 'page' : undefined}
                  className="flex-1 min-w-0 text-left px-3 py-2 text-xs truncate flex items-center space-x-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200 rounded-md"
                >
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${conv.id === currentId ? 'bg-fintech-200' : 'bg-fintech-500'}`}></span>
                  <span className="truncate">{conv.title || 'Banking Discussion'}</span>
                </button>
                {onDeleteConv && (
                  <button
                    type="button"
                    onClick={() => onDeleteConv(conv.id)}
                    aria-label={`Delete conversation ${conv.title || 'Banking Discussion'}`}
                    title="Delete conversation"
                    className="p-1.5 mr-1 rounded-md text-fintech-200/80 hover:text-rose-300 hover:bg-fintech-950/70 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200 shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* Status & Footer */}
        <div className="p-3 border-t border-fintech-800/90 bg-fintech-950/75 space-y-2.5 text-xs tabular-nums">
          {/* Operator Session Card */}
          <div className="rounded-lg bg-fintech-900/90 border border-fintech-800/90 px-2.5 py-2 flex items-center justify-between gap-2">
            <span className="flex items-center space-x-2 min-w-0">
              <KeyRound className="w-3.5 h-3.5 text-fintech-200 shrink-0" aria-hidden="true" />
              <span className="truncate text-[11px]">
                {authUser ? (
                  <span title={`Signed in as ${authUser.user_id} (${authUser.role})`}>
                    <span className="font-mono text-emerald-300 font-semibold">{authUser.user_id}</span>
                    <span className="text-fintech-200/80 text-[10px] ml-1">({authUser.role})</span>
                  </span>
                ) : (
                  <span className="text-fintech-200/85">Not signed in</span>
                )}
              </span>
            </span>
            {authUser ? (
              onSignOut && (
                <button
                  type="button"
                  onClick={onSignOut}
                  aria-label="Sign out operator session"
                  className="inline-flex items-center space-x-1 px-2 py-1 rounded-md bg-fintech-800 hover:bg-fintech-700 text-fintech-100 hover:text-white text-[10px] font-semibold border border-fintech-700 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200 shrink-0"
                >
                  <LogOut className="w-2.5 h-2.5" aria-hidden="true" />
                  <span>Sign Out</span>
                </button>
              )
            ) : (
              onOpenAuthModal && (
                <button
                  type="button"
                  onClick={onOpenAuthModal}
                  aria-label="Sign in operator session"
                  className="px-2.5 py-1 rounded-md bg-fintech-600 hover:bg-fintech-500 text-white text-[10px] font-semibold border border-fintech-500 transition shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200 shrink-0"
                >
                  Sign In
                </button>
              )
            )}
          </div>

          {/* System Telemetry */}
          <div className="space-y-1.5 px-1">
            <div className="flex items-center justify-between text-fintech-100/90 gap-2">
              <span className="flex items-center space-x-1.5">
                {statusMeta.icon}
                <span>Backend:</span>
              </span>
              <span className="flex items-center space-x-1.5">
                <span className={`font-mono text-[11px] font-medium ${statusMeta.color}`}>
                  {statusMeta.label}
                </span>
                {backendStatus === 'offline' && onRetryHealth && (
                  <button
                    type="button"
                    onClick={onRetryHealth}
                    aria-label="Retry backend connection"
                    className="px-1.5 py-0.5 rounded bg-fintech-800 hover:bg-fintech-700 text-fintech-100 text-[10px] font-semibold border border-fintech-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-200"
                  >
                    Retry
                  </button>
                )}
              </span>
            </div>

            <div className="flex items-center justify-between text-fintech-100/90">
              <span className="flex items-center space-x-1.5">
                <Cpu className="w-3.5 h-3.5 text-fintech-200" aria-hidden="true" />
                <span>Model:</span>
              </span>
              <span className="font-mono text-[11px] text-fintech-50 truncate max-w-[125px]" title={activeModel}>
                {activeModel || 'Configured'}
              </span>
            </div>

            <div className="flex items-center justify-between text-fintech-200/85 pt-1 border-t border-fintech-800/75 text-[11px]">
              <span>Synthetic DB:</span>
              <span className="text-fintech-100 font-mono">fintech_agent_db</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
