/**
 * SUI-Q-3 (CR-UI-2): SCR-13 top half redesign (one balance card). Written AFTER the implementation (SUI-M-146),
 * so these are regression guards, not red-first tests. Against the old screen most of them fail (see handoff).
 *
 * Counterparty lines were NOT implemented (GET /groups/{id} has no pairwise data), so only the "See all
 * balances" link is asserted (design_system 8.2 item 7.4: "show only the link").
 */
import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { View } from 'react-native';
import { AuthProvider } from '../../src/auth/AuthContext';
import { resetTokenCache } from '../../src/auth/tokenStorage';
import { GroupDetailScreen } from '../../src/screens/GroupDetailScreen';
import { formatMoney } from '../../src/money/format';
import {
  colorSchemes,
  spacing,
  touchTarget,
  typography,
  useTheme,
} from '../../src/theme';
import { contrast } from '../../src/theme/testing/contrast';
import { FakeServer } from '../../testUtils/fakeServer';
import {
  SCHEMES,
  Scheme,
  colorsOutsideScheme,
  expectTouchTargets,
  flattenStyle,
  nodesOf,
  pressIn,
  renderAtFontScale,
  renderBothThemes,
  resolvedColors,
  textOf,
  themed,
  touchTargetProblems,
} from './harness';

type Line = { amount_minor: number; currency: string };
const INR_OWED: Line = { amount_minor: 1502500, currency: 'INR' };
const USD_OWED: Line = { amount_minor: 4500, currency: 'USD' };
const USD_OWE: Line = { amount_minor: -4500, currency: 'USD' };
const OWED_TEXT = `You are owed ${formatMoney(1502500, 'INR')} and ${formatMoney(4500, 'USD')}.`;

let server: FakeServer;
const navRef = createNavigationContainerRef();
const Stack = createNativeStackNavigator();

beforeEach(async () => {
  server = new FakeServer();
  server.seedTokens();
  server.install();
  resetTokenCache();
  await AsyncStorage.clear();
});

const newClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });

const flush = async () => {
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await new Promise(r => setTimeout(r, 0));
    });
  }
};

/** Goa Trip with Asha (viewer), Ravi, Dev; GET /groups/g-goa carries `lines` as my_balances. */
function seedGoa(lines: Line[], name = 'Goa Trip') {
  const g = server.addGroup(
    name,
    [server.user('u-ravi', 'Ravi'), server.user('u-dev', 'Dev')],
    'g-goa',
  );
  g.group_type = 'trip';
  // member nets must not leak onto SCR-13 either
  g.members[1].balances = [{ amount_minor: 1502500, currency: 'INR' }];
  g.members[2].balances = [{ amount_minor: 4500, currency: 'USD' }];
  server.overrides.push(req =>
    req.method === 'GET' && req.path === '/groups/g-goa'
      ? {
          status: 200,
          body: { ...g, deleted: undefined, my_balances: lines },
        }
      : undefined,
  );
  return g;
}

const Stub = (label: string) =>
  function StubScreen() {
    return <View testID={`stub-${label}`} />;
  };

function Shell({ client }: { client: QueryClient }) {
  const { colors, isDark } = useTheme();
  const navTheme = {
    ...(isDark ? DarkTheme : DefaultTheme),
    colors: {
      primary: colors.brand,
      background: colors.background,
      card: colors.surface,
      text: colors.textPrimary,
      border: colors.border,
      notification: colors.brand,
    },
  };
  return (
    <QueryClientProvider client={client}>
      <NavigationContainer theme={navTheme} ref={navRef}>
        <AuthProvider>
          <Stack.Navigator initialRouteName="GroupDetail">
            <Stack.Screen
              name="GroupDetail"
              component={GroupDetailScreen as never}
              initialParams={{ groupId: 'g-goa' }}
            />
            <Stack.Screen name="GroupBalances" component={Stub('balances')} />
            <Stack.Screen name="SettleUp" component={Stub('settle')} />
            <Stack.Screen name="GroupMembers" component={Stub('members')} />
          </Stack.Navigator>
        </AuthProvider>
      </NavigationContainer>
    </QueryClientProvider>
  );
}

async function open(scheme: Scheme = 'light') {
  const r = await render(themed(<Shell client={newClient()} />, scheme));
  await flush();
  await r.findByTestId('balance-card');
  return r;
}
const route = () =>
  (
    navRef as unknown as { getCurrentRoute(): { name: string } | undefined }
  ).getCurrentRoute()?.name;

