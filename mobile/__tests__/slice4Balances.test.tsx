/**
 * S4-M-1 (balance rendering) and S4-M-2 (Group balances SCR-15, simplify explainer SCR-40).
 * Component/screen tests against the fake server with mocked balance data. This is NOT real E2E:
 * no emulator or Detox/Maestro exists in the repo.
 */
import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';
import { resetTokenCache } from '../src/auth/tokenStorage';
import { BalanceLines, MemberNetLines } from '../src/components/BalanceLines';
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

const press = async (text: string | RegExp) =>
  fireEvent.press(await screen.findByText(text));
const DAY = 24 * 60 * 60 * 1000;
const daysAgo = (n: number) => new Date(Date.now() - n * DAY).toISOString();

const ONE = [{ amount_minor: 12050, currency: 'INR' }];
const TWO = [
  { amount_minor: 12050, currency: 'INR' },
  { amount_minor: -300, currency: 'USD' },
];
const THREE = [
  { amount_minor: -500, currency: 'USD' },
  { amount_minor: 12050, currency: 'INR' },
  { amount_minor: 1200, currency: 'JPY' },
];

describe('S4-M-1 per-currency balance lines (snapshots)', () => {
  const renderLines = async (lines: typeof ONE, member = false) => {
    const client = newClient();
    const view = await render(
      <QueryClientProvider client={client}>
        {member ? (
          <MemberNetLines lines={lines} />
        ) : (
          <BalanceLines lines={lines} />
        )}
      </QueryClientProvider>,
    );
    return view.toJSON();
  };

  it('1 currency', async () => {
    expect(await renderLines(ONE)).toMatchSnapshot();
  });
  it('2 currencies, never summed', async () => {
    expect(await renderLines(TWO)).toMatchSnapshot();
  });
  it('3 currencies, ordered by code, 0-decimal JPY', async () => {
    expect(await renderLines(THREE)).toMatchSnapshot();
  });
  it('member net variant for the viewer uses "owe" / "get back"', async () => {
    const view = await render(
      <QueryClientProvider client={newClient()}>
        <MemberNetLines lines={TWO} isViewer />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/^get back /)).toBeTruthy();
    expect(screen.getByText(/^owe /)).toBeTruthy();
    expect(screen.queryByText(/^owes /)).toBeNull();
    expect(screen.queryByText(/^gets back /)).toBeNull();
    expect(view.toJSON()).toBeTruthy();
  });
  it('member net variant with 2 currencies', async () => {
    expect(await renderLines(TWO, true)).toMatchSnapshot();
  });
});

describe('S4-M-1 screens', () => {
  it('friend at 0 since 31 days is hidden behind "show 1 settled-up friend"; 29 days stays visible', async () => {
    server.addFriendRow('f1', 'Ravi', ONE);
    server.addFriendRow('f2', 'Old', [], daysAgo(31));
    server.addFriendRow('f3', 'Recent', [], daysAgo(29));
    await render(<App queryClient={qc} />);
    await press('Friends');
    expect(await screen.findByText('Ravi')).toBeTruthy();
    expect(screen.getByText('Recent')).toBeTruthy();
    expect(screen.queryByText('Old')).toBeNull();
    await fireEvent.press(screen.getByText('Show 1 settled-up friend'));
    expect(await screen.findByText('Old')).toBeTruthy();
  });

  it('friend detail shows 3 currencies and the breakdown separately', async () => {
    server.addFriendRow('f1', 'Ravi', THREE);
    server.friends[0].breakdown = [
      {
        scope: 'non_group',
        group_id: null,
        group_name: null,
        balances: [{ amount_minor: 12050, currency: 'INR' }],
      },
      {
        scope: 'group',
        group_id: 'g1',
        group_name: 'Goa',
        balances: [
          { amount_minor: -500, currency: 'USD' },
          { amount_minor: 1200, currency: 'JPY' },
        ],
      },
    ];
    await render(<App queryClient={qc} />);
    await press('Friends');
    await press('Ravi');
    expect(await screen.findByText('Goa')).toBeTruthy();
    expect(screen.getAllByText('owes you INR 120.50').length).toBe(2);
    expect(screen.getAllByText('you owe USD 5.00').length).toBe(2);
    expect(screen.getAllByText('owes you JPY 1,200').length).toBe(2);
  });

  it('groups tab: per-currency lines, singular settled-up label, non-group row', async () => {
    const g1 = server.addGroup('Flat', [server.user('u-a', 'Ravi')]);
    const g2 = server.addGroup('Old trip', [server.user('u-b', 'Meera')]);
    server.overrides.push(req =>
      req.path === '/groups' && req.method === 'GET'
        ? {
            status: 200,
            body: {
              items: [
                {
                  id: g1.id,
                  name: 'Flat',
                  group_type: 'home',
                  member_count: 2,
                  my_balances: TWO,
                  settled_up_since: null,
                },
                {
                  id: g2.id,
                  name: 'Old trip',
                  group_type: 'trip',
                  member_count: 2,
                  my_balances: [],
                  settled_up_since: daysAgo(40),
                },
              ],
              non_group_balances: [{ amount_minor: 30000, currency: 'INR' }],
            },
          }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('owes you INR 120.50')).toBeTruthy();
    expect(screen.getByText('you owe USD 3.00')).toBeTruthy();
    expect(screen.getByText('Non-group expenses')).toBeTruthy();
    expect(screen.queryByText('Old trip')).toBeNull();
    expect(screen.getByText('Show 1 settled-up group')).toBeTruthy();
  });
});

