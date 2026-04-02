import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ChatGroupBy } from '../../app/navigation';
import { useApi } from '../../hooks/useApi';
import { useAutoRefresh } from '../../hooks/autoRefreshContext';
import type { Conversation, ConversationMessage, RequestDetail } from '../../types';
import { JsonViewer } from '../JsonViewer/JsonViewer';

interface ChatViewProps {
  groupBy: ChatGroupBy;
  selectedGroup: string | null;
  onGroupByChange: (groupBy: ChatGroupBy) => void;
  onSelectGroup: (groupKey: string) => void;
}

export function ChatView({
  groupBy,
  selectedGroup,
  onGroupByChange,
  onSelectGroup,
}: ChatViewProps) {
  const api = useApi();
  const { refetchInterval } = useAutoRefresh();

  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations', groupBy],
    queryFn: () => api.getConversations({ group_by: groupBy, limit: 100 }),
    refetchInterval,
  });

  const { data: messages } = useQuery({
    queryKey: ['conversation-messages', selectedGroup, groupBy],
    queryFn: () => api.getConversationMessages(selectedGroup!, groupBy),
    enabled: !!selectedGroup,
  });

  return (
    <div style={styles.container}>
      <ConversationSidebar
        conversations={conversations?.items ?? []}
        groupBy={groupBy}
        isLoading={isLoading}
        onGroupByChange={onGroupByChange}
        onSelectGroup={onSelectGroup}
        selectedGroup={selectedGroup}
      />

      <div style={styles.timeline}>
        {!selectedGroup ? (
          <div style={styles.emptyState}>Select a conversation to view messages.</div>
        ) : (
          <ChatTimeline messages={messages?.items ?? []} />
        )}
      </div>
    </div>
  );
}

function ConversationSidebar({
  conversations,
  groupBy,
  isLoading,
  onGroupByChange,
  onSelectGroup,
  selectedGroup,
}: {
  conversations: Conversation[];
  groupBy: ChatGroupBy;
  isLoading: boolean;
  onGroupByChange: (groupBy: ChatGroupBy) => void;
  onSelectGroup: (groupKey: string) => void;
  selectedGroup: string | null;
}) {
  return (
    <div style={styles.sidebar}>
      <div style={styles.sidebarHeader}>
        <span style={styles.sidebarTitle}>Conversations</span>
        <select
          style={styles.select}
          value={groupBy}
          onChange={event => onGroupByChange(event.target.value as ChatGroupBy)}
        >
          <option value="system_prompt">By System Prompt</option>
          <option value="system_prompt_first_user">By System Prompt + First User</option>
          <option value="client">By Client</option>
          <option value="model">By Model</option>
        </select>
      </div>
      {isLoading ? <div style={styles.loading}>Loading…</div> : null}
      {!isLoading ? (
        <div style={styles.convList}>
          {conversations.map(conv => (
            <ConversationRow
              conversation={conv}
              isSelected={selectedGroup === conv.group_key}
              key={conv.group_key}
              onSelectGroup={onSelectGroup}
            />
          ))}
          {conversations.length === 0 ? <div style={styles.loading}>No conversations found.</div> : null}
        </div>
      ) : null}
    </div>
  );
}

function ConversationRow({
  conversation,
  isSelected,
  onSelectGroup,
}: {
  conversation: Conversation;
  isSelected: boolean;
  onSelectGroup: (groupKey: string) => void;
}) {
  const label = conversation.group_label ?? conversation.group_key ?? 'Unknown';
  const preview = label.slice(0, 72);
  const suffix = label.length > 72 ? '…' : '';

  return (
    <div
      style={{
        ...styles.convItem,
        background: isSelected ? '#21262d' : 'transparent',
        borderLeft: isSelected ? '2px solid #58a6ff' : '2px solid transparent',
      }}
      onClick={() => onSelectGroup(conversation.group_key)}
    >
      <div style={styles.convPreview}>{preview}{suffix}</div>
      <div style={styles.convMeta}>
        <span>{conversation.message_count} messages</span>
        <span>{conversation.request_count ?? 0} requests</span>
        <span>{conversation.models_used?.slice(0, 2).join(', ')}</span>
      </div>
    </div>
  );
}

