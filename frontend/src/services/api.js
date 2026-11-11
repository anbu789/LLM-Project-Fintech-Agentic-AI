import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const parsedTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
export const API_TIMEOUT_MS = Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : 40000;
const AUTH_TOKEN_STORAGE_KEY = 'fintech_agent_auth_token';

let inMemoryAuthToken = null;
let unauthorizedHandler = null;

export const getAuthToken = () => {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage && typeof window.sessionStorage.getItem === 'function') {
      return window.sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || inMemoryAuthToken;
    }
  } catch {
    // Fallback when sessionStorage is unavailable
  }
  return inMemoryAuthToken;
};

export const setAuthToken = (token) => {
  inMemoryAuthToken = token || null;
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      if (token) {
        window.sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
      } else {
        window.sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
    }
  } catch {
    // Fallback when sessionStorage is unavailable
  }
};

export const clearAuthToken = () => {
  setAuthToken(null);
};

export const setUnauthorizedHandler = (handler) => {
  unauthorizedHandler = typeof handler === 'function' ? handler : null;
};

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const classifyErrorCategory = (errorCode, statusCode) => {
  if (errorCode === 'PROVIDER_TIMEOUT') return 'provider_timeout';
  if (errorCode === 'CLIENT_TIMEOUT') return 'client_timeout';
  if (errorCode === 'REQUEST_TIMEOUT' || errorCode === 'DATABASE_TIMEOUT' || statusCode === 504) {
    return 'backend_timeout';
  }
  if (
    errorCode === 'PROVIDER_UNAVAILABLE' ||
    errorCode === 'PROVIDER_RETRY_EXHAUSTED' ||
    errorCode === 'PROVIDER_API_ERROR' ||
    errorCode === 'PROVIDER_RATE_LIMIT'
  ) {
    return 'provider_error';
  }
  if (errorCode === 'VALIDATION_ERROR' || errorCode === 'INVALID_REQUEST' || errorCode === 'MISSING_API_KEY') {
    return 'validation_error';
  }
  if (errorCode === 'AUTH_REQUIRED' || errorCode === 'FORBIDDEN' || errorCode === 'PROVIDER_AUTH_ERROR' || statusCode === 401 || statusCode === 403) {
    return 'auth_error';
  }
  if (typeof statusCode === 'number' && statusCode >= 400) {
    return 'backend_http_error';
  }
  return 'network_error';
};

const extractApiError = (error) => {
  if (error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') {
    throw error;
  }

  const statusCode = error.response?.status;
  const detail = error.response?.data?.detail;
  const wwwAuth = error.response?.headers?.['www-authenticate'];

  // Clear operator session token only when backend Bearer authentication rejects the session
  if (statusCode === 401 && (typeof detail === 'string' || wwwAuth)) {
    clearAuthToken();
    if (unauthorizedHandler) {
      unauthorizedHandler();
    }
  }

  if (detail && typeof detail === 'object') {
    const errorCode = detail.error_code || (statusCode === 504 ? 'REQUEST_TIMEOUT' : 'API_ERROR');
    throw {
      status: statusCode,
      ...detail,
      error_code: errorCode,
      error_category: classifyErrorCategory(errorCode, statusCode),
    };
  }
  if (typeof detail === 'string') {
    const errorCode = statusCode === 401 ? 'AUTH_REQUIRED' : statusCode === 403 ? 'FORBIDDEN' : 'API_ERROR';
    throw {
      success: false,
      status: statusCode,
      error_code: errorCode,
      error_category: classifyErrorCategory(errorCode, statusCode),
      message: detail,
    };
  }
  if (error.response?.data && typeof error.response.data === 'object') {
    const errorCode = error.response.data.error_code || (statusCode >= 500 ? 'BACKEND_HTTP_ERROR' : 'API_ERROR');
    throw {
      status: statusCode,
      ...error.response.data,
      error_code: errorCode,
      error_category: classifyErrorCategory(errorCode, statusCode),
    };
  }
  if (error.response) {
    const errorCode = statusCode === 504 ? 'GATEWAY_TIMEOUT' : statusCode === 503 ? 'PROVIDER_UNAVAILABLE' : 'BACKEND_HTTP_ERROR';
    throw {
      success: false,
      status: statusCode,
      error_code: errorCode,
      error_category: classifyErrorCategory(errorCode, statusCode),
      message: `Backend returned HTTP ${statusCode}${error.response.statusText ? ` (${error.response.statusText})` : ''}.`,
    };
  }

  // Distinguish Axios client-side request timeout from network connectivity failure
  const isClientTimeout =
    error?.code === 'ECONNABORTED' ||
    error?.code === 'ETIMEDOUT' ||
    /timeout of \d+ms exceeded/i.test(error?.message || '');

  if (isClientTimeout) {
    const timeoutSec = Math.round(API_TIMEOUT_MS / 1000);
    throw {
      success: false,
      status: null,
      error_code: 'CLIENT_TIMEOUT',
      error_category: 'client_timeout',
      message: `Client request timed out after ${timeoutSec}s while waiting for backend response.`,
    };
  }

  throw {
    success: false,
    status: null,
    error_code: 'NETWORK_ERROR',
    error_category: 'network_error',
    message: error.message || 'Network communication failure with backend.',
  };
};

export const loginForToken = async (userId, role = 'analyst', password = null) => {
  try {
    const payload = { user_id: userId, role };
    if (password) {
      payload.password = password;
    }
    const response = await apiClient.post('/auth/token', payload);
    if (response.data?.access_token) {
      setAuthToken(response.data.access_token);
    }
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const fetchCurrentUser = async () => {
  try {
    const response = await apiClient.get('/auth/me');
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

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

export const sendChatMessage = async (message, conversationId, signal) => {
  try {
    const config = signal ? { signal } : undefined;
    const response = await apiClient.post(
      '/chat',
      {
        message: message.trim(),
        conversation_id: conversationId || undefined,
      },
      config
    );
    return response.data;
  } catch (error) {
    extractApiError(error);
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
    extractApiError(error);
  }
};

export const deleteConversation = async (conversationId) => {
  try {
    const response = await apiClient.delete(`/chat/conversations/${conversationId}`);
    return response.data;
  } catch (error) {
    extractApiError(error);
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
    extractApiError(error);
  }
};

export const fetchSchedules = async () => {
  try {
    const response = await apiClient.get('/schedules');
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const fetchSchedule = async (jobId) => {
  try {
    const response = await apiClient.get(`/schedules/${jobId}`);
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const pauseSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/pause`);
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const resumeSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/resume`);
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const cancelSchedule = async (jobId) => {
  try {
    const response = await apiClient.post(`/schedules/${jobId}/cancel`);
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export const fetchScheduleRuns = async (jobId, limit = 50) => {
  try {
    const response = await apiClient.get(`/schedules/${jobId}/runs?limit=${limit}`);
    return response.data;
  } catch (error) {
    extractApiError(error);
  }
};

export default apiClient;
