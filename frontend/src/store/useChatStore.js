import { create } from 'zustand';
import {
  checkHealth,
  sendChatMessage,
  fetchConversations,
  fetchConversation,
  deleteConversation as apiDeleteConversation,
  loginForToken,
  fetchCurrentUser,
  getAuthToken,
  clearAuthToken,
  setUnauthorizedHandler,
} from '../services/api';

const getStorageItem = (key) => {
  try {
    if (typeof window !== 'undefined' && window.localStorage && typeof window.localStorage.getItem === 'function') {
      return window.localStorage.getItem(key);
    }
  } catch {
    // Fallback when storage is restricted or unavailable in test environment
  }
  return null;
};

const setStorageItem = (key, value) => {
  try {
    if (typeof window !== 'undefined' && window.localStorage && typeof window.localStorage.setItem === 'function') {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Fallback when storage is restricted or unavailable
  }
};

const generateDefaultConvId = () => {
  const saved = getStorageItem('fintech_agent_active_conv');
  if (saved && /^[a-zA-Z0-9_\-]{1,64}$/.test(saved)) {
    return saved;
  }
  const fresh = `conv-${Date.now().toString(36)}`;
  setStorageItem('fintech_agent_active_conv', fresh);
  return fresh;
};

const getSessionJson = (key, fallback) => {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage && typeof window.sessionStorage.getItem === 'function') {
      const raw = window.sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    }
  } catch {
    // Fallback when sessionStorage is restricted or unavailable
  }
  return fallback;
};

const setSessionJson = (key, value) => {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage && typeof window.sessionStorage.setItem === 'function') {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    }
  } catch {
    // Fallback when sessionStorage is restricted or unavailable
  }
};

let activeSelectSeq = 0;

