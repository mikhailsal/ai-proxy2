import { useState } from 'react';

export interface HighlightRule {
  path: string;
  background?: string;
  label?: string;
}

interface JsonViewerProps {
  data: unknown;
  depth?: number;
  path?: string[];
  collapsedPaths?: string[];
  expandedPaths?: string[];
  highlightRules?: HighlightRule[];
}

function isExpanded(pathKey: string, expandedPaths: string[]): boolean {
  return expandedPaths.some(ep => pathKey === ep || pathKey.startsWith(ep + '.'));
}

function findHighlight(pathKey: string, rules: HighlightRule[]): HighlightRule | null {
  for (const rule of rules) {
    if (pathKey === rule.path) return rule;
  }
  return null;
}

export function JsonViewer({ data, depth = 0, path = [], collapsedPaths = [], expandedPaths = [], highlightRules = [] }: JsonViewerProps) {
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
    return <ArrayNode data={data} depth={depth} path={path} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} />;
  }
  if (typeof data === 'object') {
    return <ObjectNode data={data as Record<string, unknown>} depth={depth} path={path} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} />;
  }
  return <span>{String(data)}</span>;
}

interface CollapsibleShellProps {
  highlight: HighlightRule | null;
  collapsed: boolean;
  onToggle: () => void;
  collapsedSummary: string;
  children: React.ReactNode;
}

function CollapsibleShell({ highlight, collapsed, onToggle, collapsedSummary, children }: CollapsibleShellProps) {
  const wrapStyle: React.CSSProperties | undefined = highlight?.background
    ? { background: highlight.background, borderRadius: 4, padding: '2px 4px', display: 'inline' }
    : undefined;

  return (
    <span style={wrapStyle}>
      {highlight?.label && collapsed ? <span style={labelStyle}>{highlight.label}</span> : null}
      <button onClick={onToggle} style={collapseBtn} title={collapsed ? 'expand' : 'collapse'}>
        {collapsed ? '▶' : '▼'}
      </button>
      {collapsed ? (
        <span style={{ color: '#8b949e' }}>{collapsedSummary}</span>
      ) : (
        <span>
          {highlight?.label ? <span style={labelStyle}>{highlight.label}</span> : null}
          {children}
        </span>
      )}
    </span>
  );
}

interface NodeProps {
  depth: number;
  path: string[];
  collapsedPaths: string[];
  expandedPaths: string[];
  highlightRules: HighlightRule[];
}

function ObjectNode({ data, depth, path, collapsedPaths, expandedPaths, highlightRules }: NodeProps & { data: Record<string, unknown> }) {
  const pathKey = path.join('.');
  const highlight = findHighlight(pathKey, highlightRules);
  const [collapsed, setCollapsed] = useState(
    isExpanded(pathKey, expandedPaths) ? false : depth > 2 || collapsedPaths.includes(pathKey),
  );
  const keys = Object.keys(data);
  if (keys.length === 0) return <span style={{ color: '#8b949e' }}>{'{}'}</span>;

  return (
    <CollapsibleShell highlight={highlight} collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} collapsedSummary={`{ ${keys.length} keys }`}>
      {'{\n'}
      <span style={{ paddingLeft: '1.2em', display: 'block' }}>
        {keys.map(k => (
          <span key={k} style={{ display: 'block' }}>
            <span style={{ color: '#ff7b72' }}>"{k}"</span>
            <span style={{ color: '#8b949e' }}>: </span>
            <JsonViewer data={data[k]} depth={depth + 1} path={[...path, k]} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} />
            <span style={{ color: '#8b949e' }}>,</span>
          </span>
        ))}
      </span>
      {'}'}
    </CollapsibleShell>
  );
}

function ArrayNode({ data, depth, path, collapsedPaths, expandedPaths, highlightRules }: NodeProps & { data: unknown[] }) {
  const pathKey = path.join('.');
  const highlight = findHighlight(pathKey, highlightRules);
  const [collapsed, setCollapsed] = useState(
    isExpanded(pathKey, expandedPaths) ? false : depth > 2 || collapsedPaths.includes(pathKey),
  );
  if (data.length === 0) return <span style={{ color: '#8b949e' }}>{'[]'}</span>;

  return (
    <CollapsibleShell highlight={highlight} collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} collapsedSummary={`[ ${data.length} items ]`}>
      {'[\n'}
      <span style={{ paddingLeft: '1.2em', display: 'block' }}>
        {data.map((item, i) => (
          <span key={i} style={{ display: 'block' }}>
            <JsonViewer data={item} depth={depth + 1} path={[...path, String(i)]} collapsedPaths={collapsedPaths} expandedPaths={expandedPaths} highlightRules={highlightRules} />
            {i < data.length - 1 && <span style={{ color: '#8b949e' }}>,</span>}
          </span>
        ))}
      </span>
      {']'}
    </CollapsibleShell>
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

const labelStyle: React.CSSProperties = {
  fontSize: '0.7em',
  fontWeight: 500,
  marginRight: 4,
  verticalAlign: 'middle',
  color: '#8b949e',
};
