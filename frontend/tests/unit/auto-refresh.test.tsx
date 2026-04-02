import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AutoRefreshProvider } from '../../src/hooks/useAutoRefresh';
import {
  REFRESH_OPTIONS,
  useAutoRefresh,
} from '../../src/hooks/autoRefreshContext';
import type { RefreshInterval } from '../../src/hooks/autoRefreshContext';

const STORAGE_KEY = 'ai-proxy-auto-refresh-ms';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <AutoRefreshProvider>{children}</AutoRefreshProvider>;
}

describe('useAutoRefresh', () => {
  it('defaults to off (0) when localStorage is empty', () => {
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    expect(result.current.intervalMs).toBe(0);
    expect(result.current.refetchInterval).toBe(false);
  });

  it('reads a previously stored interval from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, '60000');
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    expect(result.current.intervalMs).toBe(60_000);
    expect(result.current.refetchInterval).toBe(60_000);
  });

  it('falls back to 0 for invalid localStorage values', () => {
    localStorage.setItem(STORAGE_KEY, 'garbage');
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    expect(result.current.intervalMs).toBe(0);
  });

  it('falls back to 0 for unrecognized numeric values', () => {
    localStorage.setItem(STORAGE_KEY, '12345');
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    expect(result.current.intervalMs).toBe(0);
  });

  it('updates interval and persists to localStorage', () => {
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });

    act(() => {
      result.current.setIntervalMs(300_000);
    });

    expect(result.current.intervalMs).toBe(300_000);
    expect(result.current.refetchInterval).toBe(300_000);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('300000');
  });

  it('returns false for refetchInterval when set to 0', () => {
    localStorage.setItem(STORAGE_KEY, '30000');
    const { result } = renderHook(() => useAutoRefresh(), { wrapper });

    act(() => {
      result.current.setIntervalMs(0);
    });

    expect(result.current.refetchInterval).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('0');
  });

  it('returns default values when used outside provider', () => {
    const { result } = renderHook(() => useAutoRefresh());
    expect(result.current.intervalMs).toBe(0);
    expect(result.current.refetchInterval).toBe(false);
  });

  it('handles localStorage errors gracefully on read', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });

    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    expect(result.current.intervalMs).toBe(0);
    getItem.mockRestore();
  });

  it('handles localStorage errors gracefully on write', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });

    const { result } = renderHook(() => useAutoRefresh(), { wrapper });
    act(() => {
      result.current.setIntervalMs(30_000);
    });
    expect(result.current.intervalMs).toBe(30_000);
    setItem.mockRestore();
  });
});

describe('REFRESH_OPTIONS', () => {
  it('contains expected intervals', () => {
    const values = REFRESH_OPTIONS.map(o => o.value);
    expect(values).toEqual([0, 30_000, 60_000, 300_000, 900_000]);
  });

  it('all option values are valid RefreshInterval types', () => {
    const validValues = new Set<RefreshInterval>([0, 30_000, 60_000, 300_000, 900_000]);
    REFRESH_OPTIONS.forEach(opt => {
      expect(validValues.has(opt.value)).toBe(true);
    });
  });
});

describe('RefreshPicker integration via StatsBar', () => {
  it('changes the refresh interval when the dropdown is changed', async () => {
    function TestConsumer() {
      const { intervalMs, refetchInterval } = useAutoRefresh();
      return (
        <div>
          <span data-testid="interval">{intervalMs}</span>
          <span data-testid="refetch">{String(refetchInterval)}</span>
        </div>
      );
    }

    function TestPicker() {
      const { intervalMs, setIntervalMs } = useAutoRefresh();
      return (
        <select
          data-testid="picker"
          value={intervalMs}
          onChange={e => setIntervalMs(Number(e.target.value) as RefreshInterval)}
        >
          {REFRESH_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      );
    }

    render(
      <AutoRefreshProvider>
        <TestPicker />
        <TestConsumer />
      </AutoRefreshProvider>,
    );

    expect(screen.getByTestId('interval').textContent).toBe('0');
    expect(screen.getByTestId('refetch').textContent).toBe('false');

    await userEvent.selectOptions(screen.getByTestId('picker'), '60000');

    expect(screen.getByTestId('interval').textContent).toBe('60000');
    expect(screen.getByTestId('refetch').textContent).toBe('60000');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('60000');
  });
});