/** Style at rest vs after a responder grant (the host style is already resolved, so a style function is not seen). */
const pressedDiffers = async (name: string) => {
  const rest = JSON.stringify(styleOf(btn(name)));
  await pressIn(btn(name));
  return JSON.stringify(styleOf(btn(name))) !== rest;
};
const HIDDEN = { includeHiddenElements: true };
const btn = (name: string) => screen.getByRole('button', { name });
const styleOf = (el: { props: Record<string, unknown> }, pressed = false) => {
  const s = el.props.style;
  return flattenStyle(typeof s === 'function' ? s({ pressed }) : s);
};
const hasMinTarget = (el: { props: Record<string, unknown> }) => {
  const s = styleOf(el);
  const slop = el.props.hitSlop as number | undefined;
  return (
    Math.max(Number(s.height ?? 0), Number(s.minHeight ?? 0)) +
      (typeof slop === 'number' ? slop * 2 : 0) >=
    touchTarget.min
  );
};
const fontSizeOf = (el: { props: Record<string, unknown> }) =>
  Number(flattenStyle(el.props.style).fontSize);

describe('1. group name appears once', () => {
  it('the name is the nav header title only; no in-body title text', async () => {
    seedGoa([INR_OWED]);
    await open();
    // jest does not render the native header, so the header is checked through the navigation options
    const opts = (
      navRef as unknown as { getCurrentOptions(): { title?: string } }
    ).getCurrentOptions();
    expect(opts.title).toBe('Goa Trip');
    // and nothing in the screen body repeats it as text (the card's spoken label is not text)
    expect(screen.queryAllByText('Goa Trip')).toHaveLength(0);
    expect(screen.queryAllByText(/Goa Trip/)).toHaveLength(0);
  });
});

describe('2. subtitle row: type and members entry', () => {
  it('shares one row; entry is a 48dp button labelled "3 members, show list"', async () => {
    seedGoa([INR_OWED]);
    await open();
    const entry = screen.getByTestId('members-entry');
    expect(entry.props.accessibilityRole).toBe('button');
    expect(entry.props.accessibilityLabel).toBe('3 members, show list');
    expect(screen.getByRole('button', { name: '3 members, show list' })).toBe(
      entry,
    );
    expect(hasMinTarget(entry)).toBe(true);
    // the type text and the entry have the same parent row
    const type = screen.getByText('trip');
    expect(type.parent).toBe(entry.parent);
    // old combined string is gone
    expect(screen.queryByText(/trip\s*[-·]\s*3 members/)).toBeNull();
    expect(screen.queryByText(/3 members/, { exact: false })).toBeTruthy();
    expect(
      touchTargetProblems(screen.toJSON()).filter(p => p.includes('show list')),
    ).toEqual([]);
  });

  it('1 member: singular label', async () => {
    server.addGroup('Solo', [], 'g-goa');
    await open();
    expect(screen.getByTestId('members-entry').props.accessibilityLabel).toBe(
      '1 member, show list',
    );
  });

  it('pressing the entry opens GroupMembers', async () => {
    seedGoa([INR_OWED]);
    await open();
    await fireEvent.press(screen.getByTestId('members-entry'));
    await flush();
    expect(route()).toBe('GroupMembers');
  });
});