function ChatTimeline({ messages }: { messages: ConversationMessage[] }) {
  if (messages.length === 0) {
    return <div style={styles.loading}>No messages in this conversation.</div>;
  }

  return (
    <div style={styles.timelineInner}>
      {messages.map(message => (
        <MessageCard key={message.id} message={message} />
      ))}
    </div>
  );
}

function MessageCard({ message }: { message: ConversationMessage }) {
  const [showRawRequest, setShowRawRequest] = useState(false);
  const metaTagNames = Object.keys(message.meta_tags ?? {});
  const toolCalls = getAssistantToolCalls(message);

  return (
    <div style={styles.requestBlock}>
      <div style={styles.requestMeta}>
        <span style={roleBadgeStyle(message.role)}>{message.role}</span>
        {message.source_request_timestamp ? <span style={styles.reqTime}>{formatTimestamp(message.source_request_timestamp)}</span> : null}
        {message.model ? <span style={styles.reqModel}>{message.model}</span> : null}
        {message.repeat_count > 1 ? <span style={styles.reqTokens}>sent {message.repeat_count}x</span> : null}
        {message.latency_ms != null ? <span style={styles.reqLatency}>{Math.round(message.latency_ms)}ms</span> : null}
        {message.total_tokens != null ? <span style={styles.reqTokens}>{message.total_tokens} tokens</span> : null}
        {message.tool_names.length > 0 ? <span style={styles.reqTokens}>tools: {message.tool_names.join(', ')}</span> : null}
        {metaTagNames.length > 0 ? <span style={styles.reqTokens}>tags: {metaTagNames.join(', ')}</span> : null}
      </div>
      <ChatBubble role={message.role} content={message.content} />
      {toolCalls.length > 0 ? <AssistantToolCallsPanel toolCalls={toolCalls} /> : null}
      <button
        style={styles.toggleDetail}
        onClick={() => setShowRawRequest(current => !current)}
      >
        {showRawRequest ? 'Hide raw request' : 'Show raw request'}
      </button>
      {showRawRequest ? <MessageRawRequest message={message} /> : null}
    </div>
  );
}

function ChatBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === 'user';
  const isSystem = role === 'system';
  return (
    <div style={{
      ...styles.bubble,
      alignSelf: isUser ? 'flex-end' : isSystem ? 'center' : 'flex-start',
      background: isUser ? '#1f6feb' : isSystem ? '#21262d' : '#161b22',
      borderRadius: isUser ? '12px 12px 2px 12px' : isSystem ? '6px' : '12px 12px 12px 2px',
      maxWidth: isSystem ? '100%' : '80%',
    }}>
      {!isUser && <div style={styles.bubbleRole}>{role}</div>}
      <div style={styles.bubbleContent}>{content}</div>
    </div>
  );
}

function MessageRawRequest({ message }: { message: ConversationMessage }) {
  const api = useApi();
  const { data, isLoading, error } = useQuery({
    queryKey: ['request', message.source_request_id],
    queryFn: () => api.getRequest(message.source_request_id),
    enabled: true,
  });

  if (isLoading) {
    return <div style={styles.loadingInline}>Loading raw request…</div>;
  }

  if (error) {
    return <div style={styles.rawError}>{error instanceof Error ? error.message : String(error)}</div>;
  }

  if (!data) {
    return null;
  }

  return (
    <div style={styles.rawRequestPanel}>
      <div style={styles.rawRequestMeta}>
        Source request {data.id.slice(0, 8)}… {formatTimestamp(data.timestamp)}
      </div>
      <div style={styles.rawSectionTitle}>Request body</div>
      <pre style={styles.rawPre}>
        <JsonViewer
          data={getRawRequestBody(data)}
          collapsedPaths={getCollapsedRequestPaths(data, message)}
        />
      </pre>
      {hasRawResponseBody(data) ? (
        <>
          <div style={styles.rawSectionTitle}>Response body</div>
          <pre style={styles.rawPre}>
            <JsonViewer
              data={getRawResponseBody(data)}
              expandedPaths={[
                'choices.0.message',
                'choices.0.message.tool_calls',
                'choices.0.message.tool_calls.0',
                'choices.0.message.tool_calls.0.function',
              ]}
            />
          </pre>
        </>
      ) : null}
    </div>
  );
}

