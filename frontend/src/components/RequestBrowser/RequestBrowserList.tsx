import { useCallback, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { RequestSummary } from '../../types';
import { tpsColor, durationColor, costColor, cacheRatioColor, messageCountColor } from './metricColors';

const STORAGE_KEY = 'ai-proxy-col-widths';

const DEFAULT_COL_WIDTHS = {
  timestamp: 120,
  model: 200,
  status: 46,
  latency: 64,
  tokens: 90,
  msgs: 38,
  tps: 48,
  cost: 56,
  userMsg: 170,
  assistantMsg: 230,
};

type ColKey = keyof typeof DEFAULT_COL_WIDTHS;

function loadColWidths(): typeof DEFAULT_COL_WIDTHS {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_COL_WIDTHS;
    const parsed = JSON.parse(raw);
    const result = { ...DEFAULT_COL_WIDTHS };
    for (const key of Object.keys(result) as ColKey[]) {
      if (typeof parsed[key] === 'number' && parsed[key] >= 30) result[key] = parsed[key];
    }
    return result;
  } catch {
    return DEFAULT_COL_WIDTHS;
  }
}

function saveColWidths(widths: typeof DEFAULT_COL_WIDTHS): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(widths)); } catch { /* quota */ }
}

const COLUMN_DEFS: { key: ColKey; label: string; tooltip?: string }[] = [
  { key: 'timestamp', label: 'Timestamp' },
  { key: 'model', label: 'Model' },
  { key: 'status', label: 'Status' },
  {
    key: 'latency',
    label: 'Duration',
    tooltip:
      'End-to-end proxy time: from request arrival through auth, routing, ' +
      'full upstream round-trip (or entire stream duration), to response completion.',
  },
  { key: 'tokens', label: 'Tokens' },
  {
    key: 'msgs',
    label: 'Msgs',
    tooltip: 'Number of messages in the request (conversation length).',
  },
  {
    key: 'tps',
    label: 'TPS',
    tooltip: 'Tokens per second: output tokens divided by request duration.',
  },
  { key: 'cost', label: 'Cost' },
  { key: 'userMsg', label: 'User Message' },
  { key: 'assistantMsg', label: 'Assistant' },
];

interface RequestBrowserListProps {
  fetchNextPage: () => Promise<unknown>;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isLoading: boolean;
  items: RequestSummary[];
  onSelect: (request: RequestSummary) => void;
  searchQuery: string;
  selectedId?: string;
}

export function RequestBrowserList({
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  items,
  onSelect,
  searchQuery,
  selectedId,
}: RequestBrowserListProps) {
  const [colWidths, setColWidths] = useState(loadColWidths);
  const onResizeCol = useCallback(
    (key: ColKey, delta: number) => {
      setColWidths(prev => {
        const next = { ...prev, [key]: Math.max(prev[key] + delta, 30) };
        saveColWidths(next);
        return next;
      });
    },
    [],
  );

  if (isLoading) return <div style={styles.loading}>Loading…</div>;
  if (items.length === 0) return <div style={styles.loading}>No requests found.</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      <HeaderRow colWidths={colWidths} onResizeCol={onResizeCol} />
      <VirtualizedRows
        colWidths={colWidths}
        fetchNextPage={fetchNextPage}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        items={items}
        onSelect={onSelect}
        searchQuery={searchQuery}
        selectedId={selectedId}
      />
    </div>
  );
}

function VirtualizedRows({
  colWidths, fetchNextPage, hasNextPage, isFetchingNextPage, items, onSelect, searchQuery, selectedId,
}: RequestBrowserListProps & { colWidths: typeof DEFAULT_COL_WIDTHS }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: items.length + (hasNextPage && !searchQuery ? 1 : 0),
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 10,
  });

  loadNextPage(rowVirtualizer.getVirtualItems(), items.length, hasNextPage, isFetchingNextPage, fetchNextPage);

  return (
    <div ref={parentRef} style={styles.list}>
      <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
        {rowVirtualizer.getVirtualItems().map(virtualRow => {
          const item = items[virtualRow.index];
          if (!item) {
            return <LoadMoreRow isFetchingNextPage={isFetchingNextPage} key="sentinel" virtualRow={virtualRow} />;
          }
          return (
            <RequestRow
              colWidths={colWidths}
              item={item}
              isSelected={item.id === selectedId}
              key={item.id}
              onSelect={onSelect}
              virtualRow={virtualRow}
            />
          );
        })}
      </div>
    </div>
  );
}

