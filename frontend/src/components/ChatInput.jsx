import React, { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

export default function ChatInput({
  onSendMessage,
  disabled,
  restoredPrompt,
  onRestoredPromptConsumed,
}) {
  const [text, setText] = useState('');
  const [wasTruncated, setWasTruncated] = useState(false);
  const textareaRef = useRef(null);
  const MAX_CHARS = 2000;

  useEffect(() => {
    if (!restoredPrompt?.text) return;
    setText((current) => (current.trim() === '' ? restoredPrompt.text.slice(0, MAX_CHARS) : current));
    onRestoredPromptConsumed?.();
  }, [restoredPrompt, onRestoredPromptConsumed]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
  }, [text]);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSendMessage(trimmed);
    setText('');
    setWasTruncated(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleChange = (e) => {
    const val = e.target.value;
    if (val.length > MAX_CHARS) {
      setText(val.slice(0, MAX_CHARS));
      setWasTruncated(true);
      return;
    }
    setText(val);
    if (wasTruncated) {
      setWasTruncated(false);
    }
  };

  const isTooLong = text.length >= MAX_CHARS;

  return (
    <div className="px-3 py-3 sm:px-6 sm:py-3.5 bg-white/95 border-t border-slate-200/90 shrink-0">
      <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
        <div className="flex flex-col rounded-xl border border-slate-300 bg-white shadow-card focus-within:border-fintech-600 focus-within:ring-2 focus-within:ring-fintech-100 transition">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            aria-label="Banking query message"
            placeholder="Ask a banking question, query the 12 collections, or schedule a report..."
            className="w-full resize-none px-4 pt-3 pb-2 text-sm text-slate-900 placeholder-slate-500 bg-transparent focus:outline-none disabled:opacity-50 min-h-[46px] max-h-[180px] leading-relaxed"
          />

          <div className="px-3.5 py-2 border-t border-slate-100 bg-slate-50/75 rounded-b-xl flex items-center justify-between gap-2">
            <span className={`text-[11px] font-mono tabular-nums ${isTooLong ? 'text-rose-700 font-semibold' : 'text-slate-600'}`}>
              {text.length}/{MAX_CHARS}
            </span>

            <div className="flex items-center space-x-2.5">
              <span className="text-[11px] text-slate-600 hidden sm:inline-flex items-center">
                <span>Press</span>
                <kbd className="mx-1 px-1.5 py-0.5 bg-white text-slate-700 rounded border border-slate-300 text-[10px] font-mono shadow-sm">Enter ↵</kbd>
                <span>to send</span>
              </span>

              <button
                type="submit"
                disabled={!text.trim() || disabled}
                aria-label="Send message"
                className="inline-flex items-center justify-center min-w-[36px] min-h-[36px] px-3 py-1.5 rounded-lg bg-fintech-600 hover:bg-fintech-700 active:bg-fintech-800 disabled:opacity-40 disabled:pointer-events-none text-white transition shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
        {wasTruncated && (
          <p role="status" className="mt-1.5 text-center text-xs text-amber-800 font-medium">
            Query text exceeds {MAX_CHARS.toLocaleString()} characters and was trimmed to the limit.
          </p>
        )}
        <p className="mt-2 text-center text-[11px] text-slate-600">
          Read-only NL-to-MQL over synthetic banking data (<span className="font-mono text-slate-700">fintech_agent_db</span>) · Explicit approval required before scheduling.
        </p>
      </form>
    </div>
  );
}
