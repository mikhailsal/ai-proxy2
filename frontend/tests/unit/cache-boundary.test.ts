import { afterEach, describe, expect, it } from 'vitest';
import {
  computeCacheBoundary,
  countTokens,
  estimatePrefixOverhead,
  extractCachedTokensFromRequest,
  resetEncoderCache,
  selectEncoding,
} from '../../src/utils/cacheBoundary';

afterEach(() => {
  resetEncoderCache();
});

describe('selectEncoding', () => {
  it('selects o200k_base for GPT-4o models', () => {
    expect(selectEncoding('openai/gpt-4o')).toBe('o200k_base');
    expect(selectEncoding('openai/gpt-4o-mini')).toBe('o200k_base');
    expect(selectEncoding('gpt-4.5-turbo')).toBe('o200k_base');
    expect(selectEncoding('gpt-5.1-codex-mini')).toBe('o200k_base');
    expect(selectEncoding('openai/gpt-oss-120b')).toBe('o200k_base');
  });

  it('selects o200k_base for o1/o3/o4 models', () => {
    expect(selectEncoding('openai/o1-preview')).toBe('o200k_base');
    expect(selectEncoding('openai/o3-mini')).toBe('o200k_base');
    expect(selectEncoding('openai/o4-mini')).toBe('o200k_base');
  });

  it('selects cl100k_base for GPT-4 non-o and Claude models', () => {
    expect(selectEncoding('openai/gpt-4')).toBe('cl100k_base');
    expect(selectEncoding('gpt-3.5-turbo')).toBe('cl100k_base');
    expect(selectEncoding('anthropic/claude-sonnet-4.6')).toBe('cl100k_base');
    expect(selectEncoding('google/gemini-2.5-flash')).toBe('cl100k_base');
    expect(selectEncoding('mistralai/mistral-small-3.2-24b-instruct')).toBe('cl100k_base');
  });

  it('falls back to charBased for unknown models', () => {
    expect(selectEncoding('deepseek/deepseek-v3.2')).toBe('charBased');
    expect(selectEncoding('qwen/qwen3-coder')).toBe('charBased');
    expect(selectEncoding('some-unknown-model')).toBe('charBased');
  });
});

describe('countTokens', () => {
  it('counts tokens with o200k_base encoding', () => {
    const count = countTokens('hello world', 'o200k_base');
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThan(10);
  });

  it('counts tokens with cl100k_base encoding', () => {
    const count = countTokens('hello world', 'cl100k_base');
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThan(10);
  });

  it('approximates tokens for charBased encoding', () => {
    const count = countTokens('a'.repeat(35), 'charBased');
    expect(count).toBe(10);
  });

  it('handles empty strings', () => {
    expect(countTokens('', 'o200k_base')).toBe(0);
    expect(countTokens('', 'cl100k_base')).toBe(0);
    expect(countTokens('', 'charBased')).toBe(0);
  });
});

