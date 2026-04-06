import type { RequestDetail as RequestDetailType } from '../../types';
import { countTokens, selectEncoding } from '../../utils/cacheBoundary';
import type { HighlightRule } from '../JsonViewer/JsonViewer';

export function responseBodyCollapsedPaths(body: Record<string, unknown> | null): string[] {
  if (!body) return [];
  return Object.keys(body).filter(k => k !== 'choices');
}

export function requestBodyPaths(body: Record<string, unknown> | null): { collapsed: string[]; expanded: string[] } {
  if (!body) return { collapsed: [], expanded: [] };
  const collapsed: string[] = [];
  const expanded: string[] = [];
  const messages = body.messages;
  if (Array.isArray(messages) && messages.length > 0) {
    for (let i = 0; i < messages.length - 1; i++) collapsed.push(`messages.${i}`);
    expanded.push(`messages.${messages.length - 1}`);
  }
  return { collapsed, expanded };
}

function formatTokenEstimate(count: number): string {
  if (count >= 1000) return `~${(count / 1000).toFixed(1)}k tokens`;
  return `~${count} tokens`;
}

function messageToText(msg: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof msg.role === 'string') parts.push(msg.role);
  if (typeof msg.name === 'string') parts.push(msg.name);

  const content = msg.content;
  if (typeof content === 'string') {
    parts.push(content);
  } else if (Array.isArray(content)) {
    for (const part of content) {
      if (typeof part === 'object' && part !== null && (part as Record<string, unknown>).type === 'text') {
        const text = (part as Record<string, unknown>).text;
        if (typeof text === 'string') parts.push(text);
      }
    }
  }

  if (Array.isArray(msg.tool_calls)) parts.push(JSON.stringify(msg.tool_calls));
  return parts.join('\n');
}

export function buildTokenEstimateRules(data: RequestDetailType | undefined): HighlightRule[] {
  if (!data) return [];

  const body = data.request_body ?? data.client_request_body;
  if (!body || typeof body !== 'object') return [];

  const encoding = selectEncoding(data.model_requested ?? '');
  const actualInputTokens = data.input_tokens ?? 0;
  const rawToolEstimates: number[] = [];
  const rawMsgEstimates: number[] = [];

  const tools = (body as Record<string, unknown>).tools;
  if (Array.isArray(tools)) {
    for (const tool of tools) rawToolEstimates.push(countTokens(JSON.stringify(tool), encoding));
  }

  const messages = (body as Record<string, unknown>).messages;
  if (Array.isArray(messages)) {
    for (const item of messages) {
      rawMsgEstimates.push(countTokens(messageToText(item as Record<string, unknown>), encoding) + 4);
    }
  }

  const rawTotal = rawToolEstimates.reduce((sum, value) => sum + value, 0) + rawMsgEstimates.reduce((sum, value) => sum + value, 0);
  const scale = rawTotal > 0 && actualInputTokens > 0 ? actualInputTokens / rawTotal : 1;
  const rules: HighlightRule[] = [];

  if (rawToolEstimates.length > 0) {
    let toolsTotal = 0;
    for (let i = 0; i < rawToolEstimates.length; i++) {
      const calibrated = Math.round(rawToolEstimates[i] * scale);
      toolsTotal += calibrated;
      rules.push({ path: `tools.${i}`, label: formatTokenEstimate(calibrated) });
    }
    rules.push({ path: 'tools', label: formatTokenEstimate(toolsTotal) });
  }

  if (rawMsgEstimates.length > 0) {
    let messagesTotal = 0;
    for (let i = 0; i < rawMsgEstimates.length; i++) {
      const calibrated = Math.round(rawMsgEstimates[i] * scale);
      messagesTotal += calibrated;
      rules.push({ path: `messages.${i}`, label: formatTokenEstimate(calibrated) });
    }
    rules.push({ path: 'messages', label: formatTokenEstimate(messagesTotal) });
  }

  return rules;
}

export function buildResponseHighlightRules(data: RequestDetailType | undefined): HighlightRule[] {
  const body = data?.client_response_body ?? data?.response_body;
  if (!body || typeof body !== 'object' || Array.isArray(body)) return [];
  if (!Object.prototype.hasOwnProperty.call(body, 'ai_proxy_route')) return [];

  return [{
    path: 'ai_proxy_route',
    label: 'added by proxy',
    background: 'rgba(187, 128, 9, 0.15)',
  }];
}