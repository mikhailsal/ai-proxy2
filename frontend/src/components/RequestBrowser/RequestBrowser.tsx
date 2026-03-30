import { useEffect, useState } from 'react';
import { useApi } from '../../hooks/useApi';
import type { RequestSummary } from '../../types';
import { RequestBrowserList } from './RequestBrowserList';
import { RequestBrowserToolbar } from './RequestBrowserToolbar';
import { useRequestBrowserData } from './requestBrowserData';

interface RequestBrowserProps {
  modelFilter: string;
  onModelFilterChange: (value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  onSelect: (req: RequestSummary) => void;
  selectedId?: string;
}

export function RequestBrowser({
  modelFilter,
  onModelFilterChange,
  searchQuery,
  onSearchQueryChange,
  onSelect,
  selectedId,
}: RequestBrowserProps) {
  const api = useApi();
  const [searchText, setSearchText] = useState('');
  const { fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, items } = useRequestBrowserData(
    api,
    searchQuery,
    modelFilter,
  );

  useEffect(() => {
    setSearchText(searchQuery);
  }, [searchQuery]);

  return (
    <div style={styles.container}>
      <RequestBrowserToolbar
        modelFilter={modelFilter}
        onModelFilterChange={onModelFilterChange}
        onSearchQueryChange={onSearchQueryChange}
        searchQuery={searchQuery}
        searchText={searchText}
        setSearchText={setSearchText}
      />

      <div style={styles.header}>
        <span style={{ width: 170 }}>Timestamp</span>
        <span style={{ flex: 1 }}>Model</span>
        <span style={{ width: 60 }}>Status</span>
        <span style={{ width: 80 }}>Latency</span>
        <span style={{ width: 70 }}>Tokens</span>
      </div>
      <RequestBrowserList
        fetchNextPage={fetchNextPage}
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        isLoading={isLoading}
        items={items}
        onSelect={onSelect}
        searchQuery={searchQuery}
        selectedId={selectedId}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' },
  header: { display: 'flex', padding: '6px 12px', fontSize: '0.75rem', color: '#8b949e', borderBottom: '1px solid #21262d', fontWeight: 600, flexShrink: 0 },
};
