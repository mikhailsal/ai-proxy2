import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../hooks/useApi';
import type { HighlightRule } from '../JsonViewer/JsonViewer';
import { JsonViewer } from '../JsonViewer/JsonViewer';
import { DiffJsonViewer } from '../JsonViewer/DiffJsonViewer';
import type { RequestDetail as RequestDetailType, RequestSummary } from '../../types';
import { countTokens, selectEncoding } from '../../utils/cacheBoundary';
import { tpsColor, durationColor, costColor, cacheRatioColor, messageCountColor } from '../RequestBrowser/metricColors';

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
      <RequestDetailHeader
        exportingFormat={exportingFormat}
        onClose={onClose}
        onExport={handleExport}
        request={request}
        requestId={requestId}
      />
      <RequestDetailMetaRow request={request} />
      {exportError && <div style={styles.exportError}>{exportError}</div>}
      {error && <div style={styles.exportError}>{error instanceof Error ? error.message : String(error)}</div>}
      <RequestDetailBody data={data} isLoading={isLoading} />
    </div>
  );
}

export function RequestDetailContent({ requestId }: { requestId: string }) {
  const api = useApi();
  const { data, isLoading, error } = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => api.getRequest(requestId),
  });

  if (isLoading) return <div style={styles.loading}>Loading detail…</div>;
  if (error) return <div style={styles.exportError}>{error instanceof Error ? error.message : String(error)}</div>;
  if (!data) return null;

  return (
    <div style={styles.contentContainer}>
      <div style={styles.contentHeader}>
        <div style={styles.headerLeft}>
          <span style={styles.id}>#{requestId.slice(0, 8)}…</span>
          <span style={{ ...styles.badge, background: statusBg(data.response_status_code ?? null) }}>
            {data.response_status_code ?? '...'}
          </span>
          <span style={styles.model}>{data.model_requested ?? ''}</span>
          {data.model_resolved && data.model_resolved !== data.model_requested ? (
            <span style={styles.meta}>→ {data.model_resolved}</span>
          ) : null}
        </div>
      </div>
      <RequestDetailMetaRow request={data} />
      <RequestDetailBody data={data} isLoading={false} />
    </div>
  );
}

function RequestDetailHeader({
  exportingFormat,
  onClose,
  onExport,
  request,
  requestId,
}: {
  exportingFormat: 'json' | 'markdown' | null;
  onClose: () => void;
  onExport: (format: 'json' | 'markdown') => Promise<void>;
  request: RequestSummary | RequestDetailType | null;
  requestId: string;
}) {
  return (
    <div style={styles.header}>
      <div style={styles.headerLeft}>
        <span style={styles.id}>#{requestId.slice(0, 8)}…</span>
        <span style={{ ...styles.badge, background: statusBg(request?.response_status_code ?? null) }}>
          {request?.response_status_code ?? '...'}
        </span>
        <span style={styles.model}>{request?.model_requested ?? 'Loading request...'}</span>
        {request?.model_resolved && request.model_resolved !== request.model_requested ? (
          <span style={styles.meta}>→ {request.model_resolved}</span>
        ) : null}
      </div>
      <div style={styles.headerRight}>
        <ExportButton exportingFormat={exportingFormat} format="json" onExport={onExport} />
        <ExportButton exportingFormat={exportingFormat} format="markdown" onExport={onExport} />
        <button onClick={onClose} style={styles.closeBtn}>✕</button>
      </div>
    </div>
  );
}

function ExportButton({
  exportingFormat,
  format,
  onExport,
}: {
  exportingFormat: 'json' | 'markdown' | null;
  format: 'json' | 'markdown';
  onExport: (format: 'json' | 'markdown') => Promise<void>;
}) {
  const label = format === 'json' ? 'JSON' : 'MD';
  const loadingLabel = format === 'json' ? 'Exporting…' : 'Exporting…';

  return (
    <button onClick={() => void onExport(format)} style={styles.exportButton} disabled={exportingFormat !== null}>
      {exportingFormat === format ? loadingLabel : label}
    </button>
  );
}

function computeTps(request: RequestSummary | RequestDetailType | null): string {
  if (!request) return '-';
  const tokens = request.output_tokens;
  const ms = request.latency_ms;
  if (tokens == null || tokens === 0 || ms == null || ms <= 0) return '-';
  const tps = tokens / (ms / 1000);
  return tps < 10 ? tps.toFixed(1) : Math.round(tps).toString();
}