describe('S4-M-2 Group balances and simplify explainer', () => {
  // business_rules vector 20: nets A -3000, B -1000, C +2500, D +1500.
  const setup = (simplified: boolean) => {
    const g = server.addGroup('Trip', [
      server.user('u-b', 'Bea'),
      server.user('u-c', 'Cy'),
      server.user('u-d', 'Dan'),
    ]);
    g.simplify_debts = simplified;
    const inr = (n: number) => [{ amount_minor: n, currency: 'INR' }];
    const t = (f: string, to: string, n: number) => ({
      from_user_id: f,
      to_user_id: to,
      amount_minor: n,
      currency: 'INR',
    });
    server.overrides.push(req => {
      if (req.path === `/groups/${g.id}/balances` && req.method === 'GET') {
        return {
          status: 200,
          body: {
            group_id: g.id,
            simplified,
            members: [
              { user_id: 'u-me', balances: inr(-3000) },
              { user_id: 'u-b', balances: inr(-1000) },
              { user_id: 'u-c', balances: inr(2500) },
              { user_id: 'u-d', balances: inr(1500) },
            ],
            transfers: simplified
              ? [
                  t('u-me', 'u-c', 2500),
                  t('u-b', 'u-d', 1000),
                  t('u-me', 'u-d', 500),
                ]
              : [
                  t('u-me', 'u-c', 1500),
                  t('u-me', 'u-d', 1500),
                  t('u-b', 'u-c', 1000),
                ],
          },
        };
      }
      return undefined;
    });
    return g;
  };
  const open = async () => {
    await render(<App queryClient={qc} />);
    await press('Trip');
    await press('Balances');
  };
  const transfers = () =>
    screen.getAllByTestId('transfer').map(n => n.props.children);

  it('vector 20: 3 transfers in the documented order, member nets per currency', async () => {
    setup(true);
    await open();
    expect(await screen.findByText('Simplify debts is on')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getAllByTestId('transfer').length).toBe(3),
    );
    expect(transfers()).toEqual([
      'You owe Cy INR 25.00',
      'Bea owes Dan INR 10.00',
      'You owe Dan INR 5.00',
    ]);
    expect(screen.getByText('owe INR 30.00 in total')).toBeTruthy();
    expect(screen.getByText('gets back INR 25.00 in total')).toBeTruthy();
  });

  it("tapping a member expands that member's payments", async () => {
    setup(true);
    await open();
    await fireEvent.press(await screen.findByLabelText('Member: Bea'));
    // list shows the line once in the suggested section and once expanded
    expect(screen.getAllByText('Bea owes Dan INR 10.00').length).toBe(2);
  });

  it('simplify off shows the pairwise list', async () => {
    setup(false);
    await open();
    expect(await screen.findByText('Simplify debts is off')).toBeTruthy();
    expect(screen.getByText('Who owes whom')).toBeTruthy();
    expect(transfers()).toEqual([
      'You owe Cy INR 15.00',
      'You owe Dan INR 15.00',
      'Bea owes Cy INR 10.00',
    ]);
  });

  it('all zero: everyone is settled up', async () => {
    const g = server.addGroup('Trip', [server.user('u-b', 'Bea')]);
    server.overrides.push(req =>
      req.path === `/groups/${g.id}/balances`
        ? {
            status: 200,
            body: {
              group_id: g.id,
              simplified: true,
              members: [
                { user_id: 'u-me', balances: [] },
                { user_id: 'u-b', balances: [] },
              ],
              transfers: [],
            },
          }
        : undefined,
    );
    await open();
    expect(await screen.findByText('Everyone is settled up')).toBeTruthy();
  });

  it('error state offers Retry', async () => {
    const g = server.addGroup('Trip', [server.user('u-b', 'Bea')]);
    let fail = true;
    server.overrides.push(req =>
      req.path === `/groups/${g.id}/balances`
        ? fail
          ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'x' } }
          : {
              status: 200,
              body: {
                group_id: g.id,
                simplified: true,
                members: [],
                transfers: [],
              },
            }
        : undefined,
    );
    await open();
    expect(
      await screen.findByText('Something went wrong. Please try again.'),
    ).toBeTruthy();
    fail = false;
    await fireEvent.press(screen.getByText('Retry'));
    expect(await screen.findByText('Everyone is settled up')).toBeTruthy();
  });

  it('explainer: Turn on patches simplify_debts with the current version when off', async () => {
    const g = setup(false);
    g.simplify_debts = false;
    await open();
    await press('What is this?');
    expect(await screen.findByText('Ann pays Cy 10')).toBeTruthy();
    await fireEvent.press(screen.getByText('Turn on'));
    await waitFor(() => expect(server.count('PATCH', /^\/groups\//)).toBe(1));
    expect(server.log.find(r => r.method === 'PATCH')!.body).toEqual({
      version: 1,
      simplify_debts: true,
    });
  });

  it('explainer: no Turn on button when simplify is already on', async () => {
    setup(true);
    await open();
    await press('What is this?');
    expect(
      await screen.findByText('Simplify debts is on for this group.'),
    ).toBeTruthy();
    expect(screen.queryByText('Turn on')).toBeNull();
  });
});

describe('member count wording', () => {
  it('SCR-09 rows say "1 member" and "2 members"', async () => {
    const g1 = server.addGroup('Solo', []);
    const g2 = server.addGroup('Pair', [server.user('u-a', 'Ravi')]);
    server.overrides.push(req =>
      req.path === '/groups' && req.method === 'GET'
        ? {
            status: 200,
            body: {
              items: [
                {
                  id: g1.id,
                  name: 'Solo',
                  group_type: 'home',
                  member_count: 1,
                  my_balances: [],
                  settled_up_since: null,
                },
                {
                  id: g2.id,
                  name: 'Pair',
                  group_type: 'trip',
                  member_count: 2,
                  my_balances: [],
                  settled_up_since: null,
                },
              ],
              non_group_balances: [],
            },
          }
        : undefined,
    );
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('1 member')).toBeTruthy();
    expect(screen.getByText('2 members')).toBeTruthy();
    expect(screen.queryByText('1 members')).toBeNull();
  });
});

describe('SCR-08 re-evaluates the 30-day collapse on focus', () => {
  afterEach(() => jest.restoreAllMocks());

  it('29 days visible; after the clock passes 30 days and the tab is refocused it is hidden', async () => {
    server.addFriendRow('f1', 'Ravi', ONE);
    server.addFriendRow('f3', 'Recent', [], daysAgo(29));
    const real = Date.now.bind(Date);
    let offset = 0;
    jest.spyOn(Date, 'now').mockImplementation(() => real() + offset);
    await render(<App queryClient={qc} />);
    await press('Friends');
    expect(await screen.findByText('Recent')).toBeTruthy();
    expect(screen.queryByText('Show 1 settled-up friend')).toBeNull();

    offset = 2 * DAY;
    await press('Groups');
    await press('Friends');
    await waitFor(() => expect(screen.queryByText('Recent')).toBeNull());
    expect(screen.getByText('Ravi')).toBeTruthy();
    expect(screen.getByText('Show 1 settled-up friend')).toBeTruthy();
  });
});
