import { createContext, useContext } from 'react';

export type RefreshInterval = 0 | 30_000 | 60_000 | 300_000 | 900_000;

export const REFRESH_OPTIONS: { label: string; value: RefreshInterval }[] = [
  { label: 'Off', value: 0 },
  { label: '30s', value: 30_000 },
  { label: '1m', value: 60_000 },
  { label: '5m', value: 300_000 },
  { label: '15m', value: 900_000 },
];

export interface AutoRefreshContextValue {
  intervalMs: RefreshInterval;
  setIntervalMs: (ms: RefreshInterval) => void;
  refetchInterval: number | false;
}

export const AutoRefreshContext = createContext<AutoRefreshContextValue>({
  intervalMs: 0,
  setIntervalMs: () => {},
  refetchInterval: false,
});

export function useAutoRefresh(): AutoRefreshContextValue {
  return useContext(AutoRefreshContext);
}

const STORAGE_KEY = 'ai-proxy-auto-refresh-ms';

export function loadInterval(): RefreshInterval {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return 0;
    const parsed = Number(raw);
    if (REFRESH_OPTIONS.some(o => o.value === parsed)) return parsed as RefreshInterval;
  } catch { /* ignore */ }
  return 0;
}

export function saveInterval(ms: RefreshInterval): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(ms));
  } catch { /* ignore */ }
}
