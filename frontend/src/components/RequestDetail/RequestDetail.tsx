import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../hooks/useApi';
import { JsonViewer } from '../JsonViewer/JsonViewer';
import type { RequestDetail as RequestDetailType, RequestSummary } from '../../types';

interface RequestDetailProps {
  requestId: string;
  requestSummary?: RequestSummary | null;
  onClose: () => void;
}

export function RequestDetail({ requestId, requestSummary = null, onClose }: RequestDetailProps) {
  const api = useApi();
  const [exportingFormat, setExportingFormat] = useState<'json' | 'markdown' | null>(null);
  const [exportError, setExportError] = useState('');
  const { data, isLoading, error } = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => api.getRequest(requestId),
  });

  const request: RequestSummary | RequestDetailType | null = data ?? requestSummary;

  async function handleExport(format: 'json' | 'markdown') {
    setExportError('');
    setExportingFormat(format);
    try {
      await api.downloadExport(requestId, format);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : String(error));
    } finally {
      setExportingFormat(null);
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.id}>#{requestId.slice(0, 8)}…</span>
          <span style={{ ...styles.badge, background: statusBg(request?.response_status_code ?? null) }}>
            {request?.response_status_code ?? '...'}
          </span>
          <span style={styles.model}>{request?.model_requested ?? 'Loading request...'}</span>
          {request?.model_resolved && request.model_resolved !== request.model_requested && (
            <span style={styles.meta}>→ {request.model_resolved}</span>
          )}
        </div>
        <div style={styles.headerRight}>
          <button
            onClick={() => handleExport('json')}
            style={styles.exportButton}
            disabled={exportingFormat !== null}
          >
            {exportingFormat === 'json' ? 'Exporting…' : 'JSON'}
          </button>
          <button
            onClick={() => handleExport('markdown')}
            style={styles.exportButton}
            disabled={exportingFormat !== null}
          >
            {exportingFormat === 'markdown' ? 'Exporting…' : 'MD'}
          </button>
          <button onClick={onClose} style={styles.closeBtn}>✕</button>
        </div>
      </div>

      <div style={styles.metaRow}>
        <MetaBadge label="Latency" value={request?.latency_ms != null ? `${Math.round(request.latency_ms)}ms` : '-'} />
        <MetaBadge label="In" value={String(request?.input_tokens ?? '-')} />
        <MetaBadge label="Out" value={String(request?.output_tokens ?? '-')} />
        <MetaBadge label="Total" value={String(request?.total_tokens ?? '-')} />
        {request?.cost != null && <MetaBadge label="Cost" value={`$${request.cost.toFixed(6)}`} />}
        {request?.cache_status && <MetaBadge label="Cache" value={request.cache_status} />}
        <MetaBadge label="Time" value={request ? new Date(request.timestamp).toLocaleString() : '-'} />
      </div>
      {exportError && <div style={styles.exportError}>{exportError}</div>}
      {error && <div style={styles.exportError}>{error instanceof Error ? error.message : String(error)}</div>}

      {isLoading ? (
        <div style={styles.loading}>Loading detail…</div>
      ) : data ? (
        <div style={styles.sections}>
          <Section title="Request Body">
            <pre style={styles.pre}>
              <JsonViewer data={data.request_body} />
            </pre>
          </Section>
          <Section title="Response Body">
            <pre style={styles.pre}>
              <JsonViewer data={data.response_body} />
            </pre>
          </Section>
          {data.stream_chunks && data.stream_chunks.length > 0 && (
            <Section title={`Stream Chunks (${data.stream_chunks.length})`} collapsed>
              <pre style={styles.pre}>
                <JsonViewer data={data.stream_chunks} />
              </pre>
            </Section>
          )}
          {data.request_headers && (
            <Section title="Request Headers" collapsed>
              <pre style={styles.pre}>
                <JsonViewer data={data.request_headers} />
              </pre>
            </Section>
          )}
          {data.error_message && (
            <Section title="Error">
              <pre style={{ ...styles.pre, color: '#f85149' }}>{data.error_message}</pre>
            </Section>
          )}
        </div>
      ) : null}
    </div>
  );
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: '0.77rem' }}>
      <span style={{ color: '#8b949e' }}>{label}:</span>
      <span style={{ color: '#e6edf3', fontWeight: 500 }}>{value}</span>
    </span>
  );
}

function Section({
  title,
  children,
  collapsed: initCollapsed = false,
}: {
  title: string;
  children: React.ReactNode;
  collapsed?: boolean;
}) {
  const [open, setOpen] = useState(!initCollapsed);
  return (
    <div style={{ borderBottom: '1px solid #21262d' }}>
      <button onClick={() => setOpen(o => !o)} style={sectionHeaderStyle}>
        <span>{open ? '▼' : '▶'}</span>
        <span>{title}</span>
      </button>
      {open && <div style={{ padding: '0 12px 12px' }}>{children}</div>}
    </div>
  );
}

function statusBg(code: number | null) {
  if (!code) return '#6e7681';
  if (code < 300) return '#1a7f37';
  if (code < 400) return '#9a6700';
  return '#b62324';
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', color: '#e6edf3' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #21262d', flexShrink: 0, gap: 8 },
  headerLeft: { display: 'flex', gap: 8, alignItems: 'center', overflow: 'hidden' },
  headerRight: { display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 },
  id: { fontFamily: 'monospace', fontSize: '0.8rem', color: '#8b949e' },
  badge: { borderRadius: 4, padding: '1px 6px', fontSize: '0.78rem', fontWeight: 600, color: '#fff' },
  model: { fontSize: '0.85rem', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { fontSize: '0.8rem', color: '#8b949e', whiteSpace: 'nowrap' },
  metaRow: { display: 'flex', gap: 16, padding: '6px 12px', borderBottom: '1px solid #21262d', flexWrap: 'wrap', flexShrink: 0 },
  exportError: { padding: '8px 12px', color: '#f85149', borderBottom: '1px solid #21262d', fontSize: '0.8rem' },
  sections: { flex: 1, overflow: 'auto' },
  pre: { margin: 0, fontFamily: 'monospace', fontSize: '0.8rem', lineHeight: 1.5, overflowX: 'auto' },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
  exportButton: { background: 'none', border: 'none', color: '#58a6ff', fontSize: '0.8rem', cursor: 'pointer', padding: 0 },
  closeBtn: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', fontSize: '1rem', padding: '0 4px' },
};

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex', gap: 6, alignItems: 'center',
  width: '100%', background: 'none', border: 'none', color: '#e6edf3',
  cursor: 'pointer', padding: '8px 12px', fontSize: '0.85rem', fontWeight: 600,
  textAlign: 'left',
};
