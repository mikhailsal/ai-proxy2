import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../hooks/useApi';
import type { RequestDetail } from '../../types';

export function ChatView() {
  const api = useApi();
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [groupBy, setGroupBy] = useState('system_prompt');

  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations', groupBy],
    queryFn: () => api.getConversations({ group_by: groupBy, limit: 100 }),
  });

  const { data: messages } = useQuery({
    queryKey: ['conversation-messages', selectedGroup, groupBy],
    queryFn: () => api.getConversationMessages(selectedGroup!, groupBy),
    enabled: !!selectedGroup,
  });

  return (
    <div style={styles.container}>
      <div style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <span style={styles.sidebarTitle}>Conversations</span>
          <select
            style={styles.select}
            value={groupBy}
            onChange={e => { setGroupBy(e.target.value); setSelectedGroup(null); }}
          >
            <option value="system_prompt">By System Prompt</option>
            <option value="client">By Client</option>
            <option value="model">By Model</option>
          </select>
        </div>
        {isLoading ? (
          <div style={styles.loading}>Loading…</div>
        ) : (
          <div style={styles.convList}>
            {(conversations?.items ?? []).map(conv => (
              <div
                key={conv.group_key}
                style={{
                  ...styles.convItem,
                  background: selectedGroup === conv.group_key ? '#21262d' : 'transparent',
                  borderLeft: selectedGroup === conv.group_key ? '2px solid #58a6ff' : '2px solid transparent',
                }}
                onClick={() => setSelectedGroup(conv.group_key)}
              >
                <div style={styles.convPreview}>
                  {(conv.group_key ?? 'Unknown').slice(0, 60)}
                  {conv.group_key?.length > 60 ? '…' : ''}
                </div>
                <div style={styles.convMeta}>
                  <span>{conv.message_count} messages</span>
                  <span>{conv.models_used?.slice(0, 2).join(', ')}</span>
                </div>
              </div>
            ))}
            {(conversations?.items ?? []).length === 0 && (
              <div style={styles.loading}>No conversations found.</div>
            )}
          </div>
        )}
      </div>

      <div style={styles.timeline}>
        {!selectedGroup ? (
          <div style={styles.emptyState}>Select a conversation to view messages.</div>
        ) : (
          <ChatTimeline requests={messages?.items ?? []} />
        )}
      </div>
    </div>
  );
}

function ChatTimeline({ requests }: { requests: RequestDetail[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (requests.length === 0) {
    return <div style={styles.loading}>No messages in this conversation.</div>;
  }

  // Build message timeline from requests
  const timeline = buildTimeline(requests);

  return (
    <div style={styles.timelineInner}>
      {timeline.map(entry => (
        <div key={entry.requestId} style={styles.requestBlock}>
          <div style={styles.requestMeta}>
            <span style={styles.reqLabel}>Request</span>
            <span style={styles.reqTime}>{new Date(entry.timestamp).toLocaleString()}</span>
            <span style={styles.reqModel}>{entry.model}</span>
            {entry.latency && <span style={styles.reqLatency}>{Math.round(entry.latency)}ms</span>}
            {entry.tokens && <span style={styles.reqTokens}>{entry.tokens} tokens</span>}
          </div>
          {entry.messages.map((msg, i) => (
            <ChatBubble key={i} role={msg.role} content={msg.content} />
          ))}
          {entry.response && (
            <ChatBubble role="assistant" content={entry.response} />
          )}
          <button
            style={styles.toggleDetail}
            onClick={() => setExpandedId(expandedId === entry.requestId ? null : entry.requestId)}
          >
            {expandedId === entry.requestId ? 'Hide raw' : 'Show raw'}
          </button>
          {expandedId === entry.requestId && (
            <pre style={styles.rawPre}>
              {JSON.stringify(entry.rawBody, null, 2)}
            </pre>
          )}
        </div>
      ))}
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

interface TimelineEntry {
  requestId: string;
  timestamp: string;
  model: string | null;
  latency: number | null;
  tokens: number | null;
  messages: Array<{ role: string; content: string }>;
  response: string | null;
  rawBody: unknown;
}

function buildTimeline(requests: RequestDetail[]): TimelineEntry[] {
  return requests.map(req => {
    const messages: Array<{ role: string; content: string }> = [];
    const body = req.request_body as Record<string, unknown> | null;
    if (body?.messages && Array.isArray(body.messages)) {
      for (const msg of body.messages as Array<{ role: string; content: unknown }>) {
        messages.push({
          role: msg.role ?? 'unknown',
          content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
        });
      }
    }

    const respBody = req.response_body as Record<string, unknown> | null;
    let response: string | null = null;
    if (respBody?.choices && Array.isArray(respBody.choices)) {
      const choice = (respBody.choices as Array<{ message?: { content?: string } }>)[0];
      response = choice?.message?.content ?? null;
    }

    return {
      requestId: req.id,
      timestamp: req.timestamp,
      model: req.model_resolved ?? req.model_requested,
      latency: req.latency_ms,
      tokens: req.total_tokens,
      messages,
      response,
      rawBody: body,
    };
  });
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
  rawPre: { background: '#0d1117', borderRadius: 4, padding: 8, fontSize: '0.75rem', color: '#8b949e', overflowX: 'auto', margin: 0 },
  loading: { padding: '2rem', textAlign: 'center', color: '#8b949e' },
  emptyState: { display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: '#8b949e' },
};
