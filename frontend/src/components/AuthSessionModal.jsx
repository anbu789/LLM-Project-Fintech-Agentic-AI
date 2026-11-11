import React, { useEffect, useRef, useState } from 'react';
import { ShieldCheck, X, KeyRound, AlertCircle, Loader2 } from 'lucide-react';
import { useChatStore } from '../store/useChatStore';

const ROLE_OPTIONS = [
  { value: 'analyst', label: 'Analyst' },
  { value: 'auditor', label: 'Auditor' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'admin', label: 'Admin' },
];

export default function AuthSessionModal() {
  const isOpen = useChatStore((s) => s.isAuthModalOpen);
  const closeAuthModal = useChatStore((s) => s.closeAuthModal);
  const signIn = useChatStore((s) => s.signIn);
  const isSigningIn = useChatStore((s) => s.isSigningIn);
  const authError = useChatStore((s) => s.authError);

  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('analyst');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState(null);

  const dialogRef = useRef(null);
  const userIdInputRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      setLocalError(null);
      const rafId =
        typeof window !== 'undefined' && window.requestAnimationFrame
          ? window.requestAnimationFrame(() => userIdInputRef.current?.focus())
          : null;
      return () => {
        if (rafId) window.cancelAnimationFrame(rafId);
      };
    } else if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeAuthModal();
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
  }, [isOpen, closeAuthModal]);

  if (!isOpen) return null;

  const displayError = localError || authError;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = userId.trim();
    if (!trimmed) {
      setLocalError('Operator User ID is required.');
      return;
    }
    setLocalError(null);
    try {
      await signIn(trimmed, role, password.trim() || null);
      setUserId('');
      setPassword('');
    } catch {
      // Store populates authError on failure
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-fintech-950/60 backdrop-blur-[2px] p-3 sm:p-4 animate-modal-enter"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeAuthModal();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
        aria-describedby="auth-dialog-desc"
        className="bg-white border border-slate-200 rounded-2xl w-full max-w-md shadow-panel text-slate-900 overflow-hidden font-sans"
      >
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-3 bg-fintech-25/90">
          <div className="flex items-center space-x-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-fintech-100/90 border border-fintech-200 text-fintech-700 flex items-center justify-center shrink-0">
              <KeyRound className="w-4 h-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 id="auth-dialog-title" className="text-sm font-semibold tracking-tight text-slate-900 truncate">
                Operator Session Sign-In
              </h2>
              <p id="auth-dialog-desc" className="text-xs text-slate-600 truncate">
                Obtain a signed Bearer token for schedule previews &amp; approvals
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeAuthModal}
            aria-label="Close sign-in dialog"
            className="min-w-[36px] min-h-[36px] inline-flex items-center justify-center p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-white border border-transparent hover:border-slate-200 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed bg-slate-50/90 border border-slate-200 rounded-lg p-3">
            Schedule previews generated while signed in bind ownership strictly to your cryptographic JWT{' '}
            <code className="font-mono text-fintech-800">user_id</code>. Tokens are stored in session memory only.
          </p>

          {displayError && (
            <div
              role="alert"
              className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs flex items-start space-x-2"
            >
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" aria-hidden="true" />
              <span className="font-medium break-words">{displayError}</span>
            </div>
          )}

          <div>
            <label htmlFor="operator-user-id" className="block text-xs font-semibold text-slate-800 mb-1">
              User ID
            </label>
            <input
              ref={userIdInputRef}
              id="operator-user-id"
              name="user_id"
              type="text"
              autoComplete="username"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="Enter operator ID (e.g. alice)"
              disabled={isSigningIn}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-fintech-500 focus:border-fintech-500"
            />
          </div>

          <div>
            <label htmlFor="operator-role" className="block text-xs font-semibold text-slate-800 mb-1">
              Role
            </label>
            <select
              id="operator-role"
              name="role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={isSigningIn}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-fintech-500 focus:border-fintech-500"
            >
              {ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="operator-password" className="block text-xs font-semibold text-slate-800 mb-1">
              Password <span className="text-slate-500 font-normal">(optional in local token mode)</span>
            </label>
            <input
              id="operator-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Optional passphrase"
              disabled={isSigningIn}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-fintech-500 focus:border-fintech-500"
            />
          </div>

          <div className="pt-3 flex items-center justify-end space-x-2 border-t border-slate-200">
            <button
              type="button"
              onClick={closeAuthModal}
              disabled={isSigningIn}
              className="h-9 px-3.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSigningIn}
              className="h-9 inline-flex items-center space-x-1.5 px-4 text-xs font-semibold text-white bg-fintech-600 hover:bg-fintech-700 active:bg-fintech-800 rounded-lg shadow-sm transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fintech-500"
            >
              {isSigningIn ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                  <span>Signing In...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Sign In</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
