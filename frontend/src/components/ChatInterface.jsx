import React, { useEffect, useRef, useState } from 'react';
import MessageItem from './MessageItem';
import ChatInput from './ChatInput';
import SchemaGuide from './SchemaGuide';
import { Bot, Users, Building2, ArrowLeftRight, CalendarClock, Menu, ShieldCheck, Lock, Database, AlertCircle, RefreshCw } from 'lucide-react';

const SAMPLE_QUESTIONS = [
  {
    title: 'Customer KYC Breakdown',
    tag: 'Aggregation · customers',
    icon: Users,
    prompt: 'How many customers are there in each KYC status?',
  },
  {
    title: 'Accounts by Branch City',
    tag: 'Join · accounts + branches',
    icon: Building2,
    prompt: 'Show accounts grouped by branch city.',
  },
  {
    title: 'Last 30 Days Transactions',
    tag: 'Date window · transactions',
    icon: ArrowLeftRight,
    prompt: 'Show transactions from the last 30 days.',
  },
  {
    title: 'Monday KYC Report',
    tag: 'Schedule preview · Q50',
    icon: CalendarClock,
    prompt: 'Generate the customer KYC-status count report every Monday at 9 AM.',
  },
];

export default function ChatInterface({
  messages,
  onSendMessage,
  onCancelRequest,
  onRetryMessage,
  isLoading,
  error,
  onClearError,
  backendStatus = 'checking',
  onRetryHealth,
  restoredPrompt,
  onRestoredPromptConsumed,
  onOpenSidebar,
}) {
  const messagesEndRef = useRef(null);
  const [isSchemaOpen, setIsSchemaOpen] = useState(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const statusIndicator =
    backendStatus === 'online'
      ? { dotClass: 'bg-emerald-600', srText: 'Backend online' }
      : backendStatus === 'offline'
      ? { dotClass: 'bg-rose-600', srText: 'Backend offline' }
      : { dotClass: 'bg-amber-500 animate-status-dot', srText: 'Checking backend status' };

  return (
    <div className="flex-1 min-w-0 flex flex-col h-full bg-slate-50 relative overflow-hidden">
      {/* Top Workspace Header */}
      <header className="h-14 bg-white/95 backdrop-blur-sm border-b border-slate-200/90 px-3 sm:px-6 flex items-center justify-between gap-2 sm:gap-3 shrink-0 shadow-card">
        <div className="flex items-center space-x-2 sm:space-x-3 min-w-0">
          {onOpenSidebar && (
            <button
              type="button"
              onClick={onOpenSidebar}
              aria-label="Open navigation sidebar"
              className="md:hidden min-w-[40px] min-h-[40px] inline-flex items-center justify-center p-2 -ml-1 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}
          <div className="flex items-center space-x-2.5 min-w-0">
            <span
              className={`w-2 h-2 rounded-full shrink-0 ring-4 ring-slate-100 ${statusIndicator.dotClass}`}
              title={statusIndicator.srText}
              aria-label={statusIndicator.srText}
            ></span>
            <span className="font-semibold text-slate-900 text-sm tracking-tight truncate">
              Banking Operations Assistant
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {backendStatus === 'offline' && (
            <button
              type="button"
              onClick={onRetryHealth}
              aria-label="Backend offline, retry connection"
              className="inline-flex items-center space-x-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg border bg-rose-50 text-rose-800 border-rose-200 hover:bg-rose-100 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
              <span>Backend Offline</span>
              <RefreshCw className="w-3 h-3 shrink-0" aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setIsSchemaOpen((prev) => !prev)}
            aria-expanded={isSchemaOpen}
            className={`inline-flex items-center space-x-1.5 text-xs font-medium px-2.5 sm:px-3 py-1.5 rounded-lg border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500 ${
              isSchemaOpen
                ? 'bg-fintech-700 text-white border-fintech-700 shadow-card'
                : 'bg-white text-slate-700 border-slate-300 hover:border-fintech-500 hover:text-fintech-800'
            }`}
          >
            <Database className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            <span className="hidden sm:inline">12 Collections</span>
          </button>
          <div className="hidden md:inline-flex items-center space-x-1.5 text-xs text-fintech-800 font-medium bg-fintech-50 border border-fintech-200/80 px-2.5 py-1.5 rounded-lg">
            <Lock className="w-3 h-3 text-fintech-700 shrink-0" aria-hidden="true" />
            <span>Read-Only · Synthetic Data</span>
          </div>
        </div>
      </header>

      {/* Collapsible Schema Reference (when conversing) */}
      {messages.length > 0 && isSchemaOpen && (
        <div className="bg-slate-100/80 border-b border-slate-200 px-3 sm:px-6 py-3 shrink-0 max-h-[55vh] overflow-y-auto shadow-card">
          <div className="max-w-4xl mx-auto">
            <SchemaGuide
              isOpen={true}
              onToggle={() => setIsSchemaOpen(false)}
              onSelectPrompt={(prompt) => {
                setIsSchemaOpen(false);
                onSendMessage(prompt);
              }}
              disabled={isLoading}
            />
          </div>
        </div>
      )}

      {/* Non-message operational error callout */}
      {error && (
        <div role="alert" className="bg-rose-50 border-b border-rose-200 px-4 sm:px-6 py-2.5 flex items-center justify-between text-xs text-rose-900">
          <div className="flex items-center space-x-2 min-w-0">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" aria-hidden="true" />
            <span className="font-medium truncate">{error}</span>
          </div>
          <button
            type="button"
            onClick={onClearError}
            aria-label="Dismiss error banner"
            className="text-rose-700 hover:text-rose-900 font-semibold uppercase text-[11px] ml-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 rounded px-2 py-0.5 shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Conversation Stream */}
      <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-5 sm:py-6 space-y-2">
        {messages.length === 0 ? (
          <div className="min-h-full flex flex-col items-center justify-center max-w-3xl mx-auto px-1 sm:px-4 py-4 space-y-5">
            {/* Workspace Introduction */}
            <div className="w-full flex flex-col sm:flex-row sm:items-center gap-4 text-left bg-white border border-slate-200/90 rounded-2xl p-5 sm:p-6 shadow-card">
              <div className="w-12 h-12 rounded-xl bg-fintech-700 text-white ring-1 ring-inset ring-fintech-200/20 flex items-center justify-center shrink-0 shadow-card">
                <Bot className="w-6 h-6" />
              </div>
              <div className="min-w-0 space-y-1">
                <h2 className="text-lg sm:text-xl font-semibold text-slate-900 tracking-tight">
                  Welcome to FinTech Agent
                </h2>
                <p className="text-xs sm:text-sm text-slate-700 leading-relaxed max-w-[66ch]">
                  Ask banking questions in plain English. Requests translate into schema-grounded, read-only MongoDB aggregation pipelines across 12 synthetic collections—or prepare recurring report previews for your explicit approval.
                </p>
              </div>
            </div>

            {/* Guardrails Ledger Bar */}
            <div className="w-full rounded-xl bg-white border border-slate-200/90 grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-200/90 shadow-card text-left">
              <div className="px-4 py-3 flex items-start space-x-2.5">
                <Database className="w-4 h-4 text-fintech-600 shrink-0 mt-0.5" aria-hidden="true" />
                <div className="min-w-0 text-xs">
                  <div className="font-semibold text-slate-900">Synthetic dataset</div>
                  <div className="text-slate-600 mt-0.5">
                    19,120 records (<code className="font-mono text-fintech-800">fintech_agent_db</code>)
                  </div>
                </div>
              </div>
              <div className="px-4 py-3 flex items-start space-x-2.5">
                <Lock className="w-4 h-4 text-fintech-600 shrink-0 mt-0.5" aria-hidden="true" />
                <div className="min-w-0 text-xs">
                  <div className="font-semibold text-slate-900">Read-only policy</div>
                  <div className="text-slate-600 mt-0.5">
                    Writes &amp; <code className="font-mono text-fintech-800">$out/$merge/$where</code> blocked
                  </div>
                </div>
              </div>
              <div className="px-4 py-3 flex items-start space-x-2.5">
                <ShieldCheck className="w-4 h-4 text-fintech-600 shrink-0 mt-0.5" aria-hidden="true" />
                <div className="min-w-0 text-xs">
                  <div className="font-semibold text-slate-900">Explicit approval</div>
                  <div className="text-slate-600 mt-0.5">
                    Schedules preview before registration
                  </div>
                </div>
              </div>
            </div>

            {/* Sample Prompts from SAMPLE_QUERIES.md */}
            <div className="w-full space-y-2 text-left">
              <div className="px-1 text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                Sample Queries
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full">
                {SAMPLE_QUESTIONS.map((q, idx) => {
                  const IconComponent = q.icon;
                  return (
                    <button
                      type="button"
                      key={idx}
                      onClick={() => onSendMessage(q.prompt)}
                      className="p-3.5 bg-white hover:bg-fintech-25 border border-slate-200/90 hover:border-fintech-500 rounded-xl transition duration-150 text-left group shadow-card hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="flex items-center space-x-2 text-slate-900 group-hover:text-fintech-800 font-semibold text-xs">
                          <span className="p-1.5 rounded-md bg-fintech-50 text-fintech-700 border border-fintech-200/70 group-hover:bg-fintech-100 transition-colors">
                            <IconComponent className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                          </span>
                          <span>{q.title}</span>
                        </span>
                        <span className="text-[10px] font-mono text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200/80 shrink-0">
                          {q.tag}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 line-clamp-2 group-hover:text-slate-900 leading-relaxed pl-8">
                        {q.prompt}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Collapsible 12-Collection Guide */}
            <SchemaGuide
              isOpen={isSchemaOpen}
              onToggle={() => setIsSchemaOpen((prev) => !prev)}
              onSelectPrompt={onSendMessage}
              disabled={isLoading}
            />
          </div>
        ) : (
          <div className="max-w-4xl mx-auto w-full space-y-2.5">
            {messages.map((msg) => (
              <MessageItem
                key={msg.id}
                message={msg}
                onRetry={onRetryMessage}
                isLoading={isLoading}
              />
            ))}
          </div>
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="max-w-4xl mx-auto w-full flex items-center space-x-3 py-3 px-1 sm:px-3"
          >
            <div className="w-8 h-8 rounded-full bg-fintech-600 text-white flex items-center justify-center shrink-0 shadow-card">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-white border border-slate-200/90 rounded-2xl rounded-tl-sm px-4 py-2.5 shadow-card flex items-center gap-3">
              <div className="flex items-center space-x-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-fintech-600 animate-status-dot"></span>
                <span className="w-1.5 h-1.5 rounded-full bg-fintech-600 animate-status-dot [animation-delay:0.2s]"></span>
                <span className="w-1.5 h-1.5 rounded-full bg-fintech-600 animate-status-dot [animation-delay:0.4s]"></span>
                <span className="text-xs text-slate-700 font-medium ml-1.5">Consulting LLM...</span>
              </div>
              {onCancelRequest && (
                <button
                  type="button"
                  onClick={onCancelRequest}
                  aria-label="Cancel active query"
                  className="text-xs font-medium text-slate-700 hover:text-rose-800 hover:bg-rose-50 border border-slate-200 hover:border-rose-200 rounded-md px-2.5 py-1 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput
        onSendMessage={onSendMessage}
        disabled={isLoading}
        restoredPrompt={restoredPrompt}
        onRestoredPromptConsumed={onRestoredPromptConsumed}
      />
    </div>
  );
}