describe('computeCacheBoundary', () => {
  const messages = [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'user', content: 'Hello, how are you?' },
    { role: 'assistant', content: 'I am doing well, thank you!' },
    { role: 'user', content: 'What is the weather?' },
  ];

  it('marks all as uncached when cachedTokens is 0', () => {
    const result = computeCacheBoundary(messages, 0, 100, 'gpt-4o');
    expect(result.boundaryIndex).toBe(-1);
    for (const msg of result.messages) {
      expect(msg.cacheStatus).toBe('uncached');
    }
  });

  it('marks all as uncached with empty messages', () => {
    const result = computeCacheBoundary([], 50, 100, 'gpt-4o');
    expect(result.messages).toHaveLength(0);
    expect(result.boundaryIndex).toBe(-1);
  });

  it('marks first message as cached when cache covers first message only', () => {
    const twoMessages = [
      { role: 'system', content: 'A'.repeat(500) },
      { role: 'user', content: 'B'.repeat(500) },
    ];
    const totalTokens = 300;
    const cachedTokens = 140;

    const result = computeCacheBoundary(twoMessages, cachedTokens, totalTokens, 'gpt-4o');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[0].cacheStatus).toBe('cached');
    expect(['uncached', 'partial']).toContain(result.messages[1].cacheStatus);
    expect(result.boundaryIndex).toBeGreaterThanOrEqual(0);
  });

  it('marks all messages as cached when cache covers everything', () => {
    const totalTokens = 50;
    const cachedTokens = 50;

    const result = computeCacheBoundary(messages, cachedTokens, totalTokens, 'gpt-4o');

    for (const msg of result.messages) {
      expect(msg.cacheStatus).toBe('cached');
    }
  });

  it('identifies a partial message at the boundary', () => {
    const twoMessages = [
      { role: 'system', content: 'X'.repeat(100) },
      { role: 'user', content: 'Y'.repeat(400) },
    ];
    const totalTokens = 150;
    const cachedTokens = 70;

    const result = computeCacheBoundary(twoMessages, cachedTokens, totalTokens, 'gpt-4o');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[0].cacheStatus).toBe('cached');
    const secondStatus = result.messages[1].cacheStatus;
    expect(['partial', 'uncached']).toContain(secondStatus);
  });

  it('uses correct tokenizer name', () => {
    const result = computeCacheBoundary(messages, 10, 100, 'gpt-4o');
    expect(result.tokenizerUsed).toBe('o200k_base');

    const result2 = computeCacheBoundary(messages, 10, 100, 'deepseek/v3');
    expect(result2.tokenizerUsed).toBe('charBased');
  });

  it('handles negative cachedTokens', () => {
    const result = computeCacheBoundary(messages, -5, 100, 'gpt-4o');
    expect(result.boundaryIndex).toBe(-1);
    for (const msg of result.messages) {
      expect(msg.cacheStatus).toBe('uncached');
    }
  });

  it('handles messages with array content', () => {
    const arrayContentMessages = [
      { role: 'user', content: [{ type: 'text', text: 'Hello there' }] },
      { role: 'assistant', content: 'Hi!' },
    ];

    const result = computeCacheBoundary(arrayContentMessages, 5, 20, 'gpt-4o');
    expect(result.messages).toHaveLength(2);
  });

  it('handles messages with tool_calls', () => {
    const toolMessages = [
      { role: 'user', content: 'call a function' },
      { role: 'assistant', content: '', tool_calls: [{ id: 'call_1', function: { name: 'test' } }] },
    ];

    const result = computeCacheBoundary(toolMessages, 5, 30, 'gpt-4o');
    expect(result.messages).toHaveLength(2);
  });

  it('snaps to cached when drift is within tolerance at message boundary', () => {
    const msgs = [
      { role: 'system', content: 'A'.repeat(1000) },
      { role: 'user', content: 'B'.repeat(1000) },
      { role: 'assistant', content: 'C'.repeat(100) },
    ];
    const totalTokens = 600;
    const firstMsgApprox = 300;
    const cachedJustBeyondFirst = firstMsgApprox + 10;

    const result = computeCacheBoundary(msgs, cachedJustBeyondFirst, totalTokens, 'gpt-4o');
    expect(result.messages.length).toBe(3);
    expect(result.messages[0].cacheStatus).toBe('cached');
  });

  it('marks boundary message as uncached when fraction is very small', () => {
    const msgs = [
      { role: 'system', content: 'X'.repeat(2000) },
      { role: 'user', content: 'Y'.repeat(2000) },
    ];
    const totalTokens = 1200;
    const cachedTokens = totalTokens / 2 + 5;

    const result = computeCacheBoundary(msgs, cachedTokens, totalTokens, 'gpt-4o');
    expect(result.messages.length).toBe(2);
    expect(result.messages[0].cacheStatus).toBe('cached');
  });

  it('marks boundary message as cached when fraction is nearly 1', () => {
    const msgs = [
      { role: 'system', content: 'Short' },
      { role: 'user', content: 'Also short' },
    ];
    const totalTokens = 20;
    const cachedTokens = 19;

    const result = computeCacheBoundary(msgs, cachedTokens, totalTokens, 'gpt-4o');
    for (const msg of result.messages) {
      expect(['cached', 'partial']).toContain(msg.cacheStatus);
    }
  });

  it('handles single message', () => {
    const msgs = [{ role: 'user', content: 'Hello' }];
    const result = computeCacheBoundary(msgs, 3, 5, 'gpt-4o');
    expect(result.messages).toHaveLength(1);
    expect(['cached', 'partial']).toContain(result.messages[0].cacheStatus);
    expect(result.boundaryIndex).toBe(0);
  });

  it('handles messages with no content', () => {
    const msgs = [
      { role: 'system' },
      { role: 'user', content: 'hello' },
    ];
    const result = computeCacheBoundary(msgs, 3, 10, 'gpt-4o');
    expect(result.messages).toHaveLength(2);
  });

  it('handles charBased encoding for unknown models', () => {
    const msgs = [
      { role: 'system', content: 'A'.repeat(350) },
      { role: 'user', content: 'B'.repeat(350) },
    ];
    const result = computeCacheBoundary(msgs, 50, 200, 'qwen/qwen3-coder');
    expect(result.tokenizerUsed).toBe('charBased');
    expect(result.messages).toHaveLength(2);
    expect(['cached', 'partial']).toContain(result.messages[0].cacheStatus);
    expect(['uncached', 'partial']).toContain(result.messages[1].cacheStatus);
  });

  it('handles zero totalInputTokens gracefully', () => {
    const msgs = [
      { role: 'user', content: 'hello' },
    ];
    const result = computeCacheBoundary(msgs, 5, 0, 'gpt-4o');
    expect(result.messages).toHaveLength(1);
  });

  it('handles message with name field', () => {
    const msgs = [
      { role: 'system', name: 'helper', content: 'Be helpful' },
      { role: 'user', content: 'Hello' },
    ];
    const result = computeCacheBoundary(msgs, 5, 20, 'gpt-4o');
    expect(result.messages).toHaveLength(2);
  });

  it('snaps exact boundary when cumulative equals cachedTokens', () => {
    const msgs = [
      { role: 'system', content: 'AA' },
      { role: 'user', content: 'BB' },
      { role: 'assistant', content: 'CC' },
    ];
    const enc = selectEncoding('gpt-4o');
    const t0 = countTokens('system\nAA', enc) + 4;
    const t1 = countTokens('user\nBB', enc) + 4;
    const t2 = countTokens('assistant\nCC', enc) + 4;
    const total = t0 + t1 + t2;
    const cachedExact = t0 + t1;

    const result = computeCacheBoundary(msgs, cachedExact, total, 'gpt-4o');
    expect(result.messages).toHaveLength(3);
    expect(result.messages[0].cacheStatus).toBe('cached');
    expect(result.messages[1].cacheStatus).toBe('cached');
    expect(result.messages[2].cacheStatus).toBe('uncached');
    expect(result.boundaryIndex).toBe(1);
  });

  it('marks boundary as uncached when fraction is tiny', () => {
    const msgs = [
      { role: 'system', content: 'X'.repeat(2000) },
      { role: 'user', content: 'Y'.repeat(2000) },
    ];
    const enc = selectEncoding('gpt-4o');
    const t0 = countTokens('system\n' + 'X'.repeat(2000), enc) + 4;
    const t1 = countTokens('user\n' + 'Y'.repeat(2000), enc) + 4;
    const total = t0 + t1;
    const cachedTokens = t0 + 2;

    const result = computeCacheBoundary(msgs, cachedTokens, total, 'gpt-4o');
    expect(result.messages).toHaveLength(2);
    expect(result.messages[0].cacheStatus).toBe('cached');
    expect(result.messages[1].cacheStatus).toBe('uncached');
  });
});

