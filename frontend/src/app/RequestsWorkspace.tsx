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
  return (
    <>
      <div style={{ ...styles.pane, flex: navigation.requestId ? '0 0 50%' : '1' }}>
        <RequestBrowser
          modelFilter={navigation.requestModelFilter}
          onModelFilterChange={modelFilter => {
            updateNavigation(
              current => ({ ...current, activeTab: 'requests', requestModelFilter: modelFilter }),
              'replace',
            );
          }}
          searchQuery={navigation.requestSearch}
          onSearchQueryChange={searchQuery => {
            updateNavigation(current => ({ ...current, activeTab: 'requests', requestSearch: searchQuery }));
          }}
          onSelect={request => {
            onSelectRequestSummary(request);
            updateNavigation(current => ({ ...current, activeTab: 'requests', requestId: request.id }));
          }}
          selectedId={navigation.requestId ?? undefined}
        />
      </div>
      {navigation.requestId && (
        <div style={{ ...styles.pane, flex: '1', borderLeft: '1px solid #21262d' }}>
          <RequestDetail
            requestId={navigation.requestId}
            requestSummary={activeRequestSummary}
            onClose={() => {
              onSelectRequestSummary(null);
              updateNavigation(current => ({ ...current, requestId: null }));
            }}
          />
        </div>
      )}
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  pane: { display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' },
};