import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 35000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const checkHealth = async () => {
  try {
    const response = await apiClient.get('/health');
    return response.data;
  } catch (error) {
    if (error.response?.data) {
      throw error.response.data;
    }
    throw {
      success: false,
      error_code: 'NETWORK_ERROR',
      message: error.message || 'Failed to reach FinTech Agent backend.',
    };
  }
};

export const sendChatMessage = async (message, conversationId) => {
  try {
    const response = await apiClient.post('/chat', {
      message: message.trim(),
      conversation_id: conversationId || undefined,
    });
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    } else if (error.response?.data) {
      throw error.response.data;
    }
    throw {
      success: false,
      error_code: 'NETWORK_ERROR',
      message: error.message || 'Network communication failure with backend.',
    };
  }
};

export const fetchConversations = async () => {
  try {
    const response = await apiClient.get('/chat/conversations');
    return response.data;
  } catch (error) {
    return [];
  }
};

export const fetchConversation = async (conversationId) => {
  try {
    const response = await apiClient.get(`/chat/conversations/${conversationId}`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const deleteConversation = async (conversationId) => {
  try {
    const response = await apiClient.delete(`/chat/conversations/${conversationId}`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

// Phase 7 — Scheduled Queries & Reports
export const approveSchedule = async (previewId, idempotencyKey = null) => {
  try {
    const response = await apiClient.post('/schedules/approve', {
      preview_id: previewId,
      idempotency_key: idempotencyKey || undefined,
    });
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const fetchSchedules = async () => {
  try {
    const response = await apiClient.get('/schedules');
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const fetchSchedule = async (jobId) => {
  try {
    const response = await apiClient.get(`/schedules/${jobId}`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const pauseSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/pause`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const resumeSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/resume`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const cancelSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/cancel`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export const fetchScheduleRuns = async (jobId, limit = 50) => {
  try {
    const response = await apiClient.get(`/schedules/${jobId}/runs?limit=${limit}`);
    return response.data;
  } catch (error) {
    if (error.response?.data?.detail) {
      throw error.response.data.detail;
    }
    throw error;
  }
};

export default apiClient;
