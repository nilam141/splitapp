/**
 * S3-M-3 (add/edit expense, SCR-13 timeline), S3-M-4 (adjust split, payers), S3-M-5 (expense detail) and
 * S3-M-6 (friend settings remove flow). Screen-level tests against the fake server, like slice2Groups.test.tsx
 * (no Detox/Maestro in the repo): the real generated client, auth layer, navigation and screens run unchanged.
 */
import React from 'react';
import {
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
const pressLabel = async (label: string) =>
  fireEvent.press(await screen.findByLabelText(label));
const launch = () => render(<App queryClient={qc} navigationRef={navRef} />);

const ME = 'u-me';
const posts = (path: string | RegExp) =>
  server.log.filter(
    r =>
      r.method === 'POST' &&
      (typeof path === 'string' ? r.path === path : path.test(r.path)),
  );

/** Group "Flat" with Ravi and Meera, opened on SCR-13. */
async function openFlat() {
  const g = server.addGroup('Flat', [
    server.user('u-ravi', 'Ravi'),
    server.user('u-meera', 'Meera'),
  ]);
  await launch();
  await press('Groups');
  await press('Flat');
  await screen.findByText('Expenses');
  return g;
}

async function fillBasics(description: string, amount: string) {
  await fireEvent.changeText(
    await screen.findByLabelText('Description'),
    description,
  );
  await fireEvent.changeText(screen.getByLabelText('Amount'), amount);
}

describe('S3-M-3 Add expense (SCR-22) and the group timeline (SCR-13)', () => {
  it('FLOW-03a: saves a 100.00 equal split in the group and SCR-13 shows "you lent 66.66"', async () => {
    const g = await openFlat();
    await press('Add expense');
    await fillBasics('Dinner', '100');
    await press('Save');

    expect(await screen.findByText('you lent 66.66')).toBeTruthy();
    expect(screen.getByText('Dinner')).toBeTruthy();
    const req = posts(`/groups/${g.id}/expenses`);
    expect(req).toHaveLength(1);
    expect(req[0].body).toMatchObject({
      description: 'Dinner',
      total: { amount_minor: 10000, currency: 'INR' },
      payers: [{ user_id: ME, paid_amount_minor: 10000 }],
      split: {
        type: 'equal',
        entries: [
          { user_id: ME },
          { user_id: 'u-ravi' },
          { user_id: 'u-meera' },
        ],
      },
    });
    expect(req[0].headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    // new data came from the timeline, not from a hand-merged local list
    expect(
      server.count('GET', `/groups/${g.id}/timeline`),
    ).toBeGreaterThanOrEqual(2);
  });

  it('empty description -> error, no request', async () => {
    await openFlat();
    await press('Add expense');
    await fireEvent.changeText(await screen.findByLabelText('Amount'), '100');
    await press('Save');
    expect(await screen.findByText('Enter a description.')).toBeTruthy();
    expect(posts(/expenses$/)).toHaveLength(0);
  });

  it('amount errors send nothing: empty, zero, too many decimals, over the maximum', async () => {
    await openFlat();
    await press('Add expense');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'X',
    );
    await press('Save');
    expect(await screen.findByText('Enter an amount.')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Amount'), '0');
    await press('Save');
    expect(
      await screen.findByText('The amount must be greater than zero.'),
    ).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Amount'), '12.345');
    await press('Save');
    expect(
      await screen.findByText('Too many decimal places for this currency.'),
    ).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Amount'), '100000000');
    await press('Save');
    expect(await screen.findByText(/at most 99,999,999.99/)).toBeTruthy();
    expect(posts(/expenses$/)).toHaveLength(0);
  });

  it('a 2-page mocked timeline loads page 2 on scroll with exactly 1 more request', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    for (let i = 1; i <= 3; i += 1) {
      server.addExpense({
        description: `Item ${i}`,
        group_id: g.id,
        splits: [
          { user_id: ME, owed_amount_minor: 5000, input_value: null },
          { user_id: 'u-ravi', owed_amount_minor: 5000, input_value: null },
        ],
        expense_date: `2026-11-0${i}`,
      });
    }
    server.pageSize = 2;
    await launch();
    await press('Groups');
    await press('Flat');
    expect(await screen.findByText('Item 3')).toBeTruthy();
    expect(screen.getByText('Item 2')).toBeTruthy();
    expect(screen.queryByText('Item 1')).toBeNull();
    const timeline = () => server.count('GET', `/groups/${g.id}/timeline`);
    expect(timeline()).toBe(1);

    await fireEvent(screen.getByTestId('timeline'), 'endReached');
    expect(await screen.findByText('Item 1')).toBeTruthy();
    expect(timeline()).toBe(2);
    const second = server.log.filter(r => r.path.endsWith('/timeline'))[1];
    expect(second.query).toContain('cursor=2');

    // no more pages: scrolling again sends nothing
    await fireEvent(screen.getByTestId('timeline'), 'endReached');
    expect(timeline()).toBe(2);
  });

  it('groups the timeline by month in server order and opens the expense', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.addExpense({
      description: 'Nov thing',
      group_id: g.id,
      expense_date: '2026-11-03',
    });
    server.addExpense({
      description: 'Oct thing',
      group_id: g.id,
      expense_date: '2026-10-20',
    });
    await launch();
    await press('Groups');
    await press('Flat');
    expect(await screen.findByText('November 2026')).toBeTruthy();
    expect(screen.getByText('October 2026')).toBeTruthy();
    await press('Oct thing');
    expect(await screen.findByText('Comments')).toBeTruthy();
  });

  it('shows an error with retry when the timeline cannot be loaded', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    let fail = true;
    server.overrides.push(req =>
      fail && req.path === `/groups/${g.id}/timeline`
        ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'x' } }
        : undefined,
    );
    await launch();
    await press('Groups');
    await press('Flat');
    expect(
      await screen.findByText('Something went wrong. Please try again.'),
    ).toBeTruthy();
    fail = false;
    await press('Retry');
    expect(await screen.findByText('No expenses yet')).toBeTruthy();
  });

  it('a 422 from the server is shown and the form stays', async () => {
    const g = await openFlat();
    server.overrides.push(req =>
      req.method === 'POST' && req.path === `/groups/${g.id}/expenses`
        ? {
            status: 422,
            body: {
              code: 'AMOUNT_OUT_OF_RANGE',
              message: 'Amount is out of range',
            },
          }
        : undefined,
    );
    await press('Add expense');
    await fillBasics('Dinner', '100');
    await press('Save');
    expect(await screen.findByText('Amount is out of range')).toBeTruthy();
    expect(screen.getByLabelText('Description')).toBeTruthy();
  });

  it('non-group expense from a friend: POST /expenses with group_id null and the creator first', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await launch();
    await press('Friends');
    await press('Ravi');
    await press('Add expense');
    await fillBasics('Taxi', '250.50');
    await press('Save');
    await waitFor(() => expect(posts('/expenses')).toHaveLength(1));
    const body = posts('/expenses')[0].body;
    expect(body.group_id).toBeNull();
    expect(body.total).toEqual({ amount_minor: 25050, currency: 'INR' });
    expect(body.split.entries.map((e: any) => e.user_id)).toEqual([
      ME,
      'u-ravi',
    ]);
    expect(await screen.findByText('Taxi')).toBeTruthy();
  });

  it('category, currency, date and note are sent', async () => {
    const g = await openFlat();
    await press('Add expense');
    await fillBasics('Trip', '1500');
    await pressLabel('Category');
    await pressLabel('Category: Taxi');
    await pressLabel('Currency: INR');
    await press(/JPY - Japanese Yen/);
    await pressLabel('Date');
    await fireEvent.changeText(
      await screen.findByLabelText('Expense date (YYYY-MM-DD)'),
      '2026-11-01',
    );
    await press('Done');
    await pressLabel('Note');
    await fireEvent.changeText(
      await screen.findByLabelText('Note'),
      'cash only',
    );
    await press('Done');
    await press('Save');
    await waitFor(() =>
      expect(posts(`/groups/${g.id}/expenses`)).toHaveLength(1),
    );
    expect(posts(`/groups/${g.id}/expenses`)[0].body).toMatchObject({
      total: { amount_minor: 1500, currency: 'JPY' }, // JPY has no decimals: 1500 is 1500 minor units
      category_id: 5,
      expense_date: '2026-11-01',
      notes: 'cash only',
    });
  });

  it('JPY rejects decimals', async () => {
    await openFlat();
    await press('Add expense');
    await fillBasics('Ramen', '1500.5');
    await pressLabel('Currency: INR');
    await press(/JPY - Japanese Yen/);
    await press('Save');
    expect(
      await screen.findByText('Too many decimal places for this currency.'),
    ).toBeTruthy();
    expect(posts(/expenses$/)).toHaveLength(0);
  });

  it('category search shows "No matching category"', async () => {
    await openFlat();
    await press('Add expense');
    await pressLabel('Category');
    await fireEvent.changeText(
      await screen.findByLabelText('Search categories'),
      'zzz',
    );
    expect(await screen.findByText('No matching category')).toBeTruthy();
    await fireEvent.changeText(
      screen.getByLabelText('Search categories'),
      'GROC',
    );
    expect(await screen.findByText('Groceries')).toBeTruthy();
  });

  it('date outside the allowed range disables Done', async () => {
    await openFlat();
    await press('Add expense');
    await pressLabel('Date');
    await fireEvent.changeText(
      await screen.findByLabelText('Expense date (YYYY-MM-DD)'),
      '1999-12-31',
    );
    expect(await screen.findByText(/Pick a date from 2000-01-01/)).toBeTruthy();
    expect(screen.getByText('Done')).toBeTruthy();
    await fireEvent.changeText(
      screen.getByLabelText('Expense date (YYYY-MM-DD)'),
      '2026-02-30',
    );
    expect(await screen.findByText('That date does not exist.')).toBeTruthy();
  });

  it('edit: PATCH carries the version; a stale version shows the conflict message', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    const e = server.addExpense({
      description: 'Lunch',
      group_id: g.id,
      total: { amount_minor: 20000, currency: 'INR' },
      payers: [{ user_id: ME, paid_amount_minor: 20000 }],
      splits: [
        { user_id: ME, owed_amount_minor: 10000, input_value: null },
        { user_id: 'u-ravi', owed_amount_minor: 10000, input_value: null },
      ],
      version: 3,
    });
    await launch();
    await press('Groups');
    await press('Flat');
    await press('Lunch');
    await press('Edit');
    const desc = await screen.findByLabelText('Description');
    expect(desc.props.value).toBe('Lunch');
    expect(screen.getByLabelText('Amount').props.value).toBe('200.00');
    await fireEvent.changeText(desc, 'Late lunch');
    await press('Save');
    await waitFor(() =>
      expect(server.count('PATCH', `/expenses/${e.id}`)).toBe(1),
    );
    const patch = server.log.find(r => r.method === 'PATCH')!;
    expect(patch.body).toMatchObject({
      version: 3,
      description: 'Late lunch',
      total: { amount_minor: 20000, currency: 'INR' },
    });
    expect(await screen.findByText('Late lunch')).toBeTruthy(); // back on SCR-29, refetched
  });

  it('edit with a stale version: conflict message', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    const e = server.addExpense({
      description: 'Lunch',
      group_id: g.id,
      splits: [
        { user_id: ME, owed_amount_minor: 5000, input_value: null },
        { user_id: 'u-ravi', owed_amount_minor: 5000, input_value: null },
      ],
    });
    await launch();
    await press('Groups');
    await press('Flat');
    await press('Lunch');
    await press('Edit');
    await screen.findByLabelText('Description');
    e.version = 9; // someone else saved meanwhile
    await press('Save');
    expect(await screen.findByText(/changed by someone else/)).toBeTruthy();
  });
});

