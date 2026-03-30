import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { RequestSummary } from '../../types';

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
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: items.length + (hasNextPage && !searchQuery ? 1 : 0),
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 10,
  });

  loadNextPage(rowVirtualizer.getVirtualItems(), items.length, hasNextPage, isFetchingNextPage, fetchNextPage);

  if (isLoading) {
    return <div style={styles.loading}>Loading…</div>;
  }

  if (items.length === 0) {
    return <div style={styles.loading}>No requests found.</div>;
  }

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

function loadNextPage(
  virtualItems: Array<{ index: number }> ,
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
  item,
  isSelected,
  onSelect,
  virtualRow,
}: {
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
      <span style={{ width: 170, color: '#8b949e', fontSize: '0.78rem' }}>
        {new Date(item.timestamp).toLocaleString()}
      </span>
      <span style={styles.model}>{item.model_requested ?? '-'}</span>
      <span style={{ width: 60, color: statusColor(item.response_status_code) }}>
        {item.response_status_code ?? '-'}
      </span>
      <span style={{ width: 80, color: '#8b949e' }}>
        {item.latency_ms != null ? `${Math.round(item.latency_ms)}ms` : '-'}
      </span>
      <span style={{ width: 70, color: '#8b949e' }}>{item.total_tokens ?? '-'}</span>
    </div>
  );
}

function statusColor(code: number | null): string {
  if (!code) return '#8b949e';
  if (code < 300) return '#3fb950';
  if (code < 400) return '#d29922';
  return '#f85149';
}

const styles: Record<string, React.CSSProperties> = {
  list: { flex: 1, overflow: 'auto' },
  row: { display: 'flex', alignItems: 'center', padding: '0 12px', cursor: 'pointer', width: '100%', boxSizing: 'border-box', fontSize: '0.85rem', color: '#e6edf3', gap: 8 },
  model: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
};