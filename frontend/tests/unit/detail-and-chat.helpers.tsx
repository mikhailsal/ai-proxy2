import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ApiContext } from '../../src/hooks/useApi';
import type { ConversationMessage, RequestDetail as RequestDetailType, RequestSummary } from '../../src/types';

export function renderWithApi(ui: ReactElement, api: Record<string, unknown>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiContext.Provider value={api as never}>{ui}</ApiContext.Provider>
    </QueryClientProvider>,
  );
}

export function makeRequestSummary(overrides: Partial<RequestSummary>): RequestSummary {
  return {
    id: overrides.id ?? 'req-1',
    timestamp: overrides.timestamp ?? '2024-01-01T00:00:00Z',
    client_ip: null,
    client_api_key_hash: null,
    method: 'POST',
    path: '/v1/chat/completions',
    model_requested: overrides.model_requested ?? 'gpt-4o-mini',
    model_resolved: overrides.model_resolved ?? 'gpt-4o-mini',
    response_status_code: overrides.response_status_code ?? 200,
    latency_ms: overrides.latency_ms ?? 42,
    input_tokens: 1,
    output_tokens: 2,
    total_tokens: 3,
    cached_input_tokens: null,
    cost: overrides.cost ?? 0.123456,
    cache_status: overrides.cache_status ?? 'hit',
    error_message: overrides.error_message ?? null,
    last_user_message: null,
    assistant_response: null,
  };
}

export function makeRequestDetail(overrides?: Partial<RequestDetailType>): RequestDetailType {
  return {
    ...makeRequestSummary({ error_message: 'backend error' }),
    request_headers: { authorization: 'Bearer redacted' },
    client_request_headers: null,
    request_body: {
      tools: [{ type: 'function', function: { name: 'lookup_weather' } }],
      messages: [
        { role: 'system', content: 'system prompt' },
        { role: 'user', content: 'hello' },
      ],
    },
    client_request_body: null,
    response_headers: { 'content-type': 'application/json' },
    client_response_headers: null,
    response_body: { choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: 'reply' } }] },
    client_response_body: null,
    stream_chunks: [{ delta: 'hi' }],
    reasoning_tokens: null,
    metadata: null,
    ...overrides,
  };
}

function msg(overrides: Partial<ConversationMessage> & { id: string; role: string; content: string }): ConversationMessage {
  return {
    node_id: overrides.id,
    parent: null,
    children: [],
    origin: 'request',
    raw_message: { role: overrides.role, content: overrides.content },
    tool_names: [],
    meta_tags: {},
    source_request_id: 'req-1',
    source_request_timestamp: '2024-01-01T00:00:00Z',
    source_message_index: 0,
    last_seen_at: '2024-01-02T00:00:00Z',
    repeat_count: 2,
    model: 'gpt-4o-mini',
    latency_ms: 42,
    total_tokens: 3,
    ...overrides,
  };
}

export function makeConversationMessages(): ConversationMessage[] {
  return [
    msg({ id: 'msg-1', node_id: 'n1', parent: null, children: ['n2'], role: 'system', content: 'system prompt', meta_tags: { name: 'system' } }),
    msg({ id: 'msg-2', node_id: 'n2', parent: 'n1', children: ['n2b', 'n3'], role: 'user', content: 'hello', source_message_index: 1 }),
    msg({
      id: 'msg-2b', node_id: 'n2b', parent: 'n2', children: [], origin: 'response', role: 'assistant', content: 'Tool call: lookup_weather',
      raw_message: { role: 'assistant', content: '', tool_calls: [
        { id: 'call_weather_1', type: 'function', function: { name: 'lookup_weather', arguments: '{"city":"Berlin"}' } },
      ] }, tool_names: ['lookup_weather'], source_message_index: 2,
    }),
    msg({ id: 'msg-3', node_id: 'n3', parent: 'n2', children: [], origin: 'response', role: 'assistant', content: 'reply', last_seen_at: '2024-01-01T00:00:00Z', repeat_count: 1, source_message_index: 2 }),
  ];
}