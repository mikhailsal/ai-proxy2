import { useInfiniteQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useApi } from '../../hooks/useApi';
import type { RequestSummary } from '../../types';

interface RequestBrowserProps {
  onSelect: (req: RequestSummary) => void;
  selectedId?: string;
}

export function RequestBrowser({ onSelect, selectedId }: RequestBrowserProps) {
  const api = useApi();
  const [modelFilter, setModelFilter] = useState('');
  const [searchText, setSearchText] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery({
      queryKey: ['requests', modelFilter],
      queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
        api.listRequests({ cursor: pageParam, limit: 50, model: modelFilter || undefined }),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: last => last.next_cursor ?? undefined,
    });

  const searchQuery2 = useInfiniteQuery({
    queryKey: ['search', searchQuery],
    queryFn: () => api.searchRequests(searchQuery),
    initialPageParam: undefined,
    getNextPageParam: () => undefined,
    enabled: searchQuery.length > 0,
  });

  const items: RequestSummary[] = searchQuery
    ? (searchQuery2.data?.pages.flatMap(p => p.items) ?? [])
    : (data?.pages.flatMap(p => p.items) ?? []);

  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: items.length + (hasNextPage && !searchQuery ? 1 : 0),
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  // Load more when last virtual item is the sentinel
  const lastItem = virtualItems[virtualItems.length - 1];
  if (lastItem && lastItem.index >= items.length && hasNextPage && !isFetchingNextPage) {
    void fetchNextPage();
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearchQuery(searchText.trim());
  }

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <form onSubmit={handleSearch} style={styles.searchForm}>
          <input
            style={styles.searchInput}
            type="text"
            placeholder="Search requests…"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <button style={styles.searchBtn} type="submit">Search</button>
          {searchQuery && (
            <button style={styles.clearBtn} type="button" onClick={() => { setSearchText(''); setSearchQuery(''); }}>
              ✕
            </button>
          )}
        </form>
        <input
          style={{ ...styles.searchInput, width: 160 }}
          type="text"
          placeholder="Filter by model…"
          value={modelFilter}
          onChange={e => setModelFilter(e.target.value)}
        />
      </div>

      <div style={styles.header}>
        <span style={{ width: 170 }}>Timestamp</span>
        <span style={{ flex: 1 }}>Model</span>
        <span style={{ width: 60 }}>Status</span>
        <span style={{ width: 80 }}>Latency</span>
        <span style={{ width: 70 }}>Tokens</span>
      </div>

      {isLoading ? (
        <div style={styles.loading}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={styles.loading}>No requests found.</div>
      ) : (
        <div ref={parentRef} style={styles.list}>
          <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
            {virtualItems.map(virtualRow => {
              const item = items[virtualRow.index];
              if (!item) {
                return (
                  <div
                    key="sentinel"
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
              const isSelected = item.id === selectedId;
              return (
                <div
                  key={item.id}
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
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.model_requested ?? '-'}
                  </span>
                  <span style={{ width: 60, color: statusColor(item.response_status_code) }}>
                    {item.response_status_code ?? '-'}
                  </span>
                  <span style={{ width: 80, color: '#8b949e' }}>
                    {item.latency_ms != null ? `${Math.round(item.latency_ms)}ms` : '-'}
                  </span>
                  <span style={{ width: 70, color: '#8b949e' }}>
                    {item.total_tokens ?? '-'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
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
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' },
  toolbar: { display: 'flex', gap: 8, padding: '8px 12px', borderBottom: '1px solid #21262d', flexShrink: 0 },
  searchForm: { display: 'flex', gap: 4, flex: 1 },
  searchInput: { background: '#0d1117', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '4px 8px', fontSize: '0.85rem', flex: 1, outline: 'none' },
  searchBtn: { background: '#21262d', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '4px 8px', cursor: 'pointer', fontSize: '0.85rem' },
  clearBtn: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', padding: '0 4px' },
  header: { display: 'flex', padding: '6px 12px', fontSize: '0.75rem', color: '#8b949e', borderBottom: '1px solid #21262d', fontWeight: 600, flexShrink: 0 },
  list: { flex: 1, overflow: 'auto' },
  row: { display: 'flex', alignItems: 'center', padding: '0 12px', cursor: 'pointer', width: '100%', boxSizing: 'border-box', fontSize: '0.85rem', color: '#e6edf3', gap: 8 },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
};
