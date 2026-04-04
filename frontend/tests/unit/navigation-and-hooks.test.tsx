import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiContext, useApi } from '../../src/hooks/useApi';
import {
  buildNavigationUrl,
  DEFAULT_NAVIGATION,
  parseChatGroupBy,
  readNavigationFromLocation,
} from '../../src/app/navigation';
import { useNavigationState } from '../../src/app/useNavigationState';
import { StatsBar } from '../../src/components/common/StatsBar';

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('navigation helpers', () => {
  it('parses navigation state from a location-like object', () => {
    const location = { hash: '#top', pathname: '/app', search: '?tab=chat&groupBy=model&group=alpha' } as Location;
    expect(parseChatGroupBy('client')).toBe('client');
    expect(parseChatGroupBy('system_prompt_first_user')).toBe('system_prompt_first_user');
    expect(parseChatGroupBy('system_prompt_first_user_first_assistant')).toBe('system_prompt_first_user_first_assistant');
    expect(parseChatGroupBy('other')).toBe(DEFAULT_NAVIGATION.chatGroupBy);
    expect(readNavigationFromLocation(location)).toEqual({
      activeTab: 'chat',
      requestId: null,
      requestSearch: '',
      requestModelFilter: '',
      chatGroupBy: 'model',
      selectedChatGroup: 'alpha',
    });
  });

  it('builds request and chat URLs from navigation state', () => {
    const location = { hash: '#hash', pathname: '/app', search: '' } as Location;

    expect(
      buildNavigationUrl({
        ...DEFAULT_NAVIGATION,
        requestId: 'req-1',
        requestModelFilter: 'gpt',
        requestSearch: 'hello',
      }, location),
    ).toBe('/app?q=hello&model=gpt&request=req-1#hash');

    expect(
      buildNavigationUrl({
        ...DEFAULT_NAVIGATION,
        activeTab: 'chat',
        chatGroupBy: 'client',
        selectedChatGroup: 'team-a',
      }, location),
    ).toBe('/app?tab=chat&groupBy=client&group=team-a#hash');
  });
});

describe('useNavigationState', () => {
  it('updates history and tracks the active request summary', () => {
    window.history.replaceState(null, '', '/?q=before');

    const { result } = renderHook(() => useNavigationState());
    const request = { id: 'req-1' } as never;

    act(() => {
      result.current.setSelectedRequestSummary(request);
      result.current.updateNavigation(current => ({ ...current, requestId: 'req-1', requestSearch: 'after' }));
    });

    expect(result.current.activeRequestSummary).toEqual(request);
    expect(window.location.search).toContain('q=after');
    expect(window.location.search).toContain('request=req-1');
  });

  it('handles replace updates and popstate resets', () => {
    window.history.replaceState(null, '', '/?tab=chat&groupBy=client&group=alpha');
    const { result } = renderHook(() => useNavigationState());

    act(() => {
      result.current.setSelectedRequestSummary({ id: 'req-1' } as never);
      result.current.updateNavigation(current => ({ ...current, selectedChatGroup: 'beta' }), 'replace');
    });
    expect(window.location.search).toContain('group=beta');

    act(() => {
      window.history.pushState(null, '', '/?q=restored');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(result.current.navigation.requestSearch).toBe('restored');
    expect(result.current.selectedRequestSummary).toBeNull();
  });

  it('does not push a new history entry when navigation is unchanged', () => {
    window.history.replaceState(null, '', '/?q=same');
    const pushState = vi.spyOn(window.history, 'pushState');
    const { result } = renderHook(() => useNavigationState());

    act(() => {
      result.current.updateNavigation(current => current);
    });

    expect(pushState).not.toHaveBeenCalled();
  });
});

describe('useApi and StatsBar', () => {
  it('throws when the API context is missing', () => {
    expect(() => renderHook(() => useApi())).toThrow('useApi must be used within ApiContext.Provider');
  });

  it('renders fetched stats inside the API provider', async () => {
    const api = {
      getStats: vi.fn().mockResolvedValue({
        total_requests: 1234,
        avg_latency_ms: 87,
        total_tokens: 4567,
      }),
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <ApiContext.Provider value={api as never}>
          <StatsBar />
        </ApiContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('1,234')).toBeInTheDocument());
    expect(screen.getByText('0.1s')).toBeInTheDocument();
    expect(screen.getByText('4,567')).toBeInTheDocument();
  });

  it('reads the current API client from context', () => {
    const api = { getStats: vi.fn() };
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <ApiContext.Provider value={api as never}>{children}</ApiContext.Provider>
    );

    const { result } = renderHook(() => useApi(), { wrapper });
    expect(result.current).toBe(api);
  });
});