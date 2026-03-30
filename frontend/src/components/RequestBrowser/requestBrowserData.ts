import { useInfiniteQuery } from '@tanstack/react-query';
import type { ApiClient } from '../../api/client';
import type { RequestSummary } from '../../types';

interface UseRequestBrowserDataResult {
  fetchNextPage: () => Promise<unknown>;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isLoading: boolean;
  items: RequestSummary[];
}

export function useRequestBrowserData(
  api: ApiClient,
  searchQuery: string,
  modelFilter: string,
): UseRequestBrowserDataResult {
  const requestsQuery = useInfiniteQuery({
    queryKey: ['requests'],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      api.listRequests({ cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last => last.next_cursor ?? undefined,
  });

  const searchResultsQuery = useInfiniteQuery({
    queryKey: ['search', searchQuery],
    queryFn: () => api.searchRequests(searchQuery),
    initialPageParam: undefined,
    getNextPageParam: () => undefined,
    enabled: searchQuery.length > 0,
  });

  const baseItems = searchQuery
    ? (searchResultsQuery.data?.pages.flatMap(page => page.items) ?? [])
    : (requestsQuery.data?.pages.flatMap(page => page.items) ?? []);

  return {
    fetchNextPage: requestsQuery.fetchNextPage,
    hasNextPage: requestsQuery.hasNextPage ?? false,
    isFetchingNextPage: requestsQuery.isFetchingNextPage,
    isLoading: requestsQuery.isLoading,
    items: filterRequests(baseItems, modelFilter),
  };
}

export function filterRequests(items: RequestSummary[], modelFilter: string): RequestSummary[] {
  const normalizedModelFilter = modelFilter.trim().toLowerCase();
  if (!normalizedModelFilter) {
    return items;
  }

  return items.filter(item => {
    const requestedModel = item.model_requested?.toLowerCase() ?? '';
    const resolvedModel = item.model_resolved?.toLowerCase() ?? '';
    return requestedModel.includes(normalizedModelFilter) || resolvedModel.includes(normalizedModelFilter);
  });
}