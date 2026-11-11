import React from 'react';
import { Bot, User, Clock, AlertCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import SchedulePreviewCard from './SchedulePreviewCard';

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
            {isUser ? (
              <div className="whitespace-pre-wrap break-words">{message.text}</div>
            ) : isError ? (
              <div className="whitespace-pre-wrap break-words text-rose-800 font-medium">{message.text}</div>
            ) : (
              <div className="prose prose-sm max-w-none text-slate-800 leading-relaxed break-words">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ node, ...props }) => (
                      <div className="overflow-x-auto my-2 border border-slate-200 rounded-lg">
                        <table className="min-w-full divide-y divide-slate-200 text-xs" {...props} />
                      </div>
                    ),
                    thead: ({ node, ...props }) => <thead className="bg-slate-50 text-slate-700 font-semibold" {...props} />,
                    th: ({ node, ...props }) => <th className="px-3 py-2 text-left font-semibold text-slate-700" {...props} />,
                    td: ({ node, ...props }) => <td className="px-3 py-1.5 border-t border-slate-100" {...props} />,
                    code: ({ node, inline, className, children, ...props }) => {
                      if (inline) {
                        return <code className="bg-slate-100 text-pink-600 px-1 py-0.5 rounded font-mono text-xs" {...props}>{children}</code>;
                      }
                      return (
                        <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto text-xs my-2 font-mono">
                          <code {...props}>{children}</code>
                        </pre>
                      );
                    },
                  }}
                >
                  {message.text}
                </ReactMarkdown>
              </div>
            )}
            {/* Phase 7: Interactive Schedule Preview Card */}
            {!isUser && message.schedulePreview && (
              <SchedulePreviewCard preview={message.schedulePreview} />
            )}
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
              {message.latencyMs && (
                <span className="text-slate-400">{message.latencyMs}ms</span>
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
