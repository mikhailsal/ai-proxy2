interface RequestBrowserToolbarProps {
  modelFilter: string;
  onModelFilterChange: (value: string) => void;
  onSearchQueryChange: (value: string) => void;
  searchQuery: string;
  searchText: string;
  setSearchText: (value: string) => void;
}

export function RequestBrowserToolbar({
  modelFilter,
  onModelFilterChange,
  onSearchQueryChange,
  searchQuery,
  searchText,
  setSearchText,
}: RequestBrowserToolbarProps) {
  function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    onSearchQueryChange(searchText.trim());
  }

  return (
    <div style={styles.toolbar}>
      <form onSubmit={handleSearch} style={styles.searchForm}>
        <input
          style={styles.searchInput}
          type="text"
          placeholder="Search requests…"
          value={searchText}
          onChange={event => setSearchText(event.target.value)}
        />
        <button style={styles.searchBtn} type="submit">Search</button>
        {searchQuery && (
          <button
            style={styles.clearBtn}
            type="button"
            onClick={() => {
              setSearchText('');
              onSearchQueryChange('');
            }}
          >
            ✕
          </button>
        )}
      </form>
      <input
        style={{ ...styles.searchInput, width: 160 }}
        type="text"
        placeholder="Filter by model…"
        value={modelFilter}
        onChange={event => onModelFilterChange(event.target.value)}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  toolbar: { display: 'flex', gap: 8, padding: '8px 12px', borderBottom: '1px solid #21262d', flexShrink: 0 },
  searchForm: { display: 'flex', gap: 4, flex: 1 },
  searchInput: { background: '#0d1117', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '4px 8px', fontSize: '0.85rem', flex: 1, outline: 'none' },
  searchBtn: { background: '#21262d', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '4px 8px', cursor: 'pointer', fontSize: '0.85rem' },
  clearBtn: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', padding: '0 4px' },
};