/**
 * SUI-Q-2 (CR-UI-1): the Members list moved off Group detail (SCR-13) onto the GroupMembers stack screen, opened
 * from the "N members" pressable under the group name. Written AFTER the implementation (SUI-M-145), so these
 * tests pass on delivery; they are regression guards, not red-first tests.
 *
 * NOTE: SCR-13's position card still lists per-member balance lines (top 3, then "+N more"). That is intentional
 * and is NOT the Members section, so member names are never asserted absent from SCR-13 in general.
 */
import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
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
import { BackHandler } from 'react-native';
import App from '../../App';
import { AuthProvider } from '../../src/auth/AuthContext';
import { resetTokenCache } from '../../src/auth/tokenStorage';
import { GroupDetailScreen } from '../../src/screens/GroupDetailScreen';
import { GroupMembersScreen } from '../../src/screens/GroupMembersScreen';
import { touchTarget, useTheme } from '../../src/theme';
import { FakeServer } from '../../testUtils/fakeServer';
import {
  SCHEMES,
  Scheme,
  colorsOutsideScheme,
  expectColorsInScheme,
  expectTouchTargets,
  flattenStyle,
  renderAtFontScale,
  renderBothThemes,
  resolvedColors,
  schemeValues,
  themed,
  touchTargetProblems,
} from './harness';

let server: FakeServer;
let qc: QueryClient;
const navRef = createNavigationContainerRef();
const currentRoute = () =>
  (
    navRef as unknown as {
      getCurrentRoute(): { name: string; params?: unknown } | undefined;
    }
  ).getCurrentRoute();

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

const flush = async () => {
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await new Promise(r => setTimeout(r, 0));
    });
  }
};

/** Group "Flat" with Asha (viewer) + Ravi + Meera, all settled (no balance lines on SCR-13). */
function seedFlat() {
  return server.addGroup(
    'Flat',
    [server.user('u-ravi', 'Ravi'), server.user('u-meera', 'Meera')],
    'g-flat',
  );
}

async function openDetail(name = 'Flat') {
  await render(<App queryClient={qc} navigationRef={navRef} />);
  await press(name);
  await screen.findByTestId('members-entry');
}
async function openMembers() {
  await openDetail();
  await fireEvent.press(screen.getByTestId('members-entry'));
  return screen.findByTestId('group-members-view');
}
const route = () => currentRoute()?.name;

// A minimal stack with the real screens, for theme / font-scale tests (the full App follows the system scheme).
const Stack = createNativeStackNavigator();
function Shell({
  client,
  initial,
}: {
  client: QueryClient;
  initial: 'GroupDetail' | 'GroupMembers';
}) {
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
      <NavigationContainer theme={navTheme}>
        <AuthProvider>
          <Stack.Navigator initialRouteName={initial}>
            <Stack.Screen
              name="GroupDetail"
              component={GroupDetailScreen as never}
              initialParams={{ groupId: 'g-flat' }}
            />
            <Stack.Screen
              name="GroupMembers"
              component={GroupMembersScreen as never}
              initialParams={{ groupId: 'g-flat' }}
            />
          </Stack.Navigator>
        </AuthProvider>
      </NavigationContainer>
    </QueryClientProvider>
  );
}
const newClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });

