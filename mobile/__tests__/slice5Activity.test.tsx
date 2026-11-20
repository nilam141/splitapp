/**
 * S5-M-2 (Activity tab SCR-10, tab badge) component/screen tests against the fake server with mocked feed data.
 * NOT real E2E: no emulator or Detox/Maestro in the repo.
 */
import React from 'react';
import { StyleSheet } from 'react-native';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient } from '@tanstack/react-query';
import App from '../App';
import { resetTokenCache } from '../src/auth/tokenStorage';
import { lightColors } from '../src/theme';
import { FakeServer } from '../testUtils/fakeServer';

let server: FakeServer;
let qc: QueryClient;
const ME = 'u-me';

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
const nowIso = (offsetMs = 0) => new Date(Date.now() - offsetMs).toISOString();
const MIN = 60 * 1000;
// Fixed local calendar days, so the Today / Yesterday headings cannot flip around midnight.
const startOfToday = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 1);
};
const todayIso = (extraMs = 0) =>
  new Date(startOfToday().getTime() + extraMs).toISOString();
const yesterdayNoonIso = () => {
  const d = new Date();
  return new Date(
    d.getFullYear(),
    d.getMonth(),
    d.getDate() - 1,
    12,
  ).toISOString();
};

const ravi = {
  id: 'u-ravi',
  name: 'Ravi',
  email: null,
  avatar_url: null,
  is_registered: true,
};

const item = (id: string, o: Record<string, unknown> = {}) => ({
  id,
  action: 'expense.created',
  actor: ravi,
  entity_type: 'expense',
  entity_id: `x-${id}`,
  group_id: null,
  summary: {
    description: `Item ${id}`,
    total: { amount_minor: 9000, currency: 'INR' },
  },
  my_effect: [{ amount_minor: -3000, currency: 'INR' }],
  is_unread: false,
  created_at: nowIso(5 * MIN),
  ...o,
});

/** GET /activity answers; `read` flips when POST /activity/read arrives, like the real unread_count. */
function feed(items: any[], unread: number, pages?: any[][]) {
  const state = { unread, read: false };
  server.overrides.push(req => {
    if (req.path === '/activity' && req.method === 'GET') {
      const q = new URLSearchParams(req.query);
      const cursor = q.get('cursor');
      const idx = cursor ? parseInt(cursor, 10) : 0;
      const list = pages ? pages[idx] : items;
      return {
        status: 200,
        body: {
          items: q.get('limit') === '1' ? list.slice(0, 1) : list,
          next_cursor: pages && idx + 1 < pages.length ? String(idx + 1) : null,
          unread_count: state.read ? 0 : state.unread,
        },
      };
    }
    if (req.path === '/activity/read' && req.method === 'POST') {
      state.read = true;
      return { status: 204 };
    }
    return undefined;
  });
  return state;
}

const feedGets = () =>
  server.log.filter(
    r =>
      r.method === 'GET' &&
      r.path === '/activity' &&
      new URLSearchParams(r.query).get('limit') === '50',
  );
const reads = () =>
  server.log.filter(r => r.method === 'POST' && r.path === '/activity/read');

const badgeText = () => screen.queryByText(/^(\d+|99\+)$/);

describe('S5-M-2 tab badge', () => {
  it('shows the unread count on the Activity tab and labels it', async () => {
    feed([item('a')], 1);
    await render(<App queryClient={qc} />);
    await screen.findByLabelText('Activity, 1 unread');
    const badge = await screen.findByText('1');
    // neutral pill from the theme tokens (not brand, not error)
    const flat = StyleSheet.flatten(badge.props.style);
    expect(flat.backgroundColor).toBe(lightColors.inverseSurface);
    expect(flat.color).toBe(lightColors.inverseText);
  });

  it('is hidden at 0', async () => {
    feed([], 0);
    await render(<App queryClient={qc} />);
    await screen.findByLabelText('Activity');
    await waitFor(() =>
      expect(
        server.log.some(r => r.path === '/activity' && r.method === 'GET'),
      ).toBe(true),
    );
    expect(badgeText()).toBeNull();
  });

  it('shows "99+" for 250 unread but the accessibility label keeps the real count', async () => {
    feed([item('a')], 250);
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('99+')).toBeTruthy();
    expect(screen.getByLabelText('Activity, 250 unread')).toBeTruthy();
  });

  it('opening Activity calls POST /activity/read once and the badge goes to 0', async () => {
    feed([item('a', { is_unread: true }), item('b')], 1);
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('1')).toBeTruthy();
    expect(reads()).toHaveLength(0);

    await press('Activity');
    await waitFor(() => expect(reads()).toHaveLength(1));
    await waitFor(() => expect(badgeText()).toBeNull());
    expect(screen.getByLabelText('Activity')).toBeTruthy();
    expect(feedGets()).toHaveLength(1);
  });

  it('returning to the foreground refreshes the badge (B added an expense: badge shows 1)', async () => {
    const { AppState } = require('react-native');
    const callbacks: ((s: string) => void)[] = [];
    const original = AppState.addEventListener;
    AppState.addEventListener = jest.fn((type: string, cb: unknown) => {
      callbacks.push(cb as (s: string) => void);
      return original(type, cb);
    });
    const state = feed([item('a')], 0);
    await render(<App queryClient={qc} />);
    await screen.findByLabelText('Activity');
    await waitFor(() => expect(callbacks.length).toBeGreaterThan(0));
    expect(badgeText()).toBeNull();

    state.unread = 1; // B added an expense on the server
    callbacks.forEach(cb => cb('active'));
    expect(await screen.findByText('1')).toBeTruthy();
    AppState.addEventListener = original;
  });
});

