/**
 * S5-M-1 (Settle up SCR-30, Record payment SCR-31, Payment detail SCR-32) and S5-M-3 (payment rows in the SCR-13
 * timeline). Component/screen tests against the fake server with a small settlement ledger; NOT real E2E (no
 * emulator or Detox/Maestro in the repo).
 */
import React from 'react';
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
import { FakeServer } from '../testUtils/fakeServer';

let server: FakeServer;
let qc: QueryClient;
const ME = 'u-me';
const RAVI = 'u-ravi';

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
const pressLabel = async (label: string | RegExp) =>
  fireEvent.press(await screen.findByLabelText(label));
const posts = (path: string | RegExp) =>
  server.log.filter(
    r =>
      r.method === 'POST' &&
      (typeof path === 'string' ? r.path === path : path.test(r.path)),
  );

const settlement = (o: Record<string, unknown> = {}) => ({
  id: 's-1',
  group_id: null,
  from_user_id: ME,
  to_user_id: RAVI,
  amount: { amount_minor: 2000, currency: 'INR' },
  settled_on: '2026-11-12',
  note: null,
  batch_id: null,
  created_by: ME,
  created_at: '2026-11-12T10:00:00Z',
  deleted_at: null,
  version: 1,
  ...o,
});

/**
 * FLOW-05: group "Flat", me and Ravi. I owe Ravi `owed` (minor units, INR). A tiny ledger answers the balances,
 * timeline and settlement calls so the screens run against changing server state.
 */
function ledger(owed: number) {
  const g = server.addGroup('Flat', [server.user(RAVI, 'Ravi')]);
  const state = { owed, settlements: [] as any[], seq: 0 };
  server.overrides.push(req => {
    const { method, path } = req;
    if (path === `/groups/${g.id}/balances` && method === 'GET') {
      return {
        status: 200,
        body: {
          group_id: g.id,
          simplified: true,
          members: [
            {
              user_id: ME,
              balances: [{ amount_minor: -state.owed, currency: 'INR' }],
            },
            {
              user_id: RAVI,
              balances: [{ amount_minor: state.owed, currency: 'INR' }],
            },
          ],
          transfers:
            state.owed > 0
              ? [
                  {
                    from_user_id: ME,
                    to_user_id: RAVI,
                    amount_minor: state.owed,
                    currency: 'INR',
                  },
                ]
              : [],
        },
      };
    }
    if (path === '/settlements' && method === 'POST') {
      const b = req.body;
      state.seq += 1;
      const s = settlement({
        id: `s-${state.seq}`,
        group_id: b.group_id,
        from_user_id: b.from_user_id,
        to_user_id: b.to_user_id,
        amount: b.amount,
        settled_on: b.settled_on,
        note: b.note ?? null,
      });
      state.settlements.push(s);
      state.owed = state.owed - b.amount.amount_minor;
      return { status: 201, body: s };
    }
    if (path === `/groups/${g.id}/timeline` && method === 'GET') {
      return {
        status: 200,
        body: {
          items: state.settlements.map(s => ({
            kind: 'settlement',
            date: s.settled_on,
            settlement: s,
          })),
          next_cursor: null,
        },
      };
    }
    return undefined;
  });
  return { g, state };
}

async function openSettleUp() {
  await render(<App queryClient={qc} />);
  await press('Groups');
  await press('Flat');
  await press('Settle up');
}