function HeaderRow({
  colWidths,
  onResizeCol,
}: {
  colWidths: typeof DEFAULT_COL_WIDTHS;
  onResizeCol: (key: ColKey, delta: number) => void;
}) {
  return (
    <div style={styles.headerRow}>
      {COLUMN_DEFS.map(col => (
        <div
          key={col.key}
          style={{
            ...colStyle(col.key, colWidths),
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
          }}
          title={col.tooltip}
        >
          <span style={{ cursor: col.tooltip ? 'help' : undefined }}>
            {col.label}
            {col.tooltip ? ' ⓘ' : ''}
          </span>
          <ColResizer colKey={col.key} onResize={onResizeCol} />
        </div>
      ))}
    </div>
  );
}

function ColResizer({
  colKey,
  onResize,
}: {
  colKey: ColKey;
  onResize: (key: ColKey, delta: number) => void;
}) {
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      let lastX = e.clientX;
      const onMove = (ev: MouseEvent) => {
        const delta = ev.clientX - lastX;
        lastX = ev.clientX;
        onResize(colKey, delta);
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [colKey, onResize],
  );

  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        position: 'absolute',
        right: 0,
        top: 0,
        bottom: 0,
        width: 5,
        cursor: 'col-resize',
        zIndex: 1,
      }}
    />
  );
}

const SHRINKABLE_COLS: ReadonlySet<ColKey> = new Set(['userMsg', 'assistantMsg']);

function colStyle(key: ColKey, widths: typeof DEFAULT_COL_WIDTHS): React.CSSProperties {
  if (key === 'assistantMsg') {
    return { flex: 1, minWidth: widths[key], overflow: 'hidden' };
  }
  return { width: widths[key], minWidth: SHRINKABLE_COLS.has(key) ? 60 : undefined, flexShrink: SHRINKABLE_COLS.has(key) ? 1 : 0, overflow: 'hidden' };
}

function loadNextPage(
  virtualItems: Array<{ index: number }>,
  itemCount: number,
  hasNextPage: boolean,
  isFetchingNextPage: boolean,
  fetchNextPage: () => Promise<unknown>,
) {
  const lastItem = virtualItems[virtualItems.length - 1];
  if (lastItem && lastItem.index >= itemCount && hasNextPage && !isFetchingNextPage) {
    void fetchNextPage();
  }
}

function LoadMoreRow({
  isFetchingNextPage,
  virtualRow,
}: {
  isFetchingNextPage: boolean;
  virtualRow: { size: number; start: number };
}) {
  return (
    <div
      style={{
        position: 'absolute',
        top: virtualRow.start,
        height: virtualRow.size,
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#8b949e',
        fontSize: '0.8rem',
      }}
    >
      {isFetchingNextPage ? 'Loading more…' : 'Load more'}
    </div>
  );
}

