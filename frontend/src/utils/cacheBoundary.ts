import { Tiktoken } from 'js-tiktoken/lite';
import cl100k_base from 'js-tiktoken/ranks/cl100k_base';
import o200k_base from 'js-tiktoken/ranks/o200k_base';

export type CacheStatus = 'cached' | 'partial' | 'uncached';

export interface MessageCacheInfo {
  index: number;
  cacheStatus: CacheStatus;
  cachedFraction: number;
}

export interface CacheBoundaryResult {
  messages: MessageCacheInfo[];
  boundaryIndex: number;
  tokenizerUsed: string;
}

interface ChatMessage {
  role?: string;
  content?: string | Array<{ type?: string; text?: string }>;
  tool_calls?: unknown[];
  name?: string;
}

type EncodingName = 'o200k_base' | 'cl100k_base' | 'charBased';

const DRIFT_TOLERANCE_EXACT = 0.15;
const DRIFT_TOLERANCE_APPROX = 0.50;

const ENCODING_RANKS: Record<string, Record<string, string | string[]>> = {
  o200k_base,
  cl100k_base,
};

let encoderCache: Record<string, Tiktoken> = {};

export function resetEncoderCache(): void {
  encoderCache = {};
}

function getEncoder(encoding: 'o200k_base' | 'cl100k_base'): Tiktoken {
  if (!encoderCache[encoding]) {
    encoderCache[encoding] = new Tiktoken(ENCODING_RANKS[encoding]);
  }
  return encoderCache[encoding];
}

export function selectEncoding(model: string): EncodingName {
  const lower = model.toLowerCase();

  if (
    lower.includes('gpt-4o') ||
    lower.includes('gpt-4.1') ||
    lower.includes('gpt-4.5') ||
    lower.includes('gpt-5') ||
    lower.includes('o1') ||
    lower.includes('o3') ||
    lower.includes('o4') ||
    lower.includes('chatgpt') ||
    lower.includes('gpt-oss')
  ) {
    return 'o200k_base';
  }

  if (
    lower.includes('gpt-4') ||
    lower.includes('gpt-3.5') ||
    lower.includes('claude') ||
    lower.includes('gemini') ||
    lower.includes('mistral')
  ) {
    return 'cl100k_base';
  }

  return 'charBased';
}

export function countTokens(text: string, encoding: EncodingName): number {
  if (encoding === 'charBased') {
    return Math.ceil(text.length / 3.5);
  }
  const enc = getEncoder(encoding);
  return enc.encode(text).length;
}

function messageToText(msg: ChatMessage): string {
  const parts: string[] = [];

  if (msg.role) {
    parts.push(msg.role);
  }
  if (msg.name) {
    parts.push(msg.name);
  }

  if (typeof msg.content === 'string') {
    parts.push(msg.content);
  } else if (Array.isArray(msg.content)) {
    for (const part of msg.content) {
      if (typeof part === 'object' && part !== null && part.type === 'text' && typeof part.text === 'string') {
        parts.push(part.text);
      }
    }
  }

  if (Array.isArray(msg.tool_calls)) {
    parts.push(JSON.stringify(msg.tool_calls));
  }

  return parts.join('\n');
}

const PER_MESSAGE_OVERHEAD = 4;

export function estimatePrefixOverhead(
  requestBody: Record<string, unknown>,
  encoding: EncodingName,
): number {
  let overhead = 0;

  const tools = requestBody.tools;
  if (Array.isArray(tools) && tools.length > 0) {
    const toolsText = JSON.stringify(tools);
    overhead += countTokens(toolsText, encoding);
  }

  const responseFormat = requestBody.response_format;
  if (responseFormat && typeof responseFormat === 'object') {
    const schema = (responseFormat as Record<string, unknown>).json_schema;
    if (schema) {
      overhead += countTokens(JSON.stringify(schema), encoding);
    }
  }

  const toolChoice = requestBody.tool_choice;
  if (toolChoice && typeof toolChoice === 'object') {
    overhead += countTokens(JSON.stringify(toolChoice), encoding);
  }

  return overhead;
}