describe('S5-M-2 Activity tab (SCR-10)', () => {
  it('renders the mocked feed in server order under Today / Yesterday / date headings', async () => {
    feed(
      [
        item('t1', { created_at: todayIso(2000) }),
        item('t2', {
          action: 'settlement.created',
          entity_type: 'settlement',
          entity_id: 's-1',
          summary: {
            amount: { amount_minor: 2000, currency: 'INR' },
            from_user_id: ME,
            from_name: 'Asha',
            to_user_id: 'u-ravi',
            to_name: 'Ravi',
          },
          my_effect: [{ amount_minor: 2000, currency: 'INR' }],
          created_at: todayIso(1000),
        }),
        item('y1', { created_at: yesterdayNoonIso() }),
        item('o1', { created_at: '2026-01-05T10:00:00Z' }),
      ],
      0,
    );
    await render(<App queryClient={qc} />);
    await press('Activity');
    await screen.findByText('Today');
    // the section heading and the old row's relative time both say Yesterday
    expect(screen.getAllByText('Yesterday')).toHaveLength(2);
    expect(screen.getAllByText('5 Jan 2026').length).toBeGreaterThan(0);
    const rows = screen.getAllByTestId('activity-row');
    expect(rows).toHaveLength(4);
    expect(rows[0].props.accessibilityLabel).toMatch(/^Ravi added Item t1/);
    expect(rows[1].props.accessibilityLabel).toMatch(
      /^Ravi recorded a payment: You paid Ravi INR 20.00/,
    );
    expect(rows[2].props.accessibilityLabel).toMatch(/Item y1/);
    expect(rows[3].props.accessibilityLabel).toMatch(/Item o1/);
  });

  it('effect chips carry a sign and a word; unread rows have a dot and say "unread"', async () => {
    feed(
      [
        item('u', { is_unread: true }),
        item('r', {
          my_effect: [
            { amount_minor: 2500, currency: 'INR' },
            { amount_minor: -300, currency: 'USD' },
          ],
        }),
      ],
      1,
    );
    await render(<App queryClient={qc} />);
    await press('Activity');
    expect(await screen.findByText('you owe −INR 30.00')).toBeTruthy();
    expect(screen.getByText('you are owed +INR 25.00')).toBeTruthy();
    expect(screen.getByText('you owe −USD 3.00')).toBeTruthy();
    const rows = screen.getAllByTestId('activity-row');
    expect(rows[0].props.accessibilityLabel).toMatch(/unread$/);
    expect(rows[1].props.accessibilityLabel).not.toMatch(/unread/);
    expect(screen.getAllByTestId('unread-dot')).toHaveLength(1);
  });

  it('tap-through: expense item opens SCR-29', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    const e = server.addExpense({
      id: 'x-e1',
      description: 'Groceries',
      group_id: g.id,
      splits: [],
    });
    feed([item('e', { entity_id: e.id, group_id: g.id })], 0);
    await render(<App queryClient={qc} />);
    await press('Activity');
    await fireEvent.press((await screen.findAllByTestId('activity-row'))[0]);
    expect(await screen.findByText('Groceries')).toBeTruthy();
    expect(server.count('GET', `/expenses/${e.id}`)).toBeGreaterThanOrEqual(1);
  });

  it('payment item opens SCR-32', async () => {
    server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    feed(
      [
        item('s', {
          action: 'settlement.created',
          entity_type: 'settlement',
          entity_id: 's-7',
          summary: {
            amount: { amount_minor: 2000, currency: 'INR' },
            from_user_id: ME,
            to_user_id: 'u-ravi',
          },
        }),
      ],
      0,
    );
    server.overrides.push(req =>
      req.path === '/settlements/s-7' && req.method === 'GET'
        ? {
            status: 200,
            body: {
              id: 's-7',
              group_id: null,
              from_user_id: ME,
              to_user_id: 'u-ravi',
              amount: { amount_minor: 2000, currency: 'INR' },
              settled_on: '2026-11-12',
              note: null,
              batch_id: null,
              created_by: ME,
              created_at: '2026-11-12T10:00:00Z',
              deleted_at: null,
              version: 1,
            },
          }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    await press('Activity');
    await fireEvent.press((await screen.findAllByTestId('activity-row'))[0]);
    expect(await screen.findByText(/paid .* INR 20\.00/)).toBeTruthy();
    expect(server.count('GET', '/settlements/s-7')).toBe(1);
  });

  it('group item opens SCR-13', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    feed(
      [
        item('g', {
          action: 'group.created',
          entity_type: 'group',
          entity_id: g.id,
          group_id: g.id,
          summary: { name: 'Flat' },
          my_effect: [],
        }),
      ],
      0,
    );
    await render(<App queryClient={qc} />);
    await press('Activity');
    await fireEvent.press((await screen.findAllByTestId('activity-row'))[0]);
    expect(await screen.findByText('Balances')).toBeTruthy();
    expect(server.count('GET', `/groups/${g.id}/timeline`)).toBe(1);
  });

  it('infinite scroll: page 2 loads on end reached with exactly one more request, spinner footer, no duplicates', async () => {
    feed([], 0, [
      [item('p1a'), item('p1b')],
      [item('p2a'), item('p2b')],
    ]);
    await render(<App queryClient={qc} />);
    await press('Activity');
    await screen
      .findByText('Ravi added Item p1a', { exact: false })
      .catch(() => undefined);
    await waitFor(() =>
      expect(screen.getAllByTestId('activity-row')).toHaveLength(2),
    );
    expect(feedGets()).toHaveLength(1);
    await fireEvent(screen.getByTestId('activity-list'), 'endReached');
    await waitFor(() =>
      expect(screen.getAllByTestId('activity-row')).toHaveLength(4),
    );
    expect(feedGets()).toHaveLength(2);
    expect(new URLSearchParams(feedGets()[1].query).get('cursor')).toBe('1');
    // the end: next_cursor null, another scroll sends nothing
    await fireEvent(screen.getByTestId('activity-list'), 'endReached');
    expect(feedGets()).toHaveLength(2);
  });

  it('empty feed: "No activity yet"', async () => {
    feed([], 0);
    await render(<App queryClient={qc} />);
    await press('Activity');
    expect(await screen.findByText('No activity yet')).toBeTruthy();
  });

  it('first load shows a skeleton labelled Loading', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>(r => {
      release = r;
    });
    const realFetch = (global as any).fetch;
    feed([item('a')], 0);
    (global as any).fetch = jest.fn(async (url: string, init: any) => {
      if (url.includes('/activity?') && url.includes('limit=50')) {
        await gate;
      }
      return realFetch(url, init);
    });
    await render(<App queryClient={qc} />);
    await press('Activity');
    expect(await screen.findByTestId('activity-skeleton')).toBeTruthy();
    expect(screen.getByLabelText('Loading')).toBeTruthy();
    release();
    await waitFor(() =>
      expect(screen.getAllByTestId('activity-row')).toHaveLength(1),
    );
    expect(screen.queryByTestId('activity-skeleton')).toBeNull();
  });

  it('server error on first load: error view with Retry that reloads; no read is sent', async () => {
    let fail = true;
    server.overrides.push(req => {
      if (
        fail &&
        req.path === '/activity' &&
        new URLSearchParams(req.query).get('limit') === '50'
      ) {
        return { status: 500, body: { code: 'INTERNAL_ERROR', message: 'x' } };
      }
      return undefined;
    });
    feed([item('a')], 0);
    await render(<App queryClient={qc} />);
    await press('Activity');
    await press('Retry');
    expect(reads()).toHaveLength(0);
    fail = false;
    await press('Retry');
    await waitFor(() =>
      expect(screen.getAllByTestId('activity-row')).toHaveLength(1),
    );
    await waitFor(() => expect(reads()).toHaveLength(1));
  });

  it('network failure on first load shows the offline wording', async () => {
    feed([], 0);
    const realFetch = (global as any).fetch;
    (global as any).fetch = jest.fn(async (url: string, init: any) => {
      if (url.includes('limit=50')) {
        throw new TypeError('Network request failed');
      }
      return realFetch(url, init);
    });
    await render(<App queryClient={qc} />);
    await press('Activity');
    expect(
      await screen.findByText("You're offline or the server can't be reached."),
    ).toBeTruthy();
  });
});
