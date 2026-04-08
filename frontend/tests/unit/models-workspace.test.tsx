import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  formatList,
  formatContextLength,
  formatCreated,
  formatPricePerMillion,
  getInputModalities,
  getInputPrice,
  getOutputPrice,
  getOutputModalities,
  getPinnedProviders,
  getSupportedParameters,
  getTokenizer,
  modelMatchesSearch,
  parsePrice,
  sortModels,
} from '../../src/app/modelsUtils';
import type { ProxyModel } from '../../src/types';

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  vi.doUnmock('../../src/app/ModelsWorkspace');
  document.body.innerHTML = '';
});

function makeModel(overrides: Partial<ProxyModel> = {}): ProxyModel {
  return {
    id: overrides.id ?? 'openai/gpt-4o',
    provider: overrides.provider ?? 'kilocode',
    mapped_model: overrides.mapped_model ?? 'openai/gpt-4o',
    owned_by: overrides.owned_by ?? null,
    context_length: overrides.context_length ?? null,
    pricing: overrides.pricing ?? null,
    created: overrides.created ?? null,
    name: overrides.name ?? null,
    description: overrides.description ?? null,
    ...overrides,
  };
}

function makeModelWithPricing(): ProxyModel {
  return makeModel({
    id: 'anthropic/claude-3-haiku',
    provider: 'openrouter',
    context_length: 200000,
    pricing: { prompt: '0.00000025', completion: '0.00000125' },
    created: 1714521600,
    name: 'Claude 3 Haiku',
    description: 'Fast model',
    architecture: {
      input_modalities: ['text'],
      output_modalities: ['text'],
      tokenizer: 'cl100k_base',
    },
    supported_parameters: ['temperature', 'top_p', 'tools'],
    pinned_providers: ['anthropic'],
  });
}

describe('parsePrice', () => {
  it('returns null for null/undefined', () => {
    expect(parsePrice(null)).toBeNull();
    expect(parsePrice(undefined)).toBeNull();
  });

  it('parses numeric strings', () => {
    expect(parsePrice('0.000001')).toBeCloseTo(0.000001);
    expect(parsePrice('1.5')).toBe(1.5);
  });

  it('returns numeric values as-is', () => {
    expect(parsePrice(0.5)).toBe(0.5);
  });

  it('returns null for non-numeric strings', () => {
    expect(parsePrice('not-a-number')).toBeNull();
    expect(parsePrice('')).toBeNull();
  });
});

describe('formatPricePerMillion', () => {
  it('returns em dash for null/undefined', () => {
    expect(formatPricePerMillion(null)).toBe('—');
    expect(formatPricePerMillion(undefined)).toBe('—');
  });

  it('formats large prices with 2 decimals', () => {
    // $0.000005/token * 1M = $5.00
    expect(formatPricePerMillion(0.000005)).toBe('$5.00');
  });

  it('formats sub-dollar prices with 4 decimals', () => {
    // $5e-7/token * 1M = $0.5 (between 0.001 and 1, uses toFixed(4))
    expect(formatPricePerMillion(5e-7)).toBe('$0.5000');
  });

  it('formats zero price as $0', () => {
    expect(formatPricePerMillion(0)).toBe('$0');
  });

  it('uses exponential for very small prices', () => {
    const result = formatPricePerMillion(0.0000000001);
    expect(result).toContain('$');
    expect(result).toContain('e');
  });
});

describe('formatContextLength', () => {
  it('returns em dash for null/undefined', () => {
    expect(formatContextLength(null)).toBe('—');
    expect(formatContextLength(undefined)).toBe('—');
  });

  it('formats millions with M suffix', () => {
    expect(formatContextLength(1000000)).toBe('1.0M');
    expect(formatContextLength(2500000)).toBe('2.5M');
  });

  it('formats thousands with K suffix', () => {
    expect(formatContextLength(128000)).toBe('128K');
    expect(formatContextLength(32768)).toBe('33K');
  });

  it('returns raw value for small numbers', () => {
    expect(formatContextLength(512)).toBe('512');
  });
});

