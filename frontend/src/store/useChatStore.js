import { create } from 'zustand';
import {
  checkHealth,
  sendChatMessage,
  fetchConversations,
  fetchConversation,
  deleteConversation as apiDeleteConversation,
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

export const useChatStore = create((set, get) => ({
  conversationId: generateDefaultConvId(),
  conversations: [],
  messages: [],
  isLoading: false,
  error: null,
  backendStatus: 'checking',
  activeModel: '',

  setConversationId: (id) => {
    setStorageItem('fintech_agent_active_conv', id);
    set({ conversationId: id });
  },

  setMessages: (messages) => set({ messages }),

  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  setIsLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  setBackendStatus: (status) => set({ backendStatus: status }),

  setActiveModel: (model) => set({ activeModel: model }),

  checkBackendHealth: async () => {
    try {
      const data = await checkHealth();
      set({ backendStatus: data.status === 'healthy' ? 'online' : 'offline' });
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
    set({ isLoading: true, error: null });
    get().setConversationId(convId);
    try {
      const detail = await fetchConversation(convId);
      const formatted = (detail.messages || []).map((m, idx) => ({
        id: `msg-${convId}-${idx}`,
        role: m.role,
        text: m.content,
        provider: m.provider,
        model: m.model,
        requestId: m.request_id,
        timestamp: m.timestamp ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : undefined,
      }));
      set({ messages: formatted, isLoading: false });
    } catch (err) {
      set({ error: err.message || 'Failed to load conversation history.', isLoading: false });
    }
  },

  newChat: () => {
    const fresh = `conv-${Date.now().toString(36)}`;
    get().setConversationId(fresh);
    set({ messages: [], error: null });
  },

  deleteConversation: async (convId) => {
    try {
      await apiDeleteConversation(convId);
      set((state) => ({
        conversations: state.conversations.filter((c) => c.id !== convId),
      }));
      if (get().conversationId === convId) {
        get().newChat();
      }
    } catch (err) {
      console.warn('Failed to delete conversation:', err);
    }
  },

  sendMessage: async (text) => {
    const trimmed = text.trim();
    if (!trimmed || get().isLoading) return;

    set({ error: null });
    const convId = get().conversationId;
    const userMsg = {
      id: `usr-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    set((state) => ({
      messages: [...state.messages, userMsg],
      isLoading: true,
    }));

    try {
      const response = await sendChatMessage(trimmed, convId);
      const aiMsg = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        text: response.message,
        provider: response.provider,
        model: response.model,
        requestId: response.request_id,
        latencyMs: response.latency_ms,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      set((state) => ({
        messages: [...state.messages, aiMsg],
        activeModel: response.model || state.activeModel,
      }));
      // Refresh sidebar conversation list
      get().loadConversations();
    } catch (err) {
      const errorMsgText = err.message || 'Failed to communicate with LLM provider.';
      set({ error: errorMsgText });
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        isError: true,
        text: `Error: ${errorMsgText}`,
        requestId: err.request_id || null,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      set((state) => ({ messages: [...state.messages, errorMsg] }));
    } finally {
      set({ isLoading: false });
    }
  },
}));
