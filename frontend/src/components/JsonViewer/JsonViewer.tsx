import { useState } from 'react';

interface JsonViewerProps {
  data: unknown;
  depth?: number;
  path?: string[];
  collapsedPaths?: string[];
  expandedPaths?: string[];
}

function isExpanded(pathKey: string, expandedPaths: string[]): boolean {
  return expandedPaths.some(ep => pathKey === ep || pathKey.startsWith(ep + '.'));
}

export function JsonViewer({ data, depth = 0, path = [], collapsedPaths = [], expandedPaths = [] }: JsonViewerProps) {
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
    return <ArrayNode data={data} depth={depth} path={path} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} />;
  }
  if (typeof data === 'object') {
    return <ObjectNode data={data as Record<string, unknown>} depth={depth} path={path} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} />;
  }
  return <span>{String(data)}</span>;
}

function ObjectNode({
  data,
  depth,
  path,
  collapsedPaths,
  expandedPaths,
}: {
  data: Record<string, unknown>;
  depth: number;
  path: string[];
  collapsedPaths: string[];
  expandedPaths: string[];
}) {
  const pathKey = path.join('.');
  const [collapsed, setCollapsed] = useState(
    isExpanded(pathKey, expandedPaths) ? false : depth > 2 || collapsedPaths.includes(pathKey),
  );
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
                <JsonViewer
                  data={data[k]}
                  depth={depth + 1}
                  path={[...path, k]}
                  collapsedPaths={collapsedPaths}
                  expandedPaths={expandedPaths}
                />
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

function ArrayNode({
  data,
  depth,
  path,
  collapsedPaths,
  expandedPaths,
}: {
  data: unknown[];
  depth: number;
  path: string[];
  collapsedPaths: string[];
  expandedPaths: string[];
}) {
  const pathKey = path.join('.');
  const [collapsed, setCollapsed] = useState(
    isExpanded(pathKey, expandedPaths) ? false : depth > 2 || collapsedPaths.includes(pathKey),
  );
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
                <JsonViewer
                  data={item}
                  depth={depth + 1}
                  path={[...path, String(i)]}
                  collapsedPaths={collapsedPaths}
                  expandedPaths={expandedPaths}
                />
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