describe('S5-M-1 Settle up (SCR-30)', () => {
  it('shows "you owe Ravi" with a sign and the word "owe" on the chip', async () => {
    ledger(3333);
    await openSettleUp();
    expect(await screen.findByText('you owe Ravi')).toBeTruthy();
    expect(screen.getByText('−INR 33.33 owe')).toBeTruthy();
    expect(screen.getByText(/Already paid\?/)).toBeTruthy();
  });

  it('no balances: "You are settled up"', async () => {
    ledger(0);
    await openSettleUp();
    expect(await screen.findByText('You are settled up')).toBeTruthy();
    expect(screen.queryByTestId('balance-row')).toBeNull();
  });

  it('server error shows Retry; offline is not red text only', async () => {
    const { g } = ledger(3333);
    server.overrides.unshift(req =>
      req.path === `/groups/${g.id}/balances` && req.method === 'GET'
        ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'x' } }
        : undefined,
    );
    await openSettleUp();
    expect(await screen.findByText('Retry')).toBeTruthy();
  });

  it('friend scope: "Settle all balances" posts one settle-all after confirmation', async () => {
    server.addFriendRow(RAVI, 'Ravi', [
      { amount_minor: -3333, currency: 'INR' },
      { amount_minor: -500, currency: 'USD' },
    ]);
    server.friends[0].breakdown = [
      {
        scope: 'group',
        group_id: 'g-x',
        group_name: 'Flat',
        balances: [{ amount_minor: -3333, currency: 'INR' }],
      },
      {
        scope: 'non_group',
        group_id: null,
        group_name: null,
        balances: [{ amount_minor: -500, currency: 'USD' }],
      },
    ];
    server.overrides.push(req =>
      req.path === '/settlements/settle-all' && req.method === 'POST'
        ? {
            status: 201,
            body: {
              batch_id: 'b-1',
              items: [settlement({ id: 's-a' }), settlement({ id: 's-b' })],
            },
          }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    await press('Friends');
    await press('Ravi');
    await press('Settle up');
    expect(await screen.findByText('−INR 33.33 owe')).toBeTruthy();
    expect(screen.getByText('−USD 5.00 owe')).toBeTruthy();
    await press('Settle all balances');
    await press('Settle all');
    await waitFor(() =>
      expect(posts('/settlements/settle-all')).toHaveLength(1),
    );
    expect(posts('/settlements/settle-all')[0].body).toEqual({
      friend_user_id: RAVI,
    });
  });
});

describe('S5-M-1 Record payment (SCR-31), FLOW-05', () => {
  it('partial then full: nets go to zero and Settle up shows "settled up"', async () => {
    const { g, state } = ledger(3333);
    await openSettleUp();
    await press('you owe Ravi');

    // prefilled from the tapped row: from me to Ravi, 33.33 INR, today, the group
    const amount = await screen.findByLabelText('Amount');
    expect(amount.props.value).toBe('33.33');
    expect(screen.getByText('Flat')).toBeTruthy();

    await fireEvent.changeText(amount, '20.00');
    await press('Save payment');
    await waitFor(() => expect(posts('/settlements')).toHaveLength(1));
    const first = posts('/settlements')[0];
    expect(first.body).toMatchObject({
      group_id: g.id,
      from_user_id: ME,
      to_user_id: RAVI,
      amount: { amount_minor: 2000, currency: 'INR' },
    });
    expect(first.body.settled_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(first.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(state.owed).toBe(1333);
    expect(await screen.findByText('Payment recorded')).toBeTruthy();

    // back on the group, then Settle up again: 13.33 is left
    await press('Settle up');
    expect(await screen.findByText('−INR 13.33 owe')).toBeTruthy();
    await press('you owe Ravi');
    expect((await screen.findByLabelText('Amount')).props.value).toBe('13.33');
    await press('Save payment');
    await waitFor(() => expect(posts('/settlements')).toHaveLength(2));
    expect(posts('/settlements')[1].body.amount.amount_minor).toBe(1333);
    expect(state.owed).toBe(0);

    await press('Settle up');
    expect(await screen.findByText('You are settled up')).toBeTruthy();
  });

  it('amount 0 -> "Enter an amount greater than 0.", no request', async () => {
    ledger(3333);
    await openSettleUp();
    await press('you owe Ravi');
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '0');
    await press('Save payment');
    expect(
      await screen.findByText('Enter an amount greater than 0.'),
    ).toBeTruthy();
    expect(posts('/settlements')).toHaveLength(0);
  });

  it('cleared amount is also rejected without a request', async () => {
    ledger(3333);
    await openSettleUp();
    await press('you owe Ravi');
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '');
    await press('Save payment');
    expect(
      await screen.findByText('Enter an amount greater than 0.'),
    ).toBeTruthy();
    expect(posts('/settlements')).toHaveLength(0);
  });

  it('overpay: 50.00 against 13.33 asks first, states the flip in words, then saves on confirm', async () => {
    const { state } = ledger(1333);
    await openSettleUp();
    await press('you owe Ravi');
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '50.00');
    await press('Save payment');

    expect(await screen.findByText('This is more than owed')).toBeTruthy();
    expect(screen.getByText('Ravi will then owe you INR 36.67.')).toBeTruthy();
    expect(posts('/settlements')).toHaveLength(0);

    await press('Record payment');
    await waitFor(() => expect(posts('/settlements')).toHaveLength(1));
    expect(posts('/settlements')[0].body.amount.amount_minor).toBe(5000);
    expect(state.owed).toBe(-3667);
  });

  it('overpay: Cancel sends nothing and keeps the form', async () => {
    ledger(1333);
    await openSettleUp();
    await press('you owe Ravi');
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '50.00');
    await press('Save payment');
    await press('Cancel');
    expect(posts('/settlements')).toHaveLength(0);
    expect(screen.getByLabelText('Amount').props.value).toBe('50.00');
  });

  it('exactly the owed amount does not ask for confirmation', async () => {
    ledger(1333);
    await openSettleUp();
    await press('you owe Ravi');
    await press('Save payment');
    await waitFor(() => expect(posts('/settlements')).toHaveLength(1));
    expect(screen.queryByText('This is more than owed')).toBeNull();
  });

  it('a different currency than the balance is allowed without the overpay dialog', async () => {
    ledger(1333);
    await openSettleUp();
    await press('you owe Ravi');
    await pressLabel('Currency: INR');
    await press(/USD - US Dollar/);
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '5.00');
    await press('Save payment');
    await waitFor(() => expect(posts('/settlements')).toHaveLength(1));
    expect(posts('/settlements')[0].body.amount).toEqual({
      amount_minor: 500,
      currency: 'USD',
    });
  });

  it('server 422 SAME_PARTY shows the fix in a banner', async () => {
    ledger(1333);
    server.overrides.unshift(req =>
      req.path === '/settlements' && req.method === 'POST'
        ? { status: 422, body: { code: 'SAME_PARTY', message: 'same' } }
        : undefined,
    );
    await openSettleUp();
    await press('you owe Ravi');
    await press('Save payment');
    expect(
      await screen.findByText(
        'The payer and the receiver must be different people.',
      ),
    ).toBeTruthy();
  });

  it('Undo on the snackbar deletes the payment just recorded', async () => {
    const { state } = ledger(3333);
    server.overrides.push(req => {
      const m = /^\/settlements\/(s-\d+)$/.exec(req.path);
      if (m && req.method === 'DELETE') {
        const s = state.settlements.find(x => x.id === m[1]);
        state.owed += s.amount.amount_minor;
        return { status: 200, body: { ...s, deleted_at: 'now' } };
      }
      return undefined;
    });
    await openSettleUp();
    await press('you owe Ravi');
    await press('Save payment');
    await press('Undo');
    await waitFor(() => expect(state.owed).toBe(3333));
    expect(
      server.log.filter(
        r => r.method === 'DELETE' && r.path === '/settlements/s-1',
      ),
    ).toHaveLength(1);
  });
});

