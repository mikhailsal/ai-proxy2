import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createApiClient, loadSettings, clearSettings } from './api/client';
import type { ApiClient } from './api/client';
import { ConnectedApp } from './app/ConnectedApp';
import { AuthPage } from './components/Auth/AuthPage';
import { ApiContext } from './hooks/useApi';
import { AutoRefreshProvider } from './hooks/useAutoRefresh';

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

  useEffect(() => {
    const saved = loadSettings();
    if (saved) {
      setClient(createApiClient(saved));
    }
  }, []);

  function handleDisconnect() {
    clearSettings();
    setClient(null);
    queryClient.clear();
  }

  if (!client) {
    return <AuthPage onConnect={setClient} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ApiContext.Provider value={client}>
        <AutoRefreshProvider>
          <ConnectedApp onDisconnect={handleDisconnect} />
        </AutoRefreshProvider>
      </ApiContext.Provider>
    </QueryClientProvider>
  );
}