describe('3. balance card rows', () => {
  it('two currencies: two rows, both "You are owed", amounts from format.ts, never summed', async () => {
    seedGoa([INR_OWED, USD_OWED]);
    await open();
    const card = screen.getByTestId('balance-card');
    expect(within(card).getByText('Your balance')).toBeTruthy();
    const inr = within(card).getByTestId('balance-row-INR');
    const usd = within(card).getByTestId('balance-row-USD');
    expect(within(inr).getByText('You are owed')).toBeTruthy();
    expect(within(usd).getByText('You are owed')).toBeTruthy();
    expect(within(inr).getByText('INR 15,025.00')).toBeTruthy();
    expect(within(usd).getByText('USD 45.00')).toBeTruthy();
    expect(within(card).queryByText(/You owe\b/)).toBeNull();
    // never summed: no combined figure of any kind
    expect(within(card).queryByText('15,070.00', { exact: false })).toBeNull();
    expect(within(card).queryByText('1,507,000', { exact: false })).toBeNull();
    expect(within(card).getAllByText(/\d,\d{3}\.\d\d|\d\.\d\d/)).toHaveLength(
      2,
    );
    // sizing: 2+ rows use title1
    expect(fontSizeOf(within(inr).getByText('INR 15,025.00'))).toBe(
      typography.title1.fontSize,
    );
    expect(fontSizeOf(within(usd).getByText('USD 45.00'))).toBe(
      typography.title1.fontSize,
    );
  });

  it('mixed direction: INR owed and USD owe are separate rows with their own headlines', async () => {
    seedGoa([INR_OWED, USD_OWE]);
    await open();
    const inr = screen.getByTestId('balance-row-INR');
    const usd = screen.getByTestId('balance-row-USD');
    expect(within(inr).getByText('You are owed')).toBeTruthy();
    expect(within(inr).getByText('INR 15,025.00')).toBeTruthy();
    expect(within(usd).getByText('You owe')).toBeTruthy();
    expect(within(usd).getByText('USD 45.00')).toBeTruthy(); // magnitude, no minus sign
    expect(within(usd).queryByText(/-/)).toBeNull();
    expect(within(inr).queryByText('You owe')).toBeNull();
  });

  it('single currency: one row, amount in display size (larger than the two-row title1)', async () => {
    seedGoa([INR_OWED]);
    await open();
    expect(screen.getAllByTestId(/^balance-row-/)).toHaveLength(1);
    const amt = within(screen.getByTestId('balance-row-INR')).getByText(
      'INR 15,025.00',
    );
    expect(fontSizeOf(amt)).toBe(typography.display.fontSize);
    expect(Number(typography.display.fontSize)).toBeGreaterThan(
      Number(typography.title1.fontSize),
    );
  });

  it('a zero line in one currency is omitted when another is non-zero', async () => {
    seedGoa([INR_OWED, { amount_minor: 0, currency: 'USD' }]);
    await open();
    expect(screen.queryByTestId('balance-row-USD')).toBeNull();
    expect(screen.getAllByTestId(/^balance-row-/)).toHaveLength(1);
  });
});

describe('4. direction is not color alone', () => {
  it('each row has words plus a hidden decorative icon (arrow differs per direction)', async () => {
    seedGoa([INR_OWED, USD_OWE]);
    await open();
    const rows: [string, string, string, string][] = [
      ['INR', 'You are owed', '↑', 'owed'],
      ['USD', 'You owe', '↓', 'owe'],
    ];
    for (const [cur, word, arrow] of rows) {
      const row = screen.getByTestId(`balance-row-${cur}`);
      expect(within(row).getByText(word)).toBeTruthy();
      const icon = within(row).getByTestId(`balance-icon-${cur}`, HIDDEN);
      expect(icon.props.accessible).toBe(false);
      expect(icon.props.importantForAccessibility).toBe('no-hide-descendants');
      expect(textOf(icon as never)).toBe(arrow);
    }
  });

  it('settled: check icon is hidden from accessibility and the words are present', async () => {
    seedGoa([]);
    await open();
    const icon = screen.getByTestId('balance-settled-icon', HIDDEN);
    expect(icon.props.importantForAccessibility).toBe('no-hide-descendants');
    expect(textOf(icon as never)).toBe('✓');
    expect(
      screen.getByText('You are all settled up in this group'),
    ).toBeTruthy();
  });
});

describe('5. no per-member net lines on SCR-13', () => {
  it('no "in total", no "+N more", no member names with balances', async () => {
    const g = seedGoa([INR_OWED, USD_OWED]);
    for (const n of ['Meera', 'Isha', 'Kabir']) {
      g.members.push({
        ...g.members[1],
        user: server.user(`u-${n}`, n),
        balances: [{ amount_minor: 1000, currency: 'INR' }],
      });
    }
    await open();
    expect(screen.queryByText(/in total/)).toBeNull();
    expect(screen.queryByText(/\+\d+ more/)).toBeNull();
    for (const n of ['Ravi', 'Dev', 'Meera', 'Isha', 'Kabir']) {
      expect(screen.queryByText(n)).toBeNull();
    }
    expect(screen.queryByText(/You get back/i)).toBeNull();
    expect(screen.queryByText(/You owe Ravi|owes you/)).toBeNull();
  });
});

