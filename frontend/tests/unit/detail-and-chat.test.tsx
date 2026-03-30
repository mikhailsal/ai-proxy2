import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiContext } from '../../src/hooks/useApi';
import { JsonViewer } from '../../src/components/JsonViewer/JsonViewer';
import { RequestDetail } from '../../src/components/RequestDetail/RequestDetail';
import { ChatView } from '../../src/components/ChatView/ChatView';
import type { ConversationMessage, RequestDetail as RequestDetailType, RequestSummary } from '../../src/types';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('JsonViewer', () => {
  it('renders primitive JSON values', () => {
    render(
      <div>
        <JsonViewer data={null} />
        <JsonViewer data={true} />
        <JsonViewer data={7} />
        <JsonViewer data="text" />
      </div>,
    );

    expect(screen.getByText('null')).toBeInTheDocument();
    expect(screen.getByText('true')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('"text"')).toBeInTheDocument();
  });

  it('toggles collapsed object and array nodes', async () => {
    render(
      <div>
        <JsonViewer data={{ alpha: { beta: 1 } }} depth={3} />
        <JsonViewer data={[1, { nested: true }]} depth={3} />
      </div>,
    );

    const buttons = screen.getAllByRole('button');
    expect(screen.getByText('{ 1 keys }')).toBeInTheDocument();
    expect(screen.getByText('[ 2 items ]')).toBeInTheDocument();

    await userEvent.click(buttons[0]);
    await userEvent.click(buttons[1]);
    await userEvent.click(screen.getAllByTitle('expand')[1]);

    expect(screen.getByText('"alpha"')).toBeInTheDocument();
    expect(screen.getByText('"nested"')).toBeInTheDocument();
  });

  it('collapses configured paths by default', async () => {
    render(<JsonViewer data={{ history: { expanded: [{ role: 'user', content: 'hello' }] } }} collapsedPaths={['history.expanded']} />);

    expect(screen.getByText('[ 1 items ]')).toBeInTheDocument();
    await userEvent.click(screen.getByTitle('expand'));
    expect(screen.getByText('{ 2 keys }')).toBeInTheDocument();
  });
});

describe('RequestDetail', () => {
  it('renders detail data, toggles sections, exports, and closes', async () => {
    const onClose = vi.fn();
    const downloadExport = vi.fn().mockResolvedValue(undefined);
    const api = {
      downloadExport,
      getRequest: vi.fn().mockResolvedValue(makeRequestDetail()),
    };

    renderWithApi(
      <RequestDetail onClose={onClose} requestId="req-1" requestSummary={makeRequestSummary({ response_status_code: 201 })} />,
      api,
    );

    expect(screen.getByText('Loading detail…')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());
    expect(screen.getByText('Cache:')).toBeInTheDocument();
    expect(screen.getByText('$0.123456')).toBeInTheDocument();
    expect(screen.getByText('backend error')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'JSON' }));
    await userEvent.click(screen.getByRole('button', { name: /Request Headers/ }));
    await userEvent.click(screen.getByRole('button', { name: /Stream Chunks/ }));
    await userEvent.click(screen.getByRole('button', { name: '✕' }));

    expect(downloadExport).toHaveBeenCalledWith('req-1', 'json');
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByText('"authorization"')).toBeInTheDocument();
    expect(screen.getByText('"delta"')).toBeInTheDocument();
  });

  it('shows query and export errors while keeping summary metadata', async () => {
    const api = {
      downloadExport: vi.fn().mockRejectedValue(new Error('export failed')),
      getRequest: vi.fn().mockRejectedValue(new Error('detail failed')),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-2" requestSummary={makeRequestSummary({ response_status_code: 500 })} />,
      api,
    );

    await userEvent.click(screen.getByRole('button', { name: 'MD' }));

    await waitFor(() => expect(screen.getByText('detail failed')).toBeInTheDocument());
    expect(screen.getByText('export failed')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
  });
});

