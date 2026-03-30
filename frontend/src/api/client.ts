import type {
  ConversationsPage,
  RequestDetail,
  RequestSummary,
  RequestsPage,
  Stats,
} from '../types';

const STORAGE_KEY = 'ai-proxy-connection';

export class ApiError extends Error {
  status: number;
  responseText: string;

  constructor(status: number, statusText: string, responseText: string) {
    super(`${status} ${statusText}: ${responseText}`);
    this.name = 'ApiError';
    this.status = status;
    this.responseText = responseText;
  }
}

export interface ApiSettings {
  baseUrl: string;
  uiApiKey: string;
}

export interface ApiClient {
  testConnection(): Promise<void>;
  getStats(): Promise<Stats>;
  listRequests(params?: {
    cursor?: string;
    limit?: number;
    model?: string;
    client_hash?: string;
    since?: string;
    until?: string;
  }): Promise<RequestsPage>;
  getRequest(id: string): Promise<RequestDetail>;
  searchRequests(q: string, limit?: number): Promise<{ items: RequestSummary[] }>;
  getConversations(params?: {
    group_by?: string;
    limit?: number;
    offset?: number;
  }): Promise<ConversationsPage>;
  getConversationMessages(groupKey: string, groupBy?: string): Promise<{ items: RequestDetail[] }>;
  downloadExport(id: string, format?: 'json' | 'markdown'): Promise<void>;
  exportUrl(id: string, format?: 'json' | 'markdown'): string;
  getAuthHeader(): string;
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
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  return headers;
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
    throw new ApiError(resp.status, resp.statusText, text);
  }
  return resp.json() as Promise<T>;
}

async function downloadExportFile(
  baseUrl: string,
  apiKey: string,
  id: string,
  format: 'json' | 'markdown',
): Promise<void> {
  const url = `${baseUrl.replace(/\/$/, '')}/ui/v1/export/requests/${id}?format=${format}`;
  const resp = await fetch(url, { headers: getHeaders(apiKey) });
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, resp.statusText, text);
  }

  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = `request-${id}.${format === 'markdown' ? 'md' : 'json'}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export function createApiClient(settings: ApiSettings): ApiClient {
  const { baseUrl, uiApiKey } = settings;
  const api = <T>(path: string) =>
    fetchApi<T>(baseUrl, uiApiKey, path);

  return {
    async testConnection(): Promise<void> {
      await fetchApi<unknown>(baseUrl, uiApiKey, '/ui/v1/health');
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
      const url = `${baseUrl.replace(/\/$/, '')}/ui/v1/conversations/messages?${qs.toString()}`;
      const resp = await fetch(url, {
        method: 'POST',
        headers: getHeaders(uiApiKey),
        body: JSON.stringify({ group_key: groupKey }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new ApiError(resp.status, resp.statusText, text);
      }
      return resp.json() as Promise<{ items: RequestDetail[] }>;
    },

    async downloadExport(id: string, format: 'json' | 'markdown' = 'json'): Promise<void> {
      await downloadExportFile(baseUrl, uiApiKey, id, format);
    },

    exportUrl(id: string, format: 'json' | 'markdown' = 'json'): string {
      return `${baseUrl.replace(/\/$/, '')}/ui/v1/export/requests/${id}?format=${format}`;
    },

    getAuthHeader(): string {
      return uiApiKey ? `Bearer ${uiApiKey}` : '';
    },
  };
}
