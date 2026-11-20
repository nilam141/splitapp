/**
 * SUI-Q-1 dark-mode smoke test. Every file in src/screens is mounted under ThemeProvider mode="dark" with the
 * fake server. Per screen it asserts: renders without throwing, produces a tree, and (a defect check) no color
 * that exists only in the light palette is painted in the dark tree.
 *
 * The screen list is read from src/screens, and each file must have a params entry below, so a new screen cannot
 * be added without being smoke-tested. This is a component test against FakeServer, not an emulator run.
 */
import fs from 'fs';
import path from 'path';
import React from 'react';
import { act, render } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { DarkTheme, NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthProvider } from '../../src/auth/AuthContext';
import { resetTokenCache } from '../../src/auth/tokenStorage';
import { ThemeProvider, darkColors } from '../../src/theme';
import { FakeServer } from '../../testUtils/fakeServer';
import { colorsOutsideScheme, schemeValues } from './harness';

const SCREENS_DIR = path.resolve(__dirname, '../../src/screens');
const files = fs
  .readdirSync(SCREENS_DIR)
  .filter(f => /Screen\.tsx$/.test(f))
  .map(f => f.replace(/\.tsx$/, ''))
  .sort();

/** initialParams per screen (the ids match the data seeded in beforeEach). Screens not listed take none. */
const PARAMS: Record<string, object | undefined> = {
  AccountScreen: undefined,
  ActivityScreen: undefined,
  AddFriendByCodeScreen: { code: 'K7Q2M9XP' },
  AddPeopleScreen: { mode: { kind: 'friend' } },
  CreateGroupScreen: undefined,
  ExpenseDetailScreen: { expenseId: 'x-seed' },
  ExpenseFormScreen: { groupId: 'g-seed' },
  ExportSheetScreen: { groupId: 'g-seed' },
  FriendDetailScreen: { friendId: 'f-seed' },
  FriendSettingsScreen: { friendId: 'f-seed' },
  FriendsScreen: undefined,
  GroupBalancesScreen: { groupId: 'g-seed' },
  GroupDetailScreen: { groupId: 'g-seed' },
  GroupSettingsScreen: { groupId: 'g-seed' },
  GroupsScreen: undefined,
  InviteLinkScreen: { groupId: 'g-seed' },
  JoinGroupScreen: { token: '9QX2KD7MZP' },
  LaunchScreen: undefined,
  LogInScreen: undefined,
  MyCodeScreen: undefined,
  NotificationSettingsScreen: undefined,
  PasswordResetScreen: { token: 'pr_3b9d0c6a8f' },
  PaymentDetailScreen: { settlementId: 's-seed' },
  PaywallScreen: undefined,
  PlaceholderScreen: { title: 'Activity' },
  RemindScreen: {
    toUserId: 'f-seed',
    toName: 'Ravi',
    amountMinor: 12050,
    currency: 'INR',
  },
  RecordPaymentScreen: { groupId: 'g-seed' },
  SearchScreen: undefined,
  SessionExpiredScreen: { email: 'asha@example.com' },
  SettleUpScreen: { groupId: 'g-seed' },
  SignUpScreen: undefined,
  SimplifyExplainerScreen: { groupId: 'g-seed' },
  WelcomeScreen: undefined,
};

let server: FakeServer;
let qc: QueryClient;

beforeEach(async () => {
  server = new FakeServer();
  server.seedTokens();
  server.install();
  server.addFriendRow('f-seed', 'Ravi', [
    { amount_minor: 12050, currency: 'INR' },
  ]);
  const g = server.addGroup('Flat', [server.user('f-seed', 'Ravi')], 'g-seed');
  server.addExpense({
    id: 'x-seed',
    group_id: g.id,
    description: 'Groceries',
    splits: [
      { user_id: 'u-me', owed_amount_minor: 5000 },
      { user_id: 'f-seed', owed_amount_minor: 5000 },
    ],
  });
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

const Stack = createNativeStackNavigator();

async function renderDark(name: string) {
  const mod = require(`../../src/screens/${name}`);
  const Component = mod[name];
  if (typeof Component !== 'function') {
    throw new Error(`src/screens/${name}.tsx does not export ${name}`);
  }
  const navTheme = {
    ...DarkTheme,
    colors: {
      ...DarkTheme.colors,
      background: darkColors.background,
      card: darkColors.surface,
      text: darkColors.textPrimary,
      border: darkColors.border,
      primary: darkColors.brand,
    },
  };
  const view = await render(
    <ThemeProvider mode="dark">
      <SafeAreaProvider
        initialMetrics={{
          frame: { x: 0, y: 0, width: 360, height: 800 },
          insets: { top: 0, left: 0, right: 0, bottom: 0 },
        }}
      >
        <QueryClientProvider client={qc}>
          <NavigationContainer theme={navTheme}>
            <AuthProvider>
              <Stack.Navigator>
                <Stack.Screen
                  name="Screen"
                  component={Component}
                  initialParams={PARAMS[name]}
                />
              </Stack.Navigator>
            </AuthProvider>
          </NavigationContainer>
        </QueryClientProvider>
      </SafeAreaProvider>
    </ThemeProvider>,
  );
  // let the auth restore and the fake-server queries resolve
  for (let i = 0; i < 4; i++) {
    await act(async () => {
      await new Promise(r => setTimeout(r, 0));
    });
  }
  return view;
}

describe('dark smoke: every screen in src/screens', () => {
  it('lists the screens and has params for each', () => {
    expect(files.length).toBeGreaterThanOrEqual(19);
    expect(files.filter(f => !(f in PARAMS))).toEqual([]);
    expect(Object.keys(PARAMS).filter(k => !files.includes(k))).toEqual([]);
  });

  it.each(files)('%s renders under dark mode', async name => {
    const view = await renderDark(name);
    expect(view.toJSON()).toBeTruthy();
    if (process.env.SMOKE_DEBUG) {
      console.log(
        name,
        JSON.stringify(view.toJSON())
          .match(/"children":\["[^"]{2,40}"\]/g)
          ?.slice(0, 6),
        [...require('./harness').resolvedColors(view)],
      );
    }
    // Defect check: a light-only palette value must never be painted in the dark tree.
    const dark = schemeValues('dark');
    const lightOnly = colorsOutsideScheme(view, 'dark').filter(
      c => !dark.has(c),
    );
    const lightPalette = schemeValues('light');
    expect(lightOnly.filter(c => lightPalette.has(c))).toEqual([]);
    view.unmount();
  });
});