describe('formatCreated', () => {
  it('returns em dash for null/undefined', () => {
    expect(formatCreated(null)).toBe('—');
    expect(formatCreated(undefined)).toBe('—');
  });

  it('formats a unix timestamp as a date string', () => {
    const result = formatCreated(1714521600); // ~May 2024
    expect(result).toMatch(/\d{4}/);
    expect(result).toContain('2024');
  });
});

describe('getInputPrice / getOutputPrice', () => {
  it('returns null when no pricing', () => {
    expect(getInputPrice(makeModel())).toBeNull();
    expect(getOutputPrice(makeModel())).toBeNull();
  });

  it('reads prompt/completion fields', () => {
    const m = makeModel({ pricing: { prompt: '0.001', completion: '0.002' } });
    expect(getInputPrice(m)).toBeCloseTo(0.001);
    expect(getOutputPrice(m)).toBeCloseTo(0.002);
  });

  it('falls back to input/output fields', () => {
    const m = makeModel({ pricing: { input: 0.003, output: 0.004 } });
    expect(getInputPrice(m)).toBeCloseTo(0.003);
    expect(getOutputPrice(m)).toBeCloseTo(0.004);
  });
});

describe('model metadata helpers', () => {
  it('reads modalities, tokenizer, parameters, and pinned providers', () => {
    const model = makeModelWithPricing();

    expect(getInputModalities(model)).toEqual(['text']);
    expect(getOutputModalities(model)).toEqual(['text']);
    expect(getTokenizer(model)).toBe('cl100k_base');
    expect(getSupportedParameters(model)).toEqual(['temperature', 'top_p', 'tools']);
    expect(getPinnedProviders(model)).toEqual(['anthropic']);
  });

  it('formats metadata lists and request limits', () => {
    expect(formatList(['text', 'image'])).toBe('text, image');
    expect(formatList([])).toBe('—');
  });
});

describe('modelMatchesSearch', () => {
  it('returns true for empty query', () => {
    expect(modelMatchesSearch(makeModel(), '')).toBe(true);
  });

  it('matches model id', () => {
    const m = makeModel({ id: 'openai/gpt-4o' });
    expect(modelMatchesSearch(m, 'gpt-4o')).toBe(true);
    expect(modelMatchesSearch(m, 'claude')).toBe(false);
  });

  it('matches provider', () => {
    const m = makeModel({ provider: 'openrouter' });
    expect(modelMatchesSearch(m, 'openrouter')).toBe(true);
  });

  it('matches name and description', () => {
    const m = makeModel({ name: 'Claude 3 Haiku', description: 'Fast small model' });
    expect(modelMatchesSearch(m, 'haiku')).toBe(true);
    expect(modelMatchesSearch(m, 'small model')).toBe(true);
  });

  it('matches added metadata columns', () => {
    const m = makeModel({
      architecture: { input_modalities: ['text', 'image'], output_modalities: ['text'], tokenizer: 'o200k' },
      supported_parameters: ['temperature', 'tools'],
      pinned_providers: ['openai'],
    });

    expect(modelMatchesSearch(m, 'image')).toBe(true);
    expect(modelMatchesSearch(m, 'tools')).toBe(true);
    expect(modelMatchesSearch(m, 'o200k')).toBe(true);
  });

  it('is case-insensitive', () => {
    const m = makeModel({ id: 'Anthropic/Claude' });
    expect(modelMatchesSearch(m, 'anthropic')).toBe(true);
  });
});

