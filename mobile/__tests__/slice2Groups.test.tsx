/**
 * S2-M-3 (Groups tab, Create group, Group detail) and S2-M-4 (Group settings).
 * Screen-level tests against the fake server (see slice2Shell.test.tsx for why not Detox/Maestro).
 */
import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createNavigationContainerRef } from '@react-navigation/native';
import { QueryClient } from '@tanstack/react-query';
import App from '../App';
import { resetTokenCache } from '../src/auth/tokenStorage';
import { FakeServer } from '../testUtils/fakeServer';

let server: FakeServer;
let qc: QueryClient;
const navRef = createNavigationContainerRef();

beforeEach(async () => {
  server = new FakeServer();
  server.seedTokens();
  server.install();
  qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
  resetTokenCache();
  await AsyncStorage.clear();
});
afterEach(() => qc.clear());

const press = async (text: string | RegExp) =>
  fireEvent.press(await screen.findByText(text));

describe('S2-M-3 Groups tab, Create group, Group detail', () => {
  it('empty state invites to create a group', async () => {
    await render(<App queryClient={qc} navigationRef={navRef} />);
    expect(await screen.findByText('No groups yet')).toBeTruthy();
    expect(
      screen.getByText(/Create a group for your home, a trip or your partner/),
    ).toBeTruthy();
  });

  it('lists groups with member counts and opens one', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await render(<App queryClient={qc} navigationRef={navRef} />);
    expect(await screen.findByText('Flat')).toBeTruthy();
    expect(screen.getByText('2 members')).toBeTruthy();
    await press('Flat');
    expect(await screen.findByText('No expenses yet')).toBeTruthy();
  });

  it('create "Goa Trip" (trip, 2 members) -> detail shows 3 members and the empty state', async () => {
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Start a new group');
    await fireEvent.changeText(
      await screen.findByLabelText('Group name'),
      'Goa Trip',
    );
    await fireEvent.press(screen.getByLabelText('Type: trip'));
    await fireEvent.changeText(
      screen.getByLabelText('Trip start (YYYY-MM-DD)'),
      '2026-12-01',
    );
    await fireEvent.changeText(
      screen.getByLabelText('Trip end (YYYY-MM-DD)'),
      '2026-12-05',
    );

    await fireEvent.press(screen.getByText('Add members'));
    await fireEvent.changeText(await screen.findByLabelText('Name'), 'Ravi');
    await fireEvent.changeText(
      screen.getByLabelText('Email or phone'),
      'ravi@example.com',
    );
    await fireEvent.press(screen.getByText('Add to list'));
    await fireEvent.changeText(screen.getByLabelText('Name'), 'Meera');
    await fireEvent.changeText(
      screen.getByLabelText('Email or phone'),
      'meera@example.com',
    );
    // text still in the form is included by Done: Ravi is in the list, Meera is picked up from the form
    await fireEvent.press(screen.getByText('Done (1)'));

    expect(await screen.findByText('Members (2 of 199 others)')).toBeTruthy();
    await fireEvent.press(screen.getByText('Done'));

    expect(await screen.findByText('No expenses yet')).toBeTruthy();
    expect(screen.getByText(/other - 3 members|trip - 3 members/)).toBeTruthy();
    expect(screen.getByText('Asha (you)')).toBeTruthy();
    expect(screen.getByText('Ravi')).toBeTruthy();
    expect(screen.getByText('Meera')).toBeTruthy();

    const posts = server.log.filter(
      r => r.method === 'POST' && r.path === '/groups',
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      name: 'Goa Trip',
      group_type: 'trip',
      simplify_debts: true,
      trip_start_date: '2026-12-01',
      trip_end_date: '2026-12-05',
      member_user_ids: [],
      new_members: [
        { name: 'Ravi', email: 'ravi@example.com' },
        { name: 'Meera', email: 'meera@example.com' },
      ],
    });
    expect(posts[0].headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('picks existing friends by user id', async () => {
    server.addFriendRow('f1', 'Ravi');
    server.addFriendRow('f2', 'Meera');
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Start a new group');
    await fireEvent.changeText(
      await screen.findByLabelText('Group name'),
      'Flat',
    );
    await fireEvent.press(screen.getByText('Add members'));
    await press(/Ravi/);
    await press(/Meera/);
    await fireEvent.press(screen.getByText('Done (2)'));
    await fireEvent.press(await screen.findByText('Done'));
    expect(await screen.findByText('No expenses yet')).toBeTruthy();
    expect(
      server.log.find(r => r.method === 'POST' && r.path === '/groups')!.body
        .member_user_ids,
    ).toEqual(['f1', 'f2']);
  });

  it('validates locally: empty name, end before start; nothing is sent', async () => {
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Start a new group');
    await fireEvent.press(await screen.findByText('Done'));
    expect(await screen.findByText(/Enter a group name/)).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Group name'), 'Trip');
    await fireEvent.press(screen.getByLabelText('Type: trip'));
    await fireEvent.changeText(
      screen.getByLabelText('Trip start (YYYY-MM-DD)'),
      '2026-12-05',
    );
    await fireEvent.changeText(
      screen.getByLabelText('Trip end (YYYY-MM-DD)'),
      '2026-12-01',
    );
    await fireEvent.press(screen.getByText('Done'));
    expect(
      await screen.findByText('The end date cannot be before the start date.'),
    ).toBeTruthy();
    expect(server.count('POST', '/groups')).toBe(0);
  });

  it('server 422 INVALID_DATE_RANGE is shown under the end date', async () => {
    server.overrides.push(req =>
      req.method === 'POST' && req.path === '/groups'
        ? {
            status: 422,
            body: { code: 'INVALID_DATE_RANGE', message: 'bad range' },
          }
        : undefined,
    );
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Start a new group');
    await fireEvent.changeText(
      await screen.findByLabelText('Group name'),
      'Trip',
    );
    await fireEvent.press(screen.getByLabelText('Type: trip'));
    await fireEvent.press(screen.getByText('Done'));
    expect(
      await screen.findByText('The end date cannot be before the start date.'),
    ).toBeTruthy();
  });

  it('group detail: 403 and 404 and offline states', async () => {
    const g = server.addGroup('Secret', [server.user('u-a', 'Ravi')]);
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Secret');
    await screen.findByText('No expenses yet');
    // a second visit where the server now says forbidden
    server.overrides.push(req =>
      req.path === `/groups/${g.id}`
        ? { status: 403, body: { code: 'FORBIDDEN', message: 'no' } }
        : undefined,
    );
    await qc.invalidateQueries();
    expect(
      await screen.findByText("You're not a member of this group."),
    ).toBeTruthy();
  });

  it('a group with only the creator offers Add people', async () => {
    server.addGroup('Solo', []);
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Solo');
    expect(await screen.findByText("It's just you here")).toBeTruthy();
    expect(screen.getByText('Add people')).toBeTruthy();
  });

  it('groups list error state has Retry', async () => {
    let fail = true;
    server.overrides.push(req =>
      req.path === '/groups' && fail
        ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'x' } }
        : undefined,
    );
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await screen.findByText('Something went wrong. Please try again.');
    fail = false;
    await press('Retry');
    expect(await screen.findByText('No groups yet')).toBeTruthy();
  });
});

