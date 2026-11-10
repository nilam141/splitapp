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
import {
  clearTokens,
  loadTokens,
  resetTokenCache,
} from '../src/auth/tokenStorage';

const json = (status: number, body?: unknown) => ({
  status,
  headers: new Headers(),
  text: async () => (body === undefined ? '' : JSON.stringify(body)),
});

const USER = {
  id: '0b6f4f0e-1c2d-4a1b-9a5e-0d7d2f1a0001',
  email: 'asha@example.com',
  name: 'Asha',
  default_currency: 'INR',
  time_zone: 'Asia/Kolkata',
  is_registered: true,
  plan: 'free',
  notification_prefs: {},
  created_at: '2026-11-05T14:00:00Z',
};
const AUTH = {
  access_token: 'acc',
  refresh_token: 'ref',
  token_type: 'bearer',
  expires_in: 900,
  user: USER,
};

// In-memory stand-in for the secure store so "restart" can be simulated.
let vault: string | null;
let routes: Record<string, (body?: any) => ReturnType<typeof json>>;
let requests: { url: string; body?: any }[];

let qc: QueryClient;

beforeEach(async () => {
  qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
  vault = null;
  requests = [];
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
  routes = {};
  (global as any).fetch = jest.fn(async (url: string, init: RequestInit) => {
    const path = url.replace('http://10.0.2.2:8000', '');
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    requests.push({ url: path, body });
    const h = routes[path];
    if (!h) {
      return json(404, { code: 'NOT_FOUND', message: 'x' });
    }
    return h(body);
  });
  await clearTokens();
  resetTokenCache();
});

afterEach(() => {
  qc.clear(); // cancels gc timers so Jest can exit
});

async function openLogin() {
  await render(<App queryClient={qc} />);
  await fireEvent.press(await screen.findByText('Log in'));
}

describe('login', () => {
  it('logs in, stores tokens in the secure store and shows the tabs', async () => {
    routes['/auth/login'] = () => json(200, AUTH);
    routes['/users/me'] = () => json(200, USER);
    await openLogin();
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      ' Asha@Example.com ',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);

    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(requests.find(r => r.url === '/auth/login')?.body).toEqual({
      email: 'asha@example.com',
      password: 'abcd1234',
    });
    expect(JSON.parse(vault as string)).toEqual({
      accessToken: 'acc',
      refreshToken: 'ref',
    });
  });

  it('shows one combined message on 401', async () => {
    routes['/auth/login'] = () =>
      json(401, { code: 'INVALID_CREDENTIALS', message: 'x' });
    await openLogin();
    await fireEvent.changeText(screen.getByLabelText('Email'), 'a@b.co');
    await fireEvent.changeText(screen.getByLabelText('Password'), 'wrongpass');
    await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);
    expect(
      await screen.findByText('Email or password is incorrect.'),
    ).toBeTruthy();
    expect(vault).toBeNull();
  });

  it('shows the offline message when the server is unreachable', async () => {
    (global as any).fetch = jest.fn(async () => {
      throw new TypeError('Network request failed');
    });
    await openLogin();
    await fireEvent.changeText(screen.getByLabelText('Email'), 'a@b.co');
    await fireEvent.changeText(screen.getByLabelText('Password'), 'wrongpass');
    await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);
    expect(await screen.findByText(/Can't reach the server/)).toBeTruthy();
  });

  it('does not send a request when fields are empty', async () => {
    await openLogin();
    await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);
    expect(await screen.findByText('Enter your email.')).toBeTruthy();
    expect(requests).toHaveLength(0);
  });
});

describe('sign up', () => {
  async function openSignUp() {
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Sign up'));
  }

  it('registers with the chosen currency from GET /currencies', async () => {
    routes['/currencies'] = () =>
      json(200, [
        { code: 'INR', name: 'Indian Rupee', symbol: '₹', exponent: 2 },
        { code: 'JPY', name: 'Japanese Yen', symbol: '¥', exponent: 0 },
      ]);
    routes['/auth/register'] = () => json(201, AUTH);
    await openSignUp();
    await fireEvent.changeText(screen.getByLabelText('Full name'), 'Asha');
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'asha@example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getByText('Change'));
    await fireEvent.press(await screen.findByText(/JPY - Japanese Yen/));
    expect(await screen.findByText('Default currency: JPY')).toBeTruthy();
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);

    expect(await screen.findByText('Friends')).toBeTruthy();
    const body = requests.find(r => r.url === '/auth/register')?.body;
    expect(body).toMatchObject({
      name: 'Asha',
      email: 'asha@example.com',
      default_currency: 'JPY',
    });
    expect(typeof body.time_zone).toBe('string');
    expect(await loadTokens()).toEqual({
      accessToken: 'acc',
      refreshToken: 'ref',
    });
  });

  it('shows the email-taken error under the email field (409)', async () => {
    routes['/auth/register'] = () =>
      json(409, {
        code: 'EMAIL_TAKEN',
        message: 'x',
        details: { field: 'email' },
      });
    await openSignUp();
    await fireEvent.changeText(screen.getByLabelText('Full name'), 'Asha');
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'asha@example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'abcd1234');
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);
    expect(
      await screen.findByText('This email is already registered.'),
    ).toBeTruthy();
  });

  it('validates locally before calling the API', async () => {
    await openSignUp();
    await fireEvent.changeText(screen.getByLabelText('Password'), 'short');
    await fireEvent.press(screen.getAllByText('Sign up').slice(-1)[0]);
    expect(
      await screen.findByText('Password must be 8 to 128 characters.'),
    ).toBeTruthy();
    expect(requests).toHaveLength(0);
  });

  it('currency picker shows an error with Retry when the list fails', async () => {
    routes['/currencies'] = () => json(500, { code: 'X', message: 'x' });
    await openSignUp();
    await fireEvent.press(screen.getByText('Change'));
    expect(await screen.findByText("Couldn't load currencies.")).toBeTruthy();
    expect(screen.getByText('Retry')).toBeTruthy();
  });
});