describe('6. no "See all balances" link; Balances button is the single route (SUI-Q-4)', () => {
  it('the Balances button opens GroupBalances with 0 extra requests', async () => {
    seedGoa([INR_OWED]);
    await open();
    const before = server.log.length;
    await fireEvent.press(btn('Balances'));
    await flush();
    expect(route()).toBe('GroupBalances');
    expect(server.log.length).toBe(before);
  });

  it.each([
    ['normal', [INR_OWED, USD_OWED]],
    ['mixed direction', [INR_OWED, USD_OWE]],
    ['settled', []],
  ] as [string, Line[]][])(
    '%s: no see-all-balances element and no link role anywhere in the card or screen',
    async (_n, lines) => {
      seedGoa(lines);
      await open();
      const card = screen.getByTestId('balance-card');
      expect(within(card).queryByTestId('see-all-balances')).toBeNull();
      expect(within(card).queryByRole('link')).toBeNull();
      expect(screen.queryByTestId('see-all-balances')).toBeNull();
      expect(screen.queryByRole('link')).toBeNull();
      expect(screen.queryByText('See all balances')).toBeNull();
      expect(btn('Balances')).toBeTruthy();
    },
  );

  it('no counterparty lines ("owes you") are shown without pairwise data', async () => {
    seedGoa([INR_OWED]);
    await open();
    expect(screen.queryByText(/owes you/)).toBeNull();
  });

  it('opening SCR-13 needs only the group and the first timeline page (no balance or member requests)', async () => {
    seedGoa([INR_OWED]);
    await open();
    const paths = server.log.map(r => `${r.method} ${r.path}`);
    expect(paths.filter(p => p === 'GET /groups/g-goa')).toHaveLength(1);
    expect(paths.filter(p => /balances|simplif|settle/i.test(p))).toEqual([]);
  });
});

describe('7. action buttons', () => {
  it('Settle up and Balances: >= 48dp, gap >= spacing.md, pressed differs from rest, no overlap', async () => {
    seedGoa([INR_OWED]);
    await open();
    const settle = btn('Settle up');
    const bal = btn('Balances');
    for (const b of [settle, bal]) {
      expect(hasMinTarget(b)).toBe(true);
    }
    expect(
      touchTargetProblems(screen.toJSON()).filter(p =>
        /Settle up|Balances/.test(p),
      ),
    ).toEqual([]);
    const actions = screen.getByTestId('group-actions');
    const as = flattenStyle(actions.props.style);
    expect(Number(as.gap)).toBeGreaterThanOrEqual(spacing.md);
    // the primary is the filled brand one, the secondary is not
    expect(styleOf(settle).backgroundColor).toBe(colorSchemes.light.brand);
    expect(styleOf(bal).backgroundColor).not.toBe(colorSchemes.light.brand);
    // pressed feedback differs from rest
    expect(await pressedDiffers('Settle up')).toBe(true);
    expect(await pressedDiffers('Balances')).toBe(true);
  });

  it('Settle up and Balances navigate', async () => {
    seedGoa([INR_OWED]);
    await open();
    await fireEvent.press(btn('Balances'));
    await flush();
    expect(route()).toBe('GroupBalances');
    navRef.goBack();
    await flush();
    await fireEvent.press(btn('Settle up'));
    await flush();
    expect(route()).toBe('SettleUp');
  });

  it.each([
    [1.0, 'row'],
    [1.49, 'row'],
    [1.5, 'column'],
    [2.0, 'column'],
  ] as const)(
    'fontScale %s: action row is %s with a full gap',
    async (scale, dir) => {
      seedGoa([INR_OWED]);
      const r = await renderAtFontScale(<Shell client={newClient()} />, scale);
      try {
        await flush();
        const actions = await r.findByTestId('group-actions');
        const s = flattenStyle(actions.props.style);
        expect(s.flexDirection).toBe(dir);
        expect(Number(s.gap)).toBeGreaterThanOrEqual(spacing.md);
        // both buttons are still there and still at least 48dp
        expect(hasMinTarget(r.getByRole('button', { name: 'Settle up' }))).toBe(
          true,
        );
        expect(hasMinTarget(r.getByRole('button', { name: 'Balances' }))).toBe(
          true,
        );
      } finally {
        r.restore();
        await r.unmount();
      }
    },
  );
});