describe('sortModels', () => {
  const a = makeModel({ id: 'a-model', provider: 'z-provider', context_length: 8000, pricing: { prompt: '0.002', completion: '0.006' }, created: 1000 });
  const b = makeModel({ id: 'b-model', provider: 'a-provider', context_length: 128000, pricing: { prompt: '0.001', completion: '0.003' }, created: 2000 });

  it('sorts by id ascending', () => {
    const result = sortModels([b, a], 'id', 'asc');
    expect(result[0].id).toBe('a-model');
  });

  it('sorts by id descending', () => {
    const result = sortModels([a, b], 'id', 'desc');
    expect(result[0].id).toBe('b-model');
  });

  it('sorts by provider', () => {
    const result = sortModels([a, b], 'provider', 'asc');
    expect(result[0].provider).toBe('a-provider');
  });

  it('sorts by context_length', () => {
    const result = sortModels([a, b], 'context_length', 'asc');
    expect(result[0].context_length).toBe(8000);
  });

  it('sorts by input_price', () => {
    const result = sortModels([a, b], 'input_price', 'asc');
    expect(result[0].id).toBe('b-model');
  });

  it('sorts by output_price', () => {
    const result = sortModels([a, b], 'output_price', 'asc');
    expect(result[0].id).toBe('b-model');
  });

  it('sorts by created', () => {
    const result = sortModels([b, a], 'created', 'asc');
    expect(result[0].created).toBe(1000);
  });

  it('handles models with null pricing (sorted to bottom)', () => {
    const noPrice = makeModel({ id: 'no-price', pricing: null });
    const result = sortModels([noPrice, a], 'input_price', 'asc');
    expect(result[0].id).toBe('no-price');
  });
});