describe('estimatePrefixOverhead', () => {
  it('returns 0 for request with no tools or schema', () => {
    const overhead = estimatePrefixOverhead({ messages: [] }, 'o200k_base');
    expect(overhead).toBe(0);
  });

  it('counts tokens for tools array', () => {
    const body = {
      messages: [],
      tools: [
        { type: 'function', function: { name: 'get_weather', parameters: { type: 'object', properties: { city: { type: 'string' } } } } },
      ],
    };
    const overhead = estimatePrefixOverhead(body, 'o200k_base');
    expect(overhead).toBeGreaterThan(10);
  });

  it('counts tokens for response_format json_schema', () => {
    const body = {
      messages: [],
      response_format: {
        type: 'json_schema',
        json_schema: { name: 'output', schema: { type: 'object', properties: { result: { type: 'string' } } } },
      },
    };
    const overhead = estimatePrefixOverhead(body, 'cl100k_base');
    expect(overhead).toBeGreaterThan(5);
  });

  it('counts tokens for tool_choice object', () => {
    const body = {
      messages: [],
      tool_choice: { type: 'function', function: { name: 'get_weather' } },
    };
    const overhead = estimatePrefixOverhead(body, 'o200k_base');
    expect(overhead).toBeGreaterThan(3);
  });

  it('handles charBased encoding', () => {
    const body = {
      messages: [],
      tools: [{ type: 'function', function: { name: 'test' } }],
    };
    const overhead = estimatePrefixOverhead(body, 'charBased');
    expect(overhead).toBeGreaterThan(0);
  });
});