function AssistantToolCallsPanel({ toolCalls }: { toolCalls: AssistantToolCall[] }) {
  return (
    <div style={styles.toolCallsPanel}>
      <div style={styles.toolCallsTitle}>Assistant tool calls</div>
      {toolCalls.map((toolCall, index) => (
        <div key={`${toolCall.id ?? toolCall.functionName}-${index}`} style={styles.toolCallCard}>
          <div style={styles.toolCallHeader}>
            <span style={styles.toolCallName}>{toolCall.functionName}</span>
            {toolCall.id ? <span style={styles.toolCallMeta}>id: {toolCall.id}</span> : null}
            {toolCall.type ? <span style={styles.toolCallMeta}>type: {toolCall.type}</span> : null}
          </div>
          <pre style={styles.toolCallPre}>
            <JsonViewer data={toolCall.arguments} />
          </pre>
        </div>
      ))}
    </div>
  );
}

function getRawRequestBody(request: RequestDetail): Record<string, unknown> {
  return asObject(request.request_body) ?? {};
}

function getRawResponseBody(request: RequestDetail): Record<string, unknown> {
  return asObject(request.response_body) ?? {};
}

function hasRawResponseBody(request: RequestDetail): boolean {
  return Object.keys(getRawResponseBody(request)).length > 0;
}

function getCollapsedRequestPaths(request: RequestDetail, message: ConversationMessage): string[] {
  const requestBody = getRawRequestBody(request);
  const requestMessages = getRequestMessages(request);
  const visibleIndexes = getVisibleRequestMessageIndexes(requestMessages, message);
  if (!Array.isArray(requestBody.messages)) {
    return [];
  }

  return requestMessages
    .map((_, index) => index)
    .filter(index => !visibleIndexes.includes(index))
    .map(index => `messages.${index}`);
}

function getRequestMessages(request: RequestDetail): Array<Record<string, unknown>> {
  const requestBody = getRawRequestBody(request);
  const messages = requestBody.messages;
  if (!Array.isArray(messages)) {
    return [];
  }

  return messages.filter((item): item is Record<string, unknown> => isRecord(item));
}