function RequestDetailMetaRow({
  request,
}: {
  request: RequestSummary | RequestDetailType | null;
}) {
  const cachedTokens = request?.cached_input_tokens;
  const inputTokens = request?.input_tokens;
  const cachedDisplay = cachedTokens != null && cachedTokens > 0 && inputTokens != null && inputTokens > 0
    ? `${cachedTokens}/${inputTokens} (${Math.round((cachedTokens / inputTokens) * 100)}%)`
    : null;

  const tpsVal = computeTps(request);
  const summary = request as RequestSummary | null;

  return (
    <div style={styles.metaRow}>
      <MetaBadge label="Duration" value={request?.latency_ms != null ? formatDetailDuration(request.latency_ms) : '-'} valueColor={durationColor(request?.latency_ms ?? null)} />
      <MetaBadge label="TPS" value={tpsVal} valueColor={summary ? tpsColor(summary) : undefined} />
      <MetaBadge label="In" value={String(request?.input_tokens ?? '-')} />
      <MetaBadge label="Out" value={String(request?.output_tokens ?? '-')} />
      <MetaBadge label="Total" value={String(request?.total_tokens ?? '-')} />
      {cachedDisplay ? <MetaBadge label="Cached" value={cachedDisplay} valueColor={summary ? cacheRatioColor(summary) : undefined} highlight /> : null}
      {request?.cost != null ? <MetaBadge label="Cost" value={`$${request.cost.toFixed(6)}`} valueColor={costColor(request.cost)} /> : null}
      {request?.cache_status ? <MetaBadge label="Cache" value={request.cache_status} /> : null}
      {request?.message_count != null ? <MetaBadge label="Messages" value={String(request.message_count)} valueColor={messageCountColor(request.message_count)} /> : null}
      <MetaBadge label="Time" value={request ? new Date(request.timestamp).toLocaleString() : '-'} />
    </div>
  );
}

function hasDiff(a: unknown, b: unknown): boolean {
  return a != null && b != null && JSON.stringify(a) !== JSON.stringify(b);
}

function DiffOrPlainSection({ client, provider, title, diffTitle, collapsed = false, collapsedPaths = [], expandedPaths = [], highlightRules = [] }: {
  client: unknown; provider: unknown; title: string; diffTitle: string; collapsed?: boolean;
  collapsedPaths?: string[]; expandedPaths?: string[]; highlightRules?: HighlightRule[];
}) {
  if (hasDiff(client, provider)) {
    return <DiffSection left={client} right={provider} title={diffTitle} />;
  }
  const data = provider ?? client;
  return data ? <JsonSection data={data} title={title} collapsed={collapsed} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} /> : null;
}

function responseBodyCollapsedPaths(body: Record<string, unknown> | null): string[] {
  if (!body) return [];
  return Object.keys(body).filter(k => k !== 'choices');
}

function requestBodyPaths(body: Record<string, unknown> | null): { collapsed: string[]; expanded: string[] } {
  if (!body) return { collapsed: [], expanded: [] };
  const collapsed: string[] = [];
  const expanded: string[] = [];
  const messages = body.messages;
  if (Array.isArray(messages) && messages.length > 0) {
    for (let i = 0; i < messages.length - 1; i++) {
      collapsed.push(`messages.${i}`);
    }
    expanded.push(`messages.${messages.length - 1}`);
  }
  return { collapsed, expanded };
}

function RequestDetailBody({
  data,
  isLoading,
}: {
  data: RequestDetailType | undefined;
  isLoading: boolean;
}) {
  const tokenEstimateRules = useMemo(() => buildTokenEstimateRules(data), [data]);

  if (isLoading) return <div style={styles.loading}>Loading detail…</div>;
  if (!data) return null;

  const responseCollapsed = responseBodyCollapsedPaths(data.client_response_body ?? data.response_body);
  const reqPaths = requestBodyPaths(data.request_body ?? data.client_request_body);

  return (
    <div style={styles.sections}>
      <DiffOrPlainSection
        client={data.response_body} provider={data.client_response_body}
        title="Response Body" diffTitle="Response Body (Provider → Client)"
        collapsedPaths={responseCollapsed} expandedPaths={['choices']}
      />
      <DiffOrPlainSection
        client={data.client_request_body} provider={data.request_body}
        title="Request Body" diffTitle="Request Body (Client → Provider)"
        collapsedPaths={reqPaths.collapsed} expandedPaths={reqPaths.expanded}
        highlightRules={tokenEstimateRules}
      />
      {data.stream_chunks && data.stream_chunks.length > 0 ? (
        <JsonSection data={data.stream_chunks} title={`Stream Chunks (${data.stream_chunks.length})`} collapsed />
      ) : null}
      <DiffOrPlainSection
        client={data.response_headers} provider={data.client_response_headers}
        title="Response Headers" diffTitle="Response Headers (Provider → Client)" collapsed
      />
      <DiffOrPlainSection
        client={data.client_request_headers} provider={data.request_headers}
        title="Request Headers" diffTitle="Request Headers (Client → Provider)" collapsed
      />
      {data.error_message ? (
        <Section title="Error">
          <pre style={{ ...styles.pre, color: '#f85149' }}>{data.error_message}</pre>
        </Section>
      ) : null}
    </div>
  );
}