describe('S5-M-1 Payment detail (SCR-32)', () => {
  const open = async (s: any) => {
    const { g } = ledger(0);
    const row = { ...s, group_id: g.id };
    server.overrides.unshift(req =>
      req.path === `/groups/${g.id}/timeline` && req.method === 'GET'
        ? {
            status: 200,
            body: {
              items: [
                { kind: 'settlement', date: row.settled_on, settlement: row },
              ],
              next_cursor: null,
            },
          }
        : undefined,
    );
    return { g, row };
  };

  it('delete asks first, calls DELETE, then Restore appears and restores', async () => {
    let current: any = settlement();
    const { row } = await open(current);
    current = row;
    server.overrides.unshift(req => {
      if (req.path === '/settlements/s-1') {
        if (req.method === 'GET') {
          return { status: 200, body: current };
        }
        if (req.method === 'DELETE') {
          current = { ...current, deleted_at: '2026-11-13T00:00:00Z' };
          return { status: 200, body: current };
        }
      }
      if (req.path === '/settlements/s-1/restore' && req.method === 'POST') {
        current = { ...current, deleted_at: null };
        return { status: 200, body: current };
      }
      return undefined;
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await pressLabel(/^Payment: /);
    expect(await screen.findByText('You paid Ravi INR 20.00')).toBeTruthy();
    expect(screen.getByText('2026-11-12')).toBeTruthy();
    expect(screen.getByText('Flat')).toBeTruthy();

    await press('Delete');
    expect(await screen.findByText('Delete this payment?')).toBeTruthy();
    expect(server.log.filter(r => r.method === 'DELETE')).toHaveLength(0);
    await fireEvent.press(screen.getAllByText('Delete')[1]);
    expect(await screen.findByTestId('deleted-banner')).toBeTruthy();
    expect(
      server.log.filter(
        r => r.method === 'DELETE' && r.path === `/settlements/s-1`,
      ),
    ).toHaveLength(1);

    await press('Restore');
    await waitFor(() =>
      expect(screen.queryByTestId('deleted-banner')).toBeNull(),
    );
    expect(posts('/settlements/s-1/restore')).toHaveLength(1);
  });

  it('409 on delete shows the neutral conflict message', async () => {
    const { row } = await open(settlement());
    server.overrides.unshift(req => {
      if (req.path === '/settlements/s-1') {
        return req.method === 'GET'
          ? { status: 200, body: row }
          : {
              status: 409,
              body: { code: 'CONFLICT', message: 'Cannot change' },
            };
      }
      return undefined;
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await pressLabel(/^Payment: /);
    await press('Delete');
    await fireEvent.press((await screen.findAllByText('Delete'))[1]);
    expect(await screen.findByText('Cannot change')).toBeTruthy();
  });

  it('Edit opens the form with the saved values and PATCHes with the version', async () => {
    const { row } = await open(settlement({ version: 4 }));
    server.overrides.unshift(req => {
      if (req.path === '/settlements/s-1') {
        if (req.method === 'GET') {
          return { status: 200, body: row };
        }
        if (req.method === 'PATCH') {
          return { status: 200, body: { ...row, version: 5 } };
        }
      }
      return undefined;
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await pressLabel(/^Payment: /);
    await press('Edit');
    const amount = await screen.findByLabelText('Amount');
    expect(amount.props.value).toBe('20.00');
    await fireEvent.changeText(amount, '25.50');
    await press('Save payment');
    await waitFor(() =>
      expect(
        server.log.filter(
          r => r.method === 'PATCH' && r.path === '/settlements/s-1',
        ),
      ).toHaveLength(1),
    );
    const patch = server.log.find(r => r.method === 'PATCH')!;
    expect(patch.body).toMatchObject({
      version: 4,
      amount: { amount_minor: 2550, currency: 'INR' },
    });
  });
});

describe('S5-M-3 SCR-13 timeline with payment rows', () => {
  const expense = (id: string, description: string, date: string, at: string) =>
    ({
      kind: 'expense',
      date,
      expense: {
        id,
        group_id: 'g',
        description,
        total: { amount_minor: 9000, currency: 'INR' },
        category_id: 1,
        expense_date: date,
        notes: null,
        split_type: 'equal',
        payers: [{ user_id: RAVI, paid_amount_minor: 9000 }],
        splits: [],
        comment_count: 0,
        created_by: RAVI,
        updated_by: null,
        created_at: at,
        updated_at: at,
        deleted_at: null,
        deleted_by: null,
        version: 1,
        my_net: { amount_minor: -3000, currency: 'INR' },
      },
    }) as const;
  const pay = (id: string, date: string, at: string, extra = {}) => ({
    kind: 'settlement',
    date,
    settlement: settlement({ id, settled_on: date, created_at: at, ...extra }),
  });

  const labels = () =>
    screen
      .getAllByRole('button')
      .map(b => b.props.accessibilityLabel as string | undefined)
      .filter((l): l is string => !!l && /^(Expense|Payment): /.test(l))
      .map(l => l.split(':')[0] + ':' + l.split(': ')[1].split(/ INR|,/)[0]);

  it('renders a mocked mixed page in the server order, with no merging and no extra list requests', async () => {
    const g = server.addGroup('Flat', [server.user(RAVI, 'Ravi')]);
    // Server order: expense, payment, expense, payment (date desc, then created_at desc). A client sort by kind or
    // a merge with a second list would change this.
    const items = [
      expense('e-1', 'Dinner', '2026-11-12', '2026-11-12T08:00:00Z'),
      pay('s-1', '2026-11-12', '2026-11-12T07:00:00Z', { group_id: g.id }),
      expense('e-2', 'Taxi', '2026-11-10', '2026-11-10T08:00:00Z'),
      pay('s-2', '2026-11-09', '2026-11-09T07:00:00Z', {
        group_id: g.id,
        deleted_at: '2026-11-09T09:00:00Z',
      }),
    ];
    server.overrides.push(req =>
      req.path === `/groups/${g.id}/timeline` && req.method === 'GET'
        ? { status: 200, body: { items, next_cursor: null } }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await screen.findByText('Dinner');
    expect(labels()).toEqual([
      'Expense:Dinner',
      'Payment:You paid Ravi',
      'Expense:Taxi',
      'Payment:You paid Ravi',
    ]);
    // payment rows are visibly different and the deleted one is tagged
    expect(screen.getAllByTestId('payment-row')).toHaveLength(2);
    expect(screen.getByText('2026-11-09 · deleted')).toBeTruthy();
    expect(server.count('GET', '/settlements')).toBe(0);
    expect(server.count('GET', `/groups/${g.id}/expenses`)).toBe(0);
    expect(server.count('GET', `/groups/${g.id}/timeline`)).toBe(1);
  });

  it('keeps a server page exactly as sent even when it is not date-sorted (no client sort or merge)', async () => {
    const g = server.addGroup('Flat', [server.user(RAVI, 'Ravi')]);
    // Deliberately out of date order: any client-side sort by date, kind or created_at would change the result.
    const items = [
      pay('s-1', '2026-11-01', '2026-11-01T07:00:00Z', { group_id: g.id }),
      expense('e-1', 'Dinner', '2026-11-12', '2026-11-12T08:00:00Z'),
      pay('s-2', '2026-11-20', '2026-11-20T07:00:00Z', { group_id: g.id }),
      expense('e-2', 'Taxi', '2026-11-05', '2026-11-05T08:00:00Z'),
    ];
    server.overrides.push(req =>
      req.path === `/groups/${g.id}/timeline` && req.method === 'GET'
        ? { status: 200, body: { items, next_cursor: null } }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await screen.findByText('Dinner');
    expect(labels()).toEqual([
      'Payment:You paid Ravi',
      'Expense:Dinner',
      'Payment:You paid Ravi',
      'Expense:Taxi',
    ]);
  });

  it('tapping a payment row opens SCR-32 for that settlement', async () => {
    const g = server.addGroup('Flat', [server.user(RAVI, 'Ravi')]);
    const row = pay('s-9', '2026-11-12', '2026-11-12T07:00:00Z', {
      group_id: g.id,
    });
    server.overrides.push(req => {
      if (req.path === `/groups/${g.id}/timeline` && req.method === 'GET') {
        return { status: 200, body: { items: [row], next_cursor: null } };
      }
      if (req.path === '/settlements/s-9' && req.method === 'GET') {
        return { status: 200, body: row.settlement };
      }
      return undefined;
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await pressLabel(/^Payment: /);
    expect(await screen.findByText('You paid Ravi INR 20.00')).toBeTruthy();
    expect(server.count('GET', '/settlements/s-9')).toBe(1);
  });

  it('after C records a payment, SCR-13 shows it from the timeline between the expenses (vector 50 order)', async () => {
    // vector 50: expenses on 11-12 and 11-10, a payment on 11-11 -> expense, payment, expense.
    const g = server.addGroup('Flat', [server.user(RAVI, 'Ravi')]);
    const e1 = expense('e-1', 'Dinner', '2026-11-12', '2026-11-12T08:00:00Z');
    const e2 = expense('e-2', 'Taxi', '2026-11-10', '2026-11-10T08:00:00Z');
    let recorded: any;
    server.overrides.push(req => {
      if (req.path === '/settlements' && req.method === 'POST') {
        recorded = settlement({
          id: 's-new',
          group_id: g.id,
          settled_on: '2026-11-11',
          created_at: '2026-11-11T08:00:00Z',
        });
        return { status: 201, body: recorded };
      }
      if (req.path === `/groups/${g.id}/timeline` && req.method === 'GET') {
        return {
          status: 200,
          body: {
            items: recorded
              ? [
                  e1,
                  {
                    kind: 'settlement',
                    date: '2026-11-11',
                    settlement: recorded,
                  },
                  e2,
                ]
              : [e1, e2],
            next_cursor: null,
          },
        };
      }
      if (req.path === `/groups/${g.id}/balances` && req.method === 'GET') {
        return {
          status: 200,
          body: {
            group_id: g.id,
            simplified: true,
            members: [],
            transfers: [
              {
                from_user_id: ME,
                to_user_id: RAVI,
                amount_minor: 3000,
                currency: 'INR',
              },
            ],
          },
        };
      }
      return undefined;
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await screen.findByText('Dinner');
    expect(labels()).toEqual(['Expense:Dinner', 'Expense:Taxi']);
    await press('Settle up');
    await press('you owe Ravi');
    await press('Save payment');
    await waitFor(() =>
      expect(screen.queryByTestId('payment-row')).toBeTruthy(),
    );
    expect(labels()).toEqual([
      'Expense:Dinner',
      'Payment:You paid Ravi',
      'Expense:Taxi',
    ]);
  });
});
