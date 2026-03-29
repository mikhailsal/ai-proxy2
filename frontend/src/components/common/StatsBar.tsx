import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../hooks/useApi';

export function StatsBar() {
  const api = useApi();
  const { data } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: 30_000,
  });

  if (!data) return null;

  return (
    <div style={styles.bar}>
      <Stat label="Requests" value={data.total_requests.toLocaleString()} />
      <Stat label="Avg Latency" value={`${data.avg_latency_ms}ms`} />
      <Stat label="Tokens" value={data.total_tokens.toLocaleString()} />
    </div>
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
  bar: { display: 'flex', gap: 20, padding: '4px 16px', background: '#161b22', borderBottom: '1px solid #21262d', fontSize: '0.8rem', flexShrink: 0 },
  stat: { display: 'flex', gap: 4 },
  label: { color: '#8b949e' },
  value: { color: '#e6edf3', fontWeight: 500 },
};
