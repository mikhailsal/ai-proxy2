import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createApiClient, loadSettings, clearSettings } from './api/client';
import type { ApiClient } from './api/client';
import { ApiContext } from './hooks/useApi';
import { AuthPage } from './components/Auth/AuthPage';
import { RequestBrowser } from './components/RequestBrowser/RequestBrowser';
import { RequestDetail } from './components/RequestDetail/RequestDetail';
import { ChatView } from './components/ChatView/ChatView';
import { StatsBar } from './components/common/StatsBar';
import type { RequestSummary } from './types';

type ActiveTab = 'requests' | 'chat';
type ChatGroupBy = 'system_prompt' | 'client' | 'model';

interface NavigationState {
  activeTab: ActiveTab;
  requestId: string | null;
  requestSearch: string;
  requestModelFilter: string;
  chatGroupBy: ChatGroupBy;
  selectedChatGroup: string | null;
}

const DEFAULT_NAVIGATION: NavigationState = {
  activeTab: 'requests',
  requestId: null,
  requestSearch: '',
  requestModelFilter: '',
  chatGroupBy: 'system_prompt',
  selectedChatGroup: null,
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 10_000,
    },
  },
});

function parseChatGroupBy(value: string | null): ChatGroupBy {
  if (value === 'client' || value === 'model' || value === 'system_prompt') {
    return value;
  }
  return DEFAULT_NAVIGATION.chatGroupBy;
}

function readNavigationFromLocation(): NavigationState {
  const params = new URLSearchParams(window.location.search);
  return {
    activeTab: params.get('tab') === 'chat' ? 'chat' : 'requests',
    requestId: params.get('request'),
    requestSearch: params.get('q') ?? '',
    requestModelFilter: params.get('model') ?? '',
    chatGroupBy: parseChatGroupBy(params.get('groupBy')),
    selectedChatGroup: params.get('group'),
  };
}

function buildNavigationUrl(state: NavigationState): string {
  const params = new URLSearchParams();

  if (state.activeTab === 'chat') {
    params.set('tab', 'chat');
    if (state.chatGroupBy !== DEFAULT_NAVIGATION.chatGroupBy) {
      params.set('groupBy', state.chatGroupBy);
    }
    if (state.selectedChatGroup) {
      params.set('group', state.selectedChatGroup);
    }
  } else {
    if (state.requestSearch) {
      params.set('q', state.requestSearch);
    }
    if (state.requestModelFilter) {
      params.set('model', state.requestModelFilter);
    }
    if (state.requestId) {
      params.set('request', state.requestId);
    }
  }

  const search = params.toString();
  return `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`;
}