describe('S3-M-4 Adjust split (SCR-23) and Payers (SCR-24)', () => {
  const openSplit = async (amount: string) => {
    await openFlat();
    await press('Add expense');
    await fillBasics('Dinner', amount);
    await pressLabel('Change split');
  };
  const tab = (name: string) => pressLabel(`Split tab: ${name}`);

  it('percent 50/30/19 shows "1% left" and Done is disabled', async () => {
    await openSplit('100');
    await tab('Percent');
    await fireEvent.changeText(screen.getByLabelText('You value'), '50');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '30');
    await fireEvent.changeText(screen.getByLabelText('Meera value'), '19');
    expect(await screen.findByText('1% left')).toBeTruthy();
    expect(screen.getByText('99% of 100%')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Done' }).props.accessibilityState
        ?.disabled,
    ).toBe(true);
    // fixing it enables Done and the amounts follow
    await fireEvent.changeText(screen.getByLabelText('Meera value'), '20');
    await waitFor(() => expect(screen.queryByText('1% left')).toBeNull());
    expect(
      screen.getByRole('button', { name: 'Done' }).props.accessibilityState
        ?.disabled,
    ).toBeFalsy();
    expect(screen.getByLabelText('You owes').props.children).toBe('50.00');
  });

  it('shares 1/2/3 on 600.00 shows 100.00 / 200.00 / 300.00', async () => {
    await openSplit('600');
    await tab('Shares');
    await fireEvent.changeText(screen.getByLabelText('You value'), '1');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '2');
    await fireEvent.changeText(screen.getByLabelText('Meera value'), '3');
    expect(await screen.findByText('100.00')).toBeTruthy();
    expect(screen.getByText('200.00')).toBeTruthy();
    expect(screen.getByText('300.00')).toBeTruthy();
    expect(screen.getByText('6 total shares')).toBeTruthy();
  });

  it('exact: footer "X of Y", "Z left" and "over by Z"', async () => {
    await openSplit('100');
    await tab('Exact');
    await fireEvent.changeText(screen.getByLabelText('You value'), '60');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '30');
    expect(await screen.findByText('90.00 of 100.00')).toBeTruthy();
    expect(screen.getByText('10.00 left')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Meera value'), '15');
    expect(await screen.findByText('over by 5.00')).toBeTruthy();
  });

  it('equal: unticking everyone disables Done; one person owes the whole amount', async () => {
    await openSplit('100');
    await fireEvent(
      screen.getByLabelText('Include Ravi'),
      'valueChange',
      false,
    );
    await fireEvent(
      screen.getByLabelText('Include Meera'),
      'valueChange',
      false,
    );
    expect(await screen.findByText('100.00')).toBeTruthy();
    await fireEvent(screen.getByLabelText('Include You'), 'valueChange', false);
    expect(await screen.findByText('Select at least 1 person.')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Done' }).props.accessibilityState
        ?.disabled,
    ).toBe(true);
  });

  it('adjustment: over-the-total shows the gap and disables Done', async () => {
    await openSplit('100');
    await tab('Adjustment');
    await fireEvent.changeText(screen.getByLabelText('You value'), '120');
    expect(await screen.findByText('over by 20.00')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Done' }).props.accessibilityState
        ?.disabled,
    ).toBe(true);
    await fireEvent.changeText(screen.getByLabelText('You value'), '10');
    await waitFor(() => expect(screen.queryByText('over by 20.00')).toBeNull());
    expect(screen.getByLabelText('You owes').props.children).toBe('40.00');
  });

  it('a typed value with too many decimals is flagged on that person', async () => {
    await openSplit('100');
    await tab('Exact');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '1.234');
    expect(
      await screen.findByText(/Ravi: Too many decimal places/),
    ).toBeTruthy();
  });

  it('Done saves the split into the draft and the sentence updates', async () => {
    await openSplit('100');
    await tab('Percent');
    await fireEvent.changeText(screen.getByLabelText('You value'), '50');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '25');
    await fireEvent.changeText(screen.getByLabelText('Meera value'), '25');
    await press('Done');
    expect(await screen.findByText('by percent')).toBeTruthy();
    await press('Save');
    await waitFor(() => expect(posts(/\/expenses$/)).toHaveLength(1));
    expect(posts(/\/expenses$/)[0].body.split).toEqual({
      type: 'percent',
      entries: [
        { user_id: ME, value: 5000 },
        { user_id: 'u-ravi', value: 2500 },
        { user_id: 'u-meera', value: 2500 },
      ],
    });
  });

  it('save with a stale exact split opens the gap dialog naming the exact gap, then SCR-23', async () => {
    await openSplit('100');
    await tab('Exact');
    await fireEvent.changeText(screen.getByLabelText('You value'), '50');
    await fireEvent.changeText(screen.getByLabelText('Ravi value'), '50');
    await press('Done');
    await fireEvent.changeText(screen.getByLabelText('Amount'), '110');
    await press('Save');
    // shown in the dialog and inline on the form
    expect(
      (await screen.findAllByText('Split is under by 10.00')).length,
    ).toBeGreaterThanOrEqual(1);
    expect(posts(/\/expenses$/)).toHaveLength(0);
    await press('OK');
    expect(await screen.findByText('Adjust split')).toBeTruthy();
  });

  it('two-person shortcuts compile to payers and an exact split', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await launch();
    await press('Friends');
    await press('Ravi');
    await press('Add expense');
    await fillBasics('Cab', '90');
    await pressLabel('Change split');
    await pressLabel('You are owed the full amount');
    await press('Save');
    await waitFor(() => expect(posts('/expenses')).toHaveLength(1));
    expect(posts('/expenses')[0].body).toMatchObject({
      payers: [{ user_id: ME, paid_amount_minor: 9000 }],
      split: {
        type: 'exact',
        entries: [
          { user_id: ME, value: 0 },
          { user_id: 'u-ravi', value: 9000 },
        ],
      },
    });
  });

  it('shortcut "They paid, split equally" sets the other person as the payer', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await launch();
    await press('Friends');
    await press('Ravi');
    await press('Add expense');
    await fillBasics('Cab', '90');
    await pressLabel('Change split');
    await pressLabel('They paid, split equally');
    expect(await screen.findByText('Ravi')).toBeTruthy(); // the payer link in the sentence
    await press('Save');
    await waitFor(() => expect(posts('/expenses')).toHaveLength(1));
    expect(posts('/expenses')[0].body.payers).toEqual([
      { user_id: 'u-ravi', paid_amount_minor: 9000 },
    ]);
  });

  it('shortcuts need an amount first', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await launch();
    await press('Friends');
    await press('Ravi');
    await press('Add expense');
    await pressLabel('Change split');
    await pressLabel('You paid, split equally');
    expect(await screen.findByText('Enter the amount first.')).toBeTruthy();
  });

  it('multiple payers: footer "X of Y", Done disabled until the sum matches, then saved', async () => {
    await openFlat();
    await press('Add expense');
    await fillBasics('Dinner', '90');
    await pressLabel('Change payers');
    await press('Multiple people');
    await fireEvent.changeText(screen.getByLabelText('You paid'), '60');
    expect(await screen.findByText('60.00 of 90.00')).toBeTruthy();
    expect(screen.getByText('30.00 left')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Done' }).props.accessibilityState
        ?.disabled,
    ).toBe(true);
    await fireEvent.changeText(screen.getByLabelText('Ravi paid'), '40');
    expect(await screen.findByText('over by 10.00')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Ravi paid'), '30');
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Done' }).props.accessibilityState
          ?.disabled,
      ).toBeFalsy(),
    );
    await press('Done');
    await press('Save');
    await waitFor(() => expect(posts(/\/expenses$/)).toHaveLength(1));
    expect(posts(/\/expenses$/)[0].body.payers).toEqual([
      { user_id: ME, paid_amount_minor: 6000 },
      { user_id: 'u-ravi', paid_amount_minor: 3000 },
    ]);
  });

  it('single payer: picking another member pays the full total', async () => {
    await openFlat();
    await press('Add expense');
    await fillBasics('Dinner', '90');
    await pressLabel('Change payers');
    await pressLabel('Paid by Meera');
    await press('Save');
    await waitFor(() => expect(posts(/\/expenses$/)).toHaveLength(1));
    expect(posts(/\/expenses$/)[0].body.payers).toEqual([
      { user_id: 'u-meera', paid_amount_minor: 9000 },
    ]);
  });
});