describe('session restore', () => {
  it('restores a stored session on a cold start without asking for a login', async () => {
    // Tokens were written by a previous run; the in-memory cache is empty (beforeEach).
    vault = JSON.stringify({ accessToken: 'acc', refreshToken: 'ref' });
    routes['/users/me'] = () => json(200, USER);
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(screen.queryByText('Share expenses, settle up.')).toBeNull();
  });

  it('goes to welcome with no stored session', async () => {
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
  });

  it('shows Retry when the server is unreachable on launch, then recovers', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    let online = false;
    routes['/users/me'] = () => json(200, USER);
    const inner = (global as any).fetch;
    (global as any).fetch = jest.fn(async (u: string, i: RequestInit) => {
      if (!online) {
        throw new TypeError('Network request failed');
      }
      return inner(u, i);
    });
    await render(<App queryClient={qc} />);
    expect(await screen.findByText("Can't reach the server.")).toBeTruthy();
    online = true;
    await fireEvent.press(screen.getByText('Retry'));
    expect(await screen.findByText('Friends')).toBeTruthy();
  });

  it('falls back to welcome and clears tokens when the refresh token is rejected', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    routes['/users/me'] = () =>
      json(401, { code: 'TOKEN_EXPIRED', message: 'x' });
    routes['/auth/refresh'] = () =>
      json(401, { code: 'TOKEN_INVALID', message: 'x' });
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    await waitFor(() => expect(vault).toBeNull());
  });

  it.each([404, 500])(
    'keeps the tokens and shows Retry when /users/me answers %i',
    async status => {
      vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
      routes['/users/me'] = () => json(status, { code: 'X', message: 'x' });
      await render(<App queryClient={qc} />);
      expect(await screen.findByText('Retry')).toBeTruthy();
      expect(screen.queryByText('Share expenses, settle up.')).toBeNull();
      expect(JSON.parse(vault as string)).toEqual({
        accessToken: 'a',
        refreshToken: 'r',
      });
    },
  );

  it('keeps the tokens and shows Retry when /users/me gets 401 and the refresh call fails on the network', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    (global as any).fetch = jest.fn(async (url: string) => {
      if (url.endsWith('/auth/refresh')) {
        throw new TypeError('Network request failed');
      }
      return json(401, { code: 'TOKEN_EXPIRED', message: 'x' });
    });
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Retry')).toBeTruthy();
    expect(vault).not.toBeNull();
  });

  it('keeps the tokens when the network fails on launch', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    (global as any).fetch = jest.fn(async () => {
      throw new TypeError('Network request failed');
    });
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Retry')).toBeTruthy();
    expect(vault).not.toBeNull();
  });

  it('logs out via the Account tab', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    routes['/users/me'] = () => json(200, USER);
    routes['/auth/logout'] = () => json(204);
    await render(<App queryClient={qc} />);
    await fireEvent.press((await screen.findAllByText('Account'))[0]);
    await fireEvent.press(await screen.findByText('Log out'));
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    expect(vault).toBeNull();
    expect(requests.find(r => r.url === '/auth/logout')?.body).toEqual({
      refresh_token: 'r',
    });
  });

  it('logout still clears the local session when the server is unreachable, after sending the refresh token', async () => {
    vault = JSON.stringify({ accessToken: 'a', refreshToken: 'r' });
    routes['/users/me'] = () => json(200, USER);
    const inner = (global as any).fetch;
    (global as any).fetch = jest.fn(async (u: string, i: RequestInit) => {
      if (u.endsWith('/auth/logout')) {
        requests.push({
          url: '/auth/logout',
          body: JSON.parse(i.body as string),
        });
        throw new TypeError('Network request failed');
      }
      return inner(u, i);
    });
    await render(<App queryClient={qc} />);
    await fireEvent.press((await screen.findAllByText('Account'))[0]);
    await fireEvent.press(await screen.findByText('Log out'));
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    expect(vault).toBeNull();
    expect(requests.find(r => r.url === '/auth/logout')?.body).toEqual({
      refresh_token: 'r',
    });
  });

  it('logout after an expired access token sends the rotated refresh token', async () => {
    vault = JSON.stringify({ accessToken: 'old', refreshToken: 'r1' });
    routes['/users/me'] = () => json(200, USER);
    routes['/auth/refresh'] = () =>
      json(200, {
        access_token: 'new',
        refresh_token: 'r2',
        token_type: 'bearer',
        expires_in: 900,
      });
    let logoutCalls = 0;
    routes['/auth/logout'] = () => {
      logoutCalls += 1;
      return logoutCalls === 1
        ? json(401, { code: 'TOKEN_EXPIRED', message: 'x' })
        : json(204);
    };
    await render(<App queryClient={qc} />);
    await fireEvent.press((await screen.findAllByText('Account'))[0]);
    await fireEvent.press(await screen.findByText('Log out'));
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    const bodies = requests
      .filter(r => r.url === '/auth/logout')
      .map(r => r.body);
    expect(bodies).toEqual([{ refresh_token: 'r1' }, { refresh_token: 'r2' }]);
    expect(vault).toBeNull();
  });
});
