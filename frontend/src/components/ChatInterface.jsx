import React, { useEffect, useRef } from 'react';
import MessageItem from './MessageItem';
import ChatInput from './ChatInput';
import { Bot, Sparkles, BookOpen, ShieldAlert, CreditCard } from 'lucide-react';

const SAMPLE_QUESTIONS = [
  {
    title: 'NPA Loans',
    icon: ShieldAlert,
    prompt: 'Explain what an NPA loan means and how banks classify them.',
  },
  {
    title: 'KYC vs AML',
    icon: BookOpen,
    prompt: 'What is the difference between KYC and AML compliance in banking operations?',
  },
  {
    title: 'Fraud Alert Priorities',
    icon: Sparkles,
    prompt: 'What criteria typically trigger high-priority fraud alerts on transactions?',
  },
  {
    title: 'Account Types',
    icon: CreditCard,
    prompt: 'Explain the operational differences between savings accounts and current accounts.',
  },
];

export default function ChatInterface({ messages, onSendMessage, isLoading, error, onClearError }) {
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-50 relative overflow-hidden">
      {/* Top Header */}
      <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0 shadow-sm">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></div>
          <span className="font-medium text-slate-800 text-sm">Banking Operations Assistant</span>
          <span className="text-xs text-slate-400 font-mono hidden sm:inline">| INT450 LLM Shell</span>
        </div>
        <div className="text-xs text-slate-500 font-mono bg-slate-100 px-2 py-1 rounded">
          Read-Only Mode
        </div>
      </header>

      {/* Error Callout */}
      {error && (
        <div className="bg-rose-50 border-b border-rose-200 px-6 py-2.5 flex items-center justify-between text-xs text-rose-800">
          <span className="font-medium">{error}</span>
          <button
            onClick={onClearError}
            className="text-rose-600 hover:text-rose-800 font-semibold uppercase text-[10px] ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Conversation Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center max-w-xl mx-auto text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-sky-100 text-sky-600 flex items-center justify-center mb-4 shadow-sm">
              <Bot className="w-8 h-8" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900 mb-1">
              Welcome to FinTech Agent
            </h2>
            <p className="text-xs text-slate-600 mb-6 leading-relaxed max-w-md">
              Ask questions about banking terminology, regulatory definitions, risk categories, or operational workflows.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full text-left">
              {SAMPLE_QUESTIONS.map((q, idx) => {
                const IconComponent = q.icon;
                return (
                  <button
                    key={idx}
                    onClick={() => onSendMessage(q.prompt)}
                    className="p-3 bg-white hover:bg-sky-50 border border-slate-200 hover:border-sky-300 rounded-xl transition text-left group shadow-xs"
                  >
                    <div className="flex items-center space-x-2 text-sky-700 font-medium text-xs mb-1">
                      <IconComponent className="w-3.5 h-3.5 text-sky-600" />
                      <span>{q.title}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-2 group-hover:text-slate-700">
                      {q.prompt}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          messages.map((msg) => <MessageItem key={msg.id} message={msg} />)
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex items-center space-x-3 py-3 px-4">
            <div className="w-8 h-8 rounded-full bg-sky-600 text-white flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-none px-4 py-2.5 shadow-sm flex items-center space-x-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-bounce"></span>
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-bounce [animation-delay:0.2s]"></span>
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-bounce [animation-delay:0.4s]"></span>
              <span className="text-xs text-slate-400 font-mono ml-2">Consulting LLM...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSendMessage={onSendMessage} disabled={isLoading} />
    </div>
  );
}
