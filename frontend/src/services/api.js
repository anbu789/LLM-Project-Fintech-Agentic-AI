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

export default apiClient;
