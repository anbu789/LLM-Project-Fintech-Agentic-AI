import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { checkHealth, sendChatMessage } from './services/api';

export default function App() {
  const [conversationId, setConversationId] = useState(() => `conv-${Date.now().toString(36)}`);
  const [conversations, setConversations] = useState([]);
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [backendStatus, setBackendStatus] = useState('checking');
  const [activeModel, setActiveModel] = useState('');

  // Ping backend on mount
  useEffect(() => {
    let isMounted = true;
    checkHealth()
      .then((data) => {
        if (isMounted) {
          setBackendStatus(data.status === 'healthy' ? 'online' : 'offline');
        }
      })
      .catch(() => {
        if (isMounted) setBackendStatus('offline');
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleNewChat = () => {
    if (messages.length > 0) {
      const firstUserMsg = messages.find((m) => m.role === 'user');
      const title = firstUserMsg ? firstUserMsg.text.slice(0, 30) + '...' : 'Banking Discussion';
      setConversations((prev) => [
        { id: conversationId, title, messages },
        ...prev.filter((c) => c.id !== conversationId),
      ]);
    }
    setConversationId(`conv-${Date.now().toString(36)}`);
    setMessages([]);
    setError(null);
  };

  const handleSelectConv = (id) => {
    const found = conversations.find((c) => c.id === id);
    if (found) {
      setConversationId(found.id);
      setMessages(found.messages);
      setError(null);
    }
  };

  const handleSendMessage = async (text) => {
    if (!text.trim() || isLoading) return;

    setError(null);
    const userMsg = {
      id: `usr-${Date.now()}`,
      role: 'user',
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(text, conversationId);
      const aiMsg = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        text: response.message,
        provider: response.provider,
        model: response.model,
        requestId: response.request_id,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, aiMsg]);
      if (response.model) {
        setActiveModel(response.model);
      }
    } catch (err) {
      const errorMsgText = err.message || 'Failed to communicate with LLM provider.';
      setError(errorMsgText);
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        isError: true,
        text: `Error: ${errorMsgText}`,
        requestId: err.request_id || null,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-100 antialiased font-sans">
      <Sidebar
        onNewChat={handleNewChat}
        backendStatus={backendStatus}
        activeModel={activeModel}
        conversations={conversations}
        currentId={conversationId}
        onSelectConv={handleSelectConv}
      />
      <ChatInterface
        messages={messages}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
        error={error}
        onClearError={() => setError(null)}
      />
    </div>
  );
}
