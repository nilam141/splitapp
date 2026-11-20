import { useEffect } from 'react';
import { AppState } from 'react-native';
import type { QueryClient } from '@tanstack/react-query';
import {
  getListActivityQueryKey,
  listActivity,
  useListActivity,
} from '../api/generated/splitapp';

/** The tab badge reads `unread_count` from a 1-item page; every page of GET /activity carries it. */
export const BADGE_PARAMS = { limit: 1 } as const;

/**
 * Unread count for the Activity tab badge (SCR-07). Loaded on launch (mount) and again whenever the app returns to the
 * foreground; set to 0 right after the Activity tab is opened (see setUnreadCount).
 */
export function useUnreadCount(): number {
  const query = useListActivity(BADGE_PARAMS);
  const { refetch } = query;
  useEffect(() => {
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') {
        refetch();
      }
    });
    return () => sub.remove();
  }, [refetch]);
  return query.data?.status === 200 ? query.data.data.unread_count : 0;
}

/** Writes the badge count into the cache without a request (used after POST /activity/read). */
export function setUnreadCount(qc: QueryClient, count: number): void {
  qc.setQueryData(
    getListActivityQueryKey(BADGE_PARAMS),
    (old: Awaited<ReturnType<typeof listActivity>> | undefined) =>
      old && old.status === 200
        ? { ...old, data: { ...old.data, unread_count: count } }
        : old,
  );
}
