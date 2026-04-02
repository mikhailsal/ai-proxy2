import { useCallback, useState } from 'react';
import {
  AutoRefreshContext,
  loadInterval,
  saveInterval,
} from './autoRefreshContext';
import type { RefreshInterval } from './autoRefreshContext';

export function AutoRefreshProvider({ children }: { children: React.ReactNode }) {
  const [intervalMs, setRaw] = useState<RefreshInterval>(loadInterval);

  const setIntervalMs = useCallback((ms: RefreshInterval) => {
    setRaw(ms);
    saveInterval(ms);
  }, []);

  const refetchInterval: number | false = intervalMs > 0 ? intervalMs : false;

  return (
    <AutoRefreshContext.Provider value={{ intervalMs, setIntervalMs, refetchInterval }}>
      {children}
    </AutoRefreshContext.Provider>
  );
}
