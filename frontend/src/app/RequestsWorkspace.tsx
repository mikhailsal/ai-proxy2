import { useCallback, useRef, useState } from 'react';
import { RequestBrowser } from '../components/RequestBrowser/RequestBrowser';
import { RequestDetail } from '../components/RequestDetail/RequestDetail';
import type { RequestSummary } from '../types';
import type { NavigationState } from './navigation';

interface RequestsWorkspaceProps {
  activeRequestSummary: RequestSummary | null;
  navigation: NavigationState;
  onSelectRequestSummary: (request: RequestSummary | null) => void;
  updateNavigation: (
    updater: NavigationState | ((current: NavigationState) => NavigationState),
    mode?: 'push' | 'replace',
  ) => void;
}

export function RequestsWorkspace({
  activeRequestSummary,
  navigation,
  onSelectRequestSummary,
  updateNavigation,
}: RequestsWorkspaceProps) {
  const [splitPercent, setSplitPercent] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);
  const onDividerMouseDown = useDividerDrag(containerRef, setSplitPercent);
  const hasDetail = !!navigation.requestId;

  return (
    <div ref={containerRef} style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ ...styles.pane, flex: hasDetail ? `0 0 ${splitPercent}%` : '1' }}>
        <RequestBrowser
          modelFilter={navigation.requestModelFilter}
          onModelFilterChange={mf => updateNavigation(c => ({ ...c, activeTab: 'requests', requestModelFilter: mf }), 'replace')}
          searchQuery={navigation.requestSearch}
          onSearchQueryChange={sq => updateNavigation(c => ({ ...c, activeTab: 'requests', requestSearch: sq }))}
          onSelect={req => { onSelectRequestSummary(req); updateNavigation(c => ({ ...c, activeTab: 'requests', requestId: req.id })); }}
          selectedId={navigation.requestId ?? undefined}
        />
      </div>
      {hasDetail && (
        <DetailPane
          onDividerMouseDown={onDividerMouseDown}
          requestId={navigation.requestId!}
          requestSummary={activeRequestSummary}
          onClose={() => { onSelectRequestSummary(null); updateNavigation(c => ({ ...c, requestId: null })); }}
        />
      )}
    </div>
  );
}

function useDividerDrag(
  containerRef: React.RefObject<HTMLDivElement | null>,
  setSplitPercent: (v: number) => void,
) {
  return useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const container = containerRef.current;
      if (!container) return;
      const onMove = (ev: MouseEvent) => {
        const rect = container.getBoundingClientRect();
        const pct = ((ev.clientX - rect.left) / rect.width) * 100;
        setSplitPercent(Math.min(Math.max(pct, 15), 85));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [containerRef, setSplitPercent],
  );
}

function DetailPane({ onDividerMouseDown, requestId, requestSummary, onClose }: {
  onDividerMouseDown: (e: React.MouseEvent) => void;
  requestId: string;
  requestSummary: RequestSummary | null;
  onClose: () => void;
}) {
  return (
    <>
      <div onMouseDown={onDividerMouseDown} style={styles.divider}>
        <div style={styles.dividerGrip} />
      </div>
      <div style={{ ...styles.pane, flex: '1' }}>
        <RequestDetail requestId={requestId} requestSummary={requestSummary} onClose={onClose} />
      </div>
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  pane: { display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' },
  divider: {
    width: 6, cursor: 'col-resize', background: '#21262d',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, transition: 'background 0.15s',
  },
  dividerGrip: { width: 2, height: 32, borderRadius: 1, background: '#484f58' },
};
