export interface RequestSummary {
  id: string;
  timestamp: string;
  client_ip: string | null;
  client_api_key_hash: string | null;
  method: string;
  path: string;
  model_requested: string | null;
  model_resolved: string | null;
  response_status_code: number | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost: number | null;
  cache_status: string | null;
  error_message: string | null;
}

export interface RequestDetail extends RequestSummary {
  request_headers: Record<string, unknown> | null;
  request_body: Record<string, unknown> | null;
  response_headers: Record<string, unknown> | null;
  response_body: Record<string, unknown> | null;
  stream_chunks: unknown[] | null;
  reasoning_tokens: number | null;
  metadata: Record<string, unknown> | null;
}

export interface RequestsPage {
  items: RequestSummary[];
  next_cursor: string | null;
}

export interface Stats {
  total_requests: number;
  avg_latency_ms: number;
  total_tokens: number;
  total_cost: number;
}

export interface Conversation {
  group_key: string;
  message_count: number;
  first_message: string | null;
  last_message: string | null;
  models_used: string[];
}

export interface ConversationsPage {
  items: Conversation[];
}

export interface ConnectionSettings {
  baseUrl: string;
  uiApiKey: string;
}
