import { render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthCard } from '../../src/components/Auth/AuthCard';
import { RequestBrowserToolbar } from '../../src/components/RequestBrowser/RequestBrowserToolbar';
import { filterRequests, useRequestBrowserData } from '../../src/components/RequestBrowser/requestBrowserData';
import { RequestBrowserList, formatAssistantCell } from '../../src/components/RequestBrowser/RequestBrowserList';
import type { RequestSummary } from '../../src/types';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';

vi.mock('@tanstack/react-query', async importOriginal => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return { ...actual, useInfiniteQuery: vi.fn() };
});

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn(),
}));

const useInfiniteQueryMock = vi.mocked(useInfiniteQuery);
const useVirtualizerMock = vi.mocked(useVirtualizer);

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  vi.doUnmock('../../src/components/Auth/AuthPage');
  vi.doUnmock('../../src/components/RequestBrowser/requestBrowserData');
});

describe('Auth UI', () => {
  it('submits auth card values and reflects loading state', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const setBaseUrl = vi.fn();
    const setUiApiKey = vi.fn();

    const { rerender } = render(
      <AuthCard
        baseUrl="http://localhost:8000"
        error=""
        loading={false}
        onSubmit={onSubmit}
        setBaseUrl={setBaseUrl}
        setUiApiKey={setUiApiKey}
        uiApiKey=""
      />,
    );

    await userEvent.type(screen.getByLabelText('Backend URL'), '/api');
    await userEvent.type(screen.getByLabelText('UI API Key'), 'secret');
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }));

    expect(setBaseUrl).toHaveBeenCalled();
    expect(setUiApiKey).toHaveBeenCalled();
    expect(onSubmit).toHaveBeenCalled();

    rerender(
      <AuthCard
        baseUrl="http://localhost:8000"
        error="Connection failed"
        loading
        onSubmit={onSubmit}
        setBaseUrl={setBaseUrl}
        setUiApiKey={setUiApiKey}
        uiApiKey="secret"
      />,
    );

    expect(screen.getByText('Connection failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connecting…' })).toBeDisabled();
  });

  it('connects successfully and surfaces connection errors on AuthPage', async () => {
    const onConnect = vi.fn();
    const saveSettings = vi.fn();
    const client = { testConnection: vi.fn().mockResolvedValue(undefined) };

    vi.doMock('../../src/api/client', () => ({
      createApiClient: vi.fn(() => client),
      saveSettings,
    }));

    const { AuthPage } = await import('../../src/components/Auth/AuthPage');
    const { rerender } = render(<AuthPage onConnect={onConnect} />);

    await userEvent.clear(screen.getByLabelText('Backend URL'));
    await userEvent.type(screen.getByLabelText('Backend URL'), ' http://localhost:8000/ ');
    await userEvent.type(screen.getByLabelText('UI API Key'), ' secret ');
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }));

    await waitFor(() => expect(onConnect).toHaveBeenCalledWith(client));
    expect(saveSettings).toHaveBeenCalledWith({ baseUrl: 'http://localhost:8000/', uiApiKey: 'secret' });

    client.testConnection.mockRejectedValueOnce(new Error('bad key'));
    rerender(<AuthPage onConnect={onConnect} />);
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }));

    await waitFor(() => expect(screen.getByText('Error: bad key')).toBeInTheDocument());
  });
});

