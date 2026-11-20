import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import {
  createExpense,
  createGroupExpense,
  createSettlement,
} from '../api/generated/splitapp';
import type { ExpenseCreate, SettlementCreate } from '../api/generated/model';
import {
  apiErrorOf,
  idempotencyHeaders,
  invalidateAfterPayment,
  invalidateExpenses,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import { isNetworkError } from './connectivity';

// F-53 write queue: expense and settlement creates made while offline are kept here and replayed in order with the
// Idempotency-Key they were first sent with, so a request that did reach the server is never applied twice.
// The server remembers a key for 24 hours (contract), which is the longest a change should wait.
export const QUEUE_KEY = 'splitapp.writeQueue.v1';

export type QueuedWrite =
  | {
      kind: 'group_expense';
      groupId: string;
      body: Omit<ExpenseCreate, 'group_id'>;
    }
  | { kind: 'expense'; body: ExpenseCreate }
  | { kind: 'settlement'; body: SettlementCreate };

export type QueueItem = QueuedWrite & {
  /** Local id for lists and discard. */
  id: string;
  /** The Idempotency-Key sent with every attempt. */
  key: string;
  createdAt: number;
  /** 'failed' = the server rejected it (4xx); it will not be retried. */
  state: 'pending' | 'failed';
  error?: string;
};

let items: QueueItem[] = [];
let loaded: Promise<void> | null = null;
let flushing = false;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach(l => l());
const persist = () =>
  AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(items)).catch(() => undefined);

/** Loads the saved queue once. Safe to call repeatedly. */
export function loadQueue(): Promise<void> {
  loaded ??= AsyncStorage.getItem(QUEUE_KEY)
    .then(raw => {
      const saved: QueueItem[] = raw ? JSON.parse(raw) : [];
      // keep anything already enqueued before the load finished
      const ids = new Set(items.map(i => i.id));
      items = [...saved.filter(i => !ids.has(i.id)), ...items];
      emit();
    })
    .catch(() => undefined);
  return loaded;
}

export const getQueue = (): readonly QueueItem[] => items;

export async function enqueueWrite(
  write: QueuedWrite,
  key: string,
): Promise<QueueItem> {
  await loadQueue();
  const item: QueueItem = {
    ...write,
    id: `${Date.now()}-${items.length}-${key.slice(0, 8)}`,
    key,
    createdAt: Date.now(),
    state: 'pending',
  };
  items = [...items, item];
  emit();
  await persist();
  return item;
}

export async function discardWrite(id: string): Promise<void> {
  items = items.filter(i => i.id !== id);
  emit();
  await persist();
}

/** Logout: drop everything (it belongs to the signed-out account). */
export async function clearQueue(): Promise<void> {
  items = [];
  loaded = Promise.resolve();
  emit();
  await AsyncStorage.removeItem(QUEUE_KEY);
}

function send(item: QueueItem) {
  const options = idempotencyHeaders(item.key);
  switch (item.kind) {
    case 'group_expense':
      return createGroupExpense(item.groupId, item.body, options);
    case 'expense':
      return createExpense(item.body, options);
    case 'settlement':
      return createSettlement(item.body, options);
  }
}

export type FlushResult = { sent: number; failed: number; blocked: boolean };

/**
 * Replays pending writes oldest first. Stops at the first one that cannot be decided yet (no connection, 401, 429
 * or a 5xx) so order is kept; a 4xx marks that item failed and the rest continue.
 */
export async function flushQueue(client: QueryClient): Promise<FlushResult> {
  await loadQueue();
  const result: FlushResult = { sent: 0, failed: 0, blocked: false };
  if (flushing) {
    return { ...result, blocked: true };
  }
  flushing = true;
  try {
    for (const item of [...items]) {
      if (item.state !== 'pending') {
        continue;
      }
      let status: number;
      let message: string | undefined;
      try {
        const res = await send(item);
        status = res.status;
        message = apiErrorOf(res)?.message;
      } catch (e) {
        if (isNetworkError(e)) {
          result.blocked = true;
          break;
        }
        throw e;
      }
      if (status === 200 || status === 201) {
        items = items.filter(i => i.id !== item.id);
        result.sent += 1;
      } else if (status === 401 || status === 429 || status >= 500) {
        result.blocked = true;
        break;
      } else {
        items = items.map(i =>
          i.id === item.id
            ? {
                ...i,
                state: 'failed',
                error: message ?? 'The server rejected this change.',
              }
            : i,
        );
        result.failed += 1;
      }
      emit();
      await persist();
    }
  } finally {
    flushing = false;
  }
  if (result.sent > 0) {
    await Promise.all([
      invalidateExpenses(client),
      invalidateGroups(client),
      invalidateFriends(client),
      invalidateAfterPayment(client),
    ]);
  }
  return result;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useWriteQueue(): readonly QueueItem[] {
  return useSyncExternalStore(subscribe, getQueue, getQueue);
}
