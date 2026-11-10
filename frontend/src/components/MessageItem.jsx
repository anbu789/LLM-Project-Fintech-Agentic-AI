import React from 'react';
import { Bot, User, Clock, AlertCircle } from 'lucide-react';

export default function MessageItem({ message }) {
  const isUser = message.role === 'user';
  const isError = message.isError;

  return (
    <div className={`flex w-full py-3 px-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-2xl space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-white shadow-sm ${
            isUser ? 'bg-indigo-600' : isError ? 'bg-rose-600' : 'bg-sky-600'
          }`}
        >
          {isUser ? <User className="w-4 h-4" /> : isError ? <AlertCircle className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
        </div>

        {/* Bubble */}
        <div className="flex flex-col space-y-1">
          <div
            className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              isUser
                ? 'bg-sky-600 text-white rounded-tr-none'
                : isError
                ? 'bg-rose-50 text-rose-900 border border-rose-200 rounded-tl-none'
                : 'bg-white text-slate-800 border border-slate-200/80 rounded-tl-none'
            }`}
          >
            <div className="whitespace-pre-wrap break-words">{message.text}</div>
          </div>

          {/* Metadata badges for Assistant */}
          {!isUser && (
            <div className="flex items-center space-x-2 text-[10px] text-slate-400 px-1 font-mono">
              {message.provider && (
                <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                  {message.provider}:{message.model}
                </span>
              )}
              {message.requestId && (
                <span className="text-slate-400">id:{message.requestId}</span>
              )}
              {message.timestamp && (
                <span className="flex items-center space-x-0.5 text-slate-400">
                  <Clock className="w-2.5 h-2.5" />
                  <span>{message.timestamp}</span>
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
