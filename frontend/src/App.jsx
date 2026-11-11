import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import SchedulesDashboard from './components/SchedulesDashboard';
import AuthSessionModal from './components/AuthSessionModal';
import { useChatStore } from './store/useChatStore';

export default function App() {
  const [isSchedulesOpen, setIsSchedulesOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
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
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const newChat = useChatStore((s) => s.newChat);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const cancelActiveRequest = useChatStore((s) => s.cancelActiveRequest);
  const retryLastMessage = useChatStore((s) => s.retryLastMessage);
  const clearError = useChatStore((s) => s.clearError);
  const restoredPrompt = useChatStore((s) => s.restoredPrompt);
  const clearRestoredPrompt = useChatStore((s) => s.clearRestoredPrompt);
  const authUser = useChatStore((s) => s.authUser);
  const verifyAuthSession = useChatStore((s) => s.verifyAuthSession);
  const openAuthModal = useChatStore((s) => s.openAuthModal);
  const signOut = useChatStore((s) => s.signOut);

  // Ping backend, restore operator session if present, and load stored conversations on mount
  useEffect(() => {
    checkBackendHealth();
    verifyAuthSession();
    loadConversations();
  }, [checkBackendHealth, verifyAuthSession, loadConversations]);

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-slate-50 antialiased font-sans">
      <Sidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onNewChat={() => {
          newChat();
          setIsSidebarOpen(false);
        }}
        onOpenSchedules={() => {
          setIsSchedulesOpen(true);
          setIsSidebarOpen(false);
        }}
        backendStatus={backendStatus}
        onRetryHealth={checkBackendHealth}
        activeModel={activeModel}
        conversations={conversations}
        currentId={conversationId}
        onSelectConv={(id) => {
          selectConversation(id);
          setIsSidebarOpen(false);
        }}
        onDeleteConv={deleteConversation}
        authUser={authUser}
        onOpenAuthModal={openAuthModal}
        onSignOut={signOut}
      />
      <ChatInterface
        messages={messages}
        onSendMessage={sendMessage}
        onCancelRequest={cancelActiveRequest}
        onRetryMessage={retryLastMessage}
        isLoading={isLoading}
        error={error}
        onClearError={clearError}
        backendStatus={backendStatus}
        onRetryHealth={checkBackendHealth}
        restoredPrompt={restoredPrompt}
        onRestoredPromptConsumed={clearRestoredPrompt}
        onOpenSidebar={() => setIsSidebarOpen(true)}
      />
      <SchedulesDashboard
        isOpen={isSchedulesOpen}
        onClose={() => setIsSchedulesOpen(false)}
      />
      <AuthSessionModal />
    </div>
  );
}