function asObject(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface AssistantToolCall {
  id: string | null;
  type: string | null;
  functionName: string;
  arguments: unknown;
}

function getAssistantToolCalls(message: ConversationMessage): AssistantToolCall[] {
  if (message.role !== 'assistant' || !isRecord(message.raw_message)) {
    return [];
  }

  const toolCalls = message.raw_message.tool_calls;
  if (!Array.isArray(toolCalls)) {
    return [];
  }

  return toolCalls
    .filter((toolCall): toolCall is Record<string, unknown> => isRecord(toolCall))
    .map(toolCall => {
      const fn = asObject(toolCall.function);
      const rawArguments = typeof fn?.arguments === 'string' ? fn.arguments : null;
      return {
        id: typeof toolCall.id === 'string' ? toolCall.id : null,
        type: typeof toolCall.type === 'string' ? toolCall.type : null,
        functionName: typeof fn?.name === 'string' ? fn.name : 'unknown_tool',
        arguments: parseToolArguments(rawArguments),
      };
    });
}

function parseToolArguments(rawArguments: string | null): unknown {
  if (!rawArguments) {
    return {};
  }

  try {
    return JSON.parse(rawArguments) as unknown;
  } catch {
    return rawArguments;
  }
}

function getVisibleRequestMessageIndexes(
  messages: Array<Record<string, unknown>>,
  message: ConversationMessage,
): number[] {
  const maxIndex = message.origin === 'response'
    ? messages.length - 1
    : Math.min(message.source_message_index, messages.length - 1);

  if (maxIndex < 0) {
    return [];
  }

  const visible = new Set<number>();
  if (message.origin === 'request' && message.source_message_index < messages.length) {
    visible.add(message.source_message_index);
  }

  for (const role of ['assistant', 'tool', 'user']) {
    const index = findLastMessageIndexByRole(messages, role, maxIndex);
    if (index >= 0) {
      visible.add(index);
    }
  }

  if (visible.size === 0) {
    visible.add(maxIndex);
  }

  return [...visible].sort((left, right) => left - right);
}

function findLastMessageIndexByRole(
  messages: Array<Record<string, unknown>>,
  role: string,
  maxIndex: number,
): number {
  for (let index = maxIndex; index >= 0; index -= 1) {
    if (messages[index]?.role === role) {
      return index;
    }
  }

  return -1;
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}

function roleBadgeStyle(role: string): React.CSSProperties {
  const palette: Record<string, { background: string; color: string }> = {
    system: { background: '#2d1f3d', color: '#d2a8ff' },
    user: { background: '#163356', color: '#79c0ff' },
    assistant: { background: '#1c3a2b', color: '#7ee787' },
    tool: { background: '#4d2d0f', color: '#ffa657' },
  };
  const colors = palette[role] ?? { background: '#30363d', color: '#e6edf3' };
  return {
    ...styles.reqLabel,
    background: colors.background,
    color: colors.color,
    borderRadius: 999,
    padding: '3px 8px',
  };
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', height: '100%', overflow: 'hidden' },
  sidebar: { width: 280, borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', flexShrink: 0 },
  sidebarHeader: { padding: '8px 12px', borderBottom: '1px solid #21262d', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 },
  sidebarTitle: { fontSize: '0.85rem', fontWeight: 600, color: '#e6edf3', flex: 1 },
  select: { background: '#0d1117', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '2px 4px', fontSize: '0.75rem', outline: 'none' },
  convList: { flex: 1, overflowY: 'auto' },
  convItem: { padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #21262d' },
  convPreview: { fontSize: '0.82rem', color: '#e6edf3', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  convMeta: { display: 'flex', gap: 8, fontSize: '0.75rem', color: '#8b949e' },
  timeline: { flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' },
  timelineInner: { flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 },
  requestBlock: { borderRadius: 8, border: '1px solid #21262d', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 },
  requestMeta: { display: 'flex', gap: 8, fontSize: '0.75rem', color: '#8b949e', flexWrap: 'wrap', alignItems: 'center' },
  reqLabel: { fontWeight: 700, color: '#58a6ff', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' },
  reqTime: {},
  reqModel: { color: '#e6edf3', fontWeight: 500 },
  reqLatency: {},
  reqTokens: {},
  bubble: { padding: '8px 12px', color: '#e6edf3', fontSize: '0.85rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  bubbleRole: { fontSize: '0.72rem', fontWeight: 600, color: '#8b949e', marginBottom: 4, textTransform: 'capitalize' },
  bubbleContent: {},
  toggleDetail: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', fontSize: '0.75rem', alignSelf: 'flex-start', padding: '2px 0' },
  rawPre: {
    background: '#0d1117',
    borderRadius: 4,
    padding: 8,
    fontSize: '0.75rem',
    color: '#8b949e',
    margin: 0,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    overflowWrap: 'anywhere',
    overflowX: 'hidden',
  },
  rawRequestPanel: { display: 'flex', flexDirection: 'column', gap: 6, overflow: 'hidden' },
  rawRequestMeta: { color: '#8b949e', fontSize: '0.75rem' },
  rawSectionTitle: { color: '#e6edf3', fontSize: '0.78rem', fontWeight: 600 },
  rawError: { color: '#f85149', fontSize: '0.78rem' },
  loadingInline: { color: '#8b949e', fontSize: '0.78rem' },
  toolCallsPanel: { border: '1px solid #30363d', borderRadius: 8, background: '#0d1117', padding: 10, display: 'flex', flexDirection: 'column', gap: 10 },
  toolCallsTitle: { fontSize: '0.78rem', fontWeight: 700, color: '#ffa657', textTransform: 'uppercase', letterSpacing: '0.04em' },
  toolCallCard: { border: '1px solid #21262d', borderRadius: 6, padding: 10, background: '#11161d', display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden' },
  toolCallHeader: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' },
  toolCallName: { color: '#e6edf3', fontWeight: 600 },
  toolCallMeta: { color: '#8b949e', fontSize: '0.75rem' },
  toolCallPre: {
    margin: 0,
    fontFamily: 'monospace',
    fontSize: '0.77rem',
    lineHeight: 1.5,
    color: '#c9d1d9',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    overflowWrap: 'anywhere',
    overflowX: 'hidden',
  },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
  emptyState: { display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: '#8b949e' },
};
