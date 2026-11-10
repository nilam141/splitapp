/**
 * S1-Q-1 mobile smoke tests against the Slice 1 backend contract.
 *
 * The "Slice 1 backend" here is a fake fetch that behaves like the real FastAPI app: /auth/*, /currencies,
 * GET /users/me (S1-B-5, 200 with a valid bearer, else 401 TOKEN_INVALID) and POST /auth/logout (S1-B-6, 204).
 */
import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import * as Keychain from 'react-native-keychain';
import { QueryClient } from '@tanstack/react-query';
import App from '../App';
import { clearTokens, resetTokenCache } from '../src/auth/tokenStorage';

const json = (status: number, body?: unknown) => ({
  status,
  headers: new Headers(),
  text: async () => (body === undefined ? '' : JSON.stringify(body)),
});

// Shape and values exactly as the backend returns them (all 10 notification_prefs keys, nullable fields null).
const USER = {
  id: '0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1a0001',
  email: 'asha@example.com',
  name: 'Asha',
  phone_e164: null,
  default_currency: 'INR',
  time_zone: 'Asia/Kolkata',
  avatar_url: null,
  is_registered: true,
  plan: 'free',
  premium_until: null,
  friend_code: 'K7Q2M9XP',
  notification_prefs: {
    expense_added: true,
    expense_updated: true,
    comment_added: true,
    added_to_group: true,
    removed_from_group: true,
    group_updated: true,
    friend_added: true,
    friend_removed: true,
    payment_recorded: true,
    reminder: true,
  },
  created_at: '2026-11-05T14:00:00Z',
};
const AUTH = {
  access_token: 'acc1',
  refresh_token: 'rt_ref1',
  token_type: 'bearer',
  expires_in: 900,
  user: USER,
};
const NOT_FOUND = { code: 'NOT_FOUND', message: 'Not Found' };

let vault: string | null;
let calls: { method: string; path: string; body?: any }[];
let qc: QueryClient;

function installSlice1Backend() {
  (global as any).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const path = url.replace('http://10.0.2.2:8000', '');
    const method = (init.method ?? 'GET').toUpperCase();
    calls.push({
      method,
      path,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    if (method === 'POST' && path === '/auth/login') {
      return json(200, AUTH);
    }
    if (method === 'POST' && path === '/auth/register') {
      return json(201, AUTH);
    }
    if (method === 'GET' && path === '/currencies') {
      return json(200, [
        { code: 'INR', name: 'Indian Rupee', symbol: '₹', exponent: 2 },
        { code: 'KWD', name: 'Kuwaiti Dinar', symbol: 'KD', exponent: 3 },
      ]);
    }
    if (method === 'GET' && path === '/users/me') {
      const auth = new Headers(init.headers as any).get('Authorization');
      return auth === 'Bearer acc1'
        ? json(200, USER)
        : json(401, { code: 'TOKEN_INVALID', message: 'Invalid token' });
    }
    if (method === 'POST' && path === '/auth/logout') {
      return json(204);
    }
    return json(404, NOT_FOUND);
  });
}

beforeEach(async () => {
  // gcTime Infinity: no timers left behind, so Jest exits (without this the run hung after completion).
  qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
  vault = null;
  calls = [];
  (Keychain.setGenericPassword as jest.Mock).mockImplementation(
    async (_u, pw) => {
      vault = pw;
      return true;
    },
  );
  (Keychain.getGenericPassword as jest.Mock).mockImplementation(async () =>
    vault ? { username: 'session', password: vault } : false,
  );
  (Keychain.resetGenericPassword as jest.Mock).mockImplementation(async () => {
    vault = null;
    return true;
  });
  installSlice1Backend();
  await clearTokens();
  resetTokenCache();
});

afterEach(() => qc.clear());

async function logIn() {
  await render(<App queryClient={qc} />);
  await fireEvent.press(await screen.findByText('Log in'));
  await fireEvent.changeText(
    screen.getByLabelText('Email'),
    'asha@example.com',
  );
  await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
  await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);
}

describe('Slice 1 client/contract smoke', () => {
  it('login hits POST /auth/login with exactly {email, password} and accepts the real AuthResponse', async () => {
    await logIn();
    expect(await screen.findByText('Friends')).toBeTruthy();
    const login = calls.filter(c => c.path === '/auth/login');
    expect(login).toHaveLength(1);
    expect(login[0].method).toBe('POST');
    expect(login[0].body).toEqual({
      email: 'asha@example.com',
      password: 'abcd1234',
    });
    expect(JSON.parse(vault as string)).toEqual({
      accessToken: 'acc1',
      refreshToken: 'rt_ref1',
    });
  });

  it('currency list: calls GET /currencies and shows KWD (3-digit currency) in the picker', async () => {
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Sign up'));
    await fireEvent.press(screen.getByText('Change'));
    expect(await screen.findByText(/KWD - Kuwaiti Dinar/)).toBeTruthy();
    expect(
      calls.some(c => c.method === 'GET' && c.path === '/currencies'),
    ).toBe(true);
  });

  it('sign up sends only documented RegisterRequest fields', async () => {
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Sign up'));
    await fireEvent.changeText(screen.getByLabelText('Full name'), 'Asha');
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'Asha@Example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);
    expect(await screen.findByText('Friends')).toBeTruthy();
    const body = calls.find(c => c.path === '/auth/register')!.body;
    expect(Object.keys(body).sort()).toEqual([
      'default_currency',
      'email',
      'name',
      'password',
      'time_zone',
    ]);
    expect(body.email).toBe('asha@example.com');
    expect(body.default_currency).toMatch(/^[A-Z]{3}$/);
  });

  it('422 CURRENCY_UNKNOWN on sign up shows the server message and stores no session', async () => {
    (global as any).fetch = jest.fn(async () =>
      json(422, {
        code: 'CURRENCY_UNKNOWN',
        message: 'Unsupported currency',
        details: { currency: 'ZZZ' },
      }),
    );
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Sign up'));
    await fireEvent.changeText(screen.getByLabelText('Full name'), 'Asha');
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'asha@example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);
    expect(await screen.findByText('Unsupported currency')).toBeTruthy();
    expect(vault).toBeNull();
  });

  it('422 VALIDATION_ERROR with details.fields shows the message under the field', async () => {
    (global as any).fetch = jest.fn(async () =>
      json(422, {
        code: 'VALIDATION_ERROR',
        message: 'Request validation failed',
        details: { fields: [{ field: 'password', message: 'too weak' }] },
      }),
    );
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Sign up'));
    await fireEvent.changeText(screen.getByLabelText('Full name'), 'Asha');
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'asha@example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);
    expect(await screen.findByText('too weak')).toBeTruthy();
  });
});