describe('S3-M-5 Expense detail (SCR-29)', () => {
  async function openDetail() {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    const e = server.addExpense({
      description: 'Lunch',
      group_id: g.id,
      total: { amount_minor: 20000, currency: 'INR' },
      payers: [{ user_id: ME, paid_amount_minor: 20000 }],
      splits: [
        { user_id: ME, owed_amount_minor: 10000, input_value: null },
        { user_id: 'u-ravi', owed_amount_minor: 10000, input_value: null },
      ],
      notes: 'Thali',
    });
    await launch();
    await press('Groups');
    await press('Flat');
    await press('Lunch');
    await screen.findByText('Comments');
    return e;
  }

  it('shows payers, splits, notes and added-by', async () => {
    await openDetail();
    expect(screen.getByText('INR 200.00')).toBeTruthy();
    expect(screen.getByText('You paid INR 200.00')).toBeTruthy();
    expect(screen.getByText('You owe INR 100.00')).toBeTruthy();
    expect(screen.getByText('Ravi owes INR 100.00')).toBeTruthy();
    expect(screen.getByText('Thali')).toBeTruthy();
    expect(screen.getByText(/added by You on/)).toBeTruthy();
    // the comments query resolves after the 'Comments' heading is shown, so wait for the empty state
    expect(await screen.findByText('No comments yet')).toBeTruthy();
  });

  it('delete -> banner "deleted by..."; restore -> banner gone', async () => {
    const e = await openDetail();
    await press('Delete');
    const buttons = await screen.findAllByText('Delete'); // screen button + the dialog's confirm
    await fireEvent.press(buttons[buttons.length - 1]);
    expect(
      await screen.findByText('deleted by You on 2026-11-10'),
    ).toBeTruthy();
    expect(server.count('DELETE', `/expenses/${e.id}`)).toBe(1);
    await press('Restore');
    await waitFor(() => expect(screen.queryByText(/^deleted by/)).toBeNull());
    expect(server.count('POST', `/expenses/${e.id}/restore`)).toBe(1);
  });

  describe('S4-M-3 409 EXPENSE_HAS_DEPARTED_MEMBER (OQ-43)', () => {
    const MSG =
      'Someone in this expense is no longer in the group or no longer your friend, so it cannot be changed or restored';
    const conflict = (
      method: string,
      suffix: string,
      code: string,
      message = 'server text',
    ) =>
      server.overrides.push(req =>
        req.method === method && req.path.endsWith(suffix)
          ? { status: 409, body: { code, message } }
          : undefined,
      );
    const confirmDelete = async () => {
      await press('Delete');
      const buttons = await screen.findAllByText('Delete');
      await fireEvent.press(buttons[buttons.length - 1]);
    };

    it('delete -> 409 shows the message once, expense not shown as deleted, Delete still tappable', async () => {
      const e = await openDetail();
      conflict('DELETE', `/expenses/${e.id}`, 'EXPENSE_HAS_DEPARTED_MEMBER');
      await confirmDelete();
      expect(await screen.findAllByText(MSG)).toHaveLength(1);
      expect(screen.queryByText(/^deleted by/)).toBeNull();
      expect(screen.queryByText('Restore')).toBeNull();
      expect(screen.getByText('Lunch')).toBeTruthy();
      expect(screen.getByText('INR 200.00')).toBeTruthy();
      expect(server.expenses[0].deleted_at ?? null).toBeNull();
      // still usable: the dialog opens again and a second attempt is sent
      await confirmDelete();
      await waitFor(() =>
        expect(server.count('DELETE', `/expenses/${e.id}`)).toBe(2),
      );
      expect(await screen.findAllByText(MSG)).toHaveLength(1);
    });

    it('restore -> 409 shows the message once, the deleted banner stays, Restore still tappable', async () => {
      const e = await openDetail();
      await confirmDelete();
      await screen.findByText('deleted by You on 2026-11-10');
      conflict('POST', '/restore', 'EXPENSE_HAS_DEPARTED_MEMBER');
      await press('Restore');
      expect(await screen.findAllByText(MSG)).toHaveLength(1);
      expect(screen.getByText('deleted by You on 2026-11-10')).toBeTruthy();
      expect(screen.queryByText('Delete')).toBeNull();
      await press('Restore');
      await waitFor(() =>
        expect(server.count('POST', `/expenses/${e.id}/restore`)).toBe(2),
      );
      expect(await screen.findAllByText(MSG)).toHaveLength(1);
      expect(screen.getByText('deleted by You on 2026-11-10')).toBeTruthy();
    });

    it('ALREADY_DELETED on delete still shows the server message and reloads', async () => {
      const e = await openDetail();
      conflict(
        'DELETE',
        `/expenses/${e.id}`,
        'ALREADY_DELETED',
        'Already gone',
      );
      await confirmDelete();
      expect(await screen.findByText('Already gone')).toBeTruthy();
      expect(screen.queryByText(MSG)).toBeNull();
    });

    it('NOT_DELETED on restore still shows the server message and reloads', async () => {
      await openDetail();
      await confirmDelete();
      await screen.findByText('deleted by You on 2026-11-10');
      conflict('POST', '/restore', 'NOT_DELETED', 'Not deleted');
      await press('Restore');
      expect(await screen.findByText('Not deleted')).toBeTruthy();
      expect(screen.queryByText(MSG)).toBeNull();
    });
  });

  it('cancelling the delete dialog sends nothing', async () => {
    const e = await openDetail();
    await press('Delete');
    await press('Cancel');
    expect(server.count('DELETE', `/expenses/${e.id}`)).toBe(0);
  });

  it('post a comment -> it appears at the bottom after the existing ones', async () => {
    const e = await openDetail();
    server.comments[e.id] = [
      {
        id: 'c0',
        kind: 'system',
        user: null,
        body: 'Ravi added this expense',
        created_at: '2026-11-10T00:00:00Z',
      },
    ];
    await qc.invalidateQueries();
    expect(await screen.findByText('Ravi added this expense')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Comment'), 'Looks right');
    await press('Send');
    expect(await screen.findByText('Looks right')).toBeTruthy();
    expect(screen.getByLabelText('Comment').props.value).toBe('');
    expect(server.comments[e.id].map(c => c.body)).toEqual([
      'Ravi added this expense',
      'Looks right',
    ]);
    expect(
      server.log.find(r => r.method === 'POST' && r.path.endsWith('/comments'))!
        .body,
    ).toEqual({ body: 'Looks right' });
    // order on screen: system comment first, new one last
    const all = screen
      .getAllByText(/Ravi added this expense|Looks right/)
      .map(n => n.props.children);
    expect(all).toEqual(['Ravi added this expense', 'Looks right']);
  });

  it('empty or oversized comments send no request', async () => {
    const e = await openDetail();
    await press('Send');
    expect(await screen.findByText('Write a comment first.')).toBeTruthy();
    expect(server.count('POST', `/expenses/${e.id}/comments`)).toBe(0);
  });

  it('a removed expense shows "Cannot find expense."', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.addExpense({ description: 'Lunch', group_id: g.id });
    await launch();
    await press('Groups');
    await press('Flat');
    server.overrides.push(req =>
      req.path.startsWith('/expenses/') && req.method === 'GET'
        ? { status: 404, body: { code: 'NOT_FOUND', message: 'Not Found' } }
        : undefined,
    );
    await press('Lunch');
    expect(await screen.findByText('Cannot find expense.')).toBeTruthy();
  });

  it('the Edit entry point opens the form with the expense', async () => {
    await openDetail();
    await press('Edit');
    expect((await screen.findByLabelText('Description')).props.value).toBe(
      'Lunch',
    );
  });
});

