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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  const [client, setClient] = useState<ApiClient | null>(null);
  const [activeTab, setActiveTab] = useState<'requests' | 'chat'>('requests');
  const [selectedRequest, setSelectedRequest] = useState<RequestSummary | null>(null);

  useEffect(() => {
    const saved = loadSettings();
    if (saved) {
      setClient(createApiClient(saved));
    }
  }, []);

  function handleDisconnect() {
    clearSettings();
    setClient(null);
    setSelectedRequest(null);
    queryClient.clear();
  }

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
              style={{ ...styles.navTab, ...(activeTab === 'requests' ? styles.navTabActive : {}) }}
              onClick={() => setActiveTab('requests')}
            >
              Requests
            </button>
            <button
              style={{ ...styles.navTab, ...(activeTab === 'chat' ? styles.navTabActive : {}) }}
              onClick={() => setActiveTab('chat')}
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
            {activeTab === 'requests' && (
              <>
                <div style={{ ...styles.pane, flex: selectedRequest ? '0 0 50%' : '1' }}>
                  <RequestBrowser
                    onSelect={r => setSelectedRequest(r)}
                    selectedId={selectedRequest?.id}
                  />
                </div>
                {selectedRequest && (
                  <div style={{ ...styles.pane, flex: '1', borderLeft: '1px solid #21262d' }}>
                    <RequestDetail
                      request={selectedRequest}
                      onClose={() => setSelectedRequest(null)}
                    />
                  </div>
                )}
              </>
            )}
            {activeTab === 'chat' && (
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <ChatView />
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
    borderBottom: '2px solid transparent',
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
