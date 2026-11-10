import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getCurrentUser, logout as logoutRequest } from '../api/generated/splitapp';
import type { AuthResponse, UserMe } from '../api/generated/model';
import { clearTokens, loadTokens, saveTokens } from './tokenStorage';
import { onSessionExpired } from './sessionEvents';

// 'loading' = SCR-01 launch router deciding; 'error' = could not reach the
// server while restoring (MVP shows Retry instead of stale data).
export type SessionStatus = 'loading' | 'signedOut' | 'signedIn' | 'error';

type AuthContextValue = {
  status: SessionStatus;
  user: UserMe | null;
  /** Persist the tokens from a login/register response and enter the app. */
  startSession: (auth: AuthResponse) => Promise<void>;
  signOut: () => Promise<void>;
  retryRestore: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<UserMe | null>(null);
  const [attempt, setAttempt] = useState(0);

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
      try {
        // customFetch refreshes the access token transparently on 401.
        const res = await getCurrentUser();
        if (cancelled) {
          return;
        }
        if (res.status === 200) {
          setUser(res.data);
          setStatus('signedIn');
        } else if (res.status === 401) {
          // Signed out only if the HTTP layer cleared the tokens (refresh was
          // rejected). If they are still there the refresh failed for another
          // reason (network), so offer Retry instead.
          setStatus((await loadTokens()) ? 'error' : 'signedOut');
        } else {
          // 404, 5xx, anything else: keep the tokens and offer Retry.
          setStatus('error');
        }
      } catch {
        if (!cancelled) {
          setStatus('error');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // Refresh token rejected at any time -> back to the welcome screen.
  useEffect(
    () =>
      onSessionExpired(() => {
        queryClient.clear();
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
    setUser(null);
    setStatus('signedOut');
  }, [queryClient]);

  const retryRestore = useCallback(() => setAttempt(a => a + 1), []);

  const value = useMemo(
    () => ({ status, user, startSession, signOut, retryRestore }),
    [status, user, startSession, signOut, retryRestore],
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
