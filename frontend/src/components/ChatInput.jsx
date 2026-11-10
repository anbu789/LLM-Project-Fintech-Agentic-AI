import React, { useState, useRef, useEffect } from 'react';
import { Send, CornerDownLeft } from 'lucide-react';

export default function ChatInput({ onSendMessage, disabled }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);
  const MAX_CHARS = 2000;

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSendMessage(trimmed);
    setText('');
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
    if (val.length <= MAX_CHARS) {
      setText(val);
      // Auto-grow textarea
      e.target.style.height = 'auto';
      e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
    }
  };

  const isTooLong = text.length >= MAX_CHARS;

  return (
    <div className="p-4 bg-white border-t border-slate-200">
      <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
        <div className="relative rounded-xl border border-slate-300 bg-white shadow-sm focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-100 transition">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Ask a banking question (e.g. Explain what an NPA loan means)..."
            className="w-full resize-none px-4 pt-3 pb-10 text-sm text-slate-800 placeholder-slate-400 bg-transparent focus:outline-none disabled:opacity-50 min-h-[44px] max-h-[180px]"
          />

          <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between pointer-events-none">
            <span className={`text-[11px] font-mono ${isTooLong ? 'text-rose-500 font-semibold' : 'text-slate-400'}`}>
              {text.length}/{MAX_CHARS}
            </span>

            <div className="flex items-center space-x-2 pointer-events-auto">
              <span className="text-[10px] text-slate-400 hidden sm:inline-flex items-center">
                <span>Press</span>
                <kbd className="mx-1 px-1 py-0.5 bg-slate-100 text-slate-600 rounded border border-slate-200 text-[9px]">Enter ↵</kbd>
                <span>to send</span>
              </span>

              <button
                type="submit"
                disabled={!text.trim() || disabled}
                aria-label="Send message"
                className="inline-flex items-center justify-center p-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 active:bg-sky-700 disabled:opacity-30 disabled:pointer-events-none text-white transition shadow-sm"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
        <p className="mt-1.5 text-center text-[11px] text-slate-400">
          Phase 2 LLM conversational shell · Database query synthesis is reserved for Phase 4.
        </p>
      </form>
    </div>
  );
}