describe('8. settled state', () => {
  it.each([
    ['all balances zero', [{ amount_minor: 0, currency: 'INR' }]],
    ['brand-new group with no balances', []],
  ] as [string, Line[]][])('%s', async (_n, lines) => {
    seedGoa(lines);
    await open();
    expect(
      screen.getByText('You are all settled up in this group'),
    ).toBeTruthy();
    expect(screen.getByTestId('balance-settled-icon', HIDDEN)).toBeTruthy();
    expect(screen.queryByTestId(/^balance-row-/)).toBeNull();
    const card = screen.getByTestId('balance-card');
    expect(within(card).queryByText(/\d/)).toBeNull(); // no amounts
    expect(within(card).queryByText(/You are owed|You owe/)).toBeNull();
    const settle = btn('Settle up');
    expect(settle.props.accessibilityState.disabled).toBe(false);
    expect(settle.props.accessibilityState.busy).toBeFalsy();
    // secondary: not the filled brand style
    expect(styleOf(settle).backgroundColor).not.toBe(colorSchemes.light.brand);
    expect(btn('Balances')).toBeTruthy();
    await fireEvent.press(settle);
    await flush();
    expect(route()).toBe('SettleUp');
  });

  it('settled Balances button also shows pressed feedback (design_system 8.2 item 7.5)', async () => {
    seedGoa([]);
    await open();
    expect(await pressedDiffers('Balances')).toBe(true);
  });
});

describe('9. one spoken label on the card', () => {
  it.each([
    [
      'owed in two currencies',
      [INR_OWED, USD_OWED],
      `Your balance in Goa Trip. ${OWED_TEXT}`,
    ],
    [
      'mixed',
      [INR_OWED, USD_OWE],
      `Your balance in Goa Trip. You are owed INR 15,025.00. You owe USD 45.00.`,
    ],
    ['single owe', [USD_OWE], 'Your balance in Goa Trip. You owe USD 45.00.'],
    ['settled', [], 'Your balance in Goa Trip. You are all settled up.'],
  ] as [string, Line[], string][])('%s', async (_n, lines, label) => {
    seedGoa(lines);
    await open();
    const card = screen.getByTestId('balance-card');
    expect(card.props.accessible).toBe(true);
    expect(card.props.accessibilityLabel).toBe(label);
    expect(screen.getByLabelText(label)).toBe(card);
    // the amount appears in the label exactly as the visible text, never twice in nested focus stops
    const nested = nodesOf(screen.toJSON()).filter(
      n => n.props?.testID === 'balance-card' || false,
    );
    expect(nested).toHaveLength(1);
  });

  it('focus order is card, Settle up, Balances; no link stop; buttons outside the card', async () => {
    seedGoa([INR_OWED]);
    await open();
    const card = screen.getByTestId('balance-card');
    expect(within(card).queryByRole('button')).toBeNull();
    expect(within(card).queryByRole('link')).toBeNull();
    const all = nodesOf(screen.toJSON());
    const textIn = (n: unknown): string => {
      if (typeof n === 'string') return n;
      const k = (n as { children?: unknown[] } | null)?.children;
      return Array.isArray(k) ? k.map(textIn).join('') : '';
    };
    const stops: string[] = [];
    for (const n of all) {
      const p = (n.props ?? {}) as Record<string, unknown>;
      if (p.accessible === false) continue;
      if (p.testID === 'balance-card') stops.push('card');
      else if (p.accessibilityRole === 'button' || p.role === 'button')
        stops.push(textIn(n));
    }
    expect(
      stops.filter(t => ['card', 'Settle up', 'Balances'].includes(t)),
    ).toEqual(['card', 'Settle up', 'Balances']);
    expect(
      all.filter(n => {
        const p = (n.props ?? {}) as Record<string, unknown>;
        return p.accessibilityRole === 'link' || p.role === 'link';
      }),
    ).toEqual([]);
    expect(
      stops.filter(t => ['card', 'Settle up', 'Balances'].includes(t)),
    ).toEqual(['card', 'Settle up', 'Balances']);
  });
});

