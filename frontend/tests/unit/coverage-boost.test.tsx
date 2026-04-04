import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { formatAssistantCell } from '../../src/components/RequestBrowser/RequestBrowserList';
import type { RequestSummary, ConversationMessage, RequestDetail as RequestDetailType } from '../../src/types';

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn(),
}));

const useVirtualizerMock = vi.mocked(useVirtualizer);

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  vi.doUnmock('../../src/app/RequestsWorkspace');
  vi.doUnmock('../../src/app/ChatWorkspace');
  vi.doUnmock('../../src/components/RequestBrowser/RequestBrowser');
  vi.doUnmock('../../src/components/RequestDetail/RequestDetail');
  vi.doUnmock('../../src/components/ChatView/ChatView');
  vi.doUnmock('../../src/components/common/StatsBar');
  vi.doUnmock('../../src/app/useNavigationState');
  document.body.innerHTML = '';
});

function makeRequestSummary(overrides: Partial<RequestSummary> = {}): RequestSummary {
  return {
    id: overrides.id ?? 'req-1',
    timestamp: overrides.timestamp ?? '2024-01-01T00:00:00Z',
    client_ip: null,
    client_api_key_hash: null,
    method: 'POST',
    path: '/v1/chat/completions',
    model_requested: overrides.model_requested ?? 'gpt-4o-mini',
    model_resolved: overrides.model_resolved === undefined ? 'gpt-4o-mini' : overrides.model_resolved,
    response_status_code: overrides.response_status_code ?? 200,
    latency_ms: 'latency_ms' in overrides ? overrides.latency_ms! : 42,
    input_tokens: 'input_tokens' in overrides ? overrides.input_tokens! : 1,
    output_tokens: 'output_tokens' in overrides ? overrides.output_tokens! : 2,
    total_tokens: overrides.total_tokens ?? 3,
    cached_input_tokens: null,
    cost: 'cost' in overrides ? overrides.cost! : null,
    cache_status: null,
    error_message: null,
    last_user_message: null,
    assistant_response: null,
  };
}

describe('RequestBrowserList with cost and status code branches', () => {
  it('renders rows with non-zero cost and various status codes', async () => {
    const { RequestBrowserList } = await import('../../src/components/RequestBrowser/RequestBrowserList');
    const onSelect = vi.fn();
    useVirtualizerMock.mockReturnValue({
      getTotalSize: () => 176,
      getVirtualItems: () => [
        { index: 0, size: 44, start: 0 },
        { index: 1, size: 44, start: 44 },
        { index: 2, size: 44, start: 88 },
        { index: 3, size: 44, start: 132 },
      ],
    } as never);

    render(
      <RequestBrowserList
        fetchNextPage={vi.fn().mockResolvedValue(undefined)}
        hasNextPage={false}
        isFetchingNextPage={false}
        isLoading={false}
        items={[
          makeRequestSummary({ id: 'a', cost: 0.0012, response_status_code: 200 }),
          makeRequestSummary({ id: 'b', cost: 1.2345, response_status_code: 301 }),
          makeRequestSummary({ id: 'c', cost: -0.0001, response_status_code: 403 }),
          makeRequestSummary({ id: 'd', cost: null, response_status_code: null as never }),
        ]}
        onSelect={onSelect}
        searchQuery=""
      />,
    );

    expect(screen.getByText('301')).toBeInTheDocument();
    expect(screen.getByText('403')).toBeInTheDocument();
  });
});

describe('formatAssistantCell — unclosed quote and edge cases', () => {
  it('handles unclosed single quote in tool arguments', () => {
    const result = formatAssistantCell("fn(x='unclosed)", 2000);
    expect(result).toContain('fn(');
    expect(result).toContain('x=');
  });

  it('handles double-quoted values', () => {
    const result = formatAssistantCell('fn(x="hello")', 2000);
    expect(result).toContain('fn(');
    expect(result).toContain('x=');
    expect(result).toContain('"hello"');
  });

  it('handles unclosed double quote in tool arguments', () => {
    const result = formatAssistantCell('fn(x="unclosed)', 2000);
    expect(result).toContain('fn(');
    expect(result).toContain('x=');
  });

  it('handles escaped quotes in tool arguments', () => {
    const result = formatAssistantCell("fn(x='it\\'s ok')", 2000);
    expect(result).toContain('fn(');
    expect(result).toContain('x=');
  });

  it('handles bracket and brace values', () => {
    const result = formatAssistantCell('fn(a=[1,2,3], b={x:1})', 2000);
    expect(result).toContain('fn(');
    expect(result).toContain('a=');
    expect(result).toContain('b=');
  });

  it('handles empty budget gracefully', () => {
    const result = formatAssistantCell("fn(x='very long value')", 1);
    expect(result).toContain('fn');
  });
});