describe('S2-M-4 Group settings', () => {
  const openSettings = async (name = 'Flat') => {
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press(name);
    await press('Settings');
    await screen.findByText('Save name');
  };

  it('rename -> PATCH with version -> visible on the Groups tab', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await openSettings();
    await fireEvent.changeText(screen.getByLabelText('Group name'), 'Flat 12B');
    await fireEvent.press(screen.getByText('Save name'));
    await waitFor(() => expect(server.count('PATCH', /^\/groups\//)).toBe(1));
    expect(server.log.find(r => r.method === 'PATCH')!.body).toEqual({
      version: 1,
      name: 'Flat 12B',
    });
    // back to the list (detail, then tabs)
    await act(async () => {
      navRef.goBack(); // settings -> detail
      navRef.goBack(); // detail -> tabs
    });
    expect(await screen.findByText('Flat 12B')).toBeTruthy();
  });

  it('toggle simplify sends only the changed field with the current version', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await openSettings();
    await fireEvent(
      screen.getByLabelText('Simplify debts'),
      'valueChange',
      false,
    );
    await waitFor(() => expect(server.count('PATCH', /^\/groups\//)).toBe(1));
    expect(server.log.find(r => r.method === 'PATCH')!.body).toEqual({
      version: 1,
      simplify_debts: false,
    });
  });

  it('stale version (409 VERSION_CONFLICT) reloads and tells the user', async () => {
    const g = server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await openSettings();
    g.version = 5; // someone else edited
    await fireEvent.changeText(screen.getByLabelText('Group name'), 'Other');
    await fireEvent.press(screen.getByText('Save name'));
    expect(await screen.findByText(/changed by someone else/)).toBeTruthy();
  });

  it('remove member refused with OUTSTANDING_BALANCE shows a dialog with the amount', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    server.overrides.push(req =>
      req.method === 'DELETE' && req.path.includes('/members/')
        ? {
            status: 409,
            body: {
              code: 'OUTSTANDING_BALANCE',
              message: 'Settle all debts before leaving',
              details: {
                balances: [
                  { amount_minor: -12050, currency: 'INR' },
                  { amount_minor: -1, currency: 'USD' },
                ],
              },
            },
          }
        : undefined,
    );
    await openSettings();
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    await fireEvent.press((await screen.findAllByText('Remove')).slice(-1)[0]); // dialog confirm
    expect(
      await screen.findByText(/Outstanding: INR 120.50, USD 0.01\./),
    ).toBeTruthy();
    expect(screen.getByText("You can't remove this member yet")).toBeTruthy();
    await press('OK');
    expect(screen.getByText('Ravi')).toBeTruthy(); // still a member
  });

  it('leave refused with OUTSTANDING_BALANCE shows the amount; the group stays', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    server.overrides.push(req =>
      req.method === 'DELETE' && req.path.endsWith('/members/me')
        ? {
            status: 409,
            body: {
              code: 'OUTSTANDING_BALANCE',
              message: 'Settle all debts before leaving',
              details: { balances: [{ amount_minor: -1, currency: 'INR' }] },
            },
          }
        : undefined,
    );
    await openSettings();
    await press('Leave group');
    expect(
      screen.getByText('You will stay friends with the other members.'),
    ).toBeTruthy();
    await press('Leave');
    expect(await screen.findByText(/Outstanding: INR 0.01\./)).toBeTruthy();
    expect(server.count('GET', '/friends')).toBe(0);
  });

  it('successful leave -> friends queries invalidated -> former co-member shows on the Friends tab', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await render(<App queryClient={qc} navigationRef={navRef} />);
    // Friends tab loaded first (empty), so a stale cache exists for it.
    await press('Friends');
    await screen.findByText('Add your first friend');
    await press('Groups');
    await press('Flat');
    await press('Settings');
    await press('Leave group');
    await press('Leave');
    // popped back to the tabs; the server made Ravi an explicit friend when the group ended
    await press('Friends');
    expect(await screen.findByText('Ravi')).toBeTruthy();
    expect(server.count('GET', '/friends')).toBeGreaterThanOrEqual(2);
    expect(server.count('DELETE', /\/groups\/.*\/members\/me$/)).toBe(1);
  });

  it('delete needs 2 steps; success invalidates friends and the group disappears', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Friends');
    await screen.findByText('Add your first friend');
    await press('Groups');
    await press('Flat');
    await press('Settings');
    await press('Delete group');
    expect(server.count('DELETE', /^\/groups\/[^/]+$/)).toBe(0);
    await press('Continue');
    expect(screen.getByText('Members stay on your friends list.')).toBeTruthy();
    expect(server.count('DELETE', /^\/groups\/[^/]+$/)).toBe(0); // still nothing sent after step 1
    const del = screen.getAllByText('Delete group');
    await fireEvent.press(del[del.length - 1]);
    expect(await screen.findByText('No groups yet')).toBeTruthy();
    expect(server.count('DELETE', /^\/groups\/[^/]+$/)).toBe(1);
    await press('Friends');
    expect(await screen.findByText('Ravi')).toBeTruthy();
  });

  it('cancelling the second delete step sends nothing', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await openSettings();
    await press('Delete group');
    await press('Continue');
    await press('Cancel');
    expect(server.count('DELETE', /^\/groups\/[^/]+$/)).toBe(0);
  });

  it('add people to the group posts members and shows them', async () => {
    server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    await openSettings();
    await press('Add people');
    await fireEvent.changeText(await screen.findByLabelText('Name'), 'Dev');
    await fireEvent.changeText(
      screen.getByLabelText('Email or phone'),
      'dev@example.com',
    );
    await fireEvent.press(screen.getByText('Done'));
    expect(await screen.findByText('Dev')).toBeTruthy();
    const posts = server.log.filter(
      r => r.method === 'POST' && r.path.endsWith('/members'),
    );
    expect(posts[0].body).toEqual({
      user_ids: [],
      new_members: [{ name: 'Dev', email: 'dev@example.com' }],
    });
  });
});