describe('Session restore against the Slice 1 backend (GET /users/me exists, S1-B-5)', () => {
  const restart = async () => {
    // "Restart": drop JS state, keep the keystore.
    await screen.unmount();
    resetTokenCache();
    calls = [];
    qc = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { gcTime: Infinity },
      },
    });
    await render(<App queryClient={qc} />);
  };

  it('cold start with stored tokens: GET /users/me answers 200 -> lands in the tabs, tokens untouched', async () => {
    vault = JSON.stringify({ accessToken: 'acc1', refreshToken: 'rt_ref1' });
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(screen.queryByText('Share expenses, settle up.')).toBeNull();
    expect(calls.map(c => `${c.method} ${c.path}`)).toEqual(['GET /users/me']);
    expect(JSON.parse(vault as string)).toEqual({
      accessToken: 'acc1',
      refreshToken: 'rt_ref1',
    });
  });

  it('login followed by an app restart stays signed in without a second login', async () => {
    await logIn();
    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(vault).not.toBeNull();
    await restart();
    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(screen.queryByText('Share expenses, settle up.')).toBeNull();
    expect(calls.some(c => c.path === '/auth/login')).toBe(false);
    expect(calls.filter(c => c.path === '/users/me')).toHaveLength(1);
  });

  it('log out then restart lands on welcome: POST /auth/logout once with the stored refresh token, storage empty', async () => {
    await logIn();
    await fireEvent.press((await screen.findAllByText('Account'))[0]);
    await fireEvent.press(await screen.findByText('Log out'));
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    const out = calls.filter(c => c.path === '/auth/logout');
    expect(out).toHaveLength(1);
    expect(out[0].method).toBe('POST');
    expect(out[0].body).toEqual({ refresh_token: 'rt_ref1' });
    expect(vault).toBeNull();
    await restart();
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    expect(calls.some(c => c.path === '/users/me')).toBe(false);
  });

  it('logout call fails with 500: session is still cleared locally and a restart stays signed out', async () => {
    await logIn();
    await screen.findByText('Friends');
    const inner = (global as any).fetch;
    (global as any).fetch = jest.fn(async (u: string, i: RequestInit) =>
      u.endsWith('/auth/logout')
        ? json(500, { code: 'INTERNAL_ERROR', message: 'Internal server error' })
        : inner(u, i),
    );
    await fireEvent.press((await screen.findAllByText('Account'))[0]);
    await fireEvent.press(await screen.findByText('Log out'));
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    expect(vault).toBeNull();
    await restart();
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
  });

  it('stored access token rejected (401 TOKEN_INVALID) and refresh rejected (401) -> welcome and keystore wiped', async () => {
    vault = JSON.stringify({ accessToken: 'stale', refreshToken: 'rt_dead' });
    const inner = (global as any).fetch;
    (global as any).fetch = jest.fn(async (u: string, i: RequestInit) =>
      u.endsWith('/auth/refresh')
        ? json(401, { code: 'TOKEN_INVALID', message: 'Invalid refresh token' })
        : inner(u, i),
    );
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    await waitFor(() => expect(vault).toBeNull());
  });

  it.each([404, 500])(
    '/users/me answers %i -> Retry screen, keystore never wiped, Retry recovers',
    async status => {
      vault = JSON.stringify({ accessToken: 'acc1', refreshToken: 'rt_ref1' });
      const inner = (global as any).fetch;
      let broken = true;
      (global as any).fetch = jest.fn(async (u: string, i: RequestInit) =>
        broken && u.endsWith('/users/me')
          ? json(status, { code: 'X', message: 'x' })
          : inner(u, i),
      );
      await render(<App queryClient={qc} />);
      await fireEvent.press(await screen.findByText('Retry'));
      expect(await screen.findByText('Retry')).toBeTruthy();
      expect(JSON.parse(vault as string)).toEqual({
        accessToken: 'acc1',
        refreshToken: 'rt_ref1',
      });
      broken = false;
      await fireEvent.press(screen.getByText('Retry'));
      expect(await screen.findByText('Friends')).toBeTruthy();
    },
  );
});
