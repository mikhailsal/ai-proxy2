import { useState } from 'react';
import { createApiClient, saveSettings } from '../../api/client';
import type { ApiClient } from '../../api/client';

interface AuthPageProps {
  onConnect: (client: ApiClient) => void;
}

export function AuthPage({ onConnect }: AuthPageProps) {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [uiApiKey, setUiApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const settings = { baseUrl: baseUrl.trim(), uiApiKey: uiApiKey.trim() };
      const client = createApiClient(settings);
      const ok = await client.testConnection();
      if (!ok) {
        setError('Could not connect to backend. Check URL and API key.');
      } else {
        saveSettings(settings);
        onConnect(client);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>AI Proxy v2</h1>
        <p style={styles.subtitle}>Connect to your proxy backend</p>
        <form onSubmit={handleConnect} style={styles.form}>
          <label style={styles.label}>
            Backend URL
            <input
              style={styles.input}
              type="url"
              value={baseUrl}
              onChange={e => setBaseUrl(e.target.value)}
              placeholder="http://localhost:8000"
              required
            />
          </label>
          <label style={styles.label}>
            UI API Key
            <input
              style={styles.input}
              type="password"
              value={uiApiKey}
              onChange={e => setUiApiKey(e.target.value)}
              placeholder="Leave empty if not configured"
            />
          </label>
          {error && <p style={styles.error}>{error}</p>}
          <button style={styles.button} type="submit" disabled={loading}>
            {loading ? 'Connecting…' : 'Connect'}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#0d1117',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  card: {
    background: '#161b22',
    border: '1px solid #30363d',
    borderRadius: 12,
    padding: '2rem',
    width: 360,
    color: '#e6edf3',
  },
  title: { margin: '0 0 0.25rem', fontSize: '1.5rem', fontWeight: 700 },
  subtitle: { margin: '0 0 1.5rem', color: '#8b949e', fontSize: '0.9rem' },
  form: { display: 'flex', flexDirection: 'column', gap: '1rem' },
  label: { display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.85rem', color: '#8b949e' },
  input: {
    background: '#0d1117',
    border: '1px solid #30363d',
    borderRadius: 6,
    color: '#e6edf3',
    padding: '0.5rem 0.75rem',
    fontSize: '0.9rem',
    outline: 'none',
  },
  error: { color: '#f85149', fontSize: '0.85rem', margin: 0 },
  button: {
    background: '#238636',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '0.6rem',
    cursor: 'pointer',
    fontSize: '0.9rem',
    fontWeight: 600,
    marginTop: '0.5rem',
  },
};
