import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiContext } from '../../src/hooks/useApi';
import { JsonViewer } from '../../src/components/JsonViewer/JsonViewer';
import { DiffJsonViewer } from '../../src/components/JsonViewer/DiffJsonViewer';
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

describe('DiffJsonViewer', () => {
  it('highlights added, removed, and changed values', () => {
    render(
      <pre>
        <DiffJsonViewer
          left={{ model: 'gpt-4o', temperature: 0.7 }}
          right={{ model: 'openai/gpt-4o', stream: true }}
        />
      </pre>,
    );

    expect(screen.getByText('"gpt-4o"')).toBeInTheDocument();
    expect(screen.getByText('"openai/gpt-4o"')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });

  it('renders identical data without diff markers', () => {
    render(
      <pre>
        <DiffJsonViewer left={{ key: 'same' }} right={{ key: 'same' }} />
      </pre>,
    );

    expect(screen.getByText('"same"')).toBeInTheDocument();
    expect(screen.queryByText('→')).not.toBeInTheDocument();
  });

  it('auto-expands nested diffs that contain changes', async () => {
    render(
      <pre>
        <DiffJsonViewer
          left={{ nested: { a: 1 } }}
          right={{ nested: { a: 2 } }}
          depth={3}
        />
      </pre>,
    );

    expect(screen.getByText('"nested"')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();

    await userEvent.click(screen.getAllByTitle('collapse')[0]);
    expect(screen.getByText('(changed)')).toBeInTheDocument();
  });

  it('diffs arrays with added and removed elements', async () => {
    render(
      <pre>
        <DiffJsonViewer left={[1, 2, 3]} right={[1, 4]} />
      </pre>,
    );

    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });

  it('handles null transitions, type changes, and empty containers', () => {
    const { unmount } = render(<pre><DiffJsonViewer left={null} right={{ key: 'val' }} /></pre>);
    expect(screen.getByText('"key"')).toBeInTheDocument();
    unmount();

    const { unmount: u2 } = render(<pre><DiffJsonViewer left="text" right={42} /></pre>);
    expect(screen.getByText('→')).toBeInTheDocument();
    u2();

    render(<pre><DiffJsonViewer left={{}} right={{}} /></pre>);
    expect(screen.getByText('{}')).toBeInTheDocument();
  });

  it('renders nested PlainValue structures and toggles collapsible nodes', async () => {
    const { container, unmount } = render(
      <pre><DiffJsonViewer left={null} right={{ items: [{ name: 'a' }], meta: { deep: true } }} /></pre>,
    );
    expect(screen.getByText('"items"')).toBeInTheDocument();
    expect(screen.getByText('"meta"')).toBeInTheDocument();
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(0);
    await userEvent.click(buttons[0]);
    unmount();
  });

  it('handles arrays of different lengths with nested objects', () => {
    render(
      <pre>
        <DiffJsonViewer
          left={[{ role: 'user' }]}
          right={[{ role: 'user' }, { role: 'assistant' }]}
        />
      </pre>,
    );
    expect(screen.getAllByText('"role"').length).toBeGreaterThanOrEqual(2);
  });

  it('auto-expands arrays with changes and shows change indicator when collapsed', async () => {
    render(
      <pre>
        <DiffJsonViewer left={[1, 2]} right={[3, 4]} depth={3} />
      </pre>,
    );
    expect(screen.getAllByText('→').length).toBeGreaterThanOrEqual(1);

    await userEvent.click(screen.getAllByTitle('collapse')[0]);
    expect(screen.getByText('(changed)')).toBeInTheDocument();
  });

  it('renders empty arrays in diff', () => {
    render(
      <pre>
        <DiffJsonViewer left={[]} right={[]} />
      </pre>,
    );
    expect(screen.getByText('[]')).toBeInTheDocument();
  });

  it('renders removed top-level value', () => {
    render(
      <pre>
        <DiffJsonViewer left={{ removed: true }} right={null} />
      </pre>,
    );
    expect(screen.getByText('"removed"')).toBeInTheDocument();
  });

  it('renders boolean and number primitives in PlainValue', () => {
    render(
      <pre>
        <DiffJsonViewer left={null} right={{ flag: true, count: 42, label: null }} />
      </pre>,
    );
    expect(screen.getByText('true')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });
});

describe('RequestDetail', () => {
  it('renders detail data, toggles sections, exports, and closes', { timeout: 15000 }, async () => {
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

  it('shows diff view when client_request_body differs from request_body', async () => {
    const detail = makeRequestDetail({
      client_request_body: {
        model: 'gpt-4o',
        messages: [
          { role: 'system', content: 'system prompt' },
          { role: 'user', content: 'hello' },
        ],
      },
      request_body: {
        model: 'openai/gpt-4o',
        messages: [
          { role: 'system', content: 'system prompt' },
          { role: 'user', content: 'hello' },
        ],
      },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-diff" requestSummary={makeRequestSummary({})} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('Request Body (Client → Provider)')).toBeInTheDocument());
    expect(screen.getByText('→')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Plain' }));
    expect(screen.queryByText('→')).not.toBeInTheDocument();
  });

  it('shows header diff view when headers differ between client and provider', async () => {
    const detail = makeRequestDetail({
      client_request_headers: { authorization: 'Bearer sk-***', 'content-type': 'application/json' },
      request_headers: { authorization: 'Bearer sk-***', 'content-type': 'application/json', 'x-custom-header': 'added-by-proxy' },
      response_headers: { 'content-type': 'application/json', 'x-ratelimit-remaining': '99', 'transfer-encoding': 'chunked' },
      client_response_headers: { 'content-type': 'application/json', 'x-ratelimit-remaining': '99' },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-hdiff" requestSummary={makeRequestSummary({})} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('Request Headers (Client → Provider)')).toBeInTheDocument());
    expect(screen.getByText('Response Headers (Provider → Client)')).toBeInTheDocument();
  });

  it('shows response headers as plain section when no diff exists', async () => {
    const detail = makeRequestDetail({
      response_headers: { 'content-type': 'application/json' },
      client_response_headers: { 'content-type': 'application/json' },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-rh" requestSummary={makeRequestSummary({})} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('Response Headers')).toBeInTheDocument());
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

  it('shows estimated token counts and cached badge when applicable', async () => {
    const withCache = makeRequestDetail({
      cached_input_tokens: 45, input_tokens: 50, model_requested: 'openai/gpt-4o',
      request_body: {
        tools: [{ type: 'function', function: { name: 'lookup_weather', parameters: { type: 'object', properties: { city: { type: 'string' } } } } }],
        messages: [{ role: 'system', content: 'A long system prompt for cache' }, { role: 'user', content: 'hello' }],
      },
    });
    const api = { downloadExport: vi.fn().mockResolvedValue(undefined), getRequest: vi.fn().mockResolvedValue(withCache) };
    const { unmount } = renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-cache" requestSummary={makeRequestSummary({ cached_input_tokens: 45, input_tokens: 50 })} />, api,
    );
    await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());
    expect(screen.getByText('Cached:')).toBeInTheDocument();
    expect(screen.getByText('45/50 (90%)')).toBeInTheDocument();
    expect(screen.getAllByText(/~\d+ tokens/).length).toBeGreaterThanOrEqual(2);
    unmount();

    const noCache = makeRequestDetail({ cached_input_tokens: null, input_tokens: 50 });
    const api2 = { downloadExport: vi.fn().mockResolvedValue(undefined), getRequest: vi.fn().mockResolvedValue(noCache) };
    renderWithApi(<RequestDetail onClose={vi.fn()} requestId="req-nc" requestSummary={makeRequestSummary({})} />, api2);
    await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());
    expect(screen.queryByText('Cached:')).not.toBeInTheDocument();
    expect(screen.getAllByText(/~\d+ tokens/).length).toBeGreaterThanOrEqual(2);
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
      <ChatView groupBy="system_prompt_first_user_first_assistant" onGroupByChange={onGroupByChange} onSelectGroup={onSelectGroup} selectedGroup={null} />,
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
      <ChatView groupBy="system_prompt_first_user_first_assistant" onGroupByChange={vi.fn()} onSelectGroup={vi.fn()} selectedGroup="alpha" />,
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
      screen.getByText('system prompt').compareDocumentPosition(screen.getByText('hello')) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    await userEvent.click(screen.getAllByRole('button', { name: 'Show raw request' })[0]);
    await waitFor(() => expect(api.getRequest).toHaveBeenCalledWith('req-1'));
    expect(screen.getByText('Request Body')).toBeInTheDocument();
    expect(screen.getByText('Response Body')).toBeInTheDocument();
    expect(screen.getByText('"tools"')).toBeInTheDocument();
    expect(screen.getByText('"messages"')).toBeInTheDocument();
    expect(screen.getByText('"choices"')).toBeInTheDocument();

    api.getConversationMessages.mockResolvedValueOnce({ items: [] });
    initialRender.unmount();
    renderWithApi(
      <ChatView groupBy="system_prompt_first_user_first_assistant" onGroupByChange={vi.fn()} onSelectGroup={vi.fn()} selectedGroup="beta" />,
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
    cached_input_tokens: null,
    cost: overrides.cost ?? 0.123456,
    cache_status: overrides.cache_status ?? 'hit',
    error_message: overrides.error_message ?? null,
    last_user_message: null,
    assistant_response: null,
  };
}

function makeRequestDetail(overrides?: Partial<RequestDetailType>): RequestDetailType {
  return {
    ...makeRequestSummary({ error_message: 'backend error' }),
    request_headers: { authorization: 'Bearer redacted' },
    client_request_headers: null,
    request_body: {
      tools: [{ type: 'function', function: { name: 'lookup_weather' } }],
      messages: [
        { role: 'system', content: 'system prompt' },
        { role: 'user', content: 'hello' },
      ],
    },
    client_request_body: null,
    response_headers: { 'content-type': 'application/json' },
    client_response_headers: null,
    response_body: { choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: 'reply' } }] },
    client_response_body: null,
    stream_chunks: [{ delta: 'hi' }],
    reasoning_tokens: null,
    metadata: null,
    ...overrides,
  };
}

function msg(overrides: Partial<ConversationMessage> & { id: string; role: string; content: string }): ConversationMessage {
  return {
    node_id: overrides.id,
    parent: null,
    children: [],
    origin: 'request', raw_message: { role: overrides.role, content: overrides.content },
    tool_names: [], meta_tags: {}, source_request_id: 'req-1',
    source_request_timestamp: '2024-01-01T00:00:00Z', source_message_index: 0,
    last_seen_at: '2024-01-02T00:00:00Z', repeat_count: 2,
    model: 'gpt-4o-mini', latency_ms: 42, total_tokens: 3, ...overrides,
  };
}

function makeConversationMessages(): ConversationMessage[] {
  return [
    msg({ id: 'msg-1', node_id: 'n1', parent: null, children: ['n2'], role: 'system', content: 'system prompt', meta_tags: { name: 'system' } }),
    msg({ id: 'msg-2', node_id: 'n2', parent: 'n1', children: ['n2b', 'n3'], role: 'user', content: 'hello', source_message_index: 1 }),
    msg({ id: 'msg-2b', node_id: 'n2b', parent: 'n2', children: [], origin: 'response', role: 'assistant', content: 'Tool call: lookup_weather',
      raw_message: { role: 'assistant', content: '', tool_calls: [
        { id: 'call_weather_1', type: 'function', function: { name: 'lookup_weather', arguments: '{"city":"Berlin"}' } },
      ] }, tool_names: ['lookup_weather'], source_message_index: 2 }),
    msg({ id: 'msg-3', node_id: 'n3', parent: 'n2', children: [], origin: 'response', role: 'assistant', content: 'reply',
      last_seen_at: '2024-01-01T00:00:00Z', repeat_count: 1, source_message_index: 2 }),
  ];
}