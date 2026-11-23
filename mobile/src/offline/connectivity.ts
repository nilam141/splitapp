import { useSyncExternalStore } from 'react';

// No NetInfo module is installed, so connectivity is inferred from the HTTP layer: a request that fails without a
// response marks the app offline, and any response marks it online again.
let offline = false;
const listeners = new Set<() => void>();

export function setOffline(value: boolean): void {
  if (offline !== value) {
    offline = value;
    listeners.forEach(l => l());
  }
}

export const isOffline = (): boolean => offline;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useIsOffline(): boolean {
  return useSyncExternalStore(subscribe, isOffline, isOffline);
}

/** A thrown fetch (no response at all): the device is offline or the server is unreachable. */
export function isNetworkError(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof Error &&
      /network|failed to fetch|timed out/i.test(error.message))
  );
}
