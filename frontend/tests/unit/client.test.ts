import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../../src/api/client';

interface DownloadEnvironment {
  appendChild: ReturnType<typeof vi.spyOn>;
  click: ReturnType<typeof vi.fn>;
  createElement: ReturnType<typeof vi.spyOn>;
  createObjectURLMock: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  restore: () => void;
  revokeObjectURLMock: ReturnType<typeof vi.fn>;
}

describe('createApiClient', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('tests authenticated connectivity through /ui/v1/health', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    const client = createApiClient({ baseUrl: 'http://localhost:8000/', uiApiKey: 'ui-secret' });
    await client.testConnection();

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/ui/v1/health', {
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ui-secret',
      },
    });
  });

  it('surfaces invalid UI API keys as ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"detail":"Invalid UI API key"}', {
        status: 401,
        statusText: 'Unauthorized',
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const client = createApiClient({ baseUrl: 'http://localhost:8000', uiApiKey: 'bad-key' });

    await expect(client.testConnection()).rejects.toBeInstanceOf(ApiError);
  });

  it('downloads exports with the UI auth header', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const downloadEnvironment = mockDownloadEnvironment();

    const client = createApiClient({ baseUrl: 'http://localhost:8000', uiApiKey: 'ui-secret' });
    await client.downloadExport('req-123', 'markdown');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/ui/v1/export/requests/req-123?format=markdown',
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ui-secret',
        },
      },
    );
    expect(downloadEnvironment.createObjectURLMock).toHaveBeenCalled();
    expect(downloadEnvironment.click).toHaveBeenCalled();
    expect(downloadEnvironment.remove).toHaveBeenCalled();
    expect(downloadEnvironment.revokeObjectURLMock).toHaveBeenCalledWith('blob:request-export');

    downloadEnvironment.restore();
  });
});

function mockDownloadEnvironment(): DownloadEnvironment {
  const createObjectURLMock = vi.fn(() => 'blob:request-export');
  const revokeObjectURLMock = vi.fn();
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURLMock, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURLMock, configurable: true });

  const originalCreateElement = document.createElement.bind(document);
  const click = vi.fn();
  const remove = vi.fn();
  const appendChild = vi.spyOn(document.body, 'appendChild').mockImplementation(node => node);
  const createElement = vi.spyOn(document, 'createElement').mockImplementation(tagName => {
    if (tagName === 'a') {
      return {
        click,
        remove,
        href: '',
        download: '',
      } as unknown as HTMLAnchorElement;
    }

    return originalCreateElement(tagName);
  });

  return {
    appendChild,
    click,
    createElement,
    createObjectURLMock,
    remove,
    restore: () => {
      appendChild.mockRestore();
      createElement.mockRestore();
      Object.defineProperty(URL, 'createObjectURL', { value: originalCreateObjectURL, configurable: true });
      Object.defineProperty(URL, 'revokeObjectURL', { value: originalRevokeObjectURL, configurable: true });
    },
    revokeObjectURLMock,
  };
}
