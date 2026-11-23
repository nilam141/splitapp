import { customFetch } from '../src/api/http';
import {
  loadTokens,
  resetTokenCache,
  saveTokens,
  clearTokens,
} from '../src/auth/tokenStorage';
import { onSessionExpired } from '../src/auth/sessionEvents';

type Call = { url: string; auth: string | null };
const json = (status: number, body?: unknown) => ({
  status,
  headers: new Headers(),
  text: async () => (body === undefined ? '' : JSON.stringify(body)),
});

describe('customFetch', () => {
  let calls: Call[];
  let handler: (url: string, auth: string | null) => ReturnType<typeof json>;

  beforeEach(async () => {
    calls = [];
    (global as any).fetch = jest.fn(async (url: string, init: RequestInit) => {
      const auth = (init.headers as Headers).get('Authorization');
      calls.push({ url: url.replace('http://10.0.2.2:8000', ''), auth });
      return handler(url.replace('http://10.0.2.2:8000', ''), auth);
    });
    await clearTokens();
    await saveTokens({ accessToken: 'old', refreshToken: 'r1' });
  });

  it('adds base URL and bearer token and wraps the response', async () => {
    handler = () => json(200, { ok: true });
    const res: any = await customFetch('/users/me', { method: 'GET' });
    expect(calls[0]).toEqual({ url: '/users/me', auth: 'Bearer old' });
    expect(res.status).toBe(200);
    expect(res.data).toEqual({ ok: true });
  });

  it('handles empty 204 bodies', async () => {
    handler = () => json(204);
    const res: any = await customFetch('/x', {});
    expect(res.status).toBe(204);
    expect(res.data).toBeUndefined();
  });

  it('refreshes once on 401, stores rotated tokens, retries', async () => {
    handler = (url, auth) => {
      if (url === '/auth/refresh') {
        return json(200, {
          access_token: 'new',
          refresh_token: 'r2',
          token_type: 'bearer',
          expires_in: 900,
        });
      }
      return auth === 'Bearer new'
        ? json(200, { ok: 1 })
        : json(401, { code: 'TOKEN_EXPIRED', message: 'x' });
    };
    const res: any = await customFetch('/users/me', {});
    expect(res.status).toBe(200);
    expect(calls.map(c => c.url)).toEqual([
      '/users/me',
      '/auth/refresh',
      '/users/me',
    ]);
    expect(calls[1].auth).toBeNull();
    expect(await loadTokens()).toEqual({
      accessToken: 'new',
      refreshToken: 'r2',
    });
  });

  it('shares a single refresh between concurrent 401s', async () => {
    handler = (url, auth) => {
      if (url === '/auth/refresh') {
        return json(200, {
          access_token: 'new',
          refresh_token: 'r2',
          token_type: 'bearer',
          expires_in: 900,
        });
      }
      return auth === 'Bearer new' ? json(200, {}) : json(401, {});
    };
    await Promise.all([customFetch('/a', {}), customFetch('/b', {})]);
    expect(calls.filter(c => c.url === '/auth/refresh')).toHaveLength(1);
  });

  it('clears the session and notifies when the refresh token is rejected', async () => {
    handler = url =>
      url === '/auth/refresh'
        ? json(401, { code: 'TOKEN_INVALID', message: 'x' })
        : json(401, {});
    const expired = jest.fn();
    const off = onSessionExpired(expired);
    const res: any = await customFetch('/users/me', {});
    off();
    expect(res.status).toBe(401);
    expect(expired).toHaveBeenCalledTimes(1);
    resetTokenCache();
    expect(await loadTokens()).toBeNull();
  });

  it('keeps the session when the refresh call fails on the network', async () => {
    handler = url => {
      if (url === '/auth/refresh') {
        throw new Error('offline');
      }
      return json(401, {});
    };
    const res: any = await customFetch('/users/me', {});
    expect(res.status).toBe(401);
    expect(await loadTokens()).toEqual({
      accessToken: 'old',
      refreshToken: 'r1',
    });
  });

  it('never sends a token to, or refreshes on, login', async () => {
    handler = () => json(401, { code: 'INVALID_CREDENTIALS', message: 'x' });
    const res: any = await customFetch('/auth/login', { method: 'POST' });
    expect(res.status).toBe(401);
    expect(calls).toEqual([{ url: '/auth/login', auth: null }]);
  });
});
