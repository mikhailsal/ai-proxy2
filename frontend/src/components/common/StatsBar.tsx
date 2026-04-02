import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../hooks/useApi';
import { REFRESH_OPTIONS, useAutoRefresh } from '../../hooks/autoRefreshContext';
import type { RefreshInterval } from '../../hooks/autoRefreshContext';

export function StatsBar() {
  const api = useApi();
  const { refetchInterval } = useAutoRefresh();
  const { data } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: refetchInterval || 30_000,
  });

  if (!data) return null;

  return (
    <div style={styles.bar}>
      <Stat label="Requests" value={data.total_requests.toLocaleString()} />
      <Stat label="Avg Duration" value={`${(data.avg_latency_ms / 1000).toFixed(1)}s`} />
      <Stat label="Tokens" value={data.total_tokens.toLocaleString()} />
      <div style={{ flex: 1 }} />
      <RefreshPicker />
    </div>
  );
}

function RefreshPicker() {
  const { intervalMs, setIntervalMs } = useAutoRefresh();

  return (
    <label style={styles.refreshLabel} title="Auto-refresh interval">
      <span style={styles.refreshIcon}>&#x21bb;</span>
      <select
        style={styles.refreshSelect}
        value={intervalMs}
        onChange={e => setIntervalMs(Number(e.target.value) as RefreshInterval)}
      >
        {REFRESH_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span style={styles.stat}>
      <span style={styles.label}>{label}:</span>
      <span style={styles.value}>{value}</span>
    </span>
  );
}

const styles: Record<string, React.CSSProperties> = {
  bar: { display: 'flex', gap: 20, padding: '4px 16px', background: '#161b22', borderBottom: '1px solid #21262d', fontSize: '0.8rem', flexShrink: 0, alignItems: 'center' },
  stat: { display: 'flex', gap: 4 },
  label: { color: '#8b949e' },
  value: { color: '#e6edf3', fontWeight: 500 },
  refreshLabel: { display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer' },
  refreshIcon: { color: '#8b949e', fontSize: '0.85rem' },
  refreshSelect: { background: 'transparent', border: 'none', color: '#8b949e', fontSize: '0.75rem', cursor: 'pointer', outline: 'none', padding: 0 },
};
