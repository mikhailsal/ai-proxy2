import { useCallback, useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { ChatGroupBy } from '../../app/navigation';
import { useApi } from '../../hooks/useApi';
import { useAutoRefresh } from '../../hooks/autoRefreshContext';
import type { Conversation, ConversationMessage } from '../../types';
import { JsonViewer } from '../JsonViewer/JsonViewer';
import { RequestDetailContent } from '../RequestDetail/RequestDetail';
import { useBranchVisibility } from './useBranchVisibility';

const CONVERSATIONS_PAGE_SIZE = 40;

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

  const {
    data: conversationsData,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['conversations', groupBy],
    queryFn: ({ pageParam = 0 }) =>
      api.getConversations({ group_by: groupBy, limit: CONVERSATIONS_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _allPages, lastPageParam) => {
      if (lastPage.items.length < CONVERSATIONS_PAGE_SIZE) return undefined;
      return (lastPageParam as number) + CONVERSATIONS_PAGE_SIZE;
    },
    refetchInterval,
  });

  const conversations = conversationsData?.pages.flatMap(page => page.items) ?? [];

  const { data: messages, isFetching: isMessagesFetching } = useQuery({
    queryKey: ['conversation-messages', selectedGroup, groupBy],
    queryFn: () => api.getConversationMessages(selectedGroup!, groupBy),
    enabled: !!selectedGroup,
  });

  return (
    <div style={styles.container}>
      <ConversationSidebar
        conversations={conversations}
        groupBy={groupBy}
        isLoading={isLoading}
        onGroupByChange={onGroupByChange}
        onSelectGroup={onSelectGroup}
        selectedGroup={selectedGroup}
        hasNextPage={!!hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        onLoadMore={() => { fetchNextPage(); }}
      />

      <div style={styles.timeline}>
        {!selectedGroup ? (
          <div style={styles.emptyState}>Select a conversation to view messages.</div>
        ) : isMessagesFetching && !messages ? (
          <MessageLoadingSkeleton />
        ) : (
          <ChatTimeline messages={messages?.items ?? []} />
        )}
      </div>
    </div>
  );
}

function useBottomLoader(hasNextPage: boolean, isFetching: boolean, onLoadMore: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const handleScroll = useCallback(() => {
    const el = ref.current;
    if (!el || isFetching || !hasNextPage) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) onLoadMore();
  }, [hasNextPage, isFetching, onLoadMore]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  return ref;
}

function ConversationSidebar({
  conversations,
  groupBy,
  isLoading,
  onGroupByChange,
  onSelectGroup,
  selectedGroup,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
}: {
  conversations: Conversation[];
  groupBy: ChatGroupBy;
  isLoading: boolean;
  onGroupByChange: (groupBy: ChatGroupBy) => void;
  onSelectGroup: (groupKey: string) => void;
  selectedGroup: string | null;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}) {
  const listRef = useBottomLoader(hasNextPage, isFetchingNextPage, onLoadMore);

  return (
    <div style={styles.sidebar}>
      <div style={styles.sidebarHeader}>
        <span style={styles.sidebarTitle}>Conversations</span>
        <select
          style={styles.select}
          value={groupBy}
          onChange={event => onGroupByChange(event.target.value as ChatGroupBy)}
        >
          <option value="system_prompt_first_user">By System + User</option>
          <option value="system_prompt_first_user_first_assistant">By System + User + Assistant</option>
        </select>
      </div>
      {isLoading ? <div style={styles.loading}>Loading…</div> : null}
      {!isLoading ? (
        <div ref={listRef} style={styles.convList}>
          {conversations.map(conv => (
            <ConversationRow
              conversation={conv}
              isSelected={selectedGroup === conv.group_key}
              key={conv.group_key}
              onSelectGroup={onSelectGroup}
            />
          ))}
          {conversations.length === 0 ? <div style={styles.loading}>No conversations found.</div> : null}
          {isFetchingNextPage ? <div style={styles.loadingMore}>Loading more…</div> : null}
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
  if (messages.length === 0) return <div style={styles.loading}>No messages in this conversation.</div>;
  const nodeMap = new Map<string, ConversationMessage>();
  for (const m of messages) nodeMap.set(m.node_id, m);
  const roots = messages.filter(m => m.parent === null);
  if (roots.length === 0) return <div style={styles.loading}>No root messages found.</div>;
  return (
    <div style={styles.timelineInner}>
      <TreeBranch nodeIds={roots.map(r => r.node_id)} nodeMap={nodeMap} depth={0} />
    </div>
  );
}

const BRANCH_COLORS = ['#58a6ff', '#7ee787', '#d2a8ff', '#ffa657', '#ff7b72', '#79c0ff', '#f778ba', '#a5d6ff'];

function getColorForBranch(localIndex: number, depth: number): string {
  const offset = depth * 3;
  return BRANCH_COLORS[(localIndex + offset) % BRANCH_COLORS.length];
}

function TreeBranch({ nodeIds, nodeMap, depth }: { nodeIds: string[]; nodeMap: Map<string, ConversationMessage>; depth: number }) {
  if (nodeIds.length === 0) return null;
  if (nodeIds.length === 1) return <LinearChain startNodeId={nodeIds[0]} nodeMap={nodeMap} depth={depth} />;
  return <ForkContainer nodeIds={nodeIds} nodeMap={nodeMap} depth={depth} />;
}

function ForkContainer({ nodeIds, nodeMap, depth }: { nodeIds: string[]; nodeMap: Map<string, ConversationMessage>; depth: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { visible, setSentinelRef, setContentRef, heights } = useBranchVisibility(nodeIds.length, containerRef);
  const anyVisible = visible.some(Boolean);
  return (
    <div ref={containerRef} style={{ ...styles.forkContainer, alignItems: 'stretch' }}>
      {nodeIds.map((nodeId, i) => {
        const color = getColorForBranch(i, depth);
        const isVis = !anyVisible || visible[i];
        const h = heights[i] || 0;
        return (
          <div
            key={nodeId}
            style={{
              flex: isVis ? '1 1 0' : '0 0 3px',
              minWidth: isVis ? 280 : 3,
              borderLeft: `3px solid ${color}`,
              overflow: 'hidden',
              position: 'relative',
              transition: 'flex 0.35s ease, min-width 0.35s ease',
            }}
          >
            <div
              ref={el => setSentinelRef(i, el)}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: 1,
                height: h > 0 ? h : '100%',
                pointerEvents: 'none',
              }}
            />
            <div
              ref={el => setContentRef(i, el)}
              style={{
                paddingLeft: isVis ? 9 : 0,
                display: 'flex',
                flexDirection: 'column' as const,
                gap: 12,
                transition: 'padding 0.35s ease',
              }}
            >
              <BranchContent startNodeId={nodeId} nodeMap={nodeMap} depth={depth} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BranchContent({ startNodeId, nodeMap, depth }: { startNodeId: string; nodeMap: Map<string, ConversationMessage>; depth: number }) {
  const chain: ConversationMessage[] = [];
  let cur: string | null = startNodeId;
  while (cur) { const n = nodeMap.get(cur); if (!n) break; chain.push(n); cur = n.children.length === 1 ? n.children[0] : null; }
  const last = chain[chain.length - 1];
  const tailChildren = last?.children.length > 1 ? last.children : [];
  return (
    <>
      {chain.map(n => <MessageCard key={n.node_id} message={n} />)}
      {tailChildren.length > 1 ? <TreeBranch nodeIds={tailChildren} nodeMap={nodeMap} depth={depth + 1} /> : null}
    </>
  );
}

function LinearChain({ startNodeId, nodeMap, depth }: { startNodeId: string; nodeMap: Map<string, ConversationMessage>; depth: number }) {
  const chain: ConversationMessage[] = [];
  let cur: string | null = startNodeId;
  while (cur) { const n = nodeMap.get(cur); if (!n) break; chain.push(n); cur = n.children.length === 1 ? n.children[0] : null; }
  const last = chain[chain.length - 1];
  const tail = last?.children.length > 1 ? last.children : [];
  return <>{chain.map(n => <MessageCard key={n.node_id} message={n} />)}{tail.length > 1 ? <TreeBranch nodeIds={tail} nodeMap={nodeMap} depth={depth} /> : null}</>;
}

function MessageCard({ message }: { message: ConversationMessage }) {
  const [showRawRequest, setShowRawRequest] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const metaTagNames = Object.keys(message.meta_tags ?? {});
  const toolCalls = getAssistantToolCalls(message);
  const reasoning = getReasoningContent(message);

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
      {reasoning ? (
        <div style={styles.reasoningBlock}>
          <button
            style={styles.reasoningToggle}
            onClick={() => setShowReasoning(current => !current)}
          >
            <span style={styles.reasoningIcon}>&#x1F9E0;</span>
            {showReasoning ? 'Hide reasoning' : 'Show reasoning'}
            <span style={styles.reasoningLength}>({reasoning.length} chars)</span>
          </button>
          {showReasoning ? (
            <div style={styles.reasoningContent}>{reasoning}</div>
          ) : null}
        </div>
      ) : null}
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
  const isSystem = role === 'system';
  return (
    <div style={{
      ...styles.bubble,
      alignSelf: isSystem ? 'center' : 'flex-start',
      background: isSystem ? '#21262d' : '#161b22',
      borderRadius: isSystem ? '6px' : '12px 12px 12px 2px',
      maxWidth: isSystem ? '100%' : '80%',
    }}>
      <div style={styles.bubbleRole}>{role}</div>
      <div style={styles.bubbleContent}>{content}</div>
    </div>
  );
}

function MessageRawRequest({ message }: { message: ConversationMessage }) {
  return (
    <div style={styles.rawRequestPanel}>
      <RequestDetailContent requestId={message.source_request_id} />
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

function isRecord(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v); }
function asObject(v: unknown): Record<string, unknown> | null { return isRecord(v) ? v : null; }

interface AssistantToolCall { id: string | null; type: string | null; functionName: string; arguments: unknown; }

function getAssistantToolCalls(message: ConversationMessage): AssistantToolCall[] {
  if (message.role !== 'assistant' || !isRecord(message.raw_message)) return [];
  const toolCalls = message.raw_message.tool_calls;
  if (!Array.isArray(toolCalls)) return [];
  return toolCalls.filter((tc): tc is Record<string, unknown> => isRecord(tc)).map(tc => {
    const fn = asObject(tc.function);
    const raw = typeof fn?.arguments === 'string' ? fn.arguments : null;
    return { id: typeof tc.id === 'string' ? tc.id : null, type: typeof tc.type === 'string' ? tc.type : null, functionName: typeof fn?.name === 'string' ? fn.name : 'unknown_tool', arguments: raw ? (() => { try { return JSON.parse(raw); } catch { return raw; } })() : {} };
  });
}

function getReasoningContent(message: ConversationMessage): string | null {
  if (message.role !== 'assistant' || !isRecord(message.raw_message)) return null;
  const rm = message.raw_message;
  const text = (typeof rm.reasoning_content === 'string' ? rm.reasoning_content : null) ?? (typeof rm.reasoning === 'string' ? rm.reasoning : null);
  return text?.trim() || null;
}

function MessageLoadingSkeleton() {
  return (
    <div style={styles.skeletonContainer}>
      {[1, 2, 3].map(i => (
        <div key={i} style={styles.skeletonBlock}>
          <div style={{ ...styles.skeletonLine, width: '15%' }} />
          <div style={{ ...styles.skeletonLine, width: i === 2 ? '70%' : '55%' }} />
          <div style={{ ...styles.skeletonLine, width: i === 1 ? '40%' : '30%' }} />
        </div>
      ))}
    </div>
  );
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

const fc = 'column' as const, uc = 'uppercase' as const;
const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', height: '100%', overflow: 'hidden' },
  sidebar: { width: 280, borderRight: '1px solid #21262d', display: 'flex', flexDirection: fc, flexShrink: 0 },
  sidebarHeader: { padding: '8px 12px', borderBottom: '1px solid #21262d', display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 },
  sidebarTitle: { fontSize: '0.85rem', fontWeight: 600, color: '#e6edf3', flex: 1 },
  select: { background: '#0d1117', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3', padding: '2px 4px', fontSize: '0.75rem', outline: 'none' },
  convList: { flex: 1, overflowY: 'auto' },
  convItem: { padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #21262d' },
  convPreview: { fontSize: '0.82rem', color: '#e6edf3', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  convMeta: { display: 'flex', gap: 8, fontSize: '0.75rem', color: '#8b949e' },
  timeline: { flex: 1, overflow: 'hidden', display: 'flex', flexDirection: fc },
  timelineInner: { flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: fc, gap: 16 },
  requestBlock: { borderRadius: 8, border: '1px solid #21262d', padding: 12, display: 'flex', flexDirection: fc, gap: 8 },
  requestMeta: { display: 'flex', gap: 8, fontSize: '0.75rem', color: '#8b949e', flexWrap: 'wrap', alignItems: 'center' },
  reqLabel: { fontWeight: 700, color: '#58a6ff', fontSize: '0.72rem', textTransform: uc, letterSpacing: '0.05em' },
  reqModel: { color: '#e6edf3', fontWeight: 500 },
  bubble: { padding: '8px 12px', color: '#e6edf3', fontSize: '0.85rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  bubbleRole: { fontSize: '0.72rem', fontWeight: 600, color: '#8b949e', marginBottom: 4, textTransform: 'capitalize' },
  toggleDetail: { background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', fontSize: '0.75rem', alignSelf: 'flex-start', padding: '2px 0' },
  rawRequestPanel: { display: 'flex', flexDirection: fc, gap: 6, overflow: 'hidden', borderRadius: 6, border: '1px solid #21262d', background: '#0d1117' },
  toolCallsPanel: { border: '1px solid #30363d', borderRadius: 8, background: '#0d1117', padding: 10, display: 'flex', flexDirection: fc, gap: 10 },
  toolCallsTitle: { fontSize: '0.78rem', fontWeight: 700, color: '#ffa657', textTransform: uc, letterSpacing: '0.04em' },
  toolCallCard: { border: '1px solid #21262d', borderRadius: 6, padding: 10, background: '#11161d', display: 'flex', flexDirection: fc, gap: 8, overflow: 'hidden' },
  toolCallHeader: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' },
  toolCallName: { color: '#e6edf3', fontWeight: 600 }, toolCallMeta: { color: '#8b949e', fontSize: '0.75rem' },
  toolCallPre: { margin: 0, fontFamily: 'monospace', fontSize: '0.77rem', lineHeight: 1.5, color: '#c9d1d9', whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowWrap: 'anywhere', overflowX: 'hidden' },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
  loadingMore: { padding: '12px', textAlign: 'center', color: '#8b949e', fontSize: '0.78rem' },
  emptyState: { display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: '#8b949e' },
  skeletonContainer: { flex: 1, padding: 16, display: 'flex', flexDirection: fc, gap: 16, overflow: 'hidden' },
  skeletonBlock: { borderRadius: 8, border: '1px solid #21262d', padding: 16, display: 'flex', flexDirection: fc, gap: 10 },
  skeletonLine: { height: 14, borderRadius: 6, background: 'linear-gradient(90deg, #161b22 25%, #21262d 50%, #161b22 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.5s infinite ease-in-out' },
  reasoningBlock: { border: '1px solid #30363d', borderRadius: 8, background: '#0d1117', overflow: 'hidden' },
  reasoningToggle: { display: 'flex', alignItems: 'center', gap: 6, width: '100%', background: 'none', border: 'none', color: '#d2a8ff', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600, padding: '8px 12px' },
  reasoningIcon: { fontSize: '0.9rem' }, reasoningLength: { color: '#8b949e', fontWeight: 400, fontSize: '0.72rem' },
  reasoningContent: { padding: '0 12px 12px', fontSize: '0.82rem', lineHeight: 1.6, color: '#c9d1d9', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 400, overflowY: 'auto', borderTop: '1px solid #21262d' },
  forkContainer: { display: 'flex', gap: 0, padding: '4px 0', alignItems: 'flex-start' },
};
