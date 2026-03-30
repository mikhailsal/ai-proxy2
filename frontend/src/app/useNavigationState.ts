import { useEffect, useState } from 'react';
import type { RequestSummary } from '../types';
import { buildNavigationUrl, readNavigationFromLocation, type NavigationState } from './navigation';

type NavigationUpdater = NavigationState | ((current: NavigationState) => NavigationState);

interface NavigationController {
  activeRequestSummary: RequestSummary | null;
  navigation: NavigationState;
  selectedRequestSummary: RequestSummary | null;
  setSelectedRequestSummary: (request: RequestSummary | null) => void;
  updateNavigation: (updater: NavigationUpdater, mode?: 'push' | 'replace') => void;
}

export function useNavigationState(): NavigationController {
  const [navigation, setNavigation] = useState<NavigationState>(() => readNavigationFromLocation());
  const [selectedRequestSummary, setSelectedRequestSummary] = useState<RequestSummary | null>(null);

  useEffect(() => {
    function handlePopState() {
      setNavigation(readNavigationFromLocation());
      setSelectedRequestSummary(null);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  function updateNavigation(updater: NavigationUpdater, mode: 'push' | 'replace' = 'push') {
    setNavigation(current => {
      const next = typeof updater === 'function' ? updater(current) : updater;
      syncHistory(current, next, mode);
      return next;
    });
  }

  const activeRequestSummary =
    navigation.requestId && selectedRequestSummary?.id === navigation.requestId
      ? selectedRequestSummary
      : null;

  return {
    activeRequestSummary,
    navigation,
    selectedRequestSummary,
    setSelectedRequestSummary,
    updateNavigation,
  };
}

function syncHistory(
  current: NavigationState,
  next: NavigationState,
  mode: 'push' | 'replace',
): void {
  const nextUrl = buildNavigationUrl(next);
  const currentUrl = buildNavigationUrl(current);

  if (nextUrl === currentUrl) {
    return;
  }

  if (mode === 'replace') {
    window.history.replaceState(null, '', nextUrl);
    return;
  }

  window.history.pushState(null, '', nextUrl);
}