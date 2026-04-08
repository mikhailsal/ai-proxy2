import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import type { ProxyModel } from '../types';
import {
  formatList,
  type SortKey,
  type SortDir,
  formatPricePerMillion,
  formatContextLength,
  formatCreated,
  getInputModalities,
  getInputPrice,
  getOutputPrice,
  getOutputModalities,
  getPinnedProviders,
  getSupportedParameters,
  getTokenizer,
  modelMatchesSearch,
  sortModels,
} from './modelsUtils';

export function ModelsWorkspace() {
  const api = useApi();
  const [models, setModels] = useState<ProxyModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('id');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    api
      .listModels()
      .then(page => {
        setModels(page.data);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      });
  }, [api]);

  const filtered = useMemo(
    () => sortModels(models.filter(m => modelMatchesSearch(m, search)), sortKey, sortDir),
    [models, search, sortKey, sortDir],
  );

  function handleSortClick(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  return (
    <div style={styles.container}>
      <ModelsToolbar
        search={search}
        onSearchChange={setSearch}
        count={filtered.length}
        total={models.length}
        isLoading={isLoading}
      />
      {error && <div style={styles.error}>Error: {error}</div>}
      <ModelsTable
        filtered={filtered}
        isLoading={isLoading}
        search={search}
        sortKey={sortKey}
        sortDir={sortDir}
        onSortClick={handleSortClick}
      />
    </div>
  );
}

function ModelsToolbar({
  search,
  onSearchChange,
  count,
  total,
  isLoading,
}: {
  search: string;
  onSearchChange: (v: string) => void;
  count: number;
  total: number;
  isLoading: boolean;
}) {
  return (
    <div style={styles.toolbar}>
      <input
        style={styles.searchInput}
        type="text"
        placeholder="Search models…"
        value={search}
        onChange={e => onSearchChange(e.target.value)}
        autoFocus
      />
      {search && (
        <button style={styles.clearBtn} onClick={() => onSearchChange('')} type="button">
          ✕
        </button>
      )}
      <span style={styles.count}>
        {isLoading ? 'Loading…' : `${count} / ${total} models`}
      </span>
    </div>
  );
}

