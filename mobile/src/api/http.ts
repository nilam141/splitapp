import { API_BASE_URL } from '../config';
import { clearTokens, loadTokens, saveTokens } from '../auth/tokenStorage';
import { notifySessionExpired } from '../auth/sessionEvents';
import {
  getLoginUrl,
  getLogoutUrl,
  getRefreshTokenUrl,
  getRegisterUserUrl,
  refreshToken as refreshTokenRequest,
} from './generated/splitapp';

// React Query hands over a DOM-flavoured AbortSignal (and the generated client a
// FormData body) while RN's fetch types expect others; accept both so the
// generated client type-checks.
export type FetchInit = Omit<RequestInit, 'signal' | 'body'> & {
  signal?: AbortSignal | globalThis.AbortSignal | null;
  body?: RequestInit['body'] | globalThis.FormData;
};

// Endpoints that carry no bearer token and must never trigger a refresh.
// Built from the generated URL helpers, so no endpoint path is written by hand.
const isPublicAuthUrl = (url: string): boolean =>
  [
    getLoginUrl(),
    getRegisterUserUrl(),
    getRefreshTokenUrl(),
  ].includes(url);

async function send<T>(
  url: string,
  init: FetchInit,
  accessToken: string | null,
): Promise<T> {
  const headers = new Headers(
    init.headers as Record<string, string> | undefined,
  );
  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...init,
    headers,
  } as RequestInit);
  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;
  return { data, status: response.status, headers: response.headers } as T;
}

// One refresh at a time: concurrent 401s share the same rotation, because the
// server revokes the old refresh token on use.
let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const tokens = await loadTokens();
  if (!tokens) {
    return false;
  }
  try {
    const res = await refreshTokenRequest({ refresh_token: tokens.refreshToken });
    if (res.status === 200) {
      await saveTokens({
        accessToken: res.data.access_token,
        refreshToken: res.data.refresh_token,
      });
      return true;
    }
    if (res.status === 401) {
      await clearTokens();
      notifySessionExpired();
    }
    return false;
  } catch {
    // Network failure: keep the session, let the caller see the original 401.
    return false;
  }
}

// Mutator used by the generated client (see orval.config.ts). It is the only place
// that touches fetch: base URL, bearer token, one transparent refresh on 401, and
// the { data, status, headers } shape the generated response types expect.
export const customFetch = async <T>(
  url: string,
  init: FetchInit,
): Promise<T> => {
  if (isPublicAuthUrl(url)) {
    return send<T>(url, init, null);
  }
  const tokens = await loadTokens();
  const first = await send<{ status: number } & T>(
    url,
    init,
    tokens?.accessToken ?? null,
  );
  if (first.status !== 401 || !tokens) {
    return first;
  }
  refreshing =
    refreshing ?? refreshSession().finally(() => (refreshing = null));
  if (!(await refreshing)) {
    return first;
  }
  const fresh = await loadTokens();
  // Logout carries the refresh token in its body; the refresh above rotated it,
  // so re-read it from storage instead of replaying the stale body.
  const retryInit: FetchInit =
    url === getLogoutUrl() && fresh
      ? { ...init, body: JSON.stringify({ refresh_token: fresh.refreshToken }) }
      : init;
  return send<T>(url, retryInit, fresh?.accessToken ?? null);
};
