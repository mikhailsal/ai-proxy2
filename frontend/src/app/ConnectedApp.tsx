import { ChatWorkspace } from './ChatWorkspace';
import { ModelsWorkspace } from './ModelsWorkspace';
import { RequestsWorkspace } from './RequestsWorkspace';
import { AppIcon } from '../components/common/AppIcon';
import { StatsBar } from '../components/common/StatsBar';
import { useNavigationState } from './useNavigationState';

interface ConnectedAppProps {
  onDisconnect: () => void;
}

export function ConnectedApp({ onDisconnect }: ConnectedAppProps) {
  const {
    activeRequestSummary,
    navigation,
    setSelectedRequestSummary,
    updateNavigation,
  } = useNavigationState();

  return (
    <div style={styles.app}>
      <NavigationBar
        activeTab={navigation.activeTab}
        onDisconnect={onDisconnect}
        onSelectTab={activeTab => updateNavigation(current => ({ ...current, activeTab }))}
      />
      <StatsBar />
      <div style={styles.main}>
        {navigation.activeTab === 'requests' ? (
          <RequestsWorkspace
            activeRequestSummary={activeRequestSummary}
            navigation={navigation}
            onSelectRequestSummary={setSelectedRequestSummary}
            updateNavigation={updateNavigation}
          />
        ) : navigation.activeTab === 'models' ? (
          <ModelsWorkspace />
        ) : (
          <ChatWorkspace navigation={navigation} updateNavigation={updateNavigation} />
        )}
      </div>
    </div>
  );
}

interface NavigationBarProps {
  activeTab: 'requests' | 'chat' | 'models';
  onDisconnect: () => void;
  onSelectTab: (tab: 'requests' | 'chat' | 'models') => void;
}

function NavigationBar({ activeTab, onDisconnect, onSelectTab }: NavigationBarProps) {
  return (
    <div style={styles.nav}>
      <AppIcon size={22} />
      <span style={styles.navTitle}>AI Proxy v2</span>
      <button
        style={{ ...styles.navTab, ...(activeTab === 'requests' ? styles.navTabActive : {}) }}
        onClick={() => onSelectTab('requests')}
      >
        Requests
      </button>
      <button
        style={{ ...styles.navTab, ...(activeTab === 'chat' ? styles.navTabActive : {}) }}
        onClick={() => onSelectTab('chat')}
      >
        Chat
      </button>
      <button
        style={{ ...styles.navTab, ...(activeTab === 'models' ? styles.navTabActive : {}) }}
        onClick={() => onSelectTab('models')}
      >
        Models
      </button>
      <div style={{ flex: 1 }} />
      <button onClick={onDisconnect} style={styles.disconnectBtn}>
        Disconnect
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: { height: '100vh', display: 'flex', flexDirection: 'column', background: '#0d1117' },
  nav: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid #21262d', background: '#161b22', flexShrink: 0 },
  navTitle: { fontSize: '0.95rem', fontWeight: 700, color: '#e6edf3' },
  navTab: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', padding: '6px 8px', fontSize: '0.85rem', borderBottom: '2px solid transparent' },
  navTabActive: { color: '#e6edf3', borderBottomColor: '#58a6ff' },
  disconnectBtn: { background: 'none', border: '1px solid #30363d', borderRadius: 6, color: '#8b949e', cursor: 'pointer', padding: '4px 8px', fontSize: '0.8rem' },
  main: { display: 'flex', flex: 1, minHeight: 0 },
};