describe('10. themes, contrast, font scale, width', () => {
  it.each([
    ['two currencies', [INR_OWED, USD_OWED]],
    ['mixed', [INR_OWED, USD_OWE]],
    ['settled', []],
  ] as [string, Line[]][])(
    '%s: both themes, tokens only',
    async (_n, lines) => {
      seedGoa(lines);
      const c = { light: newClient(), dark: newClient() };
      const r = await renderBothThemes((s: Scheme) => <Shell client={c[s]} />);
      await flush();
      for (const s of SCHEMES) {
        await r[s].findByTestId('balance-card');
        expect(resolvedColors(r[s]).size).toBeGreaterThan(0);
        expect(colorsOutsideScheme(r[s], s)).toEqual([]);
        expectTouchTargets(r[s]);
      }
    },
  );

  it.each(SCHEMES)(
    '%s: every text/icon pair on the card meets 4.5:1 (text) and 3:1 (icons) against surface',
    async scheme => {
      const lines = [INR_OWED, USD_OWE];
      seedGoa(lines);
      const r = await open(scheme);
      const c = colorSchemes[scheme];
      const card = r.getByTestId('balance-card');
      const bg = flattenStyle(card.props.style).backgroundColor as string;
      expect(bg).toBe(c.surface);
      const colorOf = (el: { props: Record<string, unknown> }) =>
        flattenStyle(el.props.style).color as string;
      const pairs: [string, string, number][] = [
        ['label', colorOf(r.getByText('Your balance')), 4.5],
        ['owed headline', colorOf(r.getByText('You are owed')), 4.5],
        ['owe headline', colorOf(r.getByText('You owe')), 4.5],
        ['owed amount', colorOf(r.getByText('INR 15,025.00')), 4.5],
        ['owe amount', colorOf(r.getByText('USD 45.00')), 4.5],
        [
          'owed icon',
          colorOf(
            within(r.getByTestId('balance-icon-INR', HIDDEN)).getByText(
              '↑',
              HIDDEN,
            ),
          ),
          3,
        ],
        [
          'owe icon',
          colorOf(
            within(r.getByTestId('balance-icon-USD', HIDDEN)).getByText(
              '↓',
              HIDDEN,
            ),
          ),
          3,
        ],
      ];
      for (const [name, fg, min] of pairs) {
        expect([name, contrast(fg, bg) >= min]).toEqual([name, true]);
      }
    },
  );

  it.each(SCHEMES)(
    '%s: settled card text and check icon contrast',
    async scheme => {
      seedGoa([]);
      const r = await open(scheme);
      const c = colorSchemes[scheme];
      const colorOf = (el: { props: Record<string, unknown> }) =>
        flattenStyle(el.props.style).color as string;
      expect(
        contrast(
          colorOf(r.getByText('You are all settled up in this group')),
          c.surface,
        ),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(
          colorOf(
            within(r.getByTestId('balance-settled-icon', HIDDEN)).getByText(
              '✓',
              HIDDEN,
            ),
          ),
          c.surface,
        ),
      ).toBeGreaterThanOrEqual(3);
    },
  );

  it('fontScale 2.0: amounts are present in full, not truncated, buttons stacked', async () => {
    seedGoa([INR_OWED, USD_OWED]);
    const r = await renderAtFontScale(<Shell client={newClient()} />, 2.0);
    try {
      await flush();
      await r.findByTestId('balance-card');
      for (const t of ['INR 15,025.00', 'USD 45.00']) {
        const el = r.getByText(t);
        expect(el.props.numberOfLines).toBeUndefined();
        expect(el.props.ellipsizeMode).toBeUndefined();
        expect(el.props.adjustsFontSizeToFit).toBeFalsy();
        expect(
          el.props.maxFontSizeMultiplier == null ||
            el.props.maxFontSizeMultiplier >= 2,
        ).toBe(true);
      }
      // no ancestor clips the card content
      const card = r.getByTestId('balance-card');
      const s = flattenStyle(card.props.style);
      expect(s.overflow).not.toBe('hidden');
      expect(s.height).toBeUndefined();
      expect(s.maxHeight).toBeUndefined();
      expect(r.getAllByText('You are owed')).toBeTruthy();
      expect(btn('Settle up')).toBeTruthy();
      expect(btn('Balances')).toBeTruthy();
    } finally {
      r.restore();
      await r.unmount();
    }
  });

  it('375dp width: card and action row have no fixed width wider than the screen', async () => {
    seedGoa([INR_OWED, USD_OWED]);
    const { Dimensions } = require('react-native');
    const real = Dimensions.get('window');
    const spy = jest
      .spyOn(Dimensions, 'get')
      .mockImplementation(() => ({ ...real, width: 375, height: 812 }));
    try {
      await open();
      const widths = nodesOf(screen.toJSON())
        .flatMap(n => [
          flattenStyle(n.props?.style).width,
          flattenStyle(n.props?.style).minWidth,
        ])
        .filter((w): w is number => typeof w === 'number');
      expect(widths.filter(w => w > 375 - 2 * spacing.lg)).toEqual([]);
      expect(screen.getByText('INR 15,025.00')).toBeTruthy();
    } finally {
      spy.mockRestore();
    }
  });
});
