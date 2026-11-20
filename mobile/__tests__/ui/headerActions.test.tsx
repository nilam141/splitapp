/**
 * QA: header actions (Button in headerRight) must be visually smaller than the 56dp header bar while keeping a
 * 48dp touch target, a role and a label. Found after SUI-M-01 made Button 52dp: Button has no compact size, so
 * the Group detail "Settings", Friend detail "Settings" and Expense detail "Edit" actions nearly fill the bar.
 * Sites: GroupDetailScreen.tsx:98, FriendDetailScreen.tsx:84, ExpenseDetailScreen.tsx:85.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { QueryClient } from '@tanstack/react-query';
import App from '../../App';
import { resetTokenCache } from '../../src/auth/tokenStorage';
import { layout, touchTarget } from '../../src/theme';
import { FakeServer } from '../../testUtils/fakeServer';
import { flattenStyle } from './harness';

let server: FakeServer;
let qc: QueryClient;

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

/** The pressable (role button) whose label or text is `name`, with its declared height and hitSlop. */
async function headerAction(name: string) {
  const el = await screen.findByRole('button', { name });
  const props = el.props as Record<string, unknown>;
  const style = flattenStyle(
    typeof props.style === 'function'
      ? (props.style as (s: { pressed: boolean }) => unknown)({
          pressed: false,
        })
      : props.style,
  );
  const hit = (props.hitSlop ?? {}) as Record<string, number>;
  const slop =
    typeof props.hitSlop === 'number'
      ? props.hitSlop * 2
      : (hit.top ?? 0) + (hit.bottom ?? 0);
  const height = Number(style.height ?? 0);
  const minHeight = Number(style.minHeight ?? 0);
  return { props, height, minHeight, slop };
}

function expectCompactButTappable(a: Awaited<ReturnType<typeof headerAction>>) {
  expect(a.props.accessibilityRole).toBe('button');
  const visual = a.height || a.minHeight;
  // visibly smaller than the header bar, with margin: at most the 48dp touch minimum
  expect(visual).toBeGreaterThan(0);
  expect(visual).toBeLessThan(layout.headerHeight);
  expect(visual).toBeLessThanOrEqual(touchTarget.min);
  // still a 48dp target: from its own height/minHeight or from hitSlop
  expect(Math.max(a.height, a.minHeight) + a.slop).toBeGreaterThanOrEqual(
    touchTarget.min,
  );
}

describe('header actions are compact (smaller than the header) but keep a 48dp target', () => {
  it('Group detail header "Settings"', async () => {
    server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    expectCompactButTappable(await headerAction('Settings'));
  });

  it('Friend detail header "Settings"', async () => {
    server.addFriendRow('f1', 'Ravi', [
      { amount_minor: 12050, currency: 'INR' },
    ]);
    await render(<App queryClient={qc} />);
    await press('Friends');
    await press('Ravi');
    expectCompactButTappable(await headerAction('Settings'));
  });

  it('Expense detail header "Edit"', async () => {
    const g = server.addGroup('Flat', [server.user('u-ravi', 'Ravi')]);
    server.addExpense({
      description: 'Dinner',
      group_id: g.id,
      splits: [
        { user_id: server.me.id, owed_amount_minor: 5000, input_value: null },
        { user_id: 'u-ravi', owed_amount_minor: 5000, input_value: null },
      ],
    });
    await render(<App queryClient={qc} />);
    await press('Groups');
    await press('Flat');
    await press('Dinner');
    expectCompactButTappable(await headerAction('Edit'));
  });
});
