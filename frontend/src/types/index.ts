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
  cached_input_tokens: number | null;
  cost: number | null;
  cache_status: string | null;
  message_count: number | null;
  error_message: string | null;
  last_user_message: string | null;
  assistant_response: string | null;
}

export interface RequestDetail extends RequestSummary {
  request_headers: Record<string, unknown> | null;
  client_request_headers: Record<string, unknown> | null;
  request_body: Record<string, unknown> | null;
  client_request_body: Record<string, unknown> | null;
  response_headers: Record<string, unknown> | null;
  client_response_headers: Record<string, unknown> | null;
  response_body: Record<string, unknown> | null;
  client_response_body: Record<string, unknown> | null;
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
  group_label?: string;
  message_count: number;
  request_count?: number;
  first_message: string | null;
  last_message: string | null;
  models_used: string[];
}

export interface ConversationsPage {
  items: Conversation[];
}

export interface ConversationMessage {
  id: string;
  node_id: string;
  parent: string | null;
  children: string[];
  origin: 'request' | 'response';
  role: string;
  content: string;
  raw_message: Record<string, unknown> | null;
  tool_names: string[];
  meta_tags: Record<string, unknown>;
  source_request_id: string;
  source_request_timestamp: string | null;
  source_message_index: number;
  last_seen_at: string | null;
  repeat_count: number;
  model: string | null;
  latency_ms: number | null;
  total_tokens: number | null;
}

export interface ConnectionSettings {
  baseUrl: string;
  uiApiKey: string;
}

export interface ProxyModelPricing {
  prompt?: string | number | null;
  completion?: string | number | null;
  input?: string | number | null;
  output?: string | number | null;
  [key: string]: string | number | null | undefined;
}

export interface ProxyModelArchitecture {
  input_modalities?: string[] | null;
  output_modalities?: string[] | null;
  tokenizer?: string | null;
  modality?: string | string[] | null;
  instruct_type?: string | null;
  [key: string]: unknown;
}

export interface ProxyModel {
  id: string;
  provider: string;
  mapped_model: string;
  pinned_providers?: string[] | null;
  owned_by?: string | null;
  object?: string;
  created?: number | null;
  name?: string | null;
  description?: string | null;
  context_length?: number | null;
  pricing?: ProxyModelPricing | null;
  architecture?: ProxyModelArchitecture | null;
  supported_parameters?: string[] | null;
  per_request_limits?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface ProxyModelsPage {
  object: string;
  data: ProxyModel[];
}
