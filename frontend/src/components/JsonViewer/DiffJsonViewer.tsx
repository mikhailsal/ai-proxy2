import { useState } from 'react';

interface DiffJsonViewerProps {
  left: unknown;
  right: unknown;
  depth?: number;
}

export function DiffJsonViewer({ left, right, depth = 0 }: DiffJsonViewerProps) {
  if (left === right) {
    return <PlainValue value={right} depth={depth} />;
  }

  if (left === undefined || left === null) {
    return <Added value={right} depth={depth} />;
  }
  if (right === undefined || right === null) {
    return <Removed value={left} depth={depth} />;
  }

  const leftIsObj = isPlainObject(left);
  const rightIsObj = isPlainObject(right);
  if (leftIsObj && rightIsObj) {
    return <DiffObjectNode left={left as Obj} right={right as Obj} depth={depth} />;
  }

  const leftIsArr = Array.isArray(left);
  const rightIsArr = Array.isArray(right);
  if (leftIsArr && rightIsArr) {
    return <DiffArrayNode left={left} right={right} depth={depth} />;
  }

  return <ChangedValue left={left} right={right} />;
}

type Obj = Record<string, unknown>;

function DiffObjectNode({ left, right, depth }: { left: Obj; right: Obj; depth: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);
  const allKeys = Array.from(new Set([...Object.keys(left), ...Object.keys(right)]));

  if (allKeys.length === 0) return <span style={{ color: '#8b949e' }}>{'{}'}</span>;

  const hasChanges = allKeys.some(k => !deepEqual(left[k], right[k]));

  return (
    <span>
      <button onClick={() => setCollapsed(c => !c)} style={collapseBtn} title={collapsed ? 'expand' : 'collapse'}>
        {collapsed ? '▶' : '▼'}
      </button>
      {collapsed ? (
        <span style={{ color: '#8b949e' }}>
          {`{ ${allKeys.length} keys }`}
          {hasChanges && <span style={diffIndicator}> (changed)</span>}
        </span>
      ) : (
        <span>
          {'{\n'}
          <span style={{ paddingLeft: '1.2em', display: 'block' }}>
            {allKeys.map(k => {
              const inLeft = k in left;
              const inRight = k in right;

              if (!inLeft) {
                return (
                  <span key={k} style={{ display: 'block', ...addedBg }}>
                    <span style={{ color: '#ff7b72' }}>"{k}"</span>
                    <span style={{ color: '#8b949e' }}>: </span>
                    <PlainValue value={right[k]} depth={depth + 1} />
                    <span style={{ color: '#8b949e' }}>,</span>
                  </span>
                );
              }
              if (!inRight) {
                return (
                  <span key={k} style={{ display: 'block', ...removedBg }}>
                    <span style={{ color: '#ff7b72' }}>"{k}"</span>
                    <span style={{ color: '#8b949e' }}>: </span>
                    <PlainValue value={left[k]} depth={depth + 1} />
                    <span style={{ color: '#8b949e' }}>,</span>
                  </span>
                );
              }

              return (
                <span key={k} style={{ display: 'block' }}>
                  <span style={{ color: '#ff7b72' }}>"{k}"</span>
                  <span style={{ color: '#8b949e' }}>: </span>
                  <DiffJsonViewer left={left[k]} right={right[k]} depth={depth + 1} />
                  <span style={{ color: '#8b949e' }}>,</span>
                </span>
              );
            })}
          </span>
          {'}'}
        </span>
      )}
    </span>
  );
}

function DiffArrayNode({ left, right, depth }: { left: unknown[]; right: unknown[]; depth: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);
  const maxLen = Math.max(left.length, right.length);

  if (maxLen === 0) return <span style={{ color: '#8b949e' }}>{'[]'}</span>;

  const hasChanges = left.length !== right.length || left.some((v, i) => !deepEqual(v, right[i]));

  return (
    <span>
      <button onClick={() => setCollapsed(c => !c)} style={collapseBtn} title={collapsed ? 'expand' : 'collapse'}>
        {collapsed ? '▶' : '▼'}
      </button>
      {collapsed ? (
        <span style={{ color: '#8b949e' }}>
          {`[ ${right.length} items ]`}
          {hasChanges && <span style={diffIndicator}> (changed)</span>}
        </span>
      ) : (
        <span>
          {'[\n'}
          <span style={{ paddingLeft: '1.2em', display: 'block' }}>
            {Array.from({ length: maxLen }, (_, i) => {
              const inLeft = i < left.length;
              const inRight = i < right.length;

              if (!inLeft) {
                return (
                  <span key={i} style={{ display: 'block', ...addedBg }}>
                    <PlainValue value={right[i]} depth={depth + 1} />
                    {i < maxLen - 1 && <span style={{ color: '#8b949e' }}>,</span>}
                  </span>
                );
              }
              if (!inRight) {
                return (
                  <span key={i} style={{ display: 'block', ...removedBg }}>
                    <PlainValue value={left[i]} depth={depth + 1} />
                    {i < maxLen - 1 && <span style={{ color: '#8b949e' }}>,</span>}
                  </span>
                );
              }

              return (
                <span key={i} style={{ display: 'block' }}>
                  <DiffJsonViewer left={left[i]} right={right[i]} depth={depth + 1} />
                  {i < maxLen - 1 && <span style={{ color: '#8b949e' }}>,</span>}
                </span>
              );
            })}
          </span>
          {']'}
        </span>
      )}
    </span>
  );
}

function PlainValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) return <span style={{ color: '#6e7681' }}>null</span>;
  if (typeof value === 'boolean') return <span style={{ color: '#79c0ff' }}>{String(value)}</span>;
  if (typeof value === 'number') return <span style={{ color: '#79c0ff' }}>{value}</span>;
  if (typeof value === 'string') return <span style={{ color: '#a5d6ff' }}>"{value}"</span>;
  if (Array.isArray(value)) return <CollapsiblePlainArray data={value} depth={depth} />;
  if (isPlainObject(value)) return <CollapsiblePlainObject data={value as Obj} depth={depth} />;
  return <span>{String(value)}</span>;
}

function CollapsiblePlainObject({ data, depth }: { data: Obj; depth: number }) {
  const keys = Object.keys(data);
  const [collapsed, setCollapsed] = useState(depth > 2);
  if (keys.length === 0) return <span style={{ color: '#8b949e' }}>{'{}'}</span>;
  return (
    <span>
      <button onClick={() => setCollapsed(c => !c)} style={collapseBtn} title={collapsed ? 'expand' : 'collapse'}>
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
                <PlainValue value={data[k]} depth={depth + 1} />
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

function CollapsiblePlainArray({ data, depth }: { data: unknown[]; depth: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);
  if (data.length === 0) return <span style={{ color: '#8b949e' }}>{'[]'}</span>;
  return (
    <span>
      <button onClick={() => setCollapsed(c => !c)} style={collapseBtn} title={collapsed ? 'expand' : 'collapse'}>
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
                <PlainValue value={item} depth={depth + 1} />
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

function Added({ value, depth }: { value: unknown; depth: number }) {
  return (
    <span style={addedBg}>
      <PlainValue value={value} depth={depth} />
    </span>
  );
}

function Removed({ value, depth }: { value: unknown; depth: number }) {
  return (
    <span style={removedBg}>
      <PlainValue value={value} depth={depth} />
    </span>
  );
}

function ChangedValue({ left, right }: { left: unknown; right: unknown }) {
  return (
    <span>
      <span style={removedInline}>{formatPrimitive(left)}</span>
      <span style={{ color: '#8b949e' }}>{' → '}</span>
      <span style={addedInline}>{formatPrimitive(right)}</span>
    </span>
  );
}

function formatPrimitive(v: unknown): string {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'string') return `"${v}"`;
  return String(v);
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return false;

  if (Array.isArray(a)) {
    if (!Array.isArray(b)) return false;
    if (a.length !== b.length) return false;
    return a.every((v, i) => deepEqual(v, b[i]));
  }

  const aObj = a as Obj;
  const bObj = b as Obj;
  const aKeys = Object.keys(aObj);
  const bKeys = Object.keys(bObj);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every(k => k in bObj && deepEqual(aObj[k], bObj[k]));
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

const addedBg: React.CSSProperties = {
  backgroundColor: 'rgba(63, 185, 80, 0.15)',
  borderRadius: 2,
};

const removedBg: React.CSSProperties = {
  backgroundColor: 'rgba(248, 81, 73, 0.15)',
  textDecoration: 'line-through',
  borderRadius: 2,
};

const addedInline: React.CSSProperties = {
  backgroundColor: 'rgba(63, 185, 80, 0.25)',
  borderRadius: 2,
  padding: '0 2px',
};

const removedInline: React.CSSProperties = {
  backgroundColor: 'rgba(248, 81, 73, 0.25)',
  textDecoration: 'line-through',
  borderRadius: 2,
  padding: '0 2px',
};

const diffIndicator: React.CSSProperties = {
  color: '#d29922',
  fontSize: '0.85em',
  fontStyle: 'italic',
};
