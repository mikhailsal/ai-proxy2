import type { ProxyModel } from '../types';

export type SortKey = 'id' | 'provider' | 'context_length' | 'input_price' | 'output_price' | 'created';
export type SortDir = 'asc' | 'desc';

export function parsePrice(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === 'number' ? value : parseFloat(value);
  return isFinite(n) ? n : null;
}

export function formatPricePerMillion(value: string | number | null | undefined): string {
  const n = parsePrice(value);
  if (n === null) return '—';
  const perMillion = n * 1_000_000;
  if (perMillion === 0) return '$0';
  if (perMillion < 0.001) return `$${perMillion.toExponential(2)}`;
  if (perMillion < 1) return `$${perMillion.toFixed(4)}`;
  return `$${perMillion.toFixed(2)}`;
}

export function formatContextLength(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return String(value);
}

export function formatCreated(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Date(value * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === 'string' && entry.length > 0);
}

function readArchitecture(model: ProxyModel): Record<string, unknown> | null {
  if (!model.architecture || typeof model.architecture !== 'object') {
    return null;
  }
  return model.architecture as Record<string, unknown>;
}

export function getInputModalities(model: ProxyModel): string[] {
  const architecture = readArchitecture(model);
  if (!architecture) return [];

  const fromInput = readStringArray(architecture.input_modalities);
  if (fromInput.length > 0) return fromInput;

  const fallback = architecture.modality;
  if (typeof fallback === 'string' && fallback.length > 0) return [fallback];
  return readStringArray(fallback);
}

export function getOutputModalities(model: ProxyModel): string[] {
  const architecture = readArchitecture(model);
  if (!architecture) return [];

  const fromOutput = readStringArray(architecture.output_modalities);
  if (fromOutput.length > 0) return fromOutput;

  const fallback = architecture.modality;
  if (typeof fallback === 'string' && fallback.length > 0) return [fallback];
  return readStringArray(fallback);
}

export function getTokenizer(model: ProxyModel): string | null {
  const architecture = readArchitecture(model);
  if (!architecture) return null;
  return typeof architecture.tokenizer === 'string' && architecture.tokenizer.length > 0
    ? architecture.tokenizer
    : null;
}

export function getSupportedParameters(model: ProxyModel): string[] {
  return readStringArray(model.supported_parameters);
}

export function getPinnedProviders(model: ProxyModel): string[] {
  return readStringArray(model.pinned_providers);
}

export function formatList(values: string[] | null | undefined): string {
  if (!values || values.length === 0) return '—';
  return values.join(', ');
}

export function getInputPrice(model: ProxyModel): number | null {
  const p = model.pricing;
  if (!p) return null;
  return parsePrice(p.prompt ?? p.input);
}

export function getOutputPrice(model: ProxyModel): number | null {
  const p = model.pricing;
  if (!p) return null;
  return parsePrice(p.completion ?? p.output);
}

export function modelMatchesSearch(model: ProxyModel, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  const searchBlob = [
    model.id,
    model.provider,
    model.mapped_model,
    model.name ?? '',
    model.description ?? '',
    formatList(getInputModalities(model)),
    formatList(getOutputModalities(model)),
    getTokenizer(model) ?? '',
    formatList(getSupportedParameters(model)),
    formatList(getPinnedProviders(model)),
  ]
    .join(' ')
    .toLowerCase();

  return (
    searchBlob.includes(q)
  );
}

export function sortModels(models: ProxyModel[], key: SortKey, dir: SortDir): ProxyModel[] {
  return [...models].sort((a, b) => {
    let cmp = 0;
    if (key === 'id') {
      cmp = a.id.localeCompare(b.id);
    } else if (key === 'provider') {
      cmp = a.provider.localeCompare(b.provider) || a.id.localeCompare(b.id);
    } else if (key === 'context_length') {
      const va = a.context_length ?? -1;
      const vb = b.context_length ?? -1;
      cmp = va - vb;
    } else if (key === 'input_price') {
      const va = getInputPrice(a) ?? -1;
      const vb = getInputPrice(b) ?? -1;
      cmp = va - vb;
    } else if (key === 'output_price') {
      const va = getOutputPrice(a) ?? -1;
      const vb = getOutputPrice(b) ?? -1;
      cmp = va - vb;
    } else if (key === 'created') {
      const va = a.created ?? 0;
      const vb = b.created ?? 0;
      cmp = va - vb;
    }
    return dir === 'asc' ? cmp : -cmp;
  });
}
