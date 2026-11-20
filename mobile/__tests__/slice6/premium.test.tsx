/**
 * S6-M-4: paywall SCR-39 (gating only; Play Billing is Blocked, D-C), gated entry points (search SCR-36,
 * export SCR-38) and the receipt image on SCR-29. There is no purchase here: the "billing test card" DoD cannot be
 * met until D-C is approved, so no test buys anything.
 */
import { Share } from 'react-native';
import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';
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
afterEach(() => {
  jest.useRealTimers();
  env.qc.clear();
});

const premium = () => {
  env.server.me = {
    ...env.server.me,
    plan: 'premium',
    premium_until: '2027-01-01T00:00:00Z',
  };
};

const exp = (id: string, description: string) => ({
  id,
  group_id: null,
  description,
  total: { amount_minor: 4500, currency: 'INR' },
  category_id: 1,
  expense_date: '2026-11-10',
  notes: null,
  split_type: 'equal',
  payers: [{ user_id: 'u-me', paid_amount_minor: 4500 }],
  splits: [{ user_id: 'u-me', owed_amount_minor: 4500 }],
  my_net: { amount_minor: 0, currency: 'INR' },
  created_by: 'u-me',
  created_at: '2026-11-10T00:00:00Z',
  version: 1,
});

describe('S6-M-4 paywall and gated entry points', () => {
  it('a free user tapping Search opens the paywall, not the search screen', async () => {
    await launch(env);
    await pressLabel('Search expenses');
    expect(await screen.findByText('Upgrade to Premium')).toBeTruthy();
    expect(screen.getByText('Search is a Premium feature.')).toBeTruthy();
    expect(screen.queryByLabelText('Search expenses')).toBeNull();
    expect(reqs(env.server, 'GET', '/expenses')).toHaveLength(0);
  });

  it('a free user tapping Export opens the paywall and starts no export', async () => {
    env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Settings');
    await press('Export to CSV');
    expect(
      await screen.findByText('Export is a Premium feature.'),
    ).toBeTruthy();
    expect(reqs(env.server, 'POST', '/exports')).toHaveLength(0);
  });

  it('the paywall lists the benefits, says purchasing is not available, and offers no purchase or restore', async () => {
    await launch(env);
    await press('Account');
    await press('Upgrade');
    expect(await screen.findByText('Search expenses')).toBeTruthy();
    expect(screen.getByText('Export to CSV')).toBeTruthy();
    expect(
      screen.getByText('Upgrading is not available in this version yet.'),
    ).toBeTruthy();
    expect(screen.queryByText(/Restore/i)).toBeNull();
    expect(screen.queryByText(/Subscribe|Buy|Purchase/i)).toBeNull();
    expect(
      env.server.log.some(r => /subscri|purchase|billing/i.test(r.path)),
    ).toBe(false);
  });

  it('a premium user sees their plan, with no upsell notice', async () => {
    premium();
    await launch(env);
    await press('Account');
    await press('Manage plan');
    expect(await screen.findByText('You have Premium')).toBeTruthy();
    expect(screen.getByText('Premium until 2027-01-01.')).toBeTruthy();
    expect(screen.queryByText(/not available in this version/)).toBeNull();
  });
});

