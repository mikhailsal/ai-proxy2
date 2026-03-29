import { useState } from 'react';

interface JsonViewerProps {
  data: unknown;
  depth?: number;
}

export function JsonViewer({ data, depth = 0 }: JsonViewerProps) {
  if (data === null || data === undefined) {
    return <span style={{ color: '#6e7681' }}>null</span>;
  }
  if (typeof data === 'boolean') {
    return <span style={{ color: '#79c0ff' }}>{String(data)}</span>;
  }
  if (typeof data === 'number') {
    return <span style={{ color: '#79c0ff' }}>{data}</span>;
  }
  if (typeof data === 'string') {
    return <span style={{ color: '#a5d6ff' }}>"{data}"</span>;
  }
  if (Array.isArray(data)) {
    return <ArrayNode data={data} depth={depth} />;
  }
  if (typeof data === 'object') {
    return <ObjectNode data={data as Record<string, unknown>} depth={depth} />;
  }
  return <span>{String(data)}</span>;
}

function ObjectNode({ data, depth }: { data: Record<string, unknown>; depth: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);
  const keys = Object.keys(data);
  if (keys.length === 0) return <span style={{ color: '#8b949e' }}>{'{}'}</span>;

  return (
    <span>
      <button
        onClick={() => setCollapsed(c => !c)}
        style={collapseBtn}
        title={collapsed ? 'expand' : 'collapse'}
      >
        {collapsed ? '▶' : '▼'}
      </button>
      {collapsed ? (
        <span style={{ color: '#8b949e' }}>{`{ ${keys.length} keys }`}</span>
      ) : (
        <span>
          {'{\n'}
          <span style={{ paddingLeft: '1.2em', display: 'block' }}>
            {keys.map(k => (
              <span key={k} style={{ display: 'block' }}>
                <span style={{ color: '#ff7b72' }}>"{k}"</span>
                <span style={{ color: '#8b949e' }}>: </span>
                <JsonViewer data={data[k]} depth={depth + 1} />
                <span style={{ color: '#8b949e' }}>,</span>
              </span>
            ))}
          </span>
          {'}'}
        </span>
      )}
    </span>
  );
}

function ArrayNode({ data, depth }: { data: unknown[]; depth: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);
  if (data.length === 0) return <span style={{ color: '#8b949e' }}>{'[]'}</span>;

  return (
    <span>
      <button
        onClick={() => setCollapsed(c => !c)}
        style={collapseBtn}
        title={collapsed ? 'expand' : 'collapse'}
      >
        {collapsed ? '▶' : '▼'}
      </button>
      {collapsed ? (
        <span style={{ color: '#8b949e' }}>{`[ ${data.length} items ]`}</span>
      ) : (
        <span>
          {'[\n'}
          <span style={{ paddingLeft: '1.2em', display: 'block' }}>
            {data.map((item, i) => (
              <span key={i} style={{ display: 'block' }}>
                <JsonViewer data={item} depth={depth + 1} />
                {i < data.length - 1 && <span style={{ color: '#8b949e' }}>,</span>}
              </span>
            ))}
          </span>
          {']'}
        </span>
      )}
    </span>
  );
}

const collapseBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#8b949e',
  cursor: 'pointer',
  fontSize: '0.7em',
  padding: '0 2px',
  marginRight: 2,
};
