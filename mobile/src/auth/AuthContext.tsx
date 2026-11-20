import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getCurrentUser,
  logout as logoutRequest,
} from '../api/generated/splitapp';
import type { AuthResponse, UserMe } from '../api/generated/model';
import { clearTokens, loadTokens, saveTokens } from './tokenStorage';
import { onSessionExpired } from './sessionEvents';
import {
  clearOfflineData,
  loadCachedUser,
  restoreQueryCache,
  saveCachedUser,
  startCachePersistence,
} from '../offline/cache';
import { clearQueue } from '../offline/queue';

// 'loading' = SCR-01 launch router deciding; 'error' = could not reach the
// server while restoring (MVP shows Retry instead of stale data).
export type SessionStatus = 'loading' | 'signedOut' | 'signedIn' | 'error';

type AuthContextValue = {
  status: SessionStatus;
  user: UserMe | null;
  /** Persist the tokens from a login/register response and enter the app. */
  startSession: (auth: AuthResponse) => Promise<void>;
  signOut: () => Promise<void>;
  /** Replace the cached profile after a successful PATCH /users/me. */
  setUser: (user: UserMe) => void;
  /** Set when the session ended because the refresh token was rejected (SCR-44); holds the email to prefill. */
  expiredEmail: string | null;
  retryRestore: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<UserMe | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [expiredEmail, setExpiredEmail] = useState<string | null>(null);
  const userRef = useRef<UserMe | null>(null);
  userRef.current = user;

  // Restore the session on launch (and on Retry).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatus('loading');
      const tokens = await loadTokens();
      if (!tokens) {
        if (!cancelled) {
          setStatus('signedOut');
        }
        return;
      }
      // Could not reach the server: open the app from the saved profile and cache if there is one (F-53),
      // otherwise offer Retry.
      const openOffline = async () => {
        const cached = await loadCachedUser();
        if (cancelled) {
          return;
        }
        if (cached) {
          await restoreQueryCache(queryClient, cached.id);
          if (!cancelled) {
            setUser(cached);
            setStatus('signedIn');
          }
        } else {
          setStatus('error');
        }
      };
      try {
        // customFetch refreshes the access token transparently on 401.
        const res = await getCurrentUser();
        if (cancelled) {
          return;
        }
        if (res.status === 200) {
          await restoreQueryCache(queryClient, res.data.id);
          if (cancelled) {
            return;
          }
          setUser(res.data);
          setStatus('signedIn');
        } else if (res.status === 401) {
          // Signed out only if the HTTP layer cleared the tokens (refresh was
          // rejected). If they are still there the refresh failed for another
          // reason (network), so work offline or offer Retry.
          if (await loadTokens()) {
            await openOffline();
          } else {
            setStatus('signedOut');
          }
        } else {
          // 404, 5xx, anything else: keep the tokens and offer Retry.
          setStatus('error');
        }
      } catch {
        if (!cancelled) {
          await openOffline();
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt, queryClient]);

  // Refresh token rejected at any time -> back to the welcome screen.
  useEffect(
    () =>
      onSessionExpired(() => {
        // SCR-44 only when a live session ends; on launch (no user yet) SCR-01 goes to SCR-02.
        setExpiredEmail(userRef.current?.email ?? null);
        queryClient.clear();
        clearOfflineData();
        clearQueue();
        setUser(null);
        setStatus('signedOut');
      }),
    [queryClient],
  );

  const startSession = useCallback(async (auth: AuthResponse) => {
    await saveTokens({
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token,
    });
    setUser(auth.user);
    setExpiredEmail(null);
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    const tokens = await loadTokens();
    if (tokens) {
      try {
        await logoutRequest({ refresh_token: tokens.refreshToken });
      } catch {
        // Offline: still drop the local session.
      }
    }
    await clearTokens();
    queryClient.clear();
    await Promise.all([clearOfflineData(), clearQueue()]);
    setUser(null);
    setExpiredEmail(null);
    setStatus('signedOut');
  }, [queryClient]);

  // Keep the profile and the query cache on the device while signed in (offline start, F-53).
  const userId = user?.id;
  useEffect(() => {
    if (status !== 'signedIn' || !userId) {
      return;
    }
    return startCachePersistence(queryClient, userId);
  }, [status, userId, queryClient]);
  useEffect(() => {
    if (status === 'signedIn' && user) {
      saveCachedUser(user).catch(() => undefined);
    }
  }, [status, user]);

  const retryRestore = useCallback(() => setAttempt(a => a + 1), []);

  const value = useMemo(
    () => ({
      status,
      user,
      startSession,
      signOut,
      setUser,
      expiredEmail,
      retryRestore,
    }),
    [status, user, startSession, signOut, expiredEmail, retryRestore],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return ctx;
}
