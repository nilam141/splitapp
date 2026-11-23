/**
 * S6-M-2: repeat rule in SCR-27, the "repeats monthly" label and Stop repeating on SCR-29. FLOW-07 steps 1-3 are
 * driven through the screens; whether the server stores the rule is S6-B-1's test (this checks the request).
 */
import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import {
  buildRequest,
  draftFromExpense,
  initialDraft,
} from '../../src/expenses/draft';
import {
  launch,
  makeEnv,
  press,
  pressLabel,
  reqs,
  resetEnv,
} from '../../testUtils/slice6';

const env = makeEnv();
beforeEach(async () => {
  await resetEnv(env);
});
afterEach(() => env.qc.clear());

const people = [
  { id: 'u-me', name: 'Asha' },
  { id: 'u-ravi', name: 'Ravi' },
];
const fmt = (m: number) => String(m);

describe('draft: recurrence in the request body', () => {
  const base = {
    ...initialDraft('u-me', people, 'INR', '2026-01-31'),
    description: 'Rent',
    amountText: '30000',
  };

  it('never sends no recurrence', () => {
    const r = buildRequest(base, people, 2, '2026-01-31', fmt);
    expect(r.ok && 'recurrence' in r.body).toBe(false);
  });

  it('monthly with a 2-day reminder sends interval and reminder_days_before', () => {
    const r = buildRequest(
      { ...base, repeat: 'monthly', reminderDays: 2 },
      people,
      2,
      '2026-01-31',
      fmt,
    );
    expect(r.ok && r.body.recurrence).toEqual({
      interval: 'monthly',
      reminder_days_before: 2,
    });
  });

  it('reminder off sends null; on the day sends 0 (not dropped)', () => {
    const off = buildRequest(
      { ...base, repeat: 'weekly', reminderDays: null },
      people,
      2,
      '2026-01-31',
      fmt,
    );
    const day = buildRequest(
      { ...base, repeat: 'yearly', reminderDays: 0 },
      people,
      2,
      '2026-01-31',
      fmt,
    );
    expect(off.ok && off.body.recurrence?.reminder_days_before).toBeNull();
    expect(day.ok && day.body.recurrence?.reminder_days_before).toBe(0);
  });

  it('editing an expense starts with repeat never, so an edit sends no recurrence', () => {
    const d = draftFromExpense(
      {
        id: 'x',
        description: 'Rent',
        total: { amount_minor: 3000000, currency: 'INR' },
        category_id: 1,
        expense_date: '2026-01-31',
        split_type: 'equal',
        payers: [{ user_id: 'u-me', paid_amount_minor: 3000000 }],
        splits: [
          { user_id: 'u-me', owed_amount_minor: 1500000 },
          { user_id: 'u-ravi', owed_amount_minor: 1500000 },
        ],
        recurring_rule_id: 'r-1',
        created_by: 'u-me',
        created_at: '2026-01-31T00:00:00Z',
        version: 1,
      },
      2,
    );
    expect(d.repeat).toBe('never');
  });
});

async function openFlat() {
  const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
  await launch(env);
  await press('Groups');
  await press('Flat');
  await screen.findByText('Expenses');
  return g;
}