export const useChatStore = create((set, get) => ({
  conversationId: generateDefaultConvId(),
  conversations: [],
  messages: [],
  isLoading: false,
  activeController: null,
  error: null,
  backendStatus: 'checking', // 'checking' | 'online' | 'offline'
  activeModel: '',
  lastFailedPrompt: null,
  restoredPrompt: null,
  approvedPreviews: getSessionJson('fintech_agent_approved_previews', {}),
  authUser: null,
  authToken: getAuthToken(),
  authError: null,
  isSigningIn: false,
  isAuthModalOpen: false,

  openAuthModal: () => set({ isAuthModalOpen: true, authError: null }),

  closeAuthModal: () => set({ isAuthModalOpen: false, authError: null }),

  verifyAuthSession: async () => {
    const token = getAuthToken();
    if (!token) {
      set({ authUser: null, authToken: null });
      return null;
    }
    try {
      const user = await fetchCurrentUser();
      set({ authUser: user || null, authToken: token });
      return user;
    } catch {
      clearAuthToken();
      set({ authUser: null, authToken: null });
      return null;
    }
  },

  signIn: async (userId, role = 'analyst', password = null) => {
    const cleanUserId = (userId || '').trim();
    if (!cleanUserId) {
      set({ authError: 'Please enter an operator user ID.' });
      return null;
    }
    set({ isSigningIn: true, authError: null });
    try {
      const prevUserId = get().authUser?.user_id;
      const response = await loginForToken(cleanUserId, role, password || null);
      const nextUser = { user_id: response.user_id, role: response.role };
      if (prevUserId && prevUserId !== nextUser.user_id) {
        setSessionJson('fintech_agent_approved_previews', {});
        set({ approvedPreviews: {} });
      }
      set({
        authUser: nextUser,
        authToken: response.access_token || getAuthToken(),
        isSigningIn: false,
        isAuthModalOpen: false,
        authError: null,
      });
      return response;
    } catch (err) {
      const msg = typeof err === 'string' ? err : err?.message || 'Authentication failed.';
      set({ isSigningIn: false, authError: msg });
      throw err;
    }
  },

  signOut: () => {
    clearAuthToken();
    setSessionJson('fintech_agent_approved_previews', {});
    set({
      authUser: null,
      authToken: null,
      authError: null,
      approvedPreviews: {},
    });
  },

  setConversationId: (id) => {
    setStorageItem('fintech_agent_active_conv', id);
    set({ conversationId: id });
  },

  setMessages: (messages) => set({ messages }),

  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  setIsLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  clearError: () => set({ error: null }),

  clearRestoredPrompt: () => set({ restoredPrompt: null }),

  setBackendStatus: (status) => set({ backendStatus: status }),

  setActiveModel: (model) => set({ activeModel: model }),

  markPreviewApproved: (previewId, approvedJob) => {
    if (!previewId || !approvedJob) return;
    set((state) => {
      const next = { ...state.approvedPreviews, [previewId]: approvedJob };
      setSessionJson('fintech_agent_approved_previews', next);
      return { approvedPreviews: next };
    });
  },

  checkBackendHealth: async () => {
    set({ backendStatus: 'checking' });
    try {
      const data = await checkHealth();
      set({ backendStatus: data?.status === 'healthy' ? 'online' : 'offline' });
    } catch {
      set({ backendStatus: 'offline' });
    }
  },

  loadConversations: async () => {
    try {
      const items = await fetchConversations();
      if (Array.isArray(items)) {
        const mapped = items.map((c) => ({
          id: c.conversation_id,
          title: c.title,
          messageCount: c.message_count,
          updatedAt: c.updated_at,
        }));
        set({ conversations: mapped });
      }
    } catch (err) {
      console.warn('Failed to load stored conversations:', err);
    }
  },

  selectConversation: async (convId) => {
    const seq = ++activeSelectSeq;
    const prevController = get().activeController;
    set({ isLoading: true, error: null, restoredPrompt: null, lastFailedPrompt: null, activeController: null });
    if (prevController) {
      prevController.abort();
    }
    try {
      const detail = await fetchConversation(convId);
      if (seq !== activeSelectSeq) {
        return;
      }
      const formatted = (detail.messages || []).map((m, idx) => ({
        id: `msg-${convId}-${idx}`,
        role: m.role,
        text: m.content,
        rawText: m.content,
        trace: m.trace ?? null,
        provider: m.provider,
        model: m.model,
        requestId: m.request_id,
        latencyMs: m.latency_ms,
        pipelineSpec: m.pipeline_spec ?? null,
        selectedCollection: m.selected_collection ?? null,
        validationStatus: m.validation_status ?? null,
        queryExplanation: m.query_explanation ?? null,
        schedulePreview: m.schedule_preview ?? null,
        previewId: m.preview_id ?? m.schedule_preview?.preview_id ?? null,
        timestamp: m.timestamp ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : undefined,
      }));
      get().setConversationId(convId);
      set({ messages: formatted, isLoading: false });
    } catch (err) {
      if (seq !== activeSelectSeq) {
        return;
      }
      set({
        error: typeof err === 'string' ? err : err?.message || 'Failed to load conversation history.',
        isLoading: false,
      });
    }
  },

  newChat: () => {
    activeSelectSeq += 1;
    const prevController = get().activeController;
    const fresh = `conv-${Date.now().toString(36)}`;
    get().setConversationId(fresh);
    set({
      messages: [],
      error: null,
      isLoading: false,
      activeController: null,
      lastFailedPrompt: null,
      restoredPrompt: null,
    });
    if (prevController) {
      prevController.abort();
    }
  },

  deleteConversation: async (convId) => {
    set({ error: null });
    try {
      await apiDeleteConversation(convId);
      set((state) => ({
        conversations: state.conversations.filter((c) => c.id !== convId),
      }));
      if (get().conversationId === convId) {
        get().newChat();
      }
    } catch (err) {
      set({
        error: typeof err === 'string' ? err : err?.message || 'Failed to delete conversation.',
      });
    }
  },

  cancelActiveRequest: () => {
    const controller = get().activeController;
    if (controller) {
      controller.abort();
    }
  },

  retryLastMessage: async (errorMsgId, promptText) => {
    if (!promptText || get().isLoading) return;
    await get().sendMessage(promptText, { retryErrorMsgId: errorMsgId });
  },

  sendMessage: async (text, options = {}) => {
    const trimmed = text.trim();
    if (!trimmed || get().isLoading) return;

    const { retryErrorMsgId = null } = options;
    const convId = get().conversationId;
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const userMsg = {
      id: `usr-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    set((state) => {
      const cleanedMessages = retryErrorMsgId
        ? state.messages.filter((m) => m.id !== retryErrorMsgId)
        : state.messages;
      const lastMsg = cleanedMessages[cleanedMessages.length - 1];
      const shouldAppendUser = !(retryErrorMsgId && lastMsg?.role === 'user' && lastMsg?.text === trimmed);
      return {
        error: null,
        lastFailedPrompt: null,
        restoredPrompt: null,
        messages: shouldAppendUser ? [...cleanedMessages, userMsg] : cleanedMessages,
        isLoading: true,
        activeController: controller,
      };
    });

    try {
      const response = await sendChatMessage(trimmed, convId, controller?.signal);
      if (get().conversationId !== convId) {
        return;
      }
      const aiMsg = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        text: response.message,
        rawText: response.message,
        trace: response.trace,
        provider: response.provider,
        model: response.model,
        requestId: response.request_id,
        latencyMs: response.latency_ms,
        pipelineSpec: response.pipeline_spec,
        selectedCollection: response.selected_collection,
        validationStatus: response.validation_status,
        queryExplanation: response.query_explanation,
        schedulePreview: response.schedule_preview,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      set((state) => ({
        messages: [...state.messages, aiMsg],
        activeModel: response.model || state.activeModel,
      }));
      // Refresh sidebar conversation list
      get().loadConversations();
    } catch (err) {
      const isActiveRequest = get().activeController === controller && get().conversationId === convId;
      if (!isActiveRequest) {
        return;
      }

      const isCanceled =
        controller?.signal?.aborted ||
        err?.code === 'ERR_CANCELED' ||
        err?.name === 'CanceledError';
      if (isCanceled) {
        set((state) => ({
          messages: retryErrorMsgId ? state.messages : state.messages.filter((m) => m.id !== userMsg.id),
          restoredPrompt: { text: trimmed, key: Date.now() },
        }));
        return;
      }

      const errorMsgText =
        typeof err === 'string'
          ? err
          : err?.message || 'Failed to communicate with LLM provider.';
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        isError: true,
        text: errorMsgText,
        failedPrompt: trimmed,
        errorCode: err?.error_code || null,
        errorCategory: err?.error_category || null,
        httpStatus: err?.status || null,
        requestId: err?.request_id || null,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      set((state) => ({
        messages: [...state.messages, errorMsg],
        lastFailedPrompt: trimmed,
        restoredPrompt: { text: trimmed, key: Date.now() },
      }));
    } finally {
      set((state) => (
        state.activeController === controller
          ? { isLoading: false, activeController: null }
          : {}
      ));
    }
  },
}));

setUnauthorizedHandler(() => {
  useChatStore.setState({ authUser: null, authToken: null });
});
