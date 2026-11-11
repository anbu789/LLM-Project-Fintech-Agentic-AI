import React from 'react';
import { MessageSquarePlus, ShieldCheck, Database, Bot, Cpu, Calendar } from 'lucide-react';

export default function Sidebar({ onNewChat, onOpenSchedules, backendStatus, activeModel, conversations, currentId, onSelectConv }) {
  return (
    <aside className="w-72 bg-slate-900 text-slate-200 flex flex-col h-full border-r border-slate-800 select-none">
      {/* Branding */}
      <div className="p-4 border-b border-slate-800 flex items-center space-x-3">
        <div className="w-10 h-10 rounded-lg bg-sky-600 flex items-center justify-center text-white shadow-md shadow-sky-900/30">
          <Bot className="w-6 h-6" />
        </div>
        <div>
          <h1 className="font-semibold text-white tracking-tight text-base leading-none">FinTech Agent</h1>
          <p className="text-xs text-sky-400 mt-1 font-mono">Team T11 · INT450</p>
        </div>
      </div>

      {/* Action */}
      <div className="p-3 space-y-2">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 bg-sky-600 hover:bg-sky-500 active:bg-sky-700 text-white rounded-lg text-sm font-medium transition shadow-sm"
        >
          <MessageSquarePlus className="w-4 h-4" />
          <span>New Conversation</span>
        </button>
        <button
          onClick={onOpenSchedules}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-sky-300 rounded-lg text-xs font-medium transition border border-slate-700/60"
        >
          <Calendar className="w-3.5 h-3.5" />
          <span>Scheduled Reports</span>
        </button>
      </div>

      {/* Navigation / Conversation List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        <div className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
          Conversations
        </div>
        {conversations.length === 0 ? (
          <div className="text-xs text-slate-500 px-3 py-4 text-center">
            No previous conversations in this session.
          </div>
        ) : (
          conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConv(conv.id)}
              className={`w-full text-left px-3 py-2 rounded-md text-xs truncate transition flex items-center space-x-2 ${
                conv.id === currentId
                  ? 'bg-slate-800 text-sky-300 font-medium'
                  : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
              <span className="truncate">{conv.title || 'Banking Discussion'}</span>
            </button>
          ))
        )}
      </div>

      {/* Status & Footer */}
      <div className="p-3 border-t border-slate-800 bg-slate-950/40 space-y-2 text-xs">
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Backend:</span>
          </span>
          <span className={`font-mono text-[11px] font-medium ${backendStatus === 'online' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {backendStatus === 'online' ? 'Connected' : 'Connecting...'}
          </span>
        </div>

        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            <span>LLM Shell:</span>
          </span>
          <span className="font-mono text-[11px] text-slate-300 truncate max-w-[120px]" title={activeModel}>
            {activeModel || 'Configured'}
          </span>
        </div>

        <div className="flex items-center justify-between text-slate-400 pt-1 border-t border-slate-800/60 text-[10px]">
          <span>Banking DB:</span>
          <span className="text-slate-400 font-mono">fintech_agent_db</span>
        </div>
      </div>
    </aside>
  );
}