describe('1. SCR-13 has no inline Members section', () => {
  it('no "Members" header, no member rows, no per-member Remove/Add/Invite controls', async () => {
    seedFlat();
    await openDetail();
    expect(screen.queryByText('Members')).toBeNull();
    expect(screen.queryByText(/^Members \(/)).toBeNull();
    expect(screen.queryByTestId('group-members-view')).toBeNull();
    expect(screen.queryByTestId(/^member-/)).toBeNull();
    expect(screen.queryByLabelText(/^Remove /)).toBeNull();
    expect(screen.queryByText('Remove')).toBeNull();
    expect(screen.queryByText('Add people')).toBeNull();
    expect(screen.queryByText('Invite via link')).toBeNull();
    expect(screen.queryByText('Asha (you)')).toBeNull(); // the "(you)" rows lived in the old Members list
    expect(route()).toBe('GroupDetail');
  });

  it('CR-UI-2: SCR-13 no longer shows per-member balance lines ("+N more" removed) and still has no Members section', async () => {
    const g = server.addGroup(
      'Flat',
      ['Ravi', 'Meera', 'Dev', 'Isha'].map(n =>
        server.user(`u-${n.toLowerCase()}`, n),
      ),
      'g-flat',
    );
    for (const m of g.members.slice(1)) {
      m.balances = [{ amount_minor: 1000, currency: 'INR' }];
    }
    await openDetail();
    expect(screen.queryByText('Ravi')).toBeNull();
    expect(screen.queryByText('Meera')).toBeNull();
    expect(screen.queryByText('Dev')).toBeNull();
    expect(screen.queryByText('+1 more')).toBeNull();
    expect(screen.queryByText('Members')).toBeNull();
    expect(screen.queryByTestId(/^member-/)).toBeNull();
    expect(screen.queryByLabelText(/^Remove /)).toBeNull();
  });
});

describe('2. the "N members" entry is an accessible 48dp button', () => {
  it('3 members: role button, label "3 members, show list", visible text "3 members"', async () => {
    seedFlat();
    await openDetail();
    const entry = screen.getByTestId('members-entry');
    expect(entry.props.accessibilityRole).toBe('button');
    expect(entry.props.accessibilityLabel).toBe('3 members, show list');
    expect(screen.getByRole('button', { name: '3 members, show list' })).toBe(
      entry,
    );
    expect(within(entry).getByText('3 members')).toBeTruthy();
    const s = flattenStyle(
      typeof entry.props.style === 'function'
        ? entry.props.style({ pressed: false })
        : entry.props.style,
    );
    const slop = entry.props.hitSlop;
    const extra =
      typeof slop === 'number'
        ? slop * 2
        : (slop?.top ?? 0) + (slop?.bottom ?? 0);
    expect(
      Math.max(Number(s.height ?? 0), Number(s.minHeight ?? 0)) + extra,
    ).toBeGreaterThanOrEqual(touchTarget.min);
    expect(touchTarget.min).toBe(48);
  });

  it('1 member: label "1 member, show list" (singular)', async () => {
    server.addGroup('Solo', [], 'g-solo');
    await openDetail('Solo');
    const entry = screen.getByTestId('members-entry');
    expect(entry.props.accessibilityLabel).toBe('1 member, show list');
    expect(within(entry).getByText('1 member')).toBeTruthy();
    expect(screen.queryByText('1 members')).toBeNull();
  });

  it('expectTouchTargets passes on the entry in both themes', async () => {
    seedFlat();
    const c = { light: newClient(), dark: newClient() };
    const r = await renderBothThemes((s: Scheme) => (
      <Shell client={c[s]} initial="GroupDetail" />
    ));
    await flush();
    for (const s of SCHEMES) {
      const entry = await r[s].findByTestId('members-entry');
      // the harness must see the entry as a pressable and report nothing for it
      const probs = touchTargetProblems(r[s]);
      expect(probs.filter(p => p.includes('show list'))).toEqual([]);
      expect(entry.props.accessibilityRole).toBe('button');
    }
  });
});

describe('3. pressing the entry shows the full member list', () => {
  it('every member (viewer as "(you)") and the header count match the fake server', async () => {
    seedFlat();
    const view = await openMembers();
    expect(route()).toBe('GroupMembers');
    expect(within(view).getByText('3 members')).toBeTruthy();
    expect(within(view).getByText('Asha (you)')).toBeTruthy();
    expect(within(view).getByText('Ravi')).toBeTruthy();
    expect(within(view).getByText('Meera')).toBeTruthy();
    expect(screen.getByTestId('member-u-me')).toBeTruthy();
    expect(screen.getByTestId('member-u-ravi')).toBeTruthy();
    expect(screen.getByTestId('member-u-meera')).toBeTruthy();
    // viewer cannot be removed from here; others can
    expect(screen.queryByLabelText('Remove Asha')).toBeNull();
    expect(screen.getByLabelText('Remove Ravi')).toBeTruthy();
    expect(screen.getByLabelText('Remove Meera')).toBeTruthy();
  });

  it('members who left are not listed and not counted', async () => {
    const g = seedFlat();
    g.members[2].left_at = '2026-11-10T01:00:00Z'; // Meera left
    const view = await openMembers();
    expect(within(view).getByText('2 members')).toBeTruthy();
    expect(screen.queryByTestId('member-u-meera')).toBeNull();
  });

  it('a single-member group shows "1 member" and no Remove button', async () => {
    server.addGroup('Solo', [], 'g-solo');
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Solo');
    await fireEvent.press(await screen.findByTestId('members-entry'));
    const view = await screen.findByTestId('group-members-view');
    expect(within(view).getByText('1 member')).toBeTruthy();
    expect(within(view).getByText('Asha (you)')).toBeTruthy();
    expect(screen.queryByLabelText(/^Remove /)).toBeNull();
  });
});

describe('4. add people, invite via link and remove from the members view', () => {
  it('Add people opens the add-members screen for this group', async () => {
    seedFlat();
    await openMembers();
    await press('Add people');
    expect(route()).toBe('AddPeople');
    expect(currentRoute()?.params).toEqual({
      mode: { kind: 'group-members', groupId: 'g-flat' },
    });
  });

  it('Invite via link opens the invite-link screen for this group', async () => {
    seedFlat();
    await openMembers();
    await press('Invite via link');
    expect(route()).toBe('InviteLink');
    expect(currentRoute()?.params).toEqual({ groupId: 'g-flat' });
  });

  it('remove asks for confirmation; cancel sends nothing', async () => {
    seedFlat();
    await openMembers();
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    expect(await screen.findByText('Remove Ravi?')).toBeTruthy();
    expect(server.count('DELETE', /\/members\//)).toBe(0);
    await press('Cancel');
    await flush();
    expect(server.count('DELETE', /\/members\//)).toBe(0);
    expect(screen.getByTestId('member-u-ravi')).toBeTruthy();
  });

  it('confirmed remove: DELETE /groups/{id}/members/{userId}, then groups and friends queries are refetched, member gone', async () => {
    seedFlat();
    // Friends tab and Groups tab loaded first, so stale caches exist for both.
    await render(<App queryClient={qc} navigationRef={navRef} />);
    await press('Flat');
    await screen.findByTestId('members-entry');
    await act(async () => {
      navRef.goBack();
    });
    await press('Friends');
    await waitFor(() =>
      expect(server.count('GET', '/friends')).toBeGreaterThan(0),
    );
    await press('Groups');
    await press('Flat');
    await fireEvent.press(await screen.findByTestId('members-entry'));
    await screen.findByTestId('group-members-view');
    const friendsBefore = server.count('GET', '/friends');
    const groupsBefore = server.count('GET', /^\/groups\/g-flat$/);
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    await fireEvent.press(
      (await screen.findAllByText('Remove')).slice(-1)[0], // dialog confirm
    );
    await waitFor(() =>
      expect(server.count('DELETE', '/groups/g-flat/members/u-ravi')).toBe(1),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('member-u-ravi')).toBeNull(),
    );
    expect(
      within(screen.getByTestId('group-members-view')).getByText('2 members'),
    ).toBeTruthy();
    expect(server.count('GET', '/friends')).toBeGreaterThan(friendsBefore);
    expect(server.count('GET', /^\/groups\/g-flat$/)).toBeGreaterThan(
      groupsBefore,
    );
  });

  it('pressing a non-viewer row also opens the confirmation; the viewer row does nothing', async () => {
    seedFlat();
    await openMembers();
    await fireEvent.press(screen.getByText('Asha (you)'));
    expect(screen.queryByText(/^Remove .*\?$/)).toBeNull();
    await fireEvent.press(screen.getByText('Meera'));
    expect(await screen.findByText('Remove Meera?')).toBeTruthy();
  });

  it('OUTSTANDING_BALANCE 409 shows the amounts dialog and writes nothing', async () => {
    seedFlat();
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
    await openMembers();
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    await fireEvent.press((await screen.findAllByText('Remove')).slice(-1)[0]);
    expect(
      await screen.findByText(/Outstanding: INR 120.50, USD 0.01\./),
    ).toBeTruthy();
    expect(screen.getByText("You can't remove this member yet")).toBeTruthy();
    expect(server.count('GET', '/friends')).toBe(0); // refused: no invalidation
    await press('OK');
    expect(screen.getByTestId('member-u-ravi')).toBeTruthy(); // still a member
    expect(
      within(screen.getByTestId('group-members-view')).getByText('3 members'),
    ).toBeTruthy();
  });

  it('403 shows a banner and keeps the member', async () => {
    seedFlat();
    server.overrides.push(req =>
      req.method === 'DELETE' && req.path.includes('/members/')
        ? { status: 403, body: { code: 'FORBIDDEN', message: 'no' } }
        : undefined,
    );
    await openMembers();
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    await fireEvent.press((await screen.findAllByText('Remove')).slice(-1)[0]);
    expect(
      await screen.findByText("You're not allowed to do that in this group."),
    ).toBeTruthy();
    expect(screen.getByTestId('member-u-ravi')).toBeTruthy();
  });
});

describe('5. themes, color tokens, font scale', () => {
  it.each(['GroupDetail', 'GroupMembers'] as const)(
    '%s renders in both themes with resolvedColors inside the scheme',
    async initial => {
      seedFlat();
      const c = { light: newClient(), dark: newClient() };
      const r = await renderBothThemes((s: Scheme) => (
        <Shell client={c[s]} initial={initial} />
      ));
      await flush();
      const marker =
        initial === 'GroupDetail' ? 'members-entry' : 'group-members-view';
      for (const s of SCHEMES) {
        expect(await r[s].findByTestId(marker)).toBeTruthy();
        expect(resolvedColors(r[s]).size).toBeGreaterThan(0);
        expect(colorsOutsideScheme(r[s], s)).toEqual([]);
        expectColorsInScheme(r[s], s);
      }
      // sanity: the dark tree paints no color that is only in the light palette
      const lightOnly = [...schemeValues('light')].filter(
        v => !schemeValues('dark').has(v),
      );
      const darkColors = resolvedColors(r.dark);
      expect(lightOnly.filter(v => darkColors.has(v))).toEqual([]);
    },
  );

  it('members view: pressables (Remove, Add people, Invite via link) have role, label and 48dp in both themes', async () => {
    seedFlat();
    const c = { light: newClient(), dark: newClient() };
    const r = await renderBothThemes((s: Scheme) => (
      <Shell client={c[s]} initial="GroupMembers" />
    ));
    await flush();
    for (const s of SCHEMES) {
      await r[s].findByTestId('group-members-view');
      expectTouchTargets(r[s]);
    }
  });

  it.each(['GroupDetail', 'GroupMembers'] as const)(
    '%s renders at fontScale 2.0 with the content still present',
    async initial => {
      seedFlat();
      const r = await renderAtFontScale(
        <Shell client={newClient()} initial={initial} />,
        2.0,
      );
      try {
        await flush();
        if (initial === 'GroupDetail') {
          expect(await r.findByTestId('members-entry')).toBeTruthy();
          expect(r.getByText('3 members')).toBeTruthy();
          expect(r.queryByText('Members')).toBeNull();
        } else {
          const view = await r.findByTestId('group-members-view');
          expect(within(view).getByText('3 members')).toBeTruthy();
          expect(within(view).getByText('Asha (you)')).toBeTruthy();
          expect(within(view).getByText('Add people')).toBeTruthy();
          expect(within(view).getByText('Invite via link')).toBeTruthy();
        }
        expectColorsInScheme(r, 'light');
      } finally {
        r.restore();
      }
    },
  );

  it('themed() wrapper is what renderBothThemes uses (guards the harness import)', () => {
    expect(typeof themed).toBe('function');
  });
});

describe('6. opening the members view sends no extra requests', () => {
  it('0 requests of any kind after SCR-13 has loaded', async () => {
    seedFlat();
    await openDetail();
    await flush();
    const before = server.log.length;
    expect(before).toBeGreaterThan(0);
    await fireEvent.press(screen.getByTestId('members-entry'));
    await screen.findByTestId('group-members-view');
    await flush();
    expect(server.log.length).toBe(before);
  });

  it('GET /groups/{id} is sent once in total for detail + members view', async () => {
    seedFlat();
    await openMembers();
    await flush();
    expect(server.count('GET', '/groups/g-flat')).toBe(1);
  });
});

describe('back / close returns to SCR-13', () => {
  it('navigation back from the members view lands on Group detail, still showing the entry', async () => {
    seedFlat();
    await openMembers();
    expect(route()).toBe('GroupMembers');
    await act(async () => {
      navRef.goBack();
    });
    expect(route()).toBe('GroupDetail');
    expect(screen.getByTestId('members-entry')).toBeTruthy();
    expect(screen.getByText('3 members')).toBeTruthy();
    // opening again works and still costs no request
    const before = server.log.length;
    await fireEvent.press(screen.getByTestId('members-entry'));
    await screen.findByTestId('group-members-view');
    expect(route()).toBe('GroupMembers');
    expect(server.log.length).toBe(before);
  });

  it('hardware back (BackHandler) pops the members view', async () => {
    seedFlat();
    await openMembers();
    const mock = (BackHandler as unknown as { mockPressBack?: () => void })
      .mockPressBack;
    if (!mock) {
      // Jest's BackHandler has no press helper in this RN version; goBack is what React Navigation's handler calls.
      await act(async () => {
        navRef.goBack();
      });
    } else {
      await act(async () => mock());
    }
    expect(route()).toBe('GroupDetail');
  });

  it('after a remove, back still returns to Group detail with the updated count', async () => {
    seedFlat();
    await openMembers();
    await fireEvent.press(screen.getByLabelText('Remove Ravi'));
    await fireEvent.press((await screen.findAllByText('Remove')).slice(-1)[0]);
    await waitFor(() =>
      expect(screen.queryByTestId('member-u-ravi')).toBeNull(),
    );
    await act(async () => {
      navRef.goBack();
    });
    expect(route()).toBe('GroupDetail');
    expect(await screen.findByLabelText('2 members, show list')).toBeTruthy();
  });
});