function classifyBoundaryMessage(fraction: number, driftTolerance: number): { status: CacheStatus; frac: number } {
  if (fraction >= 1 - driftTolerance) return { status: 'cached', frac: 1 };
  if (fraction <= driftTolerance) return { status: 'uncached', frac: 0 };
  return { status: 'partial', frac: fraction };
}

function fillUncached(result: MessageCacheInfo[], from: number, to: number) {
  for (let j = from; j < to; j++) result.push({ index: j, cacheStatus: 'uncached', cachedFraction: 0 });
}

function scaleTokenCounts(messages: ChatMessage[], encoding: EncodingName, prefixOverhead: number, totalInputTokens: number) {
  const raw = messages.map(msg => countTokens(messageToText(msg), encoding) + PER_MESSAGE_OVERHEAD);
  const estTotal = raw.reduce((s, c) => s + c, 0) + prefixOverhead;
  const factor = totalInputTokens > 0 && estTotal > 0 ? totalInputTokens / estTotal : 1;
  return { scaled: raw.map(c => Math.round(c * factor)), scaledOverhead: Math.round(prefixOverhead * factor) };
}

export function computeCacheBoundary(
  messages: ChatMessage[], cachedTokens: number, totalInputTokens: number,
  model: string, requestBody?: Record<string, unknown>,
): CacheBoundaryResult {
  if (cachedTokens <= 0 || messages.length === 0) {
    return { messages: messages.map((_, i) => ({ index: i, cacheStatus: 'uncached' as CacheStatus, cachedFraction: 0 })), boundaryIndex: -1, tokenizerUsed: 'none' };
  }

  const encoding = selectEncoding(model);
  const drift = encoding === 'charBased' ? DRIFT_TOLERANCE_APPROX : DRIFT_TOLERANCE_EXACT;
  const overhead = requestBody ? estimatePrefixOverhead(requestBody, encoding) : 0;
  const { scaled, scaledOverhead } = scaleTokenCounts(messages, encoding, overhead, totalInputTokens);
  const cachedForMsgs = Math.max(0, cachedTokens - scaledOverhead);

  const result: MessageCacheInfo[] = [];
  let cumul = 0;
  let boundaryIndex = -1;

  for (let i = 0; i < messages.length; i++) {
    const prev = cumul;
    cumul += scaled[i];

    if (cumul <= cachedForMsgs) {
      result.push({ index: i, cacheStatus: 'cached', cachedFraction: 1 });
      const gap = cachedForMsgs - cumul;
      if (cumul === cachedForMsgs || (i < messages.length - 1 && gap > 0 && gap < scaled[i] * drift)) {
        boundaryIndex = i;
        fillUncached(result, i + 1, messages.length);
        break;
      }
    } else {
      const frac = scaled[i] > 0 ? (cachedForMsgs - prev) / scaled[i] : 0;
      const cls = classifyBoundaryMessage(frac, drift);
      result.push({ index: i, cacheStatus: cls.status, cachedFraction: cls.frac });
      boundaryIndex = i;
      fillUncached(result, i + 1, messages.length);
      break;
    }
  }

  return { messages: result, boundaryIndex, tokenizerUsed: encoding };
}

export function extractCachedTokensFromRequest(
  requestDetail: {
    response_body?: Record<string, unknown> | null;
    client_response_body?: Record<string, unknown> | null;
    input_tokens?: number | null;
    cached_input_tokens?: number | null;
    model_requested?: string | null;
    request_body?: Record<string, unknown> | null;
    client_request_body?: Record<string, unknown> | null;
  },
): { cachedTokens: number; inputTokens: number; model: string; messages: ChatMessage[]; requestBody: Record<string, unknown> } | null {
  const cachedTokens = requestDetail.cached_input_tokens;
  const inputTokens = requestDetail.input_tokens;
  const model = requestDetail.model_requested;

  if (!cachedTokens || cachedTokens <= 0 || !inputTokens || !model) {
    return null;
  }

  const body = requestDetail.request_body ?? requestDetail.client_request_body;
  if (!body || typeof body !== 'object') {
    return null;
  }

  const bodyRecord = body as Record<string, unknown>;
  const messages = bodyRecord.messages;
  if (!Array.isArray(messages)) {
    return null;
  }

  return {
    cachedTokens,
    inputTokens,
    model,
    messages: messages as ChatMessage[],
    requestBody: bodyRecord,
  };
}
