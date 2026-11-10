import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../App';
import * as apiService from '../services/api';

describe('FinTech Agent Frontend Chat Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiService, 'checkHealth').mockResolvedValue({
      status: 'healthy',
      service: 'fintech-agent-api',
      version: '1.0.0',
    });
  });

  it('1. Chat page renders with branding and welcome state', async () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'FinTech Agent' })).toBeInTheDocument();
    expect(screen.getByText(/Welcome to FinTech Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/Banking Operations Assistant/i)).toBeInTheDocument();
  });

  it('2. Input accepts text', () => {
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'Explain KYC requirements' } });
    expect(textarea.value).toBe('Explain KYC requirements');
  });

  it('3. Empty or whitespace messages cannot be submitted', () => {
    render(<App />);
    const sendButton = screen.getByRole('button', { name: /Send message/i });
    expect(sendButton).toBeDisabled();

    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: '   ' } });
    expect(sendButton).toBeDisabled();
  });

  it('4. Send operation calls the API service and displays user and AI message', async () => {
    vi.spyOn(apiService, 'sendChatMessage').mockResolvedValue({
      success: true,
      conversation_id: 'conv-test-123',
      request_id: 'req-abc-456',
      message: 'A Non-Performing Asset (NPA) is a loan overdue for over 90 days.',
      provider: 'mock',
      model: 'claude-3-5-sonnet-20241022',
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    const sendButton = screen.getByRole('button', { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: 'What is an NPA?' } });
    fireEvent.click(sendButton);

    // 5. User message appears
    expect(screen.getByText('What is an NPA?')).toBeInTheDocument();

    // 6. AI response appears
    await waitFor(() => {
      expect(screen.getByText(/A Non-Performing Asset \(NPA\) is a loan overdue/i)).toBeInTheDocument();
    });
  });

  it('7. Displays loading indicator during pending API call', async () => {
    let resolvePromise;
    const delayedPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    vi.spyOn(apiService, 'sendChatMessage').mockReturnValue(delayedPromise);

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    const sendButton = screen.getByRole('button', { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: 'Test loading' } });
    fireEvent.click(sendButton);

    expect(screen.getByText(/Consulting LLM\.\.\./i)).toBeInTheDocument();

    resolvePromise({
      success: true,
      conversation_id: 'conv-test',
      request_id: 'req-1',
      message: 'Finished loading.',
      provider: 'mock',
      model: 'test-model',
    });

    await waitFor(() => {
      expect(screen.queryByText(/Consulting LLM\.\.\./i)).not.toBeInTheDocument();
    });
  });

  it('8. Displays error banner and error bubble when API fails', async () => {
    vi.spyOn(apiService, 'sendChatMessage').mockRejectedValue({
      success: false,
      error_code: 'MISSING_API_KEY',
      message: 'API key for LLM provider is not configured. Please set LLM_API_KEY in .env.',
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    const sendButton = screen.getByRole('button', { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: 'Trigger error' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getAllByText(/API key for LLM provider is not configured/i).length).toBeGreaterThan(0);
    });
  });

  it('9. Clicking a sample prompt populates and submits the question', async () => {
    vi.spyOn(apiService, 'sendChatMessage').mockResolvedValue({
      success: true,
      conversation_id: 'conv-sample',
      request_id: 'req-sample',
      message: 'NPA classification explanation...',
      provider: 'mock',
      model: 'test-model',
    });

    render(<App />);
    const sampleBtn = screen.getByText(/NPA Loans/i);
    fireEvent.click(sampleBtn);

    await waitFor(() => {
      expect(screen.getByText(/NPA classification explanation/i)).toBeInTheDocument();
    });
  });

  it('10. Prevents duplicate submissions while loading', async () => {
    let resolvePromise;
    const delayedPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    const sendMock = vi.spyOn(apiService, 'sendChatMessage').mockReturnValue(delayedPromise);

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    const sendButton = screen.getByRole('button', { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: 'Duplicate click test' } });
    fireEvent.click(sendButton);

    // Attempt second submit while loading
    fireEvent.click(sendButton);

    expect(sendMock).toHaveBeenCalledTimes(1);

    resolvePromise({
      success: true,
      conversation_id: 'conv-dup',
      request_id: 'req-dup',
      message: 'Done',
      provider: 'mock',
      model: 'test',
    });
  });
});
