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
  return (
    model.id.toLowerCase().includes(q) ||
    model.provider.toLowerCase().includes(q) ||
    (model.name ?? '').toLowerCase().includes(q) ||
    (model.description ?? '').toLowerCase().includes(q)
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
