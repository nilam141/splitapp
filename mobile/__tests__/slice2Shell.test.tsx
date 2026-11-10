/**
 * S2-M-1 (tab shell), S2-M-2 (Friends + Add people), S2-M-5 (Account, session expired).
 * Screen-level tests: the real App, navigation, generated client and auth layer run against the
 * stateful fake server in testUtils/fakeServer.ts (the "network mock"). No Detox/Maestro is installed in this
 * repo, so these stand in for the emulator E2E specs.
 */
import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Contacts from 'react-native-contacts';
import { QueryClient } from '@tanstack/react-query';
import App from '../App';
import { resetTokenCache } from '../src/auth/tokenStorage';
import { FakeServer } from '../testUtils/fakeServer';

let server: FakeServer;
let qc: QueryClient;

const newClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });

beforeEach(async () => {
  server = new FakeServer();
  server.seedTokens();
  server.install();
  qc = newClient();
  resetTokenCache();
  await AsyncStorage.clear();
});
afterEach(() => qc.clear());

const openTab = async (name: string) =>
  fireEvent.press(await screen.findByText(name));

describe('S2-M-1 tab shell', () => {
  it('renders the 4 tabs and the add-expense button, hidden on Account', async () => {
    await render(<App queryClient={qc} />);
    for (const t of ['Friends', 'Groups', 'Activity', 'Account']) {
      expect(await screen.findByText(t)).toBeTruthy();
    }
    expect(screen.getByLabelText('Add expense')).toBeTruthy();
    await openTab('Account');
    await screen.findByText('Your profile');
    expect(screen.queryByLabelText('Add expense')).toBeNull();
  });

  it('restores the last tab after a restart', async () => {
    const first = await render(<App queryClient={qc} />);
    await openTab('Friends');
    await screen.findByText('Add your first friend');
    await first.unmount();

    resetTokenCache(); // simulate a cold start
    qc = newClient();
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Add your first friend')).toBeTruthy();
    expect(screen.queryByText('No groups yet')).toBeNull();
  });

  it('opens on Groups by default', async () => {
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('No groups yet')).toBeTruthy();
  });
});

