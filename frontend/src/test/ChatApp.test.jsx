import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from '../App';
import SchedulePreviewCard from '../components/SchedulePreviewCard';
import SchedulesDashboard from '../components/SchedulesDashboard';
import { useChatStore } from '../store/useChatStore';
import apiClient, * as apiService from '../services/api';

describe('FinTech Agent Frontend Chat Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useChatStore.getState().signOut();
    useChatStore.setState({ isAuthModalOpen: false, authError: null });
    vi.spyOn(apiService, 'checkHealth').mockResolvedValue({
      status: 'healthy',
      service: 'fintech-agent-api',
      version: '1.0.0',
    });
    vi.spyOn(apiService, 'fetchConversations').mockResolvedValue([]);
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

  it('8. Displays single non-duplicated error message when API fails', async () => {
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
      expect(screen.getAllByText(/API key for LLM provider is not configured/i)).toHaveLength(1);
    });
    expect(textarea.value).toBe('Trigger error');
  });

  it('9. Clicking a sample prompt populates and submits the question', async () => {
    vi.spyOn(apiService, 'sendChatMessage').mockResolvedValue({
      success: true,
      conversation_id: 'conv-sample',
      request_id: 'req-sample',
      message: 'Verified customers: 640, Pending: 120.',
      provider: 'mock',
      model: 'test-model',
    });

    render(<App />);
    const sampleBtn = screen.getByText(/Customer KYC Breakdown/i);
    fireEvent.click(sampleBtn);

    await waitFor(() => {
      expect(screen.getByText(/Verified customers: 640/i)).toBeInTheDocument();
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

  it('11. Keeps subtle Team T11 / INT450 branding, removes Phase 2/LLM Shell copy, and opens 12-collection schema guide', () => {
    render(<App />);
    expect(screen.queryByText(/Phase 2/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/INT450 LLM Shell/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Team T11 · INT450/i)).toBeInTheDocument();
    expect(screen.getByText(/Banking Operations Analytics/i)).toBeInTheDocument();
    expect(screen.getByText(/Read-Only · Synthetic Data/i)).toBeInTheDocument();

    const guideBtn = screen.getByRole('button', { name: /Approved Banking Schema Guide \(12 Collections\)/i });
    fireEvent.click(guideBtn);

    expect(screen.getByRole('tab', { name: 'customers' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'fraud_alerts' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'investments' })).toBeInTheDocument();
  });

  it('12. Preserves prompt and allows retrying failed query once', async () => {
    useChatStore.getState().newChat();
    const sendMock = vi
      .spyOn(apiService, 'sendChatMessage')
      .mockRejectedValueOnce({ message: 'Transient LLM timeout' })
      .mockResolvedValueOnce({
        success: true,
        conversation_id: 'conv-retry',
        request_id: 'req-retry-ok',
        message: 'Active loans across branches: 1,420.',
        provider: 'mock',
        model: 'test-model',
      });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    const sendButton = screen.getByRole('button', { name: /Send message/i });

    fireEvent.change(textarea, { target: { value: 'Count active loans' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getAllByText(/Transient LLM timeout/i)).toHaveLength(1);
    });
    expect(textarea.value).toBe('Count active loans');

    fireEvent.click(screen.getByRole('button', { name: /Retry Query/i }));

    await waitFor(() => {
      expect(screen.getByText(/Active loans across branches: 1,420\./i)).toBeInTheDocument();
    });
    expect(sendMock).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Transient LLM timeout/i)).not.toBeInTheDocument();
  });

  it('13. Shows truthful offline backend status and supports manual health retry', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'checkHealth')
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValueOnce({
        status: 'healthy',
        service: 'fintech-agent-api',
        version: '1.0.0',
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Offline')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Backend offline, retry connection/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Retry backend connection/i }));

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });
  });

  it('14. Allows cancelling an in-flight chat request and restores prompt', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'sendChatMessage').mockImplementation(
      (_msg, _convId, signal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            reject({ code: 'ERR_CANCELED', name: 'CanceledError' });
          });
        })
    );

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'Long running aggregation' } });
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }));

    expect(screen.getByText(/Consulting LLM\.\.\./i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Cancel active query/i }));

    await waitFor(() => {
      expect(screen.queryByText(/Consulting LLM\.\.\./i)).not.toBeInTheDocument();
    });
    expect(textarea.value).toBe('Long running aggregation');
  });

  it('15. SchedulePreviewCard accurately distinguishes dry-run states, renders table, and approves safely', async () => {
    useChatStore.setState({ approvedPreviews: {} });
    const approveMock = vi.spyOn(apiService, 'approveSchedule').mockResolvedValue({
      job_id: 'job-kyc-001',
      status: 'ACTIVE',
      message: 'Activated',
    });

    const { rerender } = render(
      <SchedulePreviewCard
        preview={{
          preview_id: 'prev-gated-1',
          report_name: 'Weekly KYC Breakdown',
          target_collection: 'customers',
          dry_run_status: 'EXECUTION_GATE_BLOCKED',
          dry_run_results: [],
          schedule_spec: { recurrence_expression: 'Every Monday at 9 AM' },
          next_run_times: ['2026-11-16 09:00'],
          approved_pipeline: [{ $group: { _id: '$kyc_status', count: { $sum: 1 } } }],
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
        }}
      />
    );

    expect(screen.getByText(/Live dry-run execution is currently disabled/i)).toBeInTheDocument();
    expect(screen.queryByText(/pending native MongoDB RBAC/i)).not.toBeInTheDocument();

    rerender(
      <SchedulePreviewCard
        preview={{
          preview_id: 'prev-empty-2',
          report_name: 'Empty Match Report',
          target_collection: 'customers',
          dry_run_status: 'SUCCESS_EMPTY',
          dry_run_results: [],
          schedule_spec: { recurrence_expression: 'Daily' },
          next_run_times: [],
          approved_pipeline: [],
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
        }}
      />
    );
    expect(screen.getByText(/matched 0 records/i)).toBeInTheDocument();

    rerender(
      <SchedulePreviewCard
        preview={{
          preview_id: 'prev-table-3',
          report_name: 'KYC Status Table',
          target_collection: 'customers',
          dry_run_status: 'SUCCESS_PREVIEW',
          dry_run_results: [
            { _id: 'verified', count: 640 },
            { _id: 'pending', count: 120 },
          ],
          schedule_spec: { recurrence_expression: 'Weekly' },
          next_run_times: ['2026-11-16 09:00'],
          approved_pipeline: [{ $group: { _id: '$kyc_status', count: { $sum: 1 } } }],
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
        }}
      />
    );

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('verified')).toBeInTheDocument();
    expect(screen.getByText('640')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Approve Schedule/i }));
    await waitFor(() => {
      expect(screen.getByText(/Job Activated \(job-kyc-001\)/i)).toBeInTheDocument();
    });
    expect(approveMock).toHaveBeenCalledTimes(1);
  });

  it('16. SchedulesDashboard uses accessible dialog semantics, Escape close, and in-modal cancel confirm', async () => {
    vi.spyOn(apiService, 'fetchSchedules').mockResolvedValue([
      {
        job_id: 'job-delinq-1',
        report_name: 'Loan Delinquency Report',
        target_collection: 'loans',
        status: 'ACTIVE',
        timezone: 'Asia/Kolkata',
        consecutive_failures: 0,
        schedule_spec: { recurrence_expression: 'Every Monday at 9 AM' },
        next_run_at: '2026-11-16T03:30:00Z',
        last_run_at: null,
      },
    ]);
    const cancelMock = vi.spyOn(apiService, 'cancelSchedule').mockResolvedValue({ status: 'CANCELLED' });
    const confirmSpy = vi.spyOn(window, 'confirm');
    const onClose = vi.fn();

    render(<SchedulesDashboard isOpen={true} onClose={onClose} />);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(await screen.findByText('Loan Delinquency Report')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Cancel$/i }));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Confirm Cancel/i }));
    await waitFor(() => {
      expect(cancelMock).toHaveBeenCalledWith('job-delinq-1');
    });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('17. Switching conversations aborts an in-flight request without leaking its prompt across threads', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'fetchConversations').mockResolvedValue([
      {
        conversation_id: 'conv-other',
        title: 'Branch Loan Summary',
        message_count: 2,
        created_at: '2026-11-11T10:00:00Z',
        updated_at: '2026-11-11T10:05:00Z',
      },
    ]);
    vi.spyOn(apiService, 'fetchConversation').mockResolvedValue({
      conversation_id: 'conv-other',
      title: 'Branch Loan Summary',
      created_at: '2026-11-11T10:00:00Z',
      updated_at: '2026-11-11T10:05:00Z',
      messages: [
        { role: 'user', content: 'Show branch totals' },
        { role: 'assistant', content: 'Here are the branch totals.' },
      ],
    });
    vi.spyOn(apiService, 'sendChatMessage').mockImplementation(
      (_msg, _convId, signal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            reject({ code: 'ERR_CANCELED', name: 'CanceledError' });
          });
        })
    );

    render(<App />);
    const convBtn = await screen.findByText('Branch Loan Summary');

    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'Old thread pending query' } });
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }));
    expect(screen.getByText(/Consulting LLM\.\.\./i)).toBeInTheDocument();

    fireEvent.click(convBtn);

    await waitFor(() => {
      expect(screen.getByText('Here are the branch totals.')).toBeInTheDocument();
    });
    expect(textarea.value).toBe('');
  });

  it('18. Operator sign-in modal validates user ID, requests token without hardcoded defaults, and supports sign-out', async () => {
    vi.spyOn(apiService, 'fetchConversations').mockResolvedValue([]);
    const loginMock = vi.spyOn(apiService, 'loginForToken').mockResolvedValue({
      access_token: 'signed-jwt-alice',
      token_type: 'bearer',
      user_id: 'alice',
      role: 'compliance',
      expires_in: 3600,
    });

    render(<App />);

    const signInBtn = screen.getByRole('button', { name: /Sign in operator session/i });
    fireEvent.click(signInBtn);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    const userInput = screen.getByLabelText(/^User ID/i);
    expect(userInput.value).toBe('');

    // Empty submission must show validation message and avoid API call
    fireEvent.click(screen.getByRole('button', { name: /^Sign In$/i }));
    expect(screen.getByText(/Operator User ID is required/i)).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();

    fireEvent.change(userInput, { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/^Role/i), { target: { value: 'compliance' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign In$/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('alice', 'compliance', null);
    });

    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(screen.getByText('(compliance)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Sign out operator session/i }));
    expect(screen.getByText('Not signed in')).toBeInTheDocument();
  });

  it('19. Axios request interceptor attaches Bearer token without X-User-ID spoofing', () => {
    apiService.setAuthToken('jwt-token-xyz');
    const handler = apiClient.interceptors.request.handlers[0].fulfilled;
    const config = handler({ headers: {} });
    expect(config.headers.Authorization).toBe('Bearer jwt-token-xyz');
    expect(config.headers['X-User-ID']).toBeUndefined();

    apiService.clearAuthToken();
    const anonConfig = handler({ headers: {} });
    expect(anonConfig.headers.Authorization).toBeUndefined();
  });

  it('20. Selecting a persisted conversation restores MQL pipeline and schedule preview widgets safely alongside legacy messages', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'fetchConversations').mockResolvedValue([
      {
        conversation_id: 'conv-hydrated',
        title: 'Persisted Report Thread',
        message_count: 4,
        created_at: '2026-11-11T10:00:00Z',
        updated_at: '2026-11-11T10:05:00Z',
      },
    ]);
    vi.spyOn(apiService, 'fetchConversation').mockResolvedValue({
      conversation_id: 'conv-hydrated',
      title: 'Persisted Report Thread',
      created_at: '2026-11-11T10:00:00Z',
      updated_at: '2026-11-11T10:05:00Z',
      messages: [
        { role: 'user', content: 'Count open accounts' },
        {
          role: 'assistant',
          content: 'Account query validated.',
          pipeline_spec: [{ $match: { status: 'OPEN' } }],
          selected_collection: 'accounts',
          validation_status: 'passed',
          query_explanation: 'Filters active open accounts.',
        },
        { role: 'user', content: 'Schedule weekly KYC status' },
        {
          role: 'assistant',
          content: 'Weekly KYC schedule preview ready.',
          schedule_preview: {
            preview_id: 'prev-restored-1',
            owner_id: 'alice',
            report_name: 'Restored KYC Weekly',
            target_collection: 'customers',
            schedule_spec: { recurrence_expression: 'Every Monday at 9 AM' },
            next_run_times: ['2026-11-16 09:00'],
            approved_pipeline: [{ $group: { _id: '$kyc_status', count: { $sum: 1 } } }],
            expires_at: new Date(Date.now() + 3600_000).toISOString(),
          },
        },
      ],
    });

    render(<App />);
    fireEvent.click(await screen.findByText('Persisted Report Thread'));

    expect(await screen.findByText('Account query validated.')).toBeInTheDocument();
    expect(screen.getByText('MQL: passed')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Inspect Validated MQL Pipeline/i }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Restored KYC Weekly')).toBeInTheDocument();
  });

  it('21. SchedulePreviewCard detects owner mismatch cleanly and SchedulesDashboard offers Sign In on 401', async () => {
    useChatStore.setState({ authUser: { user_id: 'alice', role: 'analyst' }, isLoading: false });
    const sendSpy = vi.spyOn(useChatStore.getState(), 'sendMessage').mockResolvedValue(undefined);

    render(
      <SchedulePreviewCard
        preview={{
          preview_id: 'prev-mismatch-1',
          owner_id: 'default_user',
          report_name: 'Mismatch Test Report',
          natural_language_query: 'Generate weekly report every Monday',
          target_collection: 'loans',
          schedule_spec: { recurrence_expression: 'Weekly' },
          next_run_times: ['2026-11-16 09:00'],
          approved_pipeline: [{ $limit: 5 }],
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
        }}
      />
    );

    expect(screen.getAllByText(/default_user/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Preview owner is/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approve Schedule/i })).toBeDisabled();

    const regenBtn = screen.getByRole('button', { name: /Regenerate as alice/i });
    fireEvent.click(regenBtn);
    expect(sendSpy).toHaveBeenCalledWith('Generate weekly report every Monday');
    sendSpy.mockRestore();

    useChatStore.setState({ authUser: null });
    vi.spyOn(apiService, 'fetchSchedules').mockRejectedValue({
      status: 401,
      error_code: 'AUTH_REQUIRED',
      message: 'Missing authentication credentials.',
    });

    render(<SchedulesDashboard isOpen={true} onClose={vi.fn()} />);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Missing authentication credentials/i)).toBeInTheDocument();
    const modalSignInBtn = within(dialog).getByRole('button', { name: /^Sign In$/i });
    fireEvent.click(modalSignInBtn);
    expect(useChatStore.getState().isAuthModalOpen).toBe(true);
  });

  it('22. Aligns frontend timeout above 30s backend deadline and classifies timeout, HTTP 504/503, and network errors distinctly', async () => {
    expect(apiService.API_TIMEOUT_MS).toBe(40000);
    expect(apiClient.defaults.timeout).toBe(40000);

    // 1. Axios client-side timeout (ECONNABORTED, no response) -> CLIENT_TIMEOUT, NOT NETWORK_ERROR
    vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
      code: 'ECONNABORTED',
      message: 'timeout of 40000ms exceeded',
    });
    await expect(apiService.sendChatMessage('Test timeout', 'conv-t1')).rejects.toMatchObject({
      error_code: 'CLIENT_TIMEOUT',
      error_category: 'client_timeout',
    });

    // 2. Backend HTTP 504 Provider Timeout -> PROVIDER_TIMEOUT
    vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
      response: {
        status: 504,
        data: {
          detail: {
            success: false,
            error_code: 'PROVIDER_TIMEOUT',
            message: 'Call to gemini timed out after 7.0 seconds.',
            request_id: 'req-p504',
          },
        },
      },
    });
    await expect(apiService.sendChatMessage('Test 504', 'conv-t1')).rejects.toMatchObject({
      status: 504,
      error_code: 'PROVIDER_TIMEOUT',
      error_category: 'provider_timeout',
      request_id: 'req-p504',
    });

    // 3. True offline network failure -> NETWORK_ERROR
    vi.spyOn(apiClient, 'post').mockRejectedValueOnce({
      message: 'Network Error',
    });
    await expect(apiService.sendChatMessage('Test offline', 'conv-t1')).rejects.toMatchObject({
      error_code: 'NETWORK_ERROR',
      error_category: 'network_error',
    });
  });

  it('23. Renders distinct error classification badge in UI and preserves prompt without duplicate messages', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'sendChatMessage').mockRejectedValueOnce({
      status: 504,
      error_code: 'PROVIDER_TIMEOUT',
      error_category: 'provider_timeout',
      message: 'Call to gemini timed out within bounded budget.',
      request_id: 'req-ui-timeout',
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'Show transactions from the last 30 days.' } });
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }));

    expect(await screen.findByText('Provider Timeout')).toBeInTheDocument();
    expect(screen.getByText('PROVIDER_TIMEOUT')).toBeInTheDocument();
    const promptMatches = screen.getAllByText('Show transactions from the last 30 days.');
    expect(promptMatches.filter((el) => el.tagName !== 'TEXTAREA')).toHaveLength(1);
    expect(textarea.value).toBe('Show transactions from the last 30 days.');
  });

  it('24. Replaces internal Phase 6 labels with Read-only query execution in normal customer-facing results', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'sendChatMessage').mockResolvedValueOnce({
      success: true,
      conversation_id: 'conv-phase-test',
      request_id: 'req-phase-test',
      message: '✅ **Query Executed Successfully** (Phase 6)\n\n**Target Collection:** `accounts`\n**Execution Metrics:** 1500 records returned in 4 ms.\n**Explanation:** Counts all documents in the accounts collection.',
      provider: 'groq',
      model: 'openai/gpt-oss-120b',
      pipeline_spec: [{ $count: 'total_accounts' }],
      selected_collection: 'accounts',
      validation_status: 'passed',
      trace: [
        { node: 'input_guardrail', status: 'allowed' },
        { node: 'request_intent_router', status: 'QUERY_ONLY' },
        { node: 'query_executor', status: 'SUCCESS' },
      ],
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'How many total accounts are there?' } });
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }));

    await waitFor(() => {
      expect(screen.getByText(/Database query executed successfully/i)).toBeInTheDocument();
      expect(screen.getByText(/Read-only query execution/i)).toBeInTheDocument();
      expect(screen.queryByText(/Query Executed Successfully \(Phase 6\)/i)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Read-only query execution/i)).toBeInTheDocument();
    expect(screen.queryByText(/Query Executed Successfully \(Phase 6\)/i)).not.toBeInTheDocument();
  });

  it('25. Developer Diagnostics drawer reveals internal Phase numbers and LangGraph node names', async () => {
    useChatStore.getState().newChat();
    vi.spyOn(apiService, 'sendChatMessage').mockResolvedValueOnce({
      success: true,
      conversation_id: 'conv-diag-test',
      request_id: 'req-diag-test',
      message: '✅ **Query Executed Successfully** (Phase 6)\n\n**Target Collection:** `accounts`\n**Execution Metrics:** 1500 records.',
      provider: 'groq',
      model: 'openai/gpt-oss-120b',
      pipeline_spec: [{ $count: 'total_accounts' }],
      selected_collection: 'accounts',
      validation_status: 'passed',
      trace: [
        { node: 'input_guardrail', status: 'allowed' },
        { node: 'request_intent_router', status: 'QUERY_ONLY' },
        { node: 'query_executor', status: 'SUCCESS' },
      ],
    });

    render(<App />);
    const textarea = screen.getByPlaceholderText(/Ask a banking question/i);
    fireEvent.change(textarea, { target: { value: 'How many accounts?' } });
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }));

    const diagBtn = await screen.findByRole('button', { name: /Developer Diagnostics/i });
    fireEvent.click(diagBtn);

    // Diagnostics drawer exposes internal Phase 6 and LangGraph node details
    expect(await screen.findByText(/Developer Diagnostics & Audit Trace/i)).toBeInTheDocument();
    expect(screen.getByText(/Phase 6 — Read-Only Database Execution/i)).toBeInTheDocument();
    expect(screen.getByText(/query_executor \(Node 6\)/i)).toBeInTheDocument();
    expect(screen.getByText(/6\. query_executor \(Phase 6\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Monitor: Terminal 2 event stream/i)).toBeInTheDocument();
  });
});