function JsonSection({
  data,
  title,
  collapsed = false,
  collapsedPaths = [],
  expandedPaths = [],
  highlightRules = [],
}: {
  data: unknown;
  title: string;
  collapsed?: boolean;
  collapsedPaths?: string[];
  expandedPaths?: string[];
  highlightRules?: HighlightRule[];
}) {
  return (
    <Section title={title} collapsed={collapsed}>
      <pre style={styles.pre}>
        <JsonViewer data={data} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} />
      </pre>
    </Section>
  );
}

function DiffSection({
  left,
  right,
  title,
}: {
  left: unknown;
  right: unknown;
  title: string;
}) {
  const [showDiff, setShowDiff] = useState(true);

  return (
    <Section title={title} badge={
      <button
        onClick={e => { e.stopPropagation(); setShowDiff(d => !d); }}
        style={styles.diffToggle}
      >
        {showDiff ? 'Plain' : 'Diff'}
      </button>
    }>
      <pre style={styles.pre}>
        {showDiff ? (
          <DiffJsonViewer left={left} right={right} />
        ) : (
          <JsonViewer data={right} />
        )}
      </pre>
    </Section>
  );
}

function MetaBadge({ label, value, highlight, valueColor }: { label: string; value: string; highlight?: boolean; valueColor?: string }) {
  return (
    <span style={{
      display: 'flex', gap: 4, alignItems: 'center', fontSize: '0.77rem',
      ...(highlight ? { background: 'rgba(187, 128, 9, 0.15)', borderRadius: 4, padding: '1px 6px' } : {}),
    }}>
      <span style={{ color: highlight ? '#ffa657' : '#8b949e' }}>{label}:</span>
      <span style={{ color: valueColor ?? '#e6edf3', fontWeight: 500 }}>{value}</span>
    </span>
  );
}

