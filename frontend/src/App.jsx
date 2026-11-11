import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import SchedulesDashboard from './components/SchedulesDashboard';
import { useChatStore } from './store/useChatStore';

export default function App() {
  const [isSchedulesOpen, setIsSchedulesOpen] = useState(false);
  const conversationId = useChatStore((s) => s.conversationId);
  const conversations = useChatStore((s) => s.conversations);
  const messages = useChatStore((s) => s.messages);
  const isLoading = useChatStore((s) => s.isLoading);
  const error = useChatStore((s) => s.error);
  const backendStatus = useChatStore((s) => s.backendStatus);
  const activeModel = useChatStore((s) => s.activeModel);

  const checkBackendHealth = useChatStore((s) => s.checkBackendHealth);
  const loadConversations = useChatStore((s) => s.loadConversations);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const newChat = useChatStore((s) => s.newChat);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const setError = useChatStore((s) => s.setError);

  // Ping backend and load stored conversations on mount
  useEffect(() => {
    checkBackendHealth();
    loadConversations();
  }, [checkBackendHealth, loadConversations]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-100 antialiased font-sans">
      <Sidebar
        onNewChat={newChat}
        onOpenSchedules={() => setIsSchedulesOpen(true)}
        backendStatus={backendStatus}
        activeModel={activeModel}
        conversations={conversations}
        currentId={conversationId}
        onSelectConv={selectConversation}
      />
      <ChatInterface
        messages={messages}
        onSendMessage={sendMessage}
        isLoading={isLoading}
        error={error}
        onClearError={() => setError(null)}
      />
      <SchedulesDashboard
        isOpen={isSchedulesOpen}
        onClose={() => setIsSchedulesOpen(false)}
      />
    </div>
  );
}
