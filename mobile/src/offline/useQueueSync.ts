import { useCallback, useEffect } from 'react';
import { AppState } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { getHealth } from '../api/generated/splitapp';
import { useIsOffline } from './connectivity';
import { flushQueue, loadQueue, useWriteQueue } from './queue';

export const SYNC_INTERVAL_MS = 15000;

/**
 * Replays the write queue when the signed-in shell opens, when the app returns to the foreground, every 15 s while
 * something is waiting, and on demand (`syncNow`).
 */
export function useQueueSync() {
  const client = useQueryClient();
  const queue = useWriteQueue();
  const offline = useIsOffline();
  const waiting = queue.some(i => i.state === 'pending');
  const syncNow = useCallback(() => flushQueue(client), [client]);

  useEffect(() => {
    loadQueue().then(syncNow);
    const sub = AppState.addEventListener('change', s => {
      if (s === 'active') {
        syncNow();
      }
    });
    return () => sub.remove();
  }, [syncNow]);

  useEffect(() => {
    if (!waiting && !offline) {
      return;
    }
    // While offline with nothing queued, a health check notices when the connection is back.
    const t = setInterval(() => {
      if (waiting) {
        syncNow();
      } else {
        getHealth().catch(() => undefined);
      }
    }, SYNC_INTERVAL_MS);
    return () => clearInterval(t);
  }, [waiting, offline, syncNow]);

  return { queue, syncNow };
}
