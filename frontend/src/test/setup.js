import '@testing-library/jest-dom';
import { useChatStore } from '../store/useChatStore';

// Polyfill window.HTMLElement.prototype.scrollIntoView if not present in JSDOM
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = function() {};
}

beforeEach(() => {
  useChatStore.setState({
    conversationId: `conv-test-${Date.now()}`,
    conversations: [],
    messages: [],
    isLoading: false,
    error: null,
    backendStatus: 'checking',
    activeModel: '',
  });
});
