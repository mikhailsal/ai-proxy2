import type {
  ConversationMessage,
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
  getConversationMessages(groupKey: string, groupBy?: string): Promise<{ items: ConversationMessage[] }>;
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

class BrowserApiClient implements ApiClient {
  private readonly baseUrl: string;

  private readonly uiApiKey: string;

  constructor(settings: ApiSettings) {
    this.baseUrl = settings.baseUrl;
    this.uiApiKey = settings.uiApiKey;
  }

  async testConnection(): Promise<void> {
    await fetchApi<unknown>(this.baseUrl, this.uiApiKey, '/ui/v1/health');
  }

  async getStats(): Promise<Stats> {
    return fetchApi<Stats>(this.baseUrl, this.uiApiKey, '/ui/v1/stats');
  }

  async listRequests(params: {
    cursor?: string;
    limit?: number;
    model?: string;
    client_hash?: string;
    since?: string;
    until?: string;
  } = {}): Promise<RequestsPage> {
    return fetchApi<RequestsPage>(this.baseUrl, this.uiApiKey, buildRequestsPath(params));
  }

  async getRequest(id: string): Promise<RequestDetail> {
    return fetchApi<RequestDetail>(this.baseUrl, this.uiApiKey, `/ui/v1/requests/${id}`);
  }

  async searchRequests(q: string, limit = 50): Promise<{ items: RequestSummary[] }> {
    const qs = new URLSearchParams({ q, limit: String(limit) });
    return fetchApi<{ items: RequestSummary[] }>(this.baseUrl, this.uiApiKey, `/ui/v1/search?${qs.toString()}`);
  }

  async getConversations(params: {
    group_by?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<ConversationsPage> {
    return fetchApi<ConversationsPage>(this.baseUrl, this.uiApiKey, buildConversationsPath(params));
  }

  async getConversationMessages(
    groupKey: string,
    groupBy = 'system_prompt',
  ): Promise<{ items: ConversationMessage[] }> {
    return fetchConversationMessages(this.baseUrl, this.uiApiKey, groupKey, groupBy);
  }

  async downloadExport(id: string, format: 'json' | 'markdown' = 'json'): Promise<void> {
    await downloadExportFile(this.baseUrl, this.uiApiKey, id, format);
  }

  exportUrl(id: string, format: 'json' | 'markdown' = 'json'): string {
    return `${trimBaseUrl(this.baseUrl)}/ui/v1/export/requests/${id}?format=${format}`;
  }

  getAuthHeader(): string {
    return this.uiApiKey ? `Bearer ${this.uiApiKey}` : '';
  }
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
  const url = `${trimBaseUrl(baseUrl)}${path}`;
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
  const url = `${trimBaseUrl(baseUrl)}/ui/v1/export/requests/${id}?format=${format}`;
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
  return new BrowserApiClient(settings);
}

function buildRequestsPath(params: {
  cursor?: string;
  limit?: number;
  model?: string;
  client_hash?: string;
  since?: string;
  until?: string;
}): string {
  const query = buildQueryString(params);
  return `/ui/v1/requests${query ? `?${query}` : ''}`;
}

function buildConversationsPath(params: {
  group_by?: string;
  limit?: number;
  offset?: number;
}): string {
  const query = buildQueryString(params);
  return `/ui/v1/conversations${query ? `?${query}` : ''}`;
}

function buildQueryString(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      qs.set(key, String(value));
    }
  });
  return qs.toString();
}

async function fetchConversationMessages(
  baseUrl: string,
  apiKey: string,
  groupKey: string,
  groupBy: string,
): Promise<{ items: ConversationMessage[] }> {
  const url = `${trimBaseUrl(baseUrl)}/ui/v1/conversations/messages?group_by=${encodeURIComponent(groupBy)}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: getHeaders(apiKey),
    body: JSON.stringify({ group_key: groupKey }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, resp.statusText, text);
  }

  return resp.json() as Promise<{ items: ConversationMessage[] }>;
}

function trimBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/$/, '');
}
