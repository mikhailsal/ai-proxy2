import type {
  ConversationsPage,
  RequestDetail,
  RequestSummary,
  RequestsPage,
  Stats,
} from '../types';

const STORAGE_KEY = 'ai-proxy-connection';

export interface ApiSettings {
  baseUrl: string;
  uiApiKey: string;
}

export function loadSettings(): ApiSettings | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ApiSettings;
  } catch {
    return null;
  }
}

export function saveSettings(settings: ApiSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function clearSettings(): void {
  localStorage.removeItem(STORAGE_KEY);
}

function getHeaders(apiKey: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };
}

async function fetchApi<T>(
  baseUrl: string,
  apiKey: string,
  path: string,
): Promise<T> {
  const url = `${baseUrl.replace(/\/$/, '')}${path}`;
  const resp = await fetch(url, { headers: getHeaders(apiKey) });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

export function createApiClient(settings: ApiSettings) {
  const { baseUrl, uiApiKey } = settings;
  const api = <T>(path: string) =>
    fetchApi<T>(baseUrl, uiApiKey, path);

  return {
    async testConnection(): Promise<boolean> {
      try {
        await fetchApi<unknown>(baseUrl, uiApiKey, '/health');
        return true;
      } catch {
        return false;
      }
    },

    async getStats(): Promise<Stats> {
      return api<Stats>('/ui/v1/stats');
    },

    async listRequests(params: {
      cursor?: string;
      limit?: number;
      model?: string;
      client_hash?: string;
      since?: string;
      until?: string;
    } = {}): Promise<RequestsPage> {
      const qs = new URLSearchParams();
      if (params.cursor) qs.set('cursor', params.cursor);
      if (params.limit) qs.set('limit', String(params.limit));
      if (params.model) qs.set('model', params.model);
      if (params.client_hash) qs.set('client_hash', params.client_hash);
      if (params.since) qs.set('since', params.since);
      if (params.until) qs.set('until', params.until);
      const query = qs.toString();
      return api<RequestsPage>(`/ui/v1/requests${query ? `?${query}` : ''}`);
    },

    async getRequest(id: string): Promise<RequestDetail> {
      return api<RequestDetail>(`/ui/v1/requests/${id}`);
    },

    async searchRequests(q: string, limit = 50): Promise<{ items: RequestSummary[] }> {
      const qs = new URLSearchParams({ q, limit: String(limit) });
      return api<{ items: RequestSummary[] }>(`/ui/v1/search?${qs.toString()}`);
    },

    async getConversations(params: {
      group_by?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<ConversationsPage> {
      const qs = new URLSearchParams();
      if (params.group_by) qs.set('group_by', params.group_by);
      if (params.limit) qs.set('limit', String(params.limit));
      if (params.offset) qs.set('offset', String(params.offset));
      const query = qs.toString();
      return api<ConversationsPage>(
        `/ui/v1/conversations${query ? `?${query}` : ''}`,
      );
    },

    async getConversationMessages(
      groupKey: string,
      groupBy = 'system_prompt',
    ): Promise<{ items: RequestDetail[] }> {
      const qs = new URLSearchParams({ group_by: groupBy });
      return api<{ items: RequestDetail[] }>(
        `/ui/v1/conversations/${encodeURIComponent(groupKey)}/messages?${qs.toString()}`,
      );
    },

    exportUrl(id: string, format: 'json' | 'markdown' = 'json'): string {
      return `${baseUrl.replace(/\/$/, '')}/ui/v1/export/requests/${id}?format=${format}`;
    },

    getAuthHeader(): string {
      return `Bearer ${uiApiKey}`;
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