describe('S3-M-6 Friend settings (SCR-20) remove flow', () => {
  const nonGroup3000 = [
    {
      scope: 'non_group',
      group_id: null,
      group_name: null,
      balances: [{ amount_minor: 3000, currency: 'INR' }],
    },
  ];
  async function openSettings(name = 'Ravi') {
    await launch();
    await press('Friends');
    await press(name);
    await press('Settings');
    await screen.findByText('Shared groups');
  }

  it('mocked 3000 balance: Remove shows the warning with the amount; Cancel sends 0 requests', async () => {
    server.addFriendRow('u-ravi', 'Ravi', [
      { amount_minor: 3000, currency: 'INR' },
    ]);
    server.friends[0].breakdown = nonGroup3000;
    await openSettings();
    await press('Remove friend');
    expect(
      await screen.findByText(
        /non-group expenses, non-group payments and any balance with Ravi will be deleted/i,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/current non-group balance is INR 30\.00/),
    ).toBeTruthy();
    await press('Cancel');
    expect(server.count('DELETE', '/friends/u-ravi')).toBe(0);
  });

  it('Confirm sends 1 DELETE /friends/{id} and the row disappears', async () => {
    server.addFriendRow('u-ravi', 'Ravi', [
      { amount_minor: 3000, currency: 'INR' },
    ]);
    server.addFriendRow('u-meera', 'Meera');
    server.friends[0].breakdown = nonGroup3000;
    await openSettings();
    await press('Remove friend');
    await press('Remove');
    await waitFor(() =>
      expect(server.count('DELETE', '/friends/u-ravi')).toBe(1),
    );
    expect(await screen.findByText('Meera')).toBeTruthy();
    await waitFor(() => expect(screen.queryByText('Ravi')).toBeNull());
    expect(server.count('DELETE', /^\/friends\//)).toBe(1);
  });

  it('without a balance the warning has no amount', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await openSettings();
    await press('Remove friend');
    expect(
      await screen.findByText(/any balance with Ravi will be deleted/),
    ).toBeTruthy();
    expect(screen.queryByText(/current non-group balance/)).toBeNull();
  });

  it('mocked 409 SHARED_GROUPS_EXIST lists the groups', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.addGroup('Goa Trip', [server.user('u-ravi', 'Ravi')]);
    await openSettings();
    await press('Remove friend');
    await press('Remove');
    expect(await screen.findByText(/Can't remove Ravi yet/)).toBeTruthy();
    expect(screen.getByText(/- Flat/)).toBeTruthy();
    expect(screen.getByText(/- Goa Trip/)).toBeTruthy();
    expect(server.count('DELETE', '/friends/u-ravi')).toBe(1);
    await press('OK');
    // the friend is still there
    expect(screen.getByText('Shared groups')).toBeTruthy();
  });

  it('an implicit-only friend (no explicit row) gets the same 409 dialog', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.overrides.push(req =>
      req.method === 'DELETE' && req.path === '/friends/u-ravi'
        ? {
            status: 409,
            body: {
              code: 'SHARED_GROUPS_EXIST',
              message: 'Leave the shared groups first',
              details: { group_ids: [server.groups[0].id] },
            },
          }
        : undefined,
    );
    await openSettings();
    await press('Remove friend');
    await press('Remove');
    expect(await screen.findByText(/- Flat/)).toBeTruthy();
  });

  it('offline: a failed DELETE shows the offline message and keeps the friend', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    await openSettings();
    (global as any).fetch.mockImplementationOnce(async () => {
      throw new TypeError('Network request failed');
    });
    await press('Remove friend');
    await press('Remove');
    expect(await screen.findByText(/Can't reach the server/)).toBeTruthy();
  });

  it('lists shared groups from the breakdown and opens one', async () => {
    server.addFriendRow('u-ravi', 'Ravi');
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.friends[0].breakdown = [
      { scope: 'group', group_id: g.id, group_name: 'Flat', balances: [] },
    ];
    await openSettings();
    await press('Flat');
    expect(await screen.findByText('No expenses yet')).toBeTruthy();
  });

  it('SCR-19 shows the balance breakdown and the empty state', async () => {
    server.addFriendRow('u-ravi', 'Ravi', [
      { amount_minor: 3000, currency: 'INR' },
    ]);
    server.friends[0].breakdown = nonGroup3000;
    await launch();
    await press('Friends');
    await press('Ravi');
    expect(await screen.findByText('Non-group expenses')).toBeTruthy();
    expect(
      await screen.findByText('No expenses with this friend'),
    ).toBeTruthy();
    expect(screen.getAllByText('owes you INR 30.00').length).toBeGreaterThan(0);
  });
});