function ModelsTable({
  filtered,
  isLoading,
  search,
  sortKey,
  sortDir,
  onSortClick,
}: {
  filtered: ProxyModel[];
  isLoading: boolean;
  search: string;
  sortKey: SortKey;
  sortDir: SortDir;
  onSortClick: (key: SortKey) => void;
}) {
  return (
    <div style={styles.tableWrapper}>
      <table style={styles.table}>
        <thead>
          <tr>
            <SortHeader label="Model ID" sortKey="id" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <SortHeader label="Provider" sortKey="provider" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <th style={styles.th}>Mapped To</th>
            <SortHeader label="Context" sortKey="context_length" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <SortHeader label="Input $/1M" sortKey="input_price" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <SortHeader label="Output $/1M" sortKey="output_price" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <SortHeader label="Released" sortKey="created" current={sortKey} dir={sortDir} onClick={onSortClick} />
            <th style={styles.th}>Input Modalities</th>
            <th style={styles.th}>Output Modalities</th>
            <th style={styles.th}>Tokenizer</th>
            <th style={styles.th}>Supported Parameters</th>
            <th style={styles.th}>Pinned Providers</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(model => (
            <ModelRow key={model.id} model={model} />
          ))}
          {!isLoading && filtered.length === 0 && (
            <tr>
              <td colSpan={12} style={styles.empty}>
                {search ? 'No models match your search.' : 'No models available.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  current,
  dir,
  onClick,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: SortDir;
  onClick: (key: SortKey) => void;
}) {
  const isActive = current === sortKey;
  return (
    <th style={{ ...styles.th, ...styles.thSortable }} onClick={() => onClick(sortKey)}>
      {label}
      <span style={{ ...styles.sortIcon, opacity: isActive ? 1 : 0.3 }}>
        {isActive && dir === 'desc' ? ' ▼' : ' ▲'}
      </span>
    </th>
  );
}

function ModelRow({ model }: { model: ProxyModel }) {
  const inputPrice = getInputPrice(model);
  const outputPrice = getOutputPrice(model);
  const mappedDiffers = model.mapped_model !== model.id;

  return (
    <tr style={styles.row}>
      <td style={styles.tdId}>
        <span style={styles.modelId} title={model.description ?? model.id}>
          {model.id}
        </span>
        {model.name && model.name !== model.id && (
          <span style={styles.modelName}>{model.name}</span>
        )}
      </td>
      <td style={styles.td}>
        <span style={styles.badge}>{model.provider}</span>
      </td>
      <td style={styles.tdMapped}>
        {mappedDiffers ? (
          <span style={styles.mappedModel} title={model.mapped_model}>
            {model.mapped_model}
          </span>
        ) : (
          <span style={styles.same}>same</span>
        )}
      </td>
      <td style={styles.tdNum}>{formatContextLength(model.context_length)}</td>
      <td style={{ ...styles.tdNum, color: inputPrice !== null ? '#58a6ff' : '#8b949e' }}>
        {formatPricePerMillion(inputPrice)}
      </td>
      <td style={{ ...styles.tdNum, color: outputPrice !== null ? '#58a6ff' : '#8b949e' }}>
        {formatPricePerMillion(outputPrice)}
      </td>
      <td style={{ ...styles.tdNum, color: model.created ? '#e6edf3' : '#8b949e' }}>
        {formatCreated(model.created)}
      </td>
      <ModelMetadataCells model={model} />
    </tr>
  );
}

function ModelMetadataCells({ model }: { model: ProxyModel }) {
  const columns = [
    { value: formatList(getInputModalities(model)) },
    { value: formatList(getOutputModalities(model)) },
    { value: getTokenizer(model) ?? '—', monospace: true },
    { value: formatList(getSupportedParameters(model)), monospace: true, wide: true },
    { value: formatList(getPinnedProviders(model)), monospace: true },
  ];

  return (
    <>
      {columns.map((column, index) => (
        <td key={`${index}-${column.value}-${column.wide ? 'wide' : 'base'}`} style={column.wide ? styles.tdMetaWide : styles.tdMeta}>
          <MetadataValue value={column.value} monospace={column.monospace} />
        </td>
      ))}
    </>
  );
}

function MetadataValue({ value, monospace = false }: { value: string; monospace?: boolean }) {
  const empty = value === '—';
  return (
    <span
      style={{
        ...styles.metadataValue,
        ...(monospace ? styles.metadataMono : {}),
        color: empty ? '#8b949e' : '#e6edf3',
      }}
      title={empty ? undefined : value}
    >
      {value}
    </span>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flex: 1, flexDirection: 'column', height: '100%', minWidth: 0, overflow: 'hidden' },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    borderBottom: '1px solid #21262d',
    flexShrink: 0,
    background: '#161b22',
  },
  searchInput: {
    background: '#0d1117',
    border: '1px solid #30363d',
    borderRadius: 4,
    color: '#e6edf3',
    padding: '4px 8px',
    fontSize: '0.85rem',
    width: 300,
    outline: 'none',
  },
  clearBtn: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', padding: '0 4px', fontSize: '0.9rem' },
  count: { marginLeft: 'auto', color: '#8b949e', fontSize: '0.8rem' },
  error: { padding: 12, color: '#f85149', background: '#161b22', flexShrink: 0 },
  tableWrapper: { flex: 1, minWidth: 0, overflow: 'auto' },
  table: { width: 'max-content', minWidth: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' },
  th: {
    padding: '8px 12px',
    textAlign: 'left',
    color: '#8b949e',
    borderBottom: '1px solid #21262d',
    background: '#161b22',
    position: 'sticky',
    top: 0,
    zIndex: 1,
    whiteSpace: 'nowrap',
    fontWeight: 600,
  },
  thSortable: { cursor: 'pointer', userSelect: 'none' },
  sortIcon: { fontSize: '0.7rem' },
  row: { borderBottom: '1px solid #161b22' },
  td: { padding: '7px 12px', color: '#e6edf3', verticalAlign: 'middle' },
  tdId: { padding: '7px 12px', verticalAlign: 'middle', maxWidth: 340 },
  tdNum: { padding: '7px 12px', color: '#e6edf3', verticalAlign: 'middle', textAlign: 'right', whiteSpace: 'nowrap' },
  tdMapped: { padding: '7px 12px', verticalAlign: 'middle', maxWidth: 280 },
  tdMeta: { padding: '7px 12px', verticalAlign: 'top', minWidth: 150, maxWidth: 220 },
  tdMetaWide: { padding: '7px 12px', verticalAlign: 'top', minWidth: 220, maxWidth: 320 },
  modelId: {
    display: 'block',
    color: '#e6edf3',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  modelName: {
    display: 'block',
    color: '#8b949e',
    fontSize: '0.75rem',
    marginTop: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  badge: {
    background: '#21262d',
    border: '1px solid #30363d',
    borderRadius: 4,
    color: '#79c0ff',
    padding: '1px 6px',
    fontSize: '0.75rem',
    fontFamily: 'monospace',
    whiteSpace: 'nowrap',
  },
  mappedModel: {
    color: '#8b949e',
    fontFamily: 'monospace',
    fontSize: '0.78rem',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    display: 'block',
  },
  metadataValue: {
    display: 'block',
    fontSize: '0.75rem',
    lineHeight: 1.45,
    whiteSpace: 'normal',
    overflowWrap: 'anywhere',
  },
  metadataMono: {
    fontFamily: 'monospace',
  },
  same: { color: '#30363d', fontStyle: 'italic', fontSize: '0.75rem' },
  empty: { padding: 32, textAlign: 'center', color: '#8b949e' },
};
