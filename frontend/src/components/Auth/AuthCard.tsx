import type { FormEvent } from 'react';
import { AppIcon } from '../common/AppIcon';

interface AuthCardProps {
  baseUrl: string;
  error: string;
  loading: boolean;
  onSubmit: (event: FormEvent) => Promise<void>;
  setBaseUrl: (value: string) => void;
  setUiApiKey: (value: string) => void;
  uiApiKey: string;
}

export function AuthCard({
  baseUrl,
  error,
  loading,
  onSubmit,
  setBaseUrl,
  setUiApiKey,
  uiApiKey,
}: AuthCardProps) {
  return (
    <div style={styles.card}>
      <h1 style={styles.title}><AppIcon size={28} /> AI Proxy v2</h1>
      <p style={styles.subtitle}>Connect to your proxy backend</p>
      <form onSubmit={event => void onSubmit(event)} style={styles.form}>
        <ConnectionField
          label="Backend URL"
          onChange={setBaseUrl}
          placeholder="http://localhost:8000"
          required
          type="url"
          value={baseUrl}
        />
        <ConnectionField
          label="UI API Key"
          onChange={setUiApiKey}
          placeholder="Leave empty if not configured"
          type="password"
          value={uiApiKey}
        />
        {error && <p style={styles.error}>{error}</p>}
        <button style={styles.button} type="submit" disabled={loading}>
          {loading ? 'Connecting…' : 'Connect'}
        </button>
      </form>
    </div>
  );
}

function ConnectionField({
  label,
  onChange,
  placeholder,
  required = false,
  type,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  required?: boolean;
  type: 'password' | 'url';
  value: string;
}) {
  return (
    <label style={styles.label}>
      {label}
      <input
        style={styles.input}
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
      />
    </label>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: '#161b22',
    border: '1px solid #30363d',
    borderRadius: 12,
    padding: '2rem',
    width: 360,
    color: '#e6edf3',
  },
  title: { margin: '0 0 0.25rem', fontSize: '1.5rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' },
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