describe('ModelsWorkspace component', () => {
  async function renderWorkspace(api: object) {
    const { ApiContext: FreshApiContext } = await import('../../src/hooks/useApi');
    const { ModelsWorkspace } = await import('../../src/app/ModelsWorkspace');
    render(
      <FreshApiContext.Provider value={api as never}>
        <ModelsWorkspace />
      </FreshApiContext.Provider>,
    );
  }

  it('shows loading state while fetching', async () => {
    const listModels = vi.fn(() => new Promise(() => {}));
    await renderWorkspace({ listModels });
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows error state when API fails', async () => {
    const listModels = vi.fn(() => Promise.reject(new Error('Network error')));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText(/Error: Network error/)).toBeInTheDocument());
  });

  it('displays models with all columns after load', async () => {
    const listModels = vi.fn(() =>
      Promise.resolve({ object: 'list', data: [makeModelWithPricing()] }),
    );
    await renderWorkspace({ listModels });

    await waitFor(() => expect(screen.getByText('1 / 1 models')).toBeInTheDocument());
    expect(screen.getByText('anthropic/claude-3-haiku')).toBeInTheDocument();
    expect(screen.getByText('openrouter')).toBeInTheDocument();
    expect(screen.getByText('200K')).toBeInTheDocument();
    expect(screen.getByText(/2024/)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Input Modalities/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Output Modalities/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Tokenizer/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Supported Parameters/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Pinned Providers/ })).toBeInTheDocument();
    expect(screen.getAllByText('text').length).toBeGreaterThan(0);
    expect(screen.getByText('cl100k_base')).toBeInTheDocument();
    expect(screen.getByText('temperature, top_p, tools')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
  });

  it('filters models by search query', async () => {
    const models = [
      makeModel({ id: 'anthropic/claude-3', provider: 'openrouter', name: 'Claude 3' }),
      makeModel({ id: 'openai/gpt-4o', provider: 'kilocode', name: 'GPT-4o' }),
    ];
    const listModels = vi.fn(() => Promise.resolve({ object: 'list', data: models }));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('2 / 2 models')).toBeInTheDocument());

    await userEvent.type(screen.getByPlaceholderText('Search models…'), 'claude');
    await waitFor(() => expect(screen.getByText('1 / 2 models')).toBeInTheDocument());
    expect(screen.getByText('anthropic/claude-3')).toBeInTheDocument();
  });

  it('clears search with ✕ button', async () => {
    const listModels = vi.fn(() =>
      Promise.resolve({ object: 'list', data: [makeModel({ id: 'anthropic/claude-3' })] }),
    );
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('1 / 1 models')).toBeInTheDocument());

    await userEvent.type(screen.getByPlaceholderText('Search models…'), 'xyz');
    await waitFor(() => expect(screen.getByRole('button', { name: '✕' })).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: '✕' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: '✕' })).not.toBeInTheDocument());
    expect(screen.getByText('1 / 1 models')).toBeInTheDocument();
  });

  it('shows empty message when no models match search', async () => {
    const listModels = vi.fn(() =>
      Promise.resolve({ object: 'list', data: [makeModel({ id: 'openai/gpt-4o' })] }),
    );
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('1 / 1 models')).toBeInTheDocument());

    await userEvent.type(screen.getByPlaceholderText('Search models…'), 'anthropic');
    await waitFor(() => expect(screen.getByText('No models match your search.')).toBeInTheDocument());
  });

  it('sorts by column header click (asc then desc)', async () => {
    const models = [
      makeModel({ id: 'z-model', provider: 'b-provider' }),
      makeModel({ id: 'a-model', provider: 'a-provider' }),
    ];
    const listModels = vi.fn(() => Promise.resolve({ object: 'list', data: models }));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('2 / 2 models')).toBeInTheDocument());

    const rows = () => screen.getAllByRole('row').slice(1).map(r => r.textContent ?? '');

    // initial sort is 'id' asc already, so a-model should be first
    await waitFor(() => expect(rows()[0]).toContain('a-model'));

    // clicking the active 'id' column toggles to desc (z-model first)
    await userEvent.click(screen.getByRole('columnheader', { name: /Model ID/ }));
    expect(rows()[0]).toContain('z-model');

    // clicking again toggles back to asc (a-model first)
    await userEvent.click(screen.getByRole('columnheader', { name: /Model ID/ }));
    expect(rows()[0]).toContain('a-model');
  });

  it('sorts by Provider, Context, Input price, Output price, Released columns', async () => {
    const m1 = makeModel({
      id: 'm1', provider: 'z-prov', context_length: 4096,
      pricing: { prompt: '0.001', completion: '0.006' }, created: 1000,
    });
    const m2 = makeModel({
      id: 'm2', provider: 'a-prov', context_length: 128000,
      pricing: { prompt: '0.0001', completion: '0.0003' }, created: 2000,
    });
    const listModels = vi.fn(() => Promise.resolve({ object: 'list', data: [m1, m2] }));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('2 / 2 models')).toBeInTheDocument());

    const firstRowText = () => screen.getAllByRole('row')[1].textContent ?? '';

    await userEvent.click(screen.getByRole('columnheader', { name: /^Provider/ }));
    await waitFor(() => expect(firstRowText()).toContain('m2'));

    await userEvent.click(screen.getByRole('columnheader', { name: /^Context/ }));
    await waitFor(() => expect(firstRowText()).toContain('m1'));

    await userEvent.click(screen.getByRole('columnheader', { name: /^Input \$\/1M/ }));
    await waitFor(() => expect(firstRowText()).toContain('m2'));

    await userEvent.click(screen.getByRole('columnheader', { name: /^Output \$\/1M/ }));
    await waitFor(() => expect(firstRowText()).toContain('m2'));

    await userEvent.click(screen.getByRole('columnheader', { name: /^Released/ }));
    await waitFor(() => expect(firstRowText()).toContain('m1'));
  });

  it('displays "same" for mapped_model when equal to id', async () => {
    const m = makeModel({ id: 'openai/gpt-4o', mapped_model: 'openai/gpt-4o' });
    const listModels = vi.fn(() => Promise.resolve({ object: 'list', data: [m] }));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('same')).toBeInTheDocument());
  });

  it('displays actual mapped_model when different from id', async () => {
    const m = makeModel({ id: 'gpt-4', mapped_model: 'gpt-4-turbo-preview' });
    const listModels = vi.fn(() => Promise.resolve({ object: 'list', data: [m] }));
    await renderWorkspace({ listModels });
    await waitFor(() => expect(screen.getByText('gpt-4-turbo-preview')).toBeInTheDocument());
  });
});
