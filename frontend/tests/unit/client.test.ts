import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../../src/api/client';

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
});