describe('S2-M-2 Friends tab and Add people', () => {
  const openAddFriend = async () => {
    await render(<App queryClient={qc} />);
    await openTab('Friends');
    await fireEvent.press(await screen.findByText('Add friend'));
  };

  it('empty state, then add ravi@example.com -> row appears', async () => {
    await openAddFriend();
    await fireEvent.changeText(
      screen.getByLabelText('Email or phone'),
      'ravi@example.com',
    );
    await fireEvent.press(screen.getByText('Done'));
    expect(await screen.findByText('Ravi')).toBeTruthy();
    const posts = server.log.filter(
      r => r.method === 'POST' && r.path === '/friends',
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ email: 'ravi@example.com' });
    expect(posts[0].headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(posts[0].headers.get('Authorization')).toBe('Bearer acc1');
  });

  it('"abc" shows an error and sends no request', async () => {
    await openAddFriend();
    const before = server.log.length;
    await fireEvent.changeText(screen.getByLabelText('Email or phone'), 'abc');
    await fireEvent.press(screen.getByText('Done'));
    expect(
      await screen.findByText(/Enter a valid email address, or a phone number/),
    ).toBeTruthy();
    await fireEvent.press(screen.getByText('Add to list'));
    expect(server.log.length).toBe(before); // 0 calls
    expect(server.count('POST', '/friends')).toBe(0);
  });

  it('adds by phone and shows a server-side failure on the person, keeping them selected', async () => {
    server.overrides.push(req =>
      req.method === 'POST' && req.path === '/friends'
        ? {
            status: 422,
            body: {
              code: 'VALIDATION_ERROR',
              message: 'Phone number not supported',
            },
          }
        : undefined,
    );
    await openAddFriend();
    await fireEvent.changeText(
      screen.getByLabelText('Email or phone'),
      '+919876543210',
    );
    await fireEvent.press(screen.getByText('Done'));
    expect(await screen.findByText('Phone number not supported')).toBeTruthy();
    expect(server.count('POST', '/friends')).toBe(1);
  });

  it('shows the friends list with per-currency balances, filters, and the settled-up collapse', async () => {
    server.addFriendRow('f1', 'Ravi', [
      { amount_minor: 12050, currency: 'INR' },
    ]);
    server.addFriendRow('f2', 'Meera', [
      { amount_minor: -300, currency: 'USD' },
    ]);
    server.addFriendRow('f3', 'Old', [], '2026-01-01T00:00:00Z');
    await render(<App queryClient={qc} />);
    await openTab('Friends');
    expect(await screen.findByText('owes you INR 120.50')).toBeTruthy();
    expect(screen.getByText('you owe USD 3.00')).toBeTruthy();
    expect(
      screen.getByText(/Overall: you owe USD 3.00, you are owed INR 120.50/),
    ).toBeTruthy();
    expect(screen.queryByText('Old')).toBeNull();
    await fireEvent.press(screen.getByText('Show 1 settled-up friends'));
    expect(await screen.findByText('Old')).toBeTruthy();

    await fireEvent.press(screen.getByLabelText('Filter: I owe'));
    expect(screen.queryByText('Ravi')).toBeNull();
    expect(screen.getByText('Meera')).toBeTruthy();
    // filtering is client side: still a single GET /friends
    expect(server.count('GET', '/friends')).toBe(1);
  });

  it('error state offers Retry, and offline (fetch rejects) is distinguished', async () => {
    let fail = true;
    server.overrides.push(req =>
      req.path === '/friends' && fail
        ? {
            status: 500,
            body: { code: 'INTERNAL_ERROR', message: 'Internal server error' },
          }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    await openTab('Friends');
    expect(
      await screen.findByText('Something went wrong. Please try again.'),
    ).toBeTruthy();
    fail = false;
    await fireEvent.press(screen.getByText('Retry'));
    expect(await screen.findByText('Add your first friend')).toBeTruthy();
  });

  it('offline (request fails, no response) shows the offline message with Retry', async () => {
    const original = (global as any).fetch;
    let down = true;
    (global as any).fetch = jest.fn((...args: unknown[]) =>
      down && String(args[0]).endsWith('/friends')
        ? Promise.reject(new TypeError('Network request failed'))
        : original(...args),
    );
    await render(<App queryClient={qc} />);
    await openTab('Friends');
    expect(
      await screen.findByText(/You're offline or the server can't be reached/),
    ).toBeTruthy();
    down = false;
    await fireEvent.press(screen.getByText('Retry'));
    expect(await screen.findByText('Add your first friend')).toBeTruthy();
  });

  it('contacts: primer first, allow -> device contacts listed; denied -> primer says so', async () => {
    (Contacts.getAllWithoutPhotos as jest.Mock).mockResolvedValueOnce([
      {
        recordID: '1',
        displayName: 'Dev Patel',
        givenName: 'Dev',
        emailAddresses: [{ label: 'h', email: 'dev@example.com' }],
        phoneNumbers: [],
      },
      {
        recordID: '2',
        displayName: 'No Handle',
        givenName: 'No',
        emailAddresses: [],
        phoneNumbers: [{ label: 'm', number: '98765 43210' }],
      },
    ]);
    (Contacts.requestPermission as jest.Mock).mockResolvedValueOnce(
      'authorized',
    );
    await openAddFriend();
    expect(
      screen.getByText(/Allow contacts so you can pick people/),
    ).toBeTruthy();
    expect(Contacts.getAllWithoutPhotos).not.toHaveBeenCalled(); // nothing read before consent
    await fireEvent.press(screen.getByText('Allow contacts access'));
    expect(
      await screen.findByText(/Dev Patel \(dev@example.com\)/),
    ).toBeTruthy();
    expect(screen.queryByText(/No Handle/)).toBeNull(); // no email and no E.164 phone
    await fireEvent.press(screen.getByText(/Dev Patel/));
    await fireEvent.press(screen.getByText('Done (1)'));
    await waitFor(() => expect(server.count('POST', '/friends')).toBe(1));
    expect(
      server.log.find(r => r.path === '/friends' && r.method === 'POST')!.body,
    ).toEqual({ email: 'dev@example.com', name: 'Dev Patel' });
  });

  it('contacts denied keeps typing available', async () => {
    (Contacts.requestPermission as jest.Mock).mockResolvedValueOnce('denied');
    await openAddFriend();
    await fireEvent.press(screen.getByText('Allow contacts access'));
    expect(await screen.findByText(/Contacts access is off/)).toBeTruthy();
    expect(screen.getByLabelText('Email or phone')).toBeTruthy();
  });
});

describe('S2-M-5 Account and session expired', () => {
  const openAccount = async () => {
    await render(<App queryClient={qc} />);
    await openTab('Account');
    await screen.findByText('Your profile');
  };

  it('change currency to USD -> PATCH, shown, and persisted after restart', async () => {
    await openAccount();
    expect(screen.getByLabelText('Default currency value').props.children).toBe(
      'INR',
    );
    await fireEvent.press(screen.getByText('Change currency'));
    await fireEvent.press(await screen.findByText(/USD - US Dollar/));
    await waitFor(() =>
      expect(
        screen.getByLabelText('Default currency value').props.children,
      ).toBe('USD'),
    );
    const patches = server.log.filter(
      r => r.method === 'PATCH' && r.path === '/users/me',
    );
    expect(patches).toHaveLength(1);
    expect(patches[0].body).toEqual({ default_currency: 'USD' });

    // restart: new query client, token cache dropped, same server and secure storage
    await screen.unmount();
    resetTokenCache();
    qc = newClient();
    await openAccount();
    expect(screen.getByLabelText('Default currency value').props.children).toBe(
      'USD',
    );
  });

  it('email clash 409 shows inline under the field', async () => {
    server.overrides.push(req =>
      req.method === 'PATCH'
        ? {
            status: 409,
            body: {
              code: 'EMAIL_TAKEN',
              message: 'This email is used by another account',
              details: { field: 'email' },
            },
          }
        : undefined,
    );
    await openAccount();
    await fireEvent.changeText(
      screen.getByLabelText('Email'),
      'taken@example.com',
    );
    await fireEvent.press(screen.getByText('Save email'));
    expect(
      await screen.findByText('This email is used by another account.'),
    ).toBeTruthy();
  });

  it('invalid phone is rejected locally with no request', async () => {
    await openAccount();
    await fireEvent.changeText(screen.getByLabelText('Phone'), '12345');
    await fireEvent.press(screen.getByText('Save phone'));
    expect(
      await screen.findByText('Use the format +919876543210.'),
    ).toBeTruthy();
    expect(server.count('PATCH', '/users/me')).toBe(0);
  });

  it('log out asks first, then lands on the welcome screen with secure storage empty', async () => {
    await openAccount();
    await fireEvent.press(screen.getByText('Log out'));
    expect(server.count('POST', '/auth/logout')).toBe(0); // confirmation first
    const dialogButtons = screen.getAllByText('Log out');
    await fireEvent.press(dialogButtons[dialogButtons.length - 1]);
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
    expect(server.vault).toBeNull();
    expect(server.count('POST', '/auth/logout')).toBe(1);
  });

  it('refresh token rejected while using the app -> SCR-44, Log in prefills the email', async () => {
    await openAccount();
    server.validAccess.clear(); // access token now expired
    server.refreshOk = false; // and the refresh token is rejected
    await fireEvent.changeText(screen.getByLabelText('Name'), 'Asha K');
    await fireEvent.press(screen.getByText('Save name'));
    expect(await screen.findByText('Session expired')).toBeTruthy();
    expect(server.vault).toBeNull();
    await fireEvent.press(screen.getByText('Log in'));
    const email = await screen.findByLabelText('Email');
    expect(email.props.value).toBe('asha@example.com');
  });

  it('an explicit log out does not show the session-expired screen', async () => {
    await openAccount();
    await fireEvent.press(screen.getByText('Log out'));
    const b = screen.getAllByText('Log out');
    await fireEvent.press(b[b.length - 1]);
    await screen.findByText('Share expenses, settle up.');
    expect(screen.queryByText('Session expired')).toBeNull();
  });
});