function Section({
  title,
  children,
  collapsed: initCollapsed = false,
  badge,
}: {
  title: string;
  children: React.ReactNode;
  collapsed?: boolean;
  badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(!initCollapsed);
  return (
    <div style={{ borderBottom: '1px solid #21262d', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <button onClick={() => setOpen(o => !o)} style={sectionHeaderStyle}>
          <span>{open ? '▼' : '▶'}</span>
          <span>{title}</span>
        </button>
        {badge && <div style={{ marginRight: 12, flexShrink: 0 }}>{badge}</div>}
      </div>
      {open && <div style={{ padding: '0 12px 12px', overflow: 'hidden', minWidth: 0 }}>{children}</div>}
    </div>
  );
}

function formatDetailDuration(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 0.1) return `${Math.round(ms)}ms`;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
}

function formatTokenEstimate(count: number): string {
  if (count >= 1000) return `~${(count / 1000).toFixed(1)}k tokens`;
  return `~${count} tokens`;
}

function messageToText(msg: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof msg.role === 'string') parts.push(msg.role);
  if (typeof msg.name === 'string') parts.push(msg.name);
  const content = msg.content;
  if (typeof content === 'string') {
    parts.push(content);
  } else if (Array.isArray(content)) {
    for (const part of content) {
      if (typeof part === 'object' && part !== null && (part as Record<string, unknown>).type === 'text') {
        const text = (part as Record<string, unknown>).text;
        if (typeof text === 'string') parts.push(text);
      }
    }
  }
  if (Array.isArray(msg.tool_calls)) {
    parts.push(JSON.stringify(msg.tool_calls));
  }
  return parts.join('\n');
}

function buildTokenEstimateRules(data: RequestDetailType | undefined): HighlightRule[] {
  if (!data) return [];

  const body = data.request_body ?? data.client_request_body;
  if (!body || typeof body !== 'object') return [];

  const model = data.model_requested ?? '';
  const encoding = selectEncoding(model);
  const actualInputTokens = data.input_tokens ?? 0;

  const rawToolEstimates: number[] = [];
  const rawMsgEstimates: number[] = [];

  const tools = (body as Record<string, unknown>).tools;
  if (Array.isArray(tools)) {
    for (const tool of tools) {
      rawToolEstimates.push(countTokens(JSON.stringify(tool), encoding));
    }
  }

  const messages = (body as Record<string, unknown>).messages;
  if (Array.isArray(messages)) {
    for (const m of messages) {
      const msg = m as Record<string, unknown>;
      rawMsgEstimates.push(countTokens(messageToText(msg), encoding) + 4);
    }
  }

  const rawTotal = rawToolEstimates.reduce((s, v) => s + v, 0) + rawMsgEstimates.reduce((s, v) => s + v, 0);
  const scale = rawTotal > 0 && actualInputTokens > 0 ? actualInputTokens / rawTotal : 1;

  const rules: HighlightRule[] = [];

  if (rawToolEstimates.length > 0) {
    let toolsTotal = 0;
    for (let i = 0; i < rawToolEstimates.length; i++) {
      const calibrated = Math.round(rawToolEstimates[i] * scale);
      toolsTotal += calibrated;
      rules.push({ path: `tools.${i}`, label: formatTokenEstimate(calibrated) });
    }
    rules.push({ path: 'tools', label: formatTokenEstimate(toolsTotal) });
  }

  if (rawMsgEstimates.length > 0) {
    let msgsTotal = 0;
    for (let i = 0; i < rawMsgEstimates.length; i++) {
      const calibrated = Math.round(rawMsgEstimates[i] * scale);
      msgsTotal += calibrated;
      rules.push({ path: `messages.${i}`, label: formatTokenEstimate(calibrated) });
    }
    rules.push({ path: 'messages', label: formatTokenEstimate(msgsTotal) });
  }

  return rules;
}

function statusBg(code: number | null) {
  if (!code) return '#6e7681';
  if (code < 300) return '#1a7f37';
  if (code < 400) return '#9a6700';
  return '#b62324';
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', color: '#e6edf3', minWidth: 0 },
  contentContainer: { display: 'flex', flexDirection: 'column', color: '#e6edf3', overflow: 'hidden' },
  contentHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #21262d', flexShrink: 0, gap: 8 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #21262d', flexShrink: 0, gap: 8 },
  headerLeft: { display: 'flex', gap: 8, alignItems: 'center', overflow: 'hidden' },
  headerRight: { display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 },
  id: { fontFamily: 'monospace', fontSize: '0.8rem', color: '#8b949e' },
  badge: { borderRadius: 4, padding: '1px 6px', fontSize: '0.78rem', fontWeight: 600, color: '#fff' },
  model: { fontSize: '0.85rem', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { fontSize: '0.8rem', color: '#8b949e', whiteSpace: 'nowrap' },
  metaRow: { display: 'flex', gap: 16, padding: '6px 12px', borderBottom: '1px solid #21262d', flexWrap: 'wrap', flexShrink: 0 },
  exportError: { padding: '8px 12px', color: '#f85149', borderBottom: '1px solid #21262d', fontSize: '0.8rem' },
  sections: { flex: 1, overflow: 'auto', minWidth: 0 },
  pre: { margin: 0, fontFamily: 'monospace', fontSize: '0.8rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowWrap: 'anywhere', minWidth: 0 },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
  exportButton: { background: 'none', border: 'none', color: '#58a6ff', fontSize: '0.8rem', cursor: 'pointer', padding: 0 },
  closeBtn: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', fontSize: '1rem', padding: '0 4px' },
  diffToggle: { background: 'rgba(88, 166, 255, 0.1)', border: '1px solid rgba(88, 166, 255, 0.3)', borderRadius: 4, color: '#58a6ff', cursor: 'pointer', fontSize: '0.72rem', padding: '1px 8px', whiteSpace: 'nowrap' as const },
};

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex', gap: 6, alignItems: 'center',
  width: '100%', background: 'none', border: 'none', color: '#e6edf3',
  cursor: 'pointer', padding: '8px 12px', fontSize: '0.85rem', fontWeight: 600,
  textAlign: 'left',
};
