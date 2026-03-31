import { useCallback, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { RequestSummary } from '../../types';

const STORAGE_KEY = 'ai-proxy-col-widths';

const DEFAULT_COL_WIDTHS = {
  timestamp: 120,
  model: 200,
  status: 46,
  latency: 64,
  tokens: 90,
  cost: 56,
  userMsg: 200,
  assistantMsg: 250,
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
    label: 'Latency',
    tooltip:
      'End-to-end proxy time: from request arrival through auth, routing, ' +
      'full upstream round-trip (or entire stream duration), to response completion.',
  },
  { key: 'tokens', label: 'Tokens' },
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

function colStyle(key: ColKey, widths: typeof DEFAULT_COL_WIDTHS): React.CSSProperties {
  return { width: widths[key], flexShrink: 0, overflow: 'hidden' };
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

function RequestRow({
  colWidths,
  item,
  isSelected,
  onSelect,
  virtualRow,
}: {
  colWidths: typeof DEFAULT_COL_WIDTHS;
  item: RequestSummary;
  isSelected: boolean;
  onSelect: (request: RequestSummary) => void;
  virtualRow: { size: number; start: number };
}) {
  return (
    <div
      style={{
        ...styles.row,
        position: 'absolute',
        top: virtualRow.start,
        height: virtualRow.size,
        background: isSelected ? '#21262d' : 'transparent',
        borderLeft: isSelected ? '2px solid #58a6ff' : '2px solid transparent',
      }}
      onClick={() => onSelect(item)}
    >
      <span style={{ ...colStyle('timestamp', colWidths), color: '#8b949e', fontSize: '0.78rem' }}>
        {formatTimestamp(item.timestamp)}
      </span>
      <span style={{ ...colStyle('model', colWidths), ...styles.ellipsis }}>
        {item.model_requested ?? '-'}
      </span>
      <span style={{ ...colStyle('status', colWidths), color: statusColor(item.response_status_code) }}>
        {item.response_status_code ?? '-'}
      </span>
      <span style={{ ...colStyle('latency', colWidths), color: '#8b949e' }}>
        {item.latency_ms != null ? `${Math.round(item.latency_ms)}ms` : '-'}
      </span>
      <span style={{ ...colStyle('tokens', colWidths), color: '#8b949e', fontSize: '0.78rem' }}>
        {formatTokens(item)}
      </span>
      <span style={{ ...colStyle('cost', colWidths), color: '#8b949e', fontSize: '0.78rem' }}>
        {formatCost(item.cost)}
      </span>
      <span
        style={{ ...colStyle('userMsg', colWidths), ...styles.ellipsis, color: '#8b949e', fontSize: '0.78rem' }}
        title={item.last_user_message ?? undefined}
      >
        {item.last_user_message ?? '-'}
      </span>
      <span
        style={{ ...colStyle('assistantMsg', colWidths), ...styles.ellipsis, color: '#8b949e', fontSize: '0.78rem' }}
        title={item.assistant_response ?? undefined}
      >
        {item.assistant_response ?? '-'}
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

function formatTokens(item: RequestSummary): string {
  const input = item.input_tokens;
  const output = item.output_tokens;
  const cached = item.cached_input_tokens;

  if (input == null && output == null) return item.total_tokens != null ? String(item.total_tokens) : '-';

  let inputPart = '';
  if (input != null) {
    inputPart = cached && cached > 0 ? `i${cached}/${input}` : `i${input}`;
  }

  const outputPart = output != null ? `o${output}` : '';

  return [inputPart, outputPart].filter(Boolean).join(' ');
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
  list: { flex: 1, overflow: 'auto' },
  headerRow: {
    display: 'flex',
    padding: '6px 12px',
    fontSize: '0.75rem',
    color: '#8b949e',
    borderBottom: '1px solid #21262d',
    fontWeight: 600,
    flexShrink: 0,
    gap: 8,
    userSelect: 'none',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 12px',
    cursor: 'pointer',
    width: '100%',
    boxSizing: 'border-box',
    fontSize: '0.85rem',
    color: '#e6edf3',
    gap: 8,
  },
  ellipsis: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
};