describe('computeCacheBoundary with requestBody', () => {
  it('subtracts tools overhead from cached tokens applied to messages', () => {
    const tools = [
      { type: 'function', function: { name: 'get_weather', parameters: { type: 'object', properties: { city: { type: 'string' } } } } },
      { type: 'function', function: { name: 'search', parameters: { type: 'object', properties: { query: { type: 'string' } } } } },
    ];
    const messages = [
      { role: 'system', content: 'A'.repeat(500) },
      { role: 'user', content: 'B'.repeat(500) },
      { role: 'assistant', content: 'C'.repeat(100) },
      { role: 'user', content: 'What is the weather?' },
    ];
    const requestBody = { tools, messages };
    const totalTokens = 400;
    const cachedTokens = 300;

    const result = computeCacheBoundary(messages, cachedTokens, totalTokens, 'gpt-4o', requestBody);

    expect(result.messages.length).toBe(4);
    const lastCached = result.messages.findIndex(m => m.cacheStatus !== 'cached');
    expect(lastCached).toBeGreaterThan(0);
    expect(lastCached).toBeLessThan(4);
  });

  it('works without requestBody (backward compat)', () => {
    const messages = [
      { role: 'system', content: 'Hello' },
      { role: 'user', content: 'World' },
    ];
    const result = computeCacheBoundary(messages, 5, 20, 'gpt-4o');
    expect(result.messages.length).toBe(2);
  });
});

describe('extractCachedTokensFromRequest', () => {
  it('returns null when no cached tokens', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: null,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: { messages: [{ role: 'user', content: 'hi' }] },
    });
    expect(result).toBeNull();
  });

  it('returns null when cached tokens is 0', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 0,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: { messages: [{ role: 'user', content: 'hi' }] },
    });
    expect(result).toBeNull();
  });

  it('returns null when no input_tokens', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: null,
      model_requested: 'gpt-4o',
      request_body: { messages: [{ role: 'user', content: 'hi' }] },
    });
    expect(result).toBeNull();
  });

  it('returns null when no model', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: 100,
      model_requested: null,
      request_body: { messages: [{ role: 'user', content: 'hi' }] },
    });
    expect(result).toBeNull();
  });

  it('returns null when no messages in request body', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: { prompt: 'hi' },
    });
    expect(result).toBeNull();
  });

  it('returns null when request_body is null', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: null,
    });
    expect(result).toBeNull();
  });

  it('extracts from client_request_body when request_body is missing', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: null,
      client_request_body: { messages: [{ role: 'user', content: 'hi' }] },
    });
    expect(result).not.toBeNull();
    expect(result!.cachedTokens).toBe(50);
    expect(result!.inputTokens).toBe(100);
    expect(result!.model).toBe('gpt-4o');
    expect(result!.messages).toHaveLength(1);
    expect(result!.requestBody).toBeDefined();
    expect(result!.requestBody.messages).toHaveLength(1);
  });

  it('extracts valid data from request_body', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 30,
      input_tokens: 80,
      model_requested: 'anthropic/claude-sonnet-4.6',
      request_body: {
        messages: [
          { role: 'system', content: 'Be helpful' },
          { role: 'user', content: 'Hello' },
        ],
      },
    });
    expect(result).not.toBeNull();
    expect(result!.cachedTokens).toBe(30);
    expect(result!.inputTokens).toBe(80);
    expect(result!.model).toBe('anthropic/claude-sonnet-4.6');
    expect(result!.messages).toHaveLength(2);
    expect(result!.requestBody).toBeDefined();
  });

  it('includes tools in requestBody when present', () => {
    const result = extractCachedTokensFromRequest({
      cached_input_tokens: 50,
      input_tokens: 100,
      model_requested: 'gpt-4o',
      request_body: {
        messages: [{ role: 'user', content: 'hi' }],
        tools: [{ type: 'function', function: { name: 'test' } }],
      },
    });
    expect(result).not.toBeNull();
    expect(result!.requestBody.tools).toBeDefined();
  });
});
