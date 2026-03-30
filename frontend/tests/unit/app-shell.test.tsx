import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { NavigationState } from '../../src/app/navigation';

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  vi.doUnmock('../../src/app/RequestsWorkspace');
  vi.doUnmock('../../src/app/ChatWorkspace');
  vi.doUnmock('../../src/components/RequestBrowser/RequestBrowser');
  vi.doUnmock('../../src/components/RequestDetail/RequestDetail');
  vi.doUnmock('../../src/components/ChatView/ChatView');
  vi.doUnmock('../../src/components/common/StatsBar');
  vi.doUnmock('../../src/app/useNavigationState');
  document.body.innerHTML = '';
});

describe('ConnectedApp and workspaces', () => {
  it('routes tab changes and disconnect actions through ConnectedApp', async () => {
    const onDisconnect = vi.fn();
    const updateNavigation = vi.fn();

    vi.doMock('../../src/app/useNavigationState', () => ({
      useNavigationState: () => ({
        activeRequestSummary: null,
        navigation: { activeTab: 'requests' } as NavigationState,
        setSelectedRequestSummary: vi.fn(),
        updateNavigation,
      }),
    }));
    vi.doMock('../../src/components/common/StatsBar', () => ({ StatsBar: () => <div>stats</div> }));
    vi.doMock('../../src/app/RequestsWorkspace', () => ({ RequestsWorkspace: () => <div>requests workspace</div> }));
    vi.doMock('../../src/app/ChatWorkspace', () => ({ ChatWorkspace: () => <div>chat workspace</div> }));

    const { ConnectedApp } = await import('../../src/app/ConnectedApp');
    render(<ConnectedApp onDisconnect={onDisconnect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Chat' }));
    await userEvent.click(screen.getByRole('button', { name: 'Disconnect' }));

    expect(screen.getByText('requests workspace')).toBeInTheDocument();
    expect(updateNavigation).toHaveBeenCalled();
    expect(onDisconnect).toHaveBeenCalled();
  });

  it('renders the chat workspace when chat is active', async () => {
    vi.doMock('../../src/app/useNavigationState', () => ({
      useNavigationState: () => ({
        activeRequestSummary: null,
        navigation: { activeTab: 'chat' } as NavigationState,
        setSelectedRequestSummary: vi.fn(),
        updateNavigation: vi.fn(),
      }),
    }));
    vi.doMock('../../src/components/common/StatsBar', () => ({ StatsBar: () => <div>stats</div> }));
    vi.doMock('../../src/app/RequestsWorkspace', () => ({ RequestsWorkspace: () => <div>requests workspace</div> }));
    vi.doMock('../../src/app/ChatWorkspace', () => ({ ChatWorkspace: () => <div>chat workspace</div> }));

    const { ConnectedApp } = await import('../../src/app/ConnectedApp');
    render(<ConnectedApp onDisconnect={vi.fn()} />);

    expect(screen.getByText('chat workspace')).toBeInTheDocument();
  });

  it('wires request browser and request detail callbacks', async () => {
    const onSelectRequestSummary = vi.fn();
    const updateNavigation = vi.fn();
    const request = { id: 'req-1' };

    vi.doMock('../../src/components/RequestBrowser/RequestBrowser', () => ({
      RequestBrowser: ({ onModelFilterChange, onSearchQueryChange, onSelect }: { onModelFilterChange: (value: string) => void; onSearchQueryChange: (value: string) => void; onSelect: (value: { id: string }) => void }) => (
        <>
          <button onClick={() => onModelFilterChange('gpt-4o')}>filter model</button>
          <button onClick={() => onSearchQueryChange('hello')}>search requests</button>
          <button onClick={() => onSelect(request)}>select request</button>
        </>
      ),
    }));
    vi.doMock('../../src/components/RequestDetail/RequestDetail', () => ({
      RequestDetail: ({ onClose }: { onClose: () => void }) => <button onClick={onClose}>close detail</button>,
    }));

    const { RequestsWorkspace } = await import('../../src/app/RequestsWorkspace');
    render(
      <RequestsWorkspace
        activeRequestSummary={request as never}
        navigation={{ activeTab: 'requests', requestId: 'req-1', requestModelFilter: '', requestSearch: '' } as NavigationState}
        onSelectRequestSummary={onSelectRequestSummary}
        updateNavigation={updateNavigation}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'filter model' }));
    await userEvent.click(screen.getByRole('button', { name: 'search requests' }));
    await userEvent.click(screen.getByRole('button', { name: 'select request' }));
    await userEvent.click(screen.getByRole('button', { name: 'close detail' }));

    expect(onSelectRequestSummary).toHaveBeenCalledWith(request);
    expect(updateNavigation).toHaveBeenCalledTimes(4);
  });

  it('wires chat grouping callbacks', async () => {
    const updateNavigation = vi.fn();

    vi.doMock('../../src/components/ChatView/ChatView', () => ({
      ChatView: ({ onGroupByChange, onSelectGroup }: { onGroupByChange: (value: 'model') => void; onSelectGroup: (value: string) => void }) => (
        <>
          <button onClick={() => onGroupByChange('model')}>group by model</button>
          <button onClick={() => onSelectGroup('team-a')}>select group</button>
        </>
      ),
    }));

    const { ChatWorkspace } = await import('../../src/app/ChatWorkspace');
    render(
      <ChatWorkspace
        navigation={{ activeTab: 'chat', chatGroupBy: 'client', selectedChatGroup: null } as NavigationState}
        updateNavigation={updateNavigation}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'group by model' }));
    await userEvent.click(screen.getByRole('button', { name: 'select group' }));

    expect(updateNavigation).toHaveBeenCalledTimes(2);
  });
});

describe('main bootstrap', () => {
  it('mounts the app into the root element', async () => {
    const renderRoot = vi.fn();
    const createRoot = vi.fn(() => ({ render: renderRoot }));

    document.body.innerHTML = '<div id="root"></div>';
    vi.doMock('react-dom/client', () => ({ createRoot }));
    vi.doMock('../../src/App', () => ({ default: () => <div>app</div> }));

    await import('../../src/main');

    expect(createRoot).toHaveBeenCalledWith(document.getElementById('root'));
    expect(renderRoot).toHaveBeenCalled();
  });
});