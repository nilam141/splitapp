import { QueryCache, QueryClient } from '@tanstack/react-query';
import { isNetworkError } from './connectivity';

export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

/**
 * The app's QueryClient. Data is kept for a day (so a restored cache is not garbage collected). When a refresh
 * fails because the device is offline and the query already has data, the old data stays on screen as a normal
 * success instead of flipping the screen to an error: the offline banner explains that it may be out of date.
 */
export function createAppQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.state.data !== undefined && isNetworkError(error)) {
          client.setQueryData(query.queryKey, query.state.data, {
            updatedAt: query.state.dataUpdatedAt,
          });
        }
      },
    }),
    defaultOptions: { queries: { gcTime: CACHE_MAX_AGE_MS } },
  });
  return client;
}