describe('S6-M-4 search (SCR-36)', () => {
  const searches = () =>
    reqs(env.server, 'GET', '/expenses').filter(r => r.query.includes('q='));
  const seedSearch = () => {
    premium();
    env.server.overrides.push(req => {
      if (
        req.path === '/expenses' &&
        req.method === 'GET' &&
        req.query.includes('q=')
      ) {
        const q = new URLSearchParams(req.query).get('q') ?? '';
        const all = [exp('x1', 'Goa trip'), exp('x2', 'Goa taxi')];
        return {
          status: 200,
          body: {
            items: all.filter(e =>
              e.description.toLowerCase().includes(q.toLowerCase()),
            ),
            next_cursor: null,
          },
        };
      }
    });
  };

  it('debounces typing: five keystrokes inside 300 ms send exactly one request, with 25 per page', async () => {
    seedSearch();
    await launch(env);
    await pressLabel('Search expenses');
    const input = await screen.findByLabelText('Search expenses');
    jest.useFakeTimers();
    for (const t of ['g', 'go', 'goa', 'goa ', 'goa t']) {
      await fireEvent.changeText(input, t);
      await act(async () => {
        jest.advanceTimersByTime(100);
      });
    }
    expect(searches()).toHaveLength(0);
    await act(async () => {
      jest.advanceTimersByTime(300);
    });
    // fake timers stay on: react-query schedules its notifications with timers too
    expect(await screen.findByText('Goa trip')).toBeTruthy();
    expect(searches()).toHaveLength(1);
    const params = new URLSearchParams(searches()[0].query);
    expect(params.get('q')).toBe('goa t');
    expect(params.get('limit')).toBe('25');
  });

  it('needs at least 2 characters before searching', async () => {
    seedSearch();
    await launch(env);
    await pressLabel('Search expenses');
    const input = await screen.findByLabelText('Search expenses');
    await fireEvent.changeText(input, 'g');
    await act(async () => {
      await new Promise(r => setTimeout(r, 400));
    });
    expect(searches()).toHaveLength(0);
    expect(
      (await screen.findAllByText(/at least 2 characters/)).length,
    ).toBeGreaterThan(0);
  });

  it('shows a no-results state and opens SCR-29 from a result', async () => {
    seedSearch();
    env.server.expenses.push(exp('x1', 'Goa trip'));
    await launch(env);
    await pressLabel('Search expenses');
    const input = await screen.findByLabelText('Search expenses');
    await fireEvent.changeText(input, 'zzz');
    expect(await screen.findByText('No results')).toBeTruthy();
    await fireEvent.changeText(input, 'goa trip');
    await press('Goa trip');
    expect(await screen.findByText('Comments')).toBeTruthy();
  });

  it('a 402 PREMIUM_REQUIRED from the server (plan out of date) routes to the paywall', async () => {
    premium();
    env.server.overrides.push(req => {
      if (req.path === '/expenses' && req.query.includes('q=')) {
        env.server.me = { ...env.server.me, plan: 'free' }; // the plan lapsed on the server
        return {
          status: 402,
          body: { code: 'PREMIUM_REQUIRED', message: 'premium' },
        };
      }
    });
    await launch(env);
    await pressLabel('Search expenses');
    await fireEvent.changeText(
      await screen.findByLabelText('Search expenses'),
      'goa',
    );
    expect(
      await screen.findByText('Search is a Premium feature.'),
    ).toBeTruthy();
  });

  it('a network failure shows the offline error with Retry', async () => {
    premium();
    await launch(env);
    await pressLabel('Search expenses');
    const input = await screen.findByLabelText('Search expenses');
    (global as any).fetch = jest.fn(async () => {
      throw new TypeError('Network request failed');
    });
    await fireEvent.changeText(input, 'goa');
    expect(
      await screen.findByText(/offline or the server can't be reached/),
    ).toBeTruthy();
    expect(screen.getByText('Retry')).toBeTruthy();
  });
});

describe('S6-M-4 export (SCR-38)', () => {
  type Job = { polls: number; readyAfter: number; failed: boolean };
  const job: Job = { polls: 0, readyAfter: 1, failed: false };
  const seedExport = () => {
    premium();
    job.polls = 0;
    job.readyAfter = 1;
    job.failed = false;
    env.server.overrides.push(req => {
      if (req.path === '/exports' && req.method === 'POST') {
        return {
          status: 202,
          body: {
            id: 'e1',
            status: 'pending',
            scope: 'group',
            format: 'csv',
            created_at: 'x',
          },
        };
      }
      if (req.path === '/exports/e1' && req.method === 'GET') {
        job.polls += 1;
        if (job.failed) {
          return {
            status: 200,
            body: {
              id: 'e1',
              status: 'failed',
              scope: 'group',
              format: 'csv',
              created_at: 'x',
            },
          };
        }
        return job.polls >= job.readyAfter
          ? {
              status: 200,
              body: {
                id: 'e1',
                status: 'ready',
                scope: 'group',
                format: 'csv',
                download_url: `https://files.example/e1?sig=${job.polls}`,
                file_name: 'flat.csv',
                created_at: 'x',
              },
            }
          : {
              status: 200,
              body: {
                id: 'e1',
                status: 'pending',
                scope: 'group',
                format: 'csv',
                created_at: 'x',
              },
            };
      }
    });
  };
  const open = async () => {
    env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Settings');
    await press('Export to CSV');
  };

  it('premium: POST once, shows "generating", polls, then opens the share sheet with the latest URL', async () => {
    seedExport();
    job.readyAfter = 2;
    const share = jest
      .spyOn(Share, 'share')
      .mockResolvedValue({ action: 'sharedAction' } as never);
    await open();
    expect(await screen.findByText('Generating your file...')).toBeTruthy();
    await waitFor(() => expect(share).toHaveBeenCalled(), { timeout: 6000 });
    expect(reqs(env.server, 'POST', '/exports')).toHaveLength(1);
    expect(reqs(env.server, 'POST', '/exports')[0].body).toMatchObject({
      scope: 'group',
    });
    expect(share).toHaveBeenCalledWith({
      message: 'flat.csv',
      url: 'https://files.example/e1?sig=2',
    });
    expect(job.polls).toBe(2);
    share.mockRestore();
  });

  it('failure shows a banner; Retry sends exactly one more request', async () => {
    seedExport();
    job.failed = true;
    await open();
    expect(
      await screen.findByText(
        'The export could not be created.',
        {},
        { timeout: 4000 },
      ),
    ).toBeTruthy();
    expect(reqs(env.server, 'POST', '/exports')).toHaveLength(1);
    await press('Retry');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', '/exports')).toHaveLength(2),
    );
    await screen.findByText(
      'The export could not be created.',
      {},
      { timeout: 4000 },
    );
    expect(reqs(env.server, 'POST', '/exports')).toHaveLength(2);
  });

  it('a 402 on create (plan out of date) routes to the paywall', async () => {
    premium();
    env.server.overrides.push(req => {
      if (req.path === '/exports') {
        env.server.me = { ...env.server.me, plan: 'free' }; // the plan lapsed on the server
        return {
          status: 402,
          body: { code: 'PREMIUM_REQUIRED', message: 'p' },
        };
      }
    });
    await open();
    expect(
      await screen.findByText('Export is a Premium feature.'),
    ).toBeTruthy();
  });
});

describe('S6-M-4 receipt image on SCR-29', () => {
  const openExpense = async (receipt: string | null) => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.addExpense({
      id: 'x-r',
      group_id: g.id,
      description: 'Dinner',
      receipt_url: receipt,
      splits: [{ user_id: 'u-me', owed_amount_minor: 5000 }],
    });
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Dinner');
  };

  it('shows a thumbnail that opens full screen and closes', async () => {
    await openExpense('https://files.example/r1.jpg');
    const thumb = await screen.findByLabelText('Receipt, tap to enlarge');
    expect(screen.getByText('Receipt')).toBeTruthy();
    await fireEvent.press(thumb);
    expect(await screen.findByLabelText('Receipt')).toBeTruthy();
    await press('Close');
  });

  it('shows nothing when there is no receipt', async () => {
    await openExpense(null);
    await screen.findByText('Comments');
    expect(screen.queryByLabelText('Receipt, tap to enlarge')).toBeNull();
  });
});
