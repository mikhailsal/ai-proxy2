import { useState } from 'react';
import { createApiClient, saveSettings } from '../../api/client';
import type { ApiClient } from '../../api/client';
import { AuthCard } from './AuthCard';

interface AuthPageProps {
  onConnect: (client: ApiClient) => void;
}

export function AuthPage({ onConnect }: AuthPageProps) {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [uiApiKey, setUiApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleConnect(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const client = await connectClient(baseUrl, uiApiKey);
      onConnect(client);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <AuthCard
        baseUrl={baseUrl}
        error={error}
        loading={loading}
        onSubmit={handleConnect}
        setBaseUrl={setBaseUrl}
        setUiApiKey={setUiApiKey}
        uiApiKey={uiApiKey}
      />
    </div>
  );
}

async function connectClient(baseUrl: string, uiApiKey: string): Promise<ApiClient> {
  const settings = { baseUrl: baseUrl.trim(), uiApiKey: uiApiKey.trim() };
  const client = createApiClient(settings);
  await client.testConnection();
  saveSettings(settings);
  return client;
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#0d1117',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
};