describe('ChatWorkspace callback coverage', () => {
  it('executes onGroupByChange and onSelectGroup callbacks with actual state updates', async () => {
    const capturedUpdaters: Array<(state: Record<string, unknown>) => Record<string, unknown>> = [];
    const updateNavigation = vi.fn((updater) => {
      if (typeof updater === 'function') {
        capturedUpdaters.push(updater);
      }
    });

    vi.doMock('../../src/components/ChatView/ChatView', () => ({
      ChatView: ({ onGroupByChange, onSelectGroup }: {
        onGroupByChange: (value: string) => void;
        onSelectGroup: (value: string) => void;
      }) => (
        <>
          <button onClick={() => onGroupByChange('model')}>change group</button>
          <button onClick={() => onSelectGroup('group-key')}>select group</button>
        </>
      ),
    }));

    const { ChatWorkspace } = await import('../../src/app/ChatWorkspace');

    const navigation = {
      activeTab: 'chat',
      chatGroupBy: 'system_prompt_first_user_first_assistant',
      selectedChatGroup: null,
      requestId: null,
      requestModelFilter: '',
      requestSearch: '',
    } as never;

    render(<ChatWorkspace navigation={navigation} updateNavigation={updateNavigation} />);

    await userEvent.click(screen.getByRole('button', { name: 'change group' }));
    await userEvent.click(screen.getByRole('button', { name: 'select group' }));

    expect(updateNavigation).toHaveBeenCalledTimes(2);

    const groupByResult = capturedUpdaters[0]({
      activeTab: 'chat', chatGroupBy: 'system_prompt_first_user_first_assistant', selectedChatGroup: 'old',
    });
    expect(groupByResult.chatGroupBy).toBe('model');
    expect(groupByResult.selectedChatGroup).toBeNull();

    const selectResult = capturedUpdaters[1]({
      activeTab: 'chat', chatGroupBy: 'system_prompt_first_user_first_assistant', selectedChatGroup: null,
    });
    expect(selectResult.selectedChatGroup).toBe('group-key');
  });
});

describe('RequestsWorkspace divider drag coverage', () => {
  it('handles divider mousedown and triggers mouse events on document', async () => {
    vi.doMock('../../src/components/RequestBrowser/RequestBrowser', () => ({
      RequestBrowser: () => <div>browser</div>,
    }));
    vi.doMock('../../src/components/RequestDetail/RequestDetail', () => ({
      RequestDetail: () => <div>detail panel</div>,
    }));

    const { RequestsWorkspace } = await import('../../src/app/RequestsWorkspace');

    const navigation = {
      activeTab: 'requests',
      requestId: 'req-1',
      requestModelFilter: '',
      requestSearch: '',
      chatGroupBy: 'system_prompt_first_user_first_assistant',
      selectedChatGroup: null,
    } as never;

    const { container } = render(
      <RequestsWorkspace
        activeRequestSummary={makeRequestSummary() as never}
        navigation={navigation}
        onSelectRequestSummary={vi.fn()}
        updateNavigation={vi.fn()}
      />,
    );

    expect(screen.getByText('browser')).toBeInTheDocument();
    expect(screen.getByText('detail panel')).toBeInTheDocument();

    const divider = container.querySelector('[style*="col-resize"]') as HTMLElement;
    expect(divider).toBeTruthy();

    const mouseDownEvent = new MouseEvent('mousedown', {
      clientX: 300,
      bubbles: true,
      cancelable: true,
    });
    divider.dispatchEvent(mouseDownEvent);

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 350 }));
    document.dispatchEvent(new MouseEvent('mouseup'));
  });
});

