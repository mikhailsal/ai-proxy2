import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
});

describe('App', () => {
  it('renders the auth page when no saved settings exist', async () => {
    const loadSettings = vi.fn(() => null);
    const createApiClient = vi.fn();

    vi.doMock('../../src/api/client', () => ({
      clearSettings: vi.fn(),
      createApiClient,
      loadSettings,
    }));
    vi.doMock('../../src/components/Auth/AuthPage', () => ({
      AuthPage: ({ onConnect }: { onConnect: (client: { id: string }) => void }) => (
        <button onClick={() => onConnect({ id: 'from-auth' })}>connect</button>
      ),
    }));
    vi.doMock('../../src/app/ConnectedApp', () => ({
      ConnectedApp: ({ onDisconnect }: { onDisconnect: () => void }) => (
        <button onClick={onDisconnect}>disconnect</button>
      ),
    }));

    const { default: App } = await import('../../src/App');
    render(<App />);

    expect(screen.getByRole('button', { name: 'connect' })).toBeInTheDocument();
    expect(loadSettings).toHaveBeenCalled();
    expect(createApiClient).not.toHaveBeenCalled();
  });

  it('creates a client from saved settings and handles disconnect', async () => {
    const clearSettings = vi.fn();
    const client = { getStats: vi.fn() };

    vi.doMock('../../src/api/client', () => ({
      clearSettings,
      createApiClient: vi.fn(() => client),
      loadSettings: vi.fn(() => ({ baseUrl: 'http://localhost:8000', uiApiKey: 'secret' })),
    }));
    vi.doMock('../../src/components/Auth/AuthPage', () => ({
      AuthPage: () => <div>auth</div>,
    }));
    vi.doMock('../../src/app/ConnectedApp', () => ({
      ConnectedApp: ({ onDisconnect }: { onDisconnect: () => void }) => (
        <button onClick={onDisconnect}>disconnect</button>
      ),
    }));

    const { default: App } = await import('../../src/App');
    render(<App />);

    const disconnect = await screen.findByRole('button', { name: 'disconnect' });
    await userEvent.click(disconnect);

    expect(clearSettings).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'disconnect' })).not.toBeInTheDocument());
  });
});