export default function App() {
  const [client, setClient] = useState<ApiClient | null>(null);
  const [navigation, setNavigation] = useState<NavigationState>(() => readNavigationFromLocation());
  const [selectedRequestSummary, setSelectedRequestSummary] = useState<RequestSummary | null>(null);

  useEffect(() => {
    const saved = loadSettings();
    if (saved) {
      setClient(createApiClient(saved));
    }
  }, []);

  useEffect(() => {
    function handlePopState() {
      setNavigation(readNavigationFromLocation());
      setSelectedRequestSummary(null);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  function updateNavigation(
    updater: NavigationState | ((current: NavigationState) => NavigationState),
    mode: 'push' | 'replace' = 'push',
  ) {
    setNavigation(current => {
      const next = typeof updater === 'function' ? updater(current) : updater;
      const nextUrl = buildNavigationUrl(next);
      const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;

      if (nextUrl !== currentUrl) {
        if (mode === 'replace') {
          window.history.replaceState(null, '', nextUrl);
        } else {
          window.history.pushState(null, '', nextUrl);
        }
      }

      return next;
    });
  }

  function handleDisconnect() {
    clearSettings();
    setClient(null);
    setSelectedRequestSummary(null);
    queryClient.clear();
  }

  const activeRequestSummary =
    navigation.requestId && selectedRequestSummary?.id === navigation.requestId
      ? selectedRequestSummary
      : null;

  if (!client) {
    return <AuthPage onConnect={setClient} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ApiContext.Provider value={client}>
        <div style={styles.app}>
          <div style={styles.nav}>
            <span style={styles.navTitle}>AI Proxy v2</span>
            <button
              style={{
                ...styles.navTab,
                ...(navigation.activeTab === 'requests' ? styles.navTabActive : {}),
              }}
              onClick={() => updateNavigation(current => ({ ...current, activeTab: 'requests' }))}
            >
              Requests
            </button>
            <button
              style={{
                ...styles.navTab,
                ...(navigation.activeTab === 'chat' ? styles.navTabActive : {}),
              }}
              onClick={() => updateNavigation(current => ({ ...current, activeTab: 'chat' }))}
            >
              Chat
            </button>
            <div style={{ flex: 1 }} />
            <button onClick={handleDisconnect} style={styles.disconnectBtn}>
              Disconnect
            </button>
          </div>

          <StatsBar />

          <div style={styles.main}>
            {navigation.activeTab === 'requests' && (
              <>
                <div style={{ ...styles.pane, flex: navigation.requestId ? '0 0 50%' : '1' }}>
                  <RequestBrowser
                    modelFilter={navigation.requestModelFilter}
                    onModelFilterChange={modelFilter => {
                      updateNavigation(
                        current => ({
                          ...current,
                          activeTab: 'requests',
                          requestModelFilter: modelFilter,
                        }),
                        'replace',
                      );
                    }}
                    searchQuery={navigation.requestSearch}
                    onSearchQueryChange={searchQuery => {
                      updateNavigation(current => ({
                        ...current,
                        activeTab: 'requests',
                        requestSearch: searchQuery,
                      }));
                    }}
                    onSelect={request => {
                      setSelectedRequestSummary(request);
                      updateNavigation(current => ({
                        ...current,
                        activeTab: 'requests',
                        requestId: request.id,
                      }));
                    }}
                    selectedId={navigation.requestId ?? undefined}
                  />
                </div>
                {navigation.requestId && (
                  <div style={{ ...styles.pane, flex: '1', borderLeft: '1px solid #21262d' }}>
                    <RequestDetail
                      requestId={navigation.requestId}
                      requestSummary={activeRequestSummary}
                      onClose={() => {
                        setSelectedRequestSummary(null);
                        updateNavigation(current => ({
                          ...current,
                          requestId: null,
                        }));
                      }}
                    />
                  </div>
                )}
              </>
            )}
            {navigation.activeTab === 'chat' && (
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <ChatView
                  groupBy={navigation.chatGroupBy}
                  selectedGroup={navigation.selectedChatGroup}
                  onGroupByChange={groupBy => {
                    updateNavigation(current => ({
                      ...current,
                      activeTab: 'chat',
                      chatGroupBy: groupBy,
                      selectedChatGroup: null,
                    }));
                  }}
                  onSelectGroup={groupKey => {
                    updateNavigation(current => ({
                      ...current,
                      activeTab: 'chat',
                      selectedChatGroup: groupKey,
                    }));
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </ApiContext.Provider>
    </QueryClientProvider>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    background: '#0d1117',
    color: '#e6edf3',
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace',
    fontSize: '14px',
    overflow: 'hidden',
  },
  nav: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '0 16px',
    background: '#161b22',
    borderBottom: '1px solid #21262d',
    height: 44,
    flexShrink: 0,
  },
  navTitle: { fontWeight: 700, fontSize: '0.95rem', marginRight: 8, color: '#e6edf3' },
  navTab: {
    background: 'none',
    border: 'none',
    color: '#8b949e',
    padding: '0 12px',
    height: '100%',
    cursor: 'pointer',
    fontSize: '0.875rem',
    borderBottomWidth: 2,
    borderBottomStyle: 'solid',
    borderBottomColor: 'transparent',
  },
  navTabActive: { color: '#e6edf3', borderBottomColor: '#f78166' },
  disconnectBtn: {
    background: 'none',
    border: '1px solid #30363d',
    borderRadius: 6,
    color: '#8b949e',
    padding: '4px 10px',
    cursor: 'pointer',
    fontSize: '0.8rem',
  },
  main: { flex: 1, display: 'flex', overflow: 'hidden' },
  pane: { display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 },
};