describe('Request browser helpers', () => {
  it('submits, clears, and filters through the toolbar', async () => {
    const onSearchQueryChange = vi.fn();
    const onModelFilterChange = vi.fn();
    const setSearchText = vi.fn();

    render(
      <RequestBrowserToolbar
        modelFilter="gpt"
        onModelFilterChange={onModelFilterChange}
        onSearchQueryChange={onSearchQueryChange}
        searchQuery="hello"
        searchText=" draft "
        setSearchText={setSearchText}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Search' }));
    await userEvent.click(screen.getByRole('button', { name: '✕' }));
    await userEvent.type(screen.getByPlaceholderText('Filter by model…'), '4o');

    expect(onSearchQueryChange).toHaveBeenNthCalledWith(1, 'draft');
    expect(setSearchText).toHaveBeenCalledWith('');
    expect(onSearchQueryChange).toHaveBeenNthCalledWith(2, '');
    expect(onModelFilterChange).toHaveBeenCalled();
  });

  it('filters requests and switches between request and search queries', () => {
    const items = [
      makeRequestSummary({ id: 'a', model_requested: 'gpt-4o-mini', model_resolved: 'openai/gpt-4o-mini' }),
      makeRequestSummary({ id: 'b', model_requested: 'claude', model_resolved: null }),
    ];

    useInfiniteQueryMock.mockImplementation(({ queryKey }) => {
      if (queryKey[0] === 'requests') {
        return {
          data: { pages: [{ items, next_cursor: 'cursor-1' }] },
          fetchNextPage: vi.fn(),
          hasNextPage: true,
          isFetchingNextPage: false,
          isLoading: false,
        } as never;
      }

      return {
        data: { pages: [{ items: [items[1]] }] },
        fetchNextPage: vi.fn(),
        hasNextPage: false,
        isFetchingNextPage: false,
        isLoading: false,
      } as never;
    });

    const first = renderHook(() => useRequestBrowserData({ listRequests: vi.fn(), searchRequests: vi.fn() } as never, '', '4o'));
    expect(first.result.current.items).toEqual([items[0]]);
    expect(filterRequests(items, '')).toEqual(items);

    const second = renderHook(() => useRequestBrowserData({ listRequests: vi.fn(), searchRequests: vi.fn() } as never, 'claude', ''));
    expect(second.result.current.items).toEqual([items[1]]);
  });
});

describe('Request browser components', () => {
  it('shows loading, empty, rows, and sentinel states in the virtualized list', async () => {
    const onSelect = vi.fn();
    const fetchNextPage = vi.fn().mockResolvedValue(undefined);
    useVirtualizerMock.mockReturnValue({
      getTotalSize: () => 88,
      getVirtualItems: () => [{ index: 0, size: 44, start: 0 }, { index: 1, size: 44, start: 44 }],
    } as never);

    const { rerender } = render(
      <RequestBrowserList
        fetchNextPage={fetchNextPage}
        hasNextPage={false}
        isFetchingNextPage={false}
        isLoading
        items={[]}
        onSelect={onSelect}
        searchQuery=""
      />,
    );

    expect(screen.getByText('Loading…')).toBeInTheDocument();

    rerender(
      <RequestBrowserList
        fetchNextPage={fetchNextPage}
        hasNextPage={false}
        isFetchingNextPage={false}
        isLoading={false}
        items={[]}
        onSelect={onSelect}
        searchQuery=""
      />,
    );
    expect(screen.getByText('No requests found.')).toBeInTheDocument();

    rerender(
      <RequestBrowserList
        fetchNextPage={fetchNextPage}
        hasNextPage
        isFetchingNextPage={false}
        isLoading={false}
        items={[makeRequestSummary({ id: 'req-1', response_status_code: 500 })]}
        onSelect={onSelect}
        searchQuery=""
        selectedId="req-1"
      />,
    );

    await userEvent.click(screen.getByText('500'));
    expect(onSelect).toHaveBeenCalled();
    expect(fetchNextPage).toHaveBeenCalled();
    expect(screen.getByText('Load more')).toBeInTheDocument();
  });

  it('renders RequestBrowser with synced search state and selection wiring', async () => {
    const request = makeRequestSummary({ id: 'req-1' });
    const onSelect = vi.fn();
    const onSearchQueryChange = vi.fn();
    const onModelFilterChange = vi.fn();

    vi.resetModules();
    vi.doMock('../../src/hooks/useApi', () => ({
      useApi: () => ({}),
    }));
    vi.doMock('../../src/components/RequestBrowser/requestBrowserData', () => ({
      useRequestBrowserData: () => ({
        fetchNextPage: vi.fn(),
        hasNextPage: false,
        isFetchingNextPage: false,
        isLoading: false,
        items: [request],
      }),
    }));
    vi.doMock('../../src/components/RequestBrowser/RequestBrowserToolbar', () => ({
      RequestBrowserToolbar: ({ searchText }: { searchText: string }) => <div>{searchText}</div>,
    }));
    vi.doMock('../../src/components/RequestBrowser/RequestBrowserList', () => ({
      RequestBrowserList: ({ items, onSelect }: { items: RequestSummary[]; onSelect: (item: RequestSummary) => void }) => (
        <button onClick={() => onSelect(items[0])}>{items[0].model_requested}</button>
      ),
    }));
    const { RequestBrowser } = await import('../../src/components/RequestBrowser/RequestBrowser');
    const { rerender } = render(
      <RequestBrowser
        modelFilter=""
        onModelFilterChange={onModelFilterChange}
        onSearchQueryChange={onSearchQueryChange}
        onSelect={onSelect}
        searchQuery="first"
      />,
    );

    await waitFor(() => expect(screen.getByText('first')).toBeInTheDocument());
    rerender(
      <RequestBrowser
        modelFilter=""
        onModelFilterChange={onModelFilterChange}
        onSearchQueryChange={onSearchQueryChange}
        onSelect={onSelect}
        searchQuery="second"
      />,
    );

    await waitFor(() => expect(screen.getByText('second')).toBeInTheDocument());
    await userEvent.click(screen.getByText(request.model_requested ?? '-'));
    expect(onSelect).toHaveBeenCalledWith(request);
  });
});

describe('formatAssistantCell', () => {
  it('returns dash for null', () => {
    expect(formatAssistantCell(null, 300)).toBe('-');
  });

  it('passes through plain text', () => {
    expect(formatAssistantCell('hello world', 300)).toBe('hello world');
  });

  it('formats single tool call with arguments', () => {
    const result = formatAssistantCell("greet(name='Alice', mood='happy')", 2000);
    expect(result).toContain('greet(');
    expect(result).toContain('name=');
    expect(result).toContain('mood=');
    expect(result).toMatch(/\)$/);
  });

  it('truncates long values but keeps closing bracket', () => {
    const longVal = 'a'.repeat(500);
    const result = formatAssistantCell(`fn(x='${longVal}')`, 200);
    expect(result).toMatch(/\)$/);
    expect(result).toContain('fn(');
    expect(result).toContain('x=');
  });

  it('formats tool call without args', () => {
    expect(formatAssistantCell('plain_name', 300)).toBe('plain_name');
  });

  it('handles multiple tool calls separated by pipe', () => {
    const result = formatAssistantCell("a(x='1') | b(y='2')", 2000);
    expect(result).toContain('a(');
    expect(result).toContain('b(');
    expect(result).toContain(' | ');
  });

  it('shows all param keys with tight budget', () => {
    const result = formatAssistantCell("fn(a='long_value', b='another_long_value', c='third')", 100);
    expect(result).toContain('a=');
    expect(result).toContain('b=');
    expect(result).toContain('c=');
    expect(result).toMatch(/\)$/);
  });
});

function makeRequestSummary(overrides: Partial<RequestSummary>): RequestSummary {
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
    latency_ms: overrides.latency_ms ?? 42,
    input_tokens: 1,
    output_tokens: 2,
    total_tokens: overrides.total_tokens ?? 3,
    cached_input_tokens: null,
    cost: null,
    cache_status: null,
    error_message: null,
    last_user_message: null,
    assistant_response: null,
  };
}