function RequestRow({ colWidths, item, isSelected, onSelect, virtualRow }: {
  colWidths: typeof DEFAULT_COL_WIDTHS;
  item: RequestSummary;
  isSelected: boolean;
  onSelect: (request: RequestSummary) => void;
  virtualRow: { size: number; start: number };
}) {
  const dim: React.CSSProperties = { color: '#8b949e', fontSize: '0.78rem' };
  const rowStyle: React.CSSProperties = {
    ...styles.row, position: 'absolute', top: virtualRow.start, height: virtualRow.size,
    background: isSelected ? '#21262d' : 'transparent',
    borderLeft: isSelected ? '2px solid #58a6ff' : '2px solid transparent',
  };
  return (
    <div style={rowStyle} onClick={() => onSelect(item)}>
      <span style={{ ...colStyle('timestamp', colWidths), ...dim }}>{formatTimestamp(item.timestamp)}</span>
      <span style={{ ...colStyle('model', colWidths), ...styles.ellipsis }}>{item.model_requested ?? '-'}</span>
      <span style={{ ...colStyle('status', colWidths), color: statusColor(item.response_status_code) }}>
        {item.response_status_code ?? '-'}
      </span>
      <span style={{ ...colStyle('latency', colWidths), color: durationColor(item.latency_ms) }}>
        {item.latency_ms != null ? formatDuration(item.latency_ms) : '-'}
      </span>
      <span style={{ ...colStyle('tokens', colWidths), ...dim, color: cacheRatioColor(item) }}>{formatTokens(item)}</span>
      <span style={{ ...colStyle('msgs', colWidths), ...dim, color: messageCountColor(item.message_count) }}>
        {item.message_count ?? '-'}
      </span>
      <span style={{ ...colStyle('tps', colWidths), ...dim, color: tpsColor(item) }}>{formatTps(item)}</span>
      <span style={{ ...colStyle('cost', colWidths), ...dim, color: costColor(item.cost) }}>{formatCost(item.cost)}</span>
      <span style={{ ...colStyle('userMsg', colWidths), ...styles.ellipsis, ...dim }} title={item.last_user_message ?? undefined}>
        {item.last_user_message ?? '-'}
      </span>
      <span style={{ ...colStyle('assistantMsg', colWidths), ...styles.ellipsis, ...dim }} title={item.assistant_response ?? undefined}>
        {formatAssistantCell(item.assistant_response, colWidths.assistantMsg)}
      </span>
    </div>
  );
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  const yyyy = d.getFullYear();
  const MM = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}`;
}

// eslint-disable-next-line react-refresh/only-export-components
export function formatDuration(ms: number): string {
  const s = ms / 1000;
  return s < 0.1 ? `${Math.round(ms)}ms` : s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
}

// eslint-disable-next-line react-refresh/only-export-components
export function compactNumber(n: number): string {
  return n < 1000 ? String(n) : (n / 1000) % 1 === 0 ? `${n / 1000}k` : `${(n / 1000).toFixed(1)}k`;
}

function formatTokens(item: RequestSummary): string {
  const input = item.input_tokens;
  const output = item.output_tokens;
  const cached = item.cached_input_tokens;

  if (input == null && output == null) return item.total_tokens != null ? compactNumber(item.total_tokens) : '-';

  let inputPart = '';
  if (input != null) {
    inputPart = cached && cached > 0 ? `i${compactNumber(cached)}/${compactNumber(input)}` : `i${compactNumber(input)}`;
  }

  const outputPart = output != null ? `o${compactNumber(output)}` : '';

  return [inputPart, outputPart].filter(Boolean).join(' ');
}

// eslint-disable-next-line react-refresh/only-export-components
export function formatTps(item: RequestSummary): string {
  const tokens = item.output_tokens;
  const ms = item.latency_ms;
  if (tokens == null || tokens === 0 || ms == null || ms <= 0) return '-';
  const tps = tokens / (ms / 1000);
  return tps < 10 ? tps.toFixed(1) : Math.round(tps).toString();
}

const TOOL_CALL_RE = /^(.+?)\((.+)\)$/s;
const CELL_FONT = '0.78rem sans-serif';

let _measureCtx: CanvasRenderingContext2D | null = null;
function measureText(text: string): number {
  if (!_measureCtx) {
    const canvas = document.createElement('canvas');
    _measureCtx = canvas.getContext('2d');
    if (_measureCtx) _measureCtx.font = CELL_FONT;
  }
  return _measureCtx?.measureText(text).width ?? text.length * 6;
}

// eslint-disable-next-line react-refresh/only-export-components
export function formatAssistantCell(raw: string | null, columnPx: number): string {
  if (!raw) return '-';

  const segments = raw.split(' | ');
  if (segments.length === 1) return formatOneToolCall(segments[0], columnPx);

  const separatorPx = measureText(' | ') * (segments.length - 1);
  const perSegmentPx = Math.floor((columnPx - separatorPx) / segments.length);
  return segments.map(seg => formatOneToolCall(seg, perSegmentPx)).join(' | ');
}

function formatOneToolCall(seg: string, budgetPx: number): string {
  const match = TOOL_CALL_RE.exec(seg);
  if (!match) return seg;
  const funcName = match[1];
  const params = parseParams(match[2]);
  if (params.length === 0) return seg;
  const skeleton = funcName + '(' + params.map((p, i) => p.key + '=' + (i < params.length - 1 ? ', ' : '')).join('') + ')';
  const valueBudgetPx = budgetPx - measureText(skeleton);
  if (valueBudgetPx <= 0) return funcName + '(' + params.map(p => p.key).join(', ') + ')';
  const perValuePx = valueBudgetPx / params.length;
  const parts = params.map(p => {
    if (measureText(p.value) <= perValuePx) return p.key + '=' + p.value;
    return p.key + '=' + fitText(p.value, perValuePx);
  });
  return funcName + '(' + parts.join(', ') + ')';
}

function fitText(text: string, maxPx: number): string {
  const target = maxPx - measureText('…');
  if (target <= 0) return '…';
  let lo = 0, hi = text.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (measureText(text.slice(0, mid)) <= target) lo = mid; else hi = mid - 1;
  }
  return lo === text.length ? text : text.slice(0, lo) + '…';
}

interface Param { key: string; value: string }

function parseParams(s: string): Param[] {
  const result: Param[] = [];
  let i = 0;
  while (i < s.length) {
    const eq = s.indexOf('=', i);
    if (eq === -1) break;
    const key = s.slice(i, eq).trim();
    i = eq + 1;
    let value: string;
    if (s[i] === "'") {
      const end = findClosingQuote(s, i, "'");
      value = s.slice(i, end + 1);
      i = end + 1;
    } else if (s[i] === '"') {
      const end = findClosingQuote(s, i, '"');
      value = s.slice(i, end + 1);
      i = end + 1;
    } else if (s[i] === '[' || s[i] === '{') {
      const close = s[i] === '[' ? ']' : '}';
      const end = s.indexOf(close, i);
      value = end === -1 ? s.slice(i) : s.slice(i, end + 1);
      i = end === -1 ? s.length : end + 1;
    } else {
      const comma = s.indexOf(', ', i);
      value = comma === -1 ? s.slice(i) : s.slice(i, comma);
      i = comma === -1 ? s.length : comma;
    }
    result.push({ key, value });
    if (s[i] === ',') i++;
    while (i < s.length && s[i] === ' ') i++;
  }
  return result;
}

function findClosingQuote(s: string, start: number, quote: string): number {
  let i = start + 1;
  while (i < s.length) {
    if (s[i] === '\\') { i += 2; continue; }
    if (s[i] === quote) return i;
    i++;
  }
  return s.length - 1;
}

function formatCost(cost: number | null): string {
  if (cost == null || cost === 0) return '-';
  const s = cost.toFixed(4);
  if (s.startsWith('0.')) return '$' + s.slice(1);
  if (s.startsWith('-0.')) return '-$' + s.slice(2);
  return '$' + s;
}

function statusColor(code: number | null): string {
  if (!code) return '#8b949e';
  if (code < 300) return '#3fb950';
  if (code < 400) return '#d29922';
  return '#f85149';
}

const styles: Record<string, React.CSSProperties> = {
  list: { flex: 1, overflowY: 'auto', overflowX: 'hidden' },
  headerRow: { display: 'flex', padding: '6px 12px', fontSize: '0.75rem', color: '#8b949e', borderBottom: '1px solid #21262d', fontWeight: 600, flexShrink: 0, gap: 8, userSelect: 'none', overflow: 'hidden' },
  row: { display: 'flex', alignItems: 'center', padding: '0 12px', cursor: 'pointer', width: '100%', boxSizing: 'border-box', fontSize: '0.85rem', color: '#e6edf3', gap: 8, overflow: 'hidden' },
  ellipsis: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
};
