/**
 * S6-M-5: offline cache (React Query persistence) and the write queue with Idempotency-Key for expenses and
 * settlements. Screen-level tests against the fake server; "airplane mode" is a fetch that throws.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { newIdempotencyKey } from '../../src/api/helpers';
import {
  CACHE_KEY,
  restoreQueryCache,
  saveCachedUser,
  loadCachedUser,
  startCachePersistence,
  USER_KEY,
} from '../../src/offline/cache';
import { createAppQueryClient } from '../../src/offline/queryClient';
import { isNetworkError } from '../../src/offline/connectivity';
import {
  QUEUE_KEY,
  discardWrite,
  enqueueWrite,
  flushQueue,
  getQueue,
} from '../../src/offline/queue';
import { launch, makeEnv, press, reqs, resetEnv } from '../../testUtils/slice6';

const env = makeEnv();
beforeEach(async () => {
  await resetEnv(env);
});
afterEach(() => env.qc.clear());

const goOffline = () => {
  (global as any).fetch = jest.fn(async () => {
    throw new TypeError('Network request failed');
  });
};

const settlementBody = {
  group_id: null,
  from_user_id: 'u-me',
  to_user_id: 'u-ravi',
  amount: { amount_minor: 2000, currency: 'INR' },
  settled_on: '2026-11-12',
  note: null,
};
const expenseBody = {
  description: 'Dinner',
  total: { amount_minor: 10000, currency: 'INR' },
  expense_date: '2026-11-12',
  payers: [{ user_id: 'u-me', paid_amount_minor: 10000 }],
  split: {
    type: 'equal' as const,
    entries: [{ user_id: 'u-me' }, { user_id: 'u-ravi' }],
  },
};

describe('isNetworkError', () => {
  it('is true for a thrown fetch, false for ordinary errors', () => {
    expect(isNetworkError(new TypeError('Network request failed'))).toBe(true);
    expect(isNetworkError(new Error('Network request failed'))).toBe(true);
    expect(isNetworkError(new Error('boom'))).toBe(false);
    expect(isNetworkError(undefined)).toBe(false);
  });
});

describe('write queue (unit)', () => {
  it('persists a queued write with its Idempotency-Key and reloads it', async () => {
    const key = newIdempotencyKey();
    await enqueueWrite(
      { kind: 'expense', body: { ...expenseBody, group_id: null } },
      key,
    );
    const saved = JSON.parse((await AsyncStorage.getItem(QUEUE_KEY)) ?? '[]');
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({ kind: 'expense', key, state: 'pending' });
  });

  it('replays oldest first with the saved keys, sends each once and clears the queue on 201', async () => {
    const k1 = newIdempotencyKey();
    const k2 = newIdempotencyKey();
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await enqueueWrite(
      { kind: 'group_expense', groupId: g.id, body: expenseBody },
      k1,
    );
    await enqueueWrite({ kind: 'settlement', body: settlementBody }, k2);
    env.server.overrides.push(req =>
      req.path === '/settlements'
        ? { status: 201, body: { id: 's1' } }
        : undefined,
    );
    const result = await flushQueue(env.qc);
    expect(result).toEqual({ sent: 2, failed: 0, blocked: false });
    const sent = env.server.log.filter(r => r.method === 'POST');
    expect(sent.map(r => r.path)).toEqual([
      `/groups/${g.id}/expenses`,
      '/settlements',
    ]);
    expect(sent.map(r => r.headers.get('Idempotency-Key'))).toEqual([k1, k2]);
    expect(getQueue()).toHaveLength(0);
    expect(JSON.parse((await AsyncStorage.getItem(QUEUE_KEY)) ?? '[]')).toEqual(
      [],
    );
  });

  it('keeps everything and stops when there is still no connection', async () => {
    await enqueueWrite(
      { kind: 'settlement', body: settlementBody },
      newIdempotencyKey(),
    );
    await enqueueWrite(
      { kind: 'settlement', body: settlementBody },
      newIdempotencyKey(),
    );
    goOffline();
    const result = await flushQueue(env.qc);
    expect(result).toEqual({ sent: 0, failed: 0, blocked: true });
    expect((global as any).fetch).toHaveBeenCalledTimes(1); // stopped at the first one: order is kept
    expect(getQueue()).toHaveLength(2);
  });

  it.each([500, 503, 429, 401])(
    'a %i keeps the item and stops for a later retry',
    async status => {
      await enqueueWrite(
        { kind: 'settlement', body: settlementBody },
        newIdempotencyKey(),
      );
      env.server.overrides.push(req =>
        req.path === '/settlements'
          ? { status, body: { code: 'X', message: 'x' } }
          : undefined,
      );
      env.server.refreshOk = false;
      const result = await flushQueue(env.qc);
      expect(result.blocked).toBe(true);
      expect(getQueue()[0].state).toBe('pending');
    },
  );

  it('a 422 marks that item failed (never retried) and the next one still goes', async () => {
    await enqueueWrite(
      { kind: 'settlement', body: settlementBody },
      newIdempotencyKey(),
    );
    await enqueueWrite(
      { kind: 'settlement', body: { ...settlementBody, note: 'second' } },
      newIdempotencyKey(),
    );
    let n = 0;
    env.server.overrides.push(req => {
      if (req.path === '/settlements') {
        n += 1;
        return n === 1
          ? {
              status: 422,
              body: {
                code: 'PARTICIPANT_NOT_MEMBER',
                message: 'Not a member any more',
              },
            }
          : { status: 201, body: { id: 's2' } };
      }
    });
    const result = await flushQueue(env.qc);
    expect(result).toEqual({ sent: 1, failed: 1, blocked: false });
    expect(getQueue()).toHaveLength(1);
    expect(getQueue()[0]).toMatchObject({
      state: 'failed',
      error: 'Not a member any more',
    });
    // a failed item is not sent again
    await flushQueue(env.qc);
    expect(env.server.log.filter(r => r.path === '/settlements')).toHaveLength(
      2,
    );
    await discardWrite(getQueue()[0].id);
    expect(getQueue()).toHaveLength(0);
  });

  it('a replay the server already applied (same key) is accepted as success', async () => {
    const key = newIdempotencyKey();
    await enqueueWrite({ kind: 'settlement', body: settlementBody }, key);
    env.server.overrides.push(req =>
      req.path === '/settlements'
        ? { status: 201, body: { id: 'original' } }
        : undefined,
    );
    expect((await flushQueue(env.qc)).sent).toBe(1);
    expect(getQueue()).toHaveLength(0);
  });
});

describe('cache persistence (unit)', () => {
  it('saves successful queries per user, restores them, and ignores another user or old data', async () => {
    const a = new QueryClient();
    a.setQueryData(['/groups'], { status: 200, data: { items: [1] } });
    const stop = startCachePersistence(a, 'u-me');
    a.setQueryData(['/friends'], { status: 200, data: { items: [] } });
    await new Promise(r => setTimeout(r, 1100));
    stop();
    expect(await AsyncStorage.getItem(CACHE_KEY)).toContain('/friends');

    const b = new QueryClient();
    expect(await restoreQueryCache(b, 'someone-else')).toBe(false);
    expect(b.getQueryData(['/groups'])).toBeUndefined();
    expect(
      await restoreQueryCache(b, 'u-me', Date.now() + 25 * 3600 * 1000),
    ).toBe(false);
    expect(await restoreQueryCache(b, 'u-me')).toBe(true);
    expect(b.getQueryData(['/groups'])).toEqual({
      status: 200,
      data: { items: [1] },
    });
  });

  it('keeps the last profile for an offline start', async () => {
    await saveCachedUser(env.server.me);
    expect((await loadCachedUser())?.id).toBe('u-me');
  });
});

describe('S6-M-5 offline add expense (E2E style)', () => {
  async function openForm() {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Add expense');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'Dinner',
    );
    await fireEvent.changeText(screen.getByLabelText('Amount'), '100');
    return g;
  }

  it('airplane mode -> add expense -> "1 unsynced"; reconnect -> exactly 1 expense on the server', async () => {
    const g = await openForm();
    const online = (global as any).fetch;
    goOffline();
    await press('Save');
    expect(
      await screen.findByText(
        "Saved on this device. It will sync when you're online.",
      ),
    ).toBeTruthy();
    expect(await screen.findByText('1 unsynced')).toBeTruthy();
    expect(
      screen.getByText("You're offline. Showing saved data."),
    ).toBeTruthy();
    expect(env.server.expenses).toHaveLength(0);

    (global as any).fetch = online; // reconnect
    await press('Sync now');
    await waitFor(() => expect(env.server.expenses).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText('1 unsynced')).toBeNull());
    expect(reqs(env.server, 'POST', `/groups/${g.id}/expenses`)).toHaveLength(
      1,
    );
    expect(env.server.expenses[0]).toMatchObject({
      description: 'Dinner',
      total: { amount_minor: 10000 },
    });
    // syncing again sends nothing more
    expect(getQueue()).toHaveLength(0);
  });

  it('a request that reached the server but lost its response is not applied twice', async () => {
    const g = await openForm();
    const seen = new Map<string, unknown>();
    // a server that remembers Idempotency-Keys (as the contract promises) and whose first response is lost
    let lose = true;
    let inner = false;
    env.server.overrides.push(req => {
      if (
        !inner &&
        req.method === 'POST' &&
        req.path === `/groups/${g.id}/expenses`
      ) {
        const key = req.headers.get('Idempotency-Key') ?? '';
        if (seen.has(key)) {
          return seen.get(key) as never;
        }
        inner = true;
        const res = env.server.handle(req);
        inner = false;
        seen.set(key, res);
        if (lose) {
          lose = false;
          throw new TypeError('Network request failed'); // applied, response lost
        }
        return res;
      }
    });
    await press('Save');
    expect(await screen.findByText('1 unsynced')).toBeTruthy();
    expect(env.server.expenses).toHaveLength(1); // the server did apply it
    await press('Sync now');
    await waitFor(() => expect(screen.queryByText('1 unsynced')).toBeNull());
    expect(env.server.expenses).toHaveLength(1);
    const keys = reqs(env.server, 'POST', `/groups/${g.id}/expenses`).map(r =>
      r.headers.get('Idempotency-Key'),
    );
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('a rejected queued change shows a message with Discard', async () => {
    await openForm();
    const online = (global as any).fetch;
    goOffline();
    await press('Save');
    await screen.findByText('1 unsynced');
    (global as any).fetch = online;
    env.server.overrides.push(req =>
      req.method === 'POST' && /\/expenses$/.test(req.path)
        ? {
            status: 422,
            body: {
              code: 'PARTICIPANT_NOT_MEMBER',
              message: 'Someone left the group',
            },
          }
        : undefined,
    );
    await press('Sync now');
    expect(await screen.findByText(/Someone left the group/)).toBeTruthy();
    await press('Discard');
    await waitFor(() =>
      expect(screen.queryByText(/Someone left the group/)).toBeNull(),
    );
    expect(getQueue()).toHaveLength(0);
  });

  it('editing an expense offline is not queued: it shows the offline message and stays on the form', async () => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.addExpense({
      id: 'x1',
      group_id: g.id,
      description: 'Tea',
      splits: [
        { user_id: 'u-me', owed_amount_minor: 5000 },
        { user_id: 'u-ravi', owed_amount_minor: 5000 },
      ],
    });
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Tea');
    await press('Edit');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'Tea and snacks',
    );
    goOffline();
    await press('Save');
    expect(await screen.findByText(/Can't reach the server/)).toBeTruthy();
    expect(getQueue()).toHaveLength(0);
  });
});

describe('S6-M-5 offline start and logout', () => {
  it('after one online session the app opens offline from the saved profile and cache, with the offline notice', async () => {
    env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await launch(env);
    await press('Groups');
    expect(await screen.findByText('Flat')).toBeTruthy();
    await waitFor(
      async () =>
        expect(await AsyncStorage.getItem(CACHE_KEY)).toContain('Flat'),
      {
        timeout: 3000,
      },
    );
    await cleanup(); // the app is closed

    goOffline();
    // the app's own client (it keeps cached data on a failed refresh); no retries so the test is fast
    env.qc = createAppQueryClient();
    env.qc.setDefaultOptions({ queries: { retry: false, gcTime: Infinity } });
    await launch(env);
    await press('Groups');
    expect(await screen.findByText('Flat')).toBeTruthy(); // from the cache, not an error screen
    expect(
      screen.queryByText(/offline or the server can't be reached/),
    ).toBeNull();
    expect(
      await screen.findByText("You're offline. Showing saved data."),
    ).toBeTruthy();
  });

  it('with no saved profile an unreachable server still shows Retry', async () => {
    goOffline();
    await launch(env);
    expect(await screen.findByText("Can't reach the server.")).toBeTruthy();
    expect(screen.getByText('Retry')).toBeTruthy();
  });

  it('logging out deletes the saved profile, cache and queued changes', async () => {
    await enqueueWrite(
      { kind: 'settlement', body: settlementBody },
      newIdempotencyKey(),
    );
    await launch(env);
    await press('Groups');
    await screen.findByText('No groups yet');
    await waitFor(async () =>
      expect(await AsyncStorage.getItem(USER_KEY)).not.toBeNull(),
    );
    await press('Account');
    await press('Log out');
    // the dialog's confirm button is the last "Log out"
    await fireEvent.press((await screen.findAllByText('Log out')).slice(-1)[0]);
    await screen.findByText('Share expenses, settle up.');
    expect(await AsyncStorage.getItem(USER_KEY)).toBeNull();
    expect(await AsyncStorage.getItem(CACHE_KEY)).toBeNull();
    expect(await AsyncStorage.getItem(QUEUE_KEY)).toBeNull();
    expect(getQueue()).toHaveLength(0);
  });
});