describe('ChatView', () => {
  it('loads conversations, changes grouping, and selects a conversation', async () => {
    const onGroupByChange = vi.fn();
    const onSelectGroup = vi.fn();
    const api = {
      getConversationMessages: vi.fn(),
      getRequest: vi.fn(),
      getConversations: vi.fn().mockResolvedValue({ items: [
        { group_key: 'team-a', group_label: 'team-a', message_count: 2, request_count: 1, models_used: ['gpt-4o-mini'] },
      ] }),
    };

    renderWithApi(
      <ChatView groupBy="client" onGroupByChange={onGroupByChange} onSelectGroup={onSelectGroup} selectedGroup={null} />,
      api,
    );

    expect(screen.getByText('Select a conversation to view messages.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('team-a')).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByRole('combobox'), 'system_prompt_first_user');
    await userEvent.click(screen.getByText('team-a'));

    expect(onGroupByChange).toHaveBeenCalledWith('system_prompt_first_user');
    expect(onSelectGroup).toHaveBeenCalledWith('team-a');
  });

  it('renders merged timeline messages newest first, lazy raw requests, and empty states', async () => {
    const api = {
      getConversationMessages: vi.fn().mockResolvedValue({ items: makeConversationMessages() }),
      getConversations: vi.fn().mockResolvedValue({ items: [] }),
      getRequest: vi.fn().mockResolvedValue(makeRequestDetail()),
    };

    const initialRender = renderWithApi(
      <ChatView groupBy="system_prompt" onGroupByChange={vi.fn()} onSelectGroup={vi.fn()} selectedGroup="alpha" />,
      api,
    );

    await waitFor(() => expect(screen.getByText('No conversations found.')).toBeInTheDocument());
    expect(screen.getByText('reply')).toBeInTheDocument();
    expect(screen.getByText('hello')).toBeInTheDocument();
    expect(screen.getByText('system prompt')).toBeInTheDocument();
    expect(screen.getByText('Assistant tool calls')).toBeInTheDocument();
    expect(screen.getByText('lookup_weather')).toBeInTheDocument();
    expect(screen.getByText('"city"')).toBeInTheDocument();
    expect(screen.getAllByText('sent 2x')).toHaveLength(3);
    expect(
      screen.getByText('reply').compareDocumentPosition(screen.getByText('hello')) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    await userEvent.click(screen.getAllByRole('button', { name: 'Show raw request' })[0]);
    await waitFor(() => expect(api.getRequest).toHaveBeenCalledWith('req-1'));
    expect(screen.getByText('Request body')).toBeInTheDocument();
    expect(screen.getByText('Response body')).toBeInTheDocument();
    expect(screen.getByText('"tools"')).toBeInTheDocument();
    expect(screen.getByText('"messages"')).toBeInTheDocument();
    expect(screen.getByText('"choices"')).toBeInTheDocument();
    expect(screen.queryByText('"__collapsed_previous_messages__"')).not.toBeInTheDocument();

    api.getConversationMessages.mockResolvedValueOnce({ items: [] });
    initialRender.unmount();
    renderWithApi(
      <ChatView groupBy="system_prompt" onGroupByChange={vi.fn()} onSelectGroup={vi.fn()} selectedGroup="beta" />,
      api,
    );

    await waitFor(() => expect(screen.getByText('No messages in this conversation.')).toBeInTheDocument());
  });
});

function renderWithApi(ui: React.ReactElement, api: Record<string, unknown>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiContext.Provider value={api as never}>{ui}</ApiContext.Provider>
    </QueryClientProvider>,
  );
}

function makeRequestSummary(overrides: Partial<RequestSummary>): RequestSummary {
  return {
    id: overrides.id ?? 'req-1',
    timestamp: overrides.timestamp ?? '2024-01-01T00:00:00Z',
    client_ip: null,
    client_api_key_hash: null,
    method: 'POST',
    path: '/v1/chat/completions',
    model_requested: overrides.model_requested ?? 'gpt-4o-mini',
    model_resolved: overrides.model_resolved ?? 'gpt-4o-mini',
    response_status_code: overrides.response_status_code ?? 200,
    latency_ms: overrides.latency_ms ?? 42,
    input_tokens: 1,
    output_tokens: 2,
    total_tokens: 3,
    cost: overrides.cost ?? 0.123456,
    cache_status: overrides.cache_status ?? 'hit',
    error_message: overrides.error_message ?? null,
  };
}

function makeRequestDetail(): RequestDetailType {
  return {
    ...makeRequestSummary({ error_message: 'backend error' }),
    request_headers: { authorization: 'Bearer redacted' },
    request_body: {
      tools: [{ type: 'function', function: { name: 'lookup_weather' } }],
      messages: [
        { role: 'system', content: 'system prompt' },
        { role: 'user', content: 'hello' },
      ],
    },
    response_headers: { 'content-type': 'application/json' },
    response_body: { choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: 'reply' } }] },
    stream_chunks: [{ delta: 'hi' }],
    reasoning_tokens: null,
    metadata: null,
  };
}

function makeConversationMessages(): ConversationMessage[] {
  return [
    {
      id: 'msg-3',
      origin: 'response',
      role: 'assistant',
      content: 'reply',
      raw_message: { role: 'assistant', content: 'reply' },
      tool_names: [],
      meta_tags: {},
      source_request_id: 'req-1',
      source_request_timestamp: '2024-01-01T00:00:00Z',
      source_message_index: 2,
      last_seen_at: '2024-01-01T00:00:00Z',
      repeat_count: 1,
      model: 'gpt-4o-mini',
      latency_ms: 42,
      total_tokens: 3,
    },
    {
      id: 'msg-2b',
      origin: 'response',
      role: 'assistant',
      content: 'Tool call: lookup_weather',
      raw_message: {
        role: 'assistant',
        content: '',
        tool_calls: [
          {
            id: 'call_weather_1',
            type: 'function',
            function: { name: 'lookup_weather', arguments: '{"city":"Berlin"}' },
          },
        ],
      },
      tool_names: ['lookup_weather'],
      meta_tags: {},
      source_request_id: 'req-1',
      source_request_timestamp: '2024-01-01T00:00:00Z',
      source_message_index: 2,
      last_seen_at: '2024-01-02T00:00:00Z',
      repeat_count: 2,
      model: 'gpt-4o-mini',
      latency_ms: 42,
      total_tokens: 3,
    },
    {
      id: 'msg-2',
      origin: 'request',
      role: 'user',
      content: 'hello',
      raw_message: { role: 'user', content: 'hello' },
      tool_names: [],
      meta_tags: {},
      source_request_id: 'req-1',
      source_request_timestamp: '2024-01-01T00:00:00Z',
      source_message_index: 1,
      last_seen_at: '2024-01-02T00:00:00Z',
      repeat_count: 2,
      model: 'gpt-4o-mini',
      latency_ms: 42,
      total_tokens: 3,
    },
    {
      id: 'msg-1',
      origin: 'request',
      role: 'system',
      content: 'system prompt',
      raw_message: { role: 'system', content: 'system prompt' },
      tool_names: [],
      meta_tags: { name: 'system' },
      source_request_id: 'req-1',
      source_request_timestamp: '2024-01-01T00:00:00Z',
      source_message_index: 0,
      last_seen_at: '2024-01-02T00:00:00Z',
      repeat_count: 2,
      model: 'gpt-4o-mini',
      latency_ms: 42,
      total_tokens: 3,
    },
  ];
}