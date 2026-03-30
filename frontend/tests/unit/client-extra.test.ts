import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, clearSettings, createApiClient, loadSettings, saveSettings } from '../../src/api/client';

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('client settings', () => {
  it('loads, saves, clears, and ignores invalid settings JSON', () => {
    expect(loadSettings()).toBeNull();

    saveSettings({ baseUrl: 'http://localhost:8000', uiApiKey: 'secret' });
    expect(loadSettings()).toEqual({ baseUrl: 'http://localhost:8000', uiApiKey: 'secret' });

    localStorage.setItem('ai-proxy-connection', '{bad json');
    expect(loadSettings()).toBeNull();

    saveSettings({ baseUrl: 'http://localhost:8000', uiApiKey: 'secret' });
    clearSettings();
    expect(loadSettings()).toBeNull();
  });
});

describe('BrowserApiClient', () => {
  it('fetches stats, requests, detail, search, and conversations', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ total_requests: 1, avg_latency_ms: 2, total_tokens: 3, total_cost: 4 }))
      .mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: 'cursor-1' }))
      .mockResolvedValueOnce(jsonResponse({ id: 'req-1' }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ id: 'req-1' }] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ group_key: 'team-a' }] }));
    const client = createApiClient({ baseUrl: 'http://localhost:8000/', uiApiKey: 'secret' });

    await expect(client.getStats()).resolves.toMatchObject({ total_requests: 1 });
    await expect(
      client.listRequests({ cursor: 'abc', limit: 10, model: 'gpt', client_hash: 'hash', since: 'yesterday', until: 'today' }),
    ).resolves.toEqual({ items: [], next_cursor: 'cursor-1' });
    await expect(client.getRequest('req-1')).resolves.toEqual({ id: 'req-1' });
    await expect(client.searchRequests('hello', 5)).resolves.toEqual({ items: [{ id: 'req-1' }] });
    await expect(client.getConversations({ group_by: 'client', limit: 2, offset: 3 })).resolves.toEqual({ items: [{ group_key: 'team-a' }] });

    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://localhost:8000/ui/v1/stats', withAuth('secret'));
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/ui/v1/requests?cursor=abc&limit=10&model=gpt&client_hash=hash&since=yesterday&until=today',
      withAuth('secret'),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(3, 'http://localhost:8000/ui/v1/requests/req-1', withAuth('secret'));
    expect(fetchMock).toHaveBeenNthCalledWith(4, 'http://localhost:8000/ui/v1/search?q=hello&limit=5', withAuth('secret'));
    expect(fetchMock).toHaveBeenNthCalledWith(5, 'http://localhost:8000/ui/v1/conversations?group_by=client&limit=2&offset=3', withAuth('secret'));
  });

  it('posts conversation message lookups and exposes export helpers', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ items: [{ id: 'req-1' }] }));
    const client = createApiClient({ baseUrl: 'http://localhost:8000/', uiApiKey: '' });

    await expect(client.getConversationMessages('team a', 'model')).resolves.toEqual({ items: [{ id: 'req-1' }] });
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/ui/v1/conversations/messages?group_by=model', {
      body: JSON.stringify({ group_key: 'team a' }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    expect(client.exportUrl('req-1', 'markdown')).toBe('http://localhost:8000/ui/v1/export/requests/req-1?format=markdown');
    expect(client.getAuthHeader()).toBe('');
  });

  it('throws ApiError for failed JSON fetches and export downloads', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('bad stats', { status: 500, statusText: 'Server Error' }))
      .mockResolvedValueOnce(new Response('bad export', { status: 403, statusText: 'Forbidden' }));
    const client = createApiClient({ baseUrl: 'http://localhost:8000', uiApiKey: 'secret' });

    await expect(client.getStats()).rejects.toEqual(new ApiError(500, 'Server Error', 'bad stats'));
    await expect(client.downloadExport('req-1', 'json')).rejects.toEqual(new ApiError(403, 'Forbidden', 'bad export'));
  });
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function withAuth(apiKey: string) {
  return {
    headers: apiKey
      ? { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` }
      : { 'Content-Type': 'application/json' },
  };
}