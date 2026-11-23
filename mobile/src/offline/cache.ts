import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  dehydrate,
  hydrate,
  type DehydratedState,
  type QueryClient,
} from '@tanstack/react-query';
import type { UserMe } from '../api/generated/model';
import { CACHE_MAX_AGE_MS } from './queryClient';

// F-53: persisted React Query cache, one per signed-in user, so lists open offline. Tokens are NOT stored here
// (they stay in secure storage); the cache holds the same data the screens show. It is wiped on logout.
export const CACHE_KEY = 'splitapp.queryCache.v1';
export const USER_KEY = 'splitapp.lastUser.v1';
export const THROTTLE_MS = 1000;

type Stored = { savedAt: number; userId: string; state: DehydratedState };

export async function saveCachedUser(user: UserMe): Promise<void> {
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(user));
}

export async function loadCachedUser(): Promise<UserMe | null> {
  try {
    const raw = await AsyncStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as UserMe) : null;
  } catch {
    return null;
  }
}

/** Hydrates the saved cache for `userId` (nothing if it belongs to someone else or is older than a day). */
export async function restoreQueryCache(
  client: QueryClient,
  userId: string,
  now: number = Date.now(),
): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_KEY);
    if (!raw) {
      return false;
    }
    const stored = JSON.parse(raw) as Stored;
    if (stored.userId !== userId || now - stored.savedAt > CACHE_MAX_AGE_MS) {
      return false;
    }
    hydrate(client, stored.state);
    return true;
  } catch {
    return false;
  }
}

/** Saves successful queries (throttled) while the user is signed in. Returns a stop function. */
export function startCachePersistence(
  client: QueryClient,
  userId: string,
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const write = () => {
    timer = undefined;
    const state = dehydrate(client, {
      shouldDehydrateQuery: q => q.state.status === 'success',
    });
    const stored: Stored = { savedAt: Date.now(), userId, state };
    AsyncStorage.setItem(CACHE_KEY, JSON.stringify(stored)).catch(
      () => undefined,
    );
  };
  const unsubscribe = client.getQueryCache().subscribe(() => {
    if (!timer) {
      timer = setTimeout(write, THROTTLE_MS);
    }
  });
  return () => {
    unsubscribe();
    if (timer) {
      clearTimeout(timer);
    }
  };
}

/** Logout: nothing about the account stays on the device. */
export async function clearOfflineData(): Promise<void> {
  await AsyncStorage.multiRemove([CACHE_KEY, USER_KEY]);
}