describe('ChatView — Show raw request renders unified RequestDetailContent', () => {
  function msg(overrides: Partial<ConversationMessage> & { id: string; role: string; content: string }): ConversationMessage {
    return {
      node_id: overrides.id,
      parent: null,
      children: [],
      origin: 'request',
      raw_message: { role: overrides.role, content: overrides.content },
      tool_names: [],
      meta_tags: {},
      source_request_id: 'req-1',
      source_request_timestamp: '2024-01-01T00:00:00Z',
      source_message_index: 0,
      last_seen_at: '2024-01-01T00:00:00Z',
      repeat_count: 1,
      model: 'gpt-4o-mini',
      latency_ms: 42,
      total_tokens: 3,
      ...overrides,
    };
  }

  function makeRequestDetail(overrides?: Partial<RequestDetailType>): RequestDetailType {
    return {
      ...makeRequestSummary(),
      cost: 0.01,
      cache_status: null,
      error_message: null,
      request_headers: {},
      client_request_headers: null,
      request_body: { messages: [{ role: 'user', content: 'hi' }] },
      client_request_body: null,
      response_headers: {},
      client_response_headers: null,
      response_body: { choices: [{ message: { role: 'assistant', content: 'reply' } }] },
      client_response_body: null,
      stream_chunks: null,
      reasoning_tokens: null,
      metadata: null,
      ...overrides,
    };
  }

  it('renders RequestDetailContent when Show raw request is clicked', { timeout: 15000 }, async () => {
    const { ChatView } = await import('../../src/components/ChatView/ChatView');
    const { ApiContext: FreshApiContext } = await import('../../src/hooks/useApi');

    const messages = [
      msg({
        id: 'msg-1',
        origin: 'request',
        role: 'user',
        content: 'hello',
        source_message_index: 0,
      }),
    ];

    const api = {
      getConversationMessages: vi.fn().mockResolvedValue({ items: messages }),
      getConversations: vi.fn().mockResolvedValue({ items: [] }),
      getRequest: vi.fn().mockResolvedValue(makeRequestDetail()),
    };

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <FreshApiContext.Provider value={api as never}>
          <ChatView
            groupBy="system_prompt_first_user_first_assistant"
            onGroupByChange={vi.fn()}
            onSelectGroup={vi.fn()}
            selectedGroup="alpha"
          />
        </FreshApiContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());

    const showRawButtons = screen.getAllByRole('button', { name: 'Show raw request' });
    await userEvent.click(showRawButtons[0]);
    await waitFor(() => expect(api.getRequest).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());
  });
});

describe('RequestDetail messageToText branches', () => {
  function makeRequestDetail(overrides?: Partial<RequestDetailType>): RequestDetailType {
    return {
      ...makeRequestSummary(),
      cost: 0.01,
      cache_status: null,
      error_message: null,
      request_headers: {},
      client_request_headers: null,
      request_body: overrides?.request_body ?? { messages: [] },
      client_request_body: null,
      response_headers: {},
      client_response_headers: null,
      response_body: overrides?.response_body ?? { choices: [{ message: { role: 'assistant', content: 'ok' } }] },
      client_response_body: null,
      stream_chunks: null,
      reasoning_tokens: null,
      metadata: null,
      ...overrides,
    };
  }

  it('covers messageToText with array content and tool_calls', async () => {
    const { RequestDetail } = await import('../../src/components/RequestDetail/RequestDetail');
    const { ApiContext: FreshApiContext } = await import('../../src/hooks/useApi');

    const detail = makeRequestDetail({
      request_body: {
        messages: [
          { role: 'user', content: [{ type: 'text', text: 'describe this' }, { type: 'image_url' }] },
          {
            role: 'assistant',
            name: 'helper',
            content: '',
            tool_calls: [{ type: 'function', function: { name: 'search' } }],
          },
        ],
      },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <FreshApiContext.Provider value={api as never}>
          <RequestDetail onClose={vi.fn()} requestId="req-msg" requestSummary={makeRequestSummary()} />
        </FreshApiContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());
  });
});