describe('S6-M-2 SCR-27 repeat (FLOW-07 steps 1-3)', () => {
  it('Rent 30000, monthly, reminder 2 days before -> POST with recurrence', async () => {
    const g = await openFlat();
    await press('Add expense');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'Rent',
    );
    await fireEvent.changeText(screen.getByLabelText('Amount'), '30000');
    await pressLabel('Date');
    // Reminder is offered only while repeating (OQ-22)
    expect(screen.queryByLabelText('Reminder: Off')).toBeNull();
    await pressLabel('Repeat: Every month');
    expect(screen.getByLabelText('Reminder: Off')).toBeTruthy();
    await pressLabel('Reminder: 2 days before');
    await press('Done');
    expect(await screen.findByText(/repeats monthly/)).toBeTruthy();
    await press('Save');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', `/groups/${g.id}/expenses`)).toHaveLength(
        1,
      ),
    );
    expect(
      reqs(env.server, 'POST', `/groups/${g.id}/expenses`)[0].body,
    ).toMatchObject({
      description: 'Rent',
      total: { amount_minor: 3000000, currency: 'INR' },
      recurrence: { interval: 'monthly', reminder_days_before: 2 },
    });
  });

  it('choosing Never hides the reminder again and sends no recurrence', async () => {
    const g = await openFlat();
    await press('Add expense');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'Tea',
    );
    await fireEvent.changeText(screen.getByLabelText('Amount'), '10');
    await pressLabel('Date');
    await pressLabel('Repeat: Every week');
    await pressLabel('Repeat: Never');
    expect(screen.queryByLabelText('Reminder: Off')).toBeNull();
    await press('Done');
    await press('Save');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', `/groups/${g.id}/expenses`)).toHaveLength(
        1,
      ),
    );
    expect(
      'recurrence' in
        reqs(env.server, 'POST', `/groups/${g.id}/expenses`)[0].body,
    ).toBe(false);
  });

  it('a 501 NOT_IMPLEMENTED from the server shows a clear message and keeps the form', async () => {
    env.server.overrides.push(req =>
      req.method === 'POST' &&
      /\/expenses$/.test(req.path) &&
      req.body?.recurrence
        ? { status: 501, body: { code: 'NOT_IMPLEMENTED', message: 'later' } }
        : undefined,
    );
    await openFlat();
    await press('Add expense');
    await fireEvent.changeText(
      await screen.findByLabelText('Description'),
      'Rent',
    );
    await fireEvent.changeText(screen.getByLabelText('Amount'), '100');
    await pressLabel('Date');
    await pressLabel('Repeat: Every month');
    await press('Done');
    await press('Save');
    expect(
      await screen.findByText(/Repeating expenses are not available yet/),
    ).toBeTruthy();
  });

  it('the repeat choice is not offered when editing an expense', async () => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.addExpense({
      id: 'x-rent',
      group_id: g.id,
      description: 'Rent',
      splits: [
        { user_id: 'u-me', owed_amount_minor: 5000 },
        { user_id: 'u-ravi', owed_amount_minor: 5000 },
      ],
    });
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Rent');
    await press('Edit');
    await pressLabel('Date');
    expect(screen.queryByLabelText('Repeat: Every month')).toBeNull();
  });
});

describe('S6-M-2 SCR-29 label and stop-repeat', () => {
  function seed(active = true) {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.addExpense({
      id: 'x-rent',
      group_id: g.id,
      description: 'Rent',
      recurring_rule_id: 'r-1',
      splits: [
        { user_id: 'u-me', owed_amount_minor: 5000 },
        { user_id: 'u-ravi', owed_amount_minor: 5000 },
      ],
    });
    const rule = {
      id: 'r-1',
      template_expense_id: 'x-rent',
      group_id: g.id,
      interval: 'monthly',
      anchor_date: '2026-01-31',
      next_occurrence_date: '2026-02-28',
      reminder_days_before: 2,
      active,
    };
    env.server.overrides.push(req => {
      if (req.path === '/recurring-expenses' && req.method === 'GET') {
        return { status: 200, body: { items: [rule] } };
      }
      if (req.path === '/recurring-expenses/r-1' && req.method === 'PATCH') {
        Object.assign(rule, req.body);
        return { status: 200, body: rule };
      }
    });
  }
  const open = async () => {
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Rent');
  };

  it('shows "Repeats monthly, next on ..." and Stop repeating PATCHes active=false after a confirm', async () => {
    seed();
    await open();
    expect(
      await screen.findByText('Repeats monthly, next on 2026-02-28'),
    ).toBeTruthy();
    await press('Stop repeating');
    // nothing is sent until the dialog is confirmed
    expect(reqs(env.server, 'PATCH', '/recurring-expenses/r-1')).toHaveLength(
      0,
    );
    const buttons = await screen.findAllByText('Stop repeating');
    await fireEvent.press(buttons[buttons.length - 1]);
    await waitFor(() =>
      expect(reqs(env.server, 'PATCH', '/recurring-expenses/r-1')).toHaveLength(
        1,
      ),
    );
    expect(
      reqs(env.server, 'PATCH', '/recurring-expenses/r-1')[0].body,
    ).toEqual({
      active: false,
    });
    expect(await screen.findByText('Repeating has stopped')).toBeTruthy();
    expect(screen.queryByText('Stop repeating')).toBeNull();
  });

  it('an already stopped rule shows no Stop button', async () => {
    seed(false);
    await open();
    expect(await screen.findByText('Repeating has stopped')).toBeTruthy();
    expect(screen.queryByText('Stop repeating')).toBeNull();
  });

  it('an expense without a rule shows no repeat label', async () => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.addExpense({
      id: 'x1',
      group_id: g.id,
      description: 'Tea',
      splits: [],
    });
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Tea');
    await screen.findByText('Comments');
    expect(screen.queryByText(/Repeats/)).toBeNull();
    expect(reqs(env.server, 'GET', '/recurring-expenses')).toHaveLength(0);
  });
});
