/**
 * SUI-Q-1 (5): failing tests for every component in SUI-M-01..06 (design_system.md section 6).
 *
 * Written before the components exist. Modules are loaded lazily with `load()` so each test fails on its own with
 * "Cannot find module ..." (or on the missing prop/behaviour once the module exists) and a half-finished task only
 * turns its own tests green.
 *
 * Contract used here (the Mobile agent may rename a testID or prop only by editing the test in the same change and
 * listing it in the handoff note). Where design_system.md does not fix a name, the choice is marked ASSUMED.
 *
 * New modules (ASSUMED paths): src/components/{MoneyField,Card,ListRow,SectionHeader,Avatar,BalanceChip,Skeleton,
 * useLoadingPhase,FilterChip,Fab}. ErrorBanner/OfflineBanner/EmptyView live in src/components/StateViews.
 *
 * Not tested: the icon set (OQ-46 is still open); the 4 slice4Balances snapshots (SUI-M-04 updates them and lists
 * each diff); row snapshots at font scale 1.0/2.0 are asserted structurally (wrap before ellipsize) instead.
 */
import React from 'react';
import { AccessibilityInfo } from 'react-native';
import {
  act,
  fireEvent,
  render,
  renderHook,
  RenderResult,
} from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  colorSchemes,
  control,
  layout,
  maxFontScale,
  radius,
  spacing,
  ThemeProvider,
  typography,
} from '../../src/theme';
import { FakeServer } from '../../testUtils/fakeServer';
import {
  expectColorsInScheme,
  expectTouchTargets,
  flattenStyle,
  renderAtFontScale,
  eachTheme,
  pressIn,
  renderBothThemes,
  resolvedColors,
  SCHEMES,
  Scheme,
  textOf,
  themed,
} from './harness';

type Any = any;
const load = (p: string): Any => require(`../../src/${p}`);

const noop = () => {};
const styleOf = (el: Any) => flattenStyle(el.props.style);
const C = (s: Scheme) => colorSchemes[s];

let server: FakeServer;
let qc: QueryClient;
beforeEach(() => {
  server = new FakeServer();
  server.seedTokens();
  server.install();
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
});
afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
});

/** Both themes, with a QueryClient for components that read /currencies. */
const both = (ui: React.ReactElement) =>
  renderBothThemes(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);

// ======================================================================================================== M-01
describe('SUI-M-01 Text', () => {
  const names = Object.keys(typography) as (keyof typeof typography)[];
  it('has all 11 variants', () => expect(names).toHaveLength(11));

  it.each(names)(
    'variant %s applies the typography token in both themes',
    async v => {
      const { Text } = load('components/Text');
      const r = await both(<Text variant={v}>hello</Text>);
      for (const s of SCHEMES) {
        const st = styleOf(r[s].getByText('hello'));
        expect(st.fontSize).toBe(typography[v].fontSize);
        expect(st.lineHeight).toBe(typography[v].lineHeight);
        expect(st.fontWeight).toBe(typography[v].fontWeight);
        expect(st.color).toBe(C(s).textPrimary);
      }
    },
  );

  it('defaults to body', async () => {
    const { Text } = load('components/Text');
    const { getByText } = await render(themed(<Text>hi</Text>, 'light'));
    expect(styleOf(getByText('hi')).fontSize).toBe(typography.body.fontSize);
    expect(styleOf(getByText('hi')).fontWeight).toBe(
      typography.body.fontWeight,
    );
  });
});

describe('SUI-M-01 Button', () => {
  const press = pressIn;
  const btn = (r: RenderResult, name: string) =>
    r.getByRole('button', { name });

  it.each([
    ['primary', 'brand', 'textOnBrand'],
    ['secondary', 'fieldBackground', 'textPrimary'],
  ] as const)(
    '%s: fill and label tokens in both themes',
    async (variant, fill, label) => {
      const { Button } = load('components/Button');
      const r = await both(
        <Button title="Go" variant={variant} onPress={noop} />,
      );
      for (const s of SCHEMES) {
        expect(styleOf(btn(r[s], 'Go')).backgroundColor).toBe(C(s)[fill]);
        expect(styleOf(r[s].getByText('Go')).color).toBe(C(s)[label]);
        expectColorsInScheme(r[s], s);
      }
    },
  );

  it('outlined: transparent fill, 1dp borderStrong, textPrimary label', async () => {
    const { Button } = load('components/Button');
    const r = await both(
      <Button title="Go" variant="outlined" onPress={noop} />,
    );
    for (const s of SCHEMES) {
      const st = styleOf(btn(r[s], 'Go'));
      expect(st.backgroundColor ?? 'transparent').toBe('transparent');
      expect(st.borderWidth).toBe(1);
      expect(st.borderColor).toBe(C(s).borderStrong);
      expect(styleOf(r[s].getByText('Go')).color).toBe(C(s).textPrimary);
    }
  });

  it('destructive: outlined in error, errorText label, never filled red', async () => {
    const { Button } = load('components/Button');
    const r = await both(
      <Button title="Delete" variant="destructive" onPress={noop} />,
    );
    for (const s of SCHEMES) {
      const st = styleOf(btn(r[s], 'Delete'));
      expect(st.backgroundColor ?? 'transparent').toBe('transparent');
      expect(st.borderWidth).toBe(1);
      expect(st.borderColor).toBe(C(s).error);
      expect(styleOf(r[s].getByText('Delete')).color).toBe(C(s).errorText);
    }
  });

  it('pressed primary uses brandPressed (both themes)', async () => {
    const { Button } = load('components/Button');
    // one mount per theme: a Pressable cannot be pressed after a second tree is mounted in the same test
    for (const s of SCHEMES) {
      const r = await render(themed(<Button title="Go" onPress={noop} />, s));
      await press(btn(r, 'Go'));
      expect(styleOf(btn(r, 'Go')).backgroundColor).toBe(C(s).brandPressed);
      await r.unmount();
    }
  });

  it('disabled: fieldBackground fill, textDisabled label, no press, accessibilityState.disabled', async () => {
    const { Button } = load('components/Button');
    const onPress = jest.fn();
    const r = await both(<Button title="Go" disabled onPress={onPress} />);
    for (const s of SCHEMES) {
      const b = btn(r[s], 'Go');
      expect(styleOf(b).backgroundColor).toBe(C(s).fieldBackground);
      expect(styleOf(r[s].getByText('Go')).color).toBe(C(s).textDisabled);
      expect(b.props.accessibilityState).toMatchObject({ disabled: true });
      await fireEvent.press(b);
    }
    expect(onPress).not.toHaveBeenCalled();
  });

  it('loading: spinner replaces the label, disabled, busy, announced, no press', async () => {
    const { Button } = load('components/Button');
    const onPress = jest.fn();
    const r = await both(<Button title="Save" loading onPress={onPress} />);
    for (const s of SCHEMES) {
      const b = r[s].getByRole('button', { name: /save|loading/i });
      expect(b.props.accessibilityState).toMatchObject({
        busy: true,
        disabled: true,
      });
      expect(r[s].queryByText('Save')).toBeNull();
      expect(r[s].queryByRole('progressbar')).not.toBeNull();
      expect(String(b.props.accessibilityLabel ?? '')).toMatch(/loading/i);
      await fireEvent.press(b);
    }
    expect(onPress).not.toHaveBeenCalled();
  });

  it('loading keeps the measured width', async () => {
    const { Button } = load('components/Button');
    const ui = (loading: boolean) =>
      themed(
        <Button title="Save changes" loading={loading} onPress={noop} />,
        'light',
      );
    const r = await render(ui(false));
    await fireEvent(r.getByRole('button'), 'layout', {
      nativeEvent: { layout: { x: 0, y: 0, width: 180, height: 52 } },
    });
    await r.rerender(ui(true));
    const st = styleOf(r.getByRole('button'));
    expect(st.width ?? st.minWidth).toBe(180);
  });

  it('height is 52 and fullWidth stretches', async () => {
    const { Button } = load('components/Button');
    const { getByRole } = await render(
      themed(<Button title="Go" fullWidth onPress={noop} />, 'light'),
    );
    const st = styleOf(getByRole('button'));
    expect(st.height ?? st.minHeight).toBe(52);
    expect(st.alignSelf === 'stretch' || st.width === '100%').toBe(true);
  });

  it('focus shows the focusRing color (absent before focus)', async () => {
    const { Button } = load('components/Button');
    await eachTheme(
      <Button title="Go" variant="outlined" onPress={noop} />,
      async (r, s) => {
        expect(resolvedColors(r).has(C(s).focusRing)).toBe(false);
        await fireEvent(btn(r, 'Go'), 'focus');
        expect(resolvedColors(r).has(C(s).focusRing)).toBe(true);
      },
    );
  });

  it('label caps font scaling at maxFontScale.fixedControl', async () => {
    const { Button } = load('components/Button');
    const { getByText } = await render(
      themed(<Button title="Go" onPress={noop} />, 'light'),
    );
    expect(getByText('Go').props.maxFontSizeMultiplier).toBe(
      maxFontScale.fixedControl,
    );
  });

  it('touch targets', async () => {
    const { Button } = load('components/Button');
    expectTouchTargets(
      await render(themed(<Button title="Go" onPress={noop} />, 'light')),
    );
  });
});

describe('SUI-M-01 Switch', () => {
  it('has a 48dp target, a role and colors from the scheme', async () => {
    const { Switch } = load('components/Switch');
    const r = await both(
      <Switch value onValueChange={noop} accessibilityLabel="Simplify" />,
    );
    for (const s of SCHEMES) {
      const sw = r[s].getByRole('switch', { name: 'Simplify' });
      const st = styleOf(sw);
      const slop = sw.props.hitSlop;
      const h =
        Math.max(Number(st.minHeight ?? 0), Number(st.height ?? 0)) +
        (typeof slop === 'number'
          ? 2 * slop
          : (slop?.top ?? 0) + (slop?.bottom ?? 0));
      expect(h).toBeGreaterThanOrEqual(48);
      expectColorsInScheme(r[s], s);
    }
  });

  it('shows a focus ring when focused', async () => {
    const { Switch } = load('components/Switch');
    await eachTheme(
      <Switch
        value={false}
        onValueChange={noop}
        accessibilityLabel="Simplify"
      />,
      async (r, s) => {
        // ASSUMED testID: the ring is a node (testID "focus-ring") that exists only while focused
        expect(r.queryByTestId('focus-ring')).toBeNull();
        await fireEvent(r.getByRole('switch'), 'focus');
        const ring = r.getByTestId('focus-ring');
        expect(styleOf(ring).borderColor).toBe(C(s).focusRing);
      },
    );
  });
});

// ======================================================================================================== M-02
describe('SUI-M-02 FormField', () => {
  const field = (r: RenderResult) => r.getByLabelText('Email');

  it('label above, 56dp field, borderStrong 1dp outline, token colors', async () => {
    const { FormField } = load('components/FormField');
    const r = await both(
      <FormField label="Email" value="" onChangeText={noop} />,
    );
    for (const s of SCHEMES) {
      const st = styleOf(field(r[s]));
      expect(st.height ?? st.minHeight).toBe(56);
      expect(st.borderColor).toBe(C(s).borderStrong);
      expect(st.borderWidth).toBe(1);
      expect(st.backgroundColor).toBe(C(s).fieldBackground);
      expect(st.borderRadius).toBe(radius.md);
      expect(r[s].getByText('Email')).toBeTruthy(); // visible label, not only a placeholder
      expectColorsInScheme(r[s], s);
    }
  });

  it('focus: 2dp brand outline, back to 1dp borderStrong on blur', async () => {
    const { FormField } = load('components/FormField');
    await eachTheme(
      <FormField label="Email" value="" onChangeText={noop} />,
      async (r, s) => {
        await fireEvent(field(r), 'focus');
        expect(styleOf(field(r)).borderColor).toBe(C(s).brand);
        expect(styleOf(field(r)).borderWidth).toBe(2);
        await fireEvent(field(r), 'blur');
        expect(styleOf(field(r)).borderColor).toBe(C(s).borderStrong);
      },
    );
  });

  it('error: 2dp error outline, icon, errorText message in a live region, same slot as helper text', async () => {
    const { FormField } = load('components/FormField');
    const msg = 'Password must be at least 8 characters';
    const r = await both(
      <FormField
        label="Email"
        value=""
        onChangeText={noop}
        helper="We never share it"
        error={msg}
      />,
    );
    for (const s of SCHEMES) {
      const st = styleOf(field(r[s]));
      expect(st.borderColor).toBe(C(s).error);
      expect(st.borderWidth).toBe(2);
      expect(r[s].getByTestId('field-error-icon')).toBeTruthy();
      const m = r[s].getByText(msg);
      expect(styleOf(m).color).toBe(C(s).errorText);
      const slot = r[s].getByTestId('field-message');
      expect(textOf(r[s].toJSON() as Any)).toContain(msg);
      expect(slot.props.accessibilityLiveRegion).toMatch(/polite|assertive/);
      // helper and error share one slot: the helper text is replaced by the error
      expect(r[s].queryByText('We never share it')).toBeNull();
    }
  });

  it('helper text shows in the same slot when there is no error', async () => {
    const { FormField } = load('components/FormField');
    const { getByText, getByTestId } = await render(
      themed(
        <FormField
          label="Email"
          value=""
          onChangeText={noop}
          helper="We never share it"
        />,
        'light',
      ),
    );
    expect(getByText('We never share it')).toBeTruthy();
    expect(getByTestId('field-message')).toBeTruthy();
  });

  it('disabled uses textDisabled', async () => {
    const { FormField } = load('components/FormField');
    const r = await both(
      <FormField
        label="Email"
        value="a"
        editable={false}
        onChangeText={noop}
      />,
    );
    for (const s of SCHEMES) {
      expect(styleOf(field(r[s])).color).toBe(C(s).textDisabled);
    }
  });

  it('SUI-M-02 (a): input caps font scaling at maxFontScale.fixedControl by default, both themes', async () => {
    const { FormField } = load('components/FormField');
    const r = await both(
      <FormField label="Email" value="" onChangeText={noop} />,
    );
    for (const s of SCHEMES) {
      expect(field(r[s]).props.maxFontSizeMultiplier).toBe(
        maxFontScale.fixedControl,
      );
    }
  });

  it('SUI-M-02 (b): multiline uses minHeight (control.fieldHeight), not a fixed height', async () => {
    const { FormField } = load('components/FormField');
    const r = await both(
      <FormField label="Email" value="" multiline onChangeText={noop} />,
    );
    for (const s of SCHEMES) {
      const st = styleOf(field(r[s]));
      expect(st.minHeight).toBe(control.fieldHeight);
      expect(st.height).toBeUndefined();
    }
  });

  it('password: "Show password" 48dp toggle flips secureTextEntry', async () => {
    const { FormField } = load('components/FormField');
    await eachTheme(
      <FormField label="Email" value="x" secureTextEntry onChangeText={noop} />,
      async r => {
        expect(field(r).props.secureTextEntry).toBe(true);
        const toggle = r.getByRole('button', { name: 'Show password' });
        const st = styleOf(toggle);
        expect(
          Math.max(Number(st.minHeight ?? 0), Number(st.height ?? 0)),
        ).toBeGreaterThanOrEqual(48);
        await fireEvent.press(toggle);
        expect(field(r).props.secureTextEntry).toBe(false);
        expect(r.getByRole('button', { name: 'Hide password' })).toBeTruthy();
      },
    );
  });
});

describe('SUI-M-02 MoneyField', () => {
  const mount = async (
    currency: string,
    exponent: number,
    onChangeMinor = jest.fn(),
  ) => {
    const { MoneyField } = load('components/MoneyField');
    const r = await both(
      <MoneyField
        label="Amount"
        currency={currency}
        exponent={exponent}
        onChangeMinor={onChangeMinor}
      />,
    );
    return { r, onChangeMinor };
  };
  const input = (r: RenderResult) => r.getByLabelText('Amount');

  it('shows the fixed currency code chip, amountLarge, right-aligned, in both themes', async () => {
    const { r } = await mount('INR', 2);
    for (const s of SCHEMES) {
      expect(r[s].getByText('INR')).toBeTruthy();
      const st = styleOf(input(r[s]));
      expect(st.textAlign).toBe('right');
      expect(st.fontSize).toBe(typography.amountLarge.fontSize);
      expectColorsInScheme(r[s], s);
    }
  });

  it('emits integer minor units: 12.34 INR -> 1234', async () => {
    const { r, onChangeMinor } = await mount('INR', 2);
    await fireEvent.changeText(input(r.dark), '12.34');
    expect(onChangeMinor).toHaveBeenLastCalledWith(1234);
    for (const [arg] of onChangeMinor.mock.calls) {
      expect(arg === null || Number.isInteger(arg)).toBe(true);
    }
  });

  it('rejects a 3rd decimal for INR (value and emission unchanged)', async () => {
    const { r, onChangeMinor } = await mount('INR', 2);
    await fireEvent.changeText(input(r.dark), '12.34');
    await fireEvent.changeText(input(r.dark), '12.345');
    expect(input(r.dark).props.value).toBe('12.34');
    expect(onChangeMinor).toHaveBeenLastCalledWith(1234);
  });

  it('SUI-M-02 (c): initialMinor 1234 INR shows "12.34"; omitted shows an empty field', async () => {
    const { MoneyField } = load('components/MoneyField');
    const withInit = await both(
      <MoneyField
        label="Amount"
        currency="INR"
        exponent={2}
        initialMinor={1234}
        onChangeMinor={noop}
      />,
    );
    const without = await both(
      <MoneyField
        label="Amount"
        currency="INR"
        exponent={2}
        onChangeMinor={noop}
      />,
    );
    for (const s of SCHEMES) {
      expect(input(withInit[s]).props.value).toBe('12.34');
      expect(input(without[s]).props.value).toBe('');
    }
  });

  it('rejects any decimal for JPY', async () => {
    const { r, onChangeMinor } = await mount('JPY', 0);
    await fireEvent.changeText(input(r.dark), '5');
    await fireEvent.changeText(input(r.dark), '5.5');
    expect(String(input(r.dark).props.value)).not.toContain('.');
    expect(onChangeMinor).toHaveBeenLastCalledWith(5);
  });
});

// ======================================================================================================== M-03
describe('SUI-M-03 Card', () => {
  it('surface, radius.lg, 16dp padding; border only in dark', async () => {
    const { Card } = load('components/Card');
    const r = await both(
      <Card testID="card">
        <></>
      </Card>,
    );
    for (const s of SCHEMES) {
      const st = styleOf(r[s].getByTestId('card'));
      expect(st.backgroundColor).toBe(C(s).surface);
      expect(st.borderRadius).toBe(radius.lg);
      expect(st.padding).toBe(spacing.lg);
    }
    const light = styleOf(r.light.getByTestId('card'));
    const dark = styleOf(r.dark.getByTestId('card'));
    expect(light.borderWidth ?? 0).toBe(0);
    expect(dark.borderWidth).toBe(1);
    expect(dark.borderColor).toBe(colorSchemes.dark.border);
    expect(light.elevation).toBeGreaterThan(0); // elevation 1 in light
  });
});

describe('SUI-M-03 ListRow', () => {
  const mount = async (props: object) => {
    const { ListRow } = load('components/ListRow');
    return both(
      <ListRow
        title="Flat"
        subtitle="Ravi paid"
        amount="INR 500.00"
        caption="owed"
        onPress={noop}
        {...props}
      />,
    );
  };

  it('min height 64, one pressable reading the whole row, token colors', async () => {
    const r = await mount({});
    for (const s of SCHEMES) {
      const el = r[s].getByRole('button');
      expect(styleOf(el).minHeight).toBeGreaterThanOrEqual(
        layout.listRowMinHeight,
      );
      const label = String(el.props.accessibilityLabel);
      for (const part of ['Flat', 'Ravi paid', 'INR 500.00']) {
        expect(label).toContain(part);
      }
      expect(label).not.toMatch(/unread/i);
      expectTouchTargets(r[s]);
      expectColorsInScheme(r[s], s);
    }
  });

  it('unread: bold title, 8dp dot hidden from TalkBack, "unread" in the label', async () => {
    const r = await mount({ unread: true });
    for (const s of SCHEMES) {
      expect(String(r[s].getByRole('button').props.accessibilityLabel)).toMatch(
        /unread/i,
      );
      expect(styleOf(r[s].getByText('Flat')).fontWeight).toBe('700');
      const dot = r[s].getByTestId('unread-dot');
      expect(styleOf(dot).width).toBe(8);
      expect(styleOf(dot).backgroundColor).toBe(C(s).brand);
      expect(
        dot.props.importantForAccessibility === 'no' ||
          dot.props.accessibilityElementsHidden === true,
      ).toBe(true);
    }
  });

  it('at font scale 2.0 the amount wraps (no ellipsize) while the title stays one line', async () => {
    const { ListRow } = load('components/ListRow');
    const r = await renderAtFontScale(
      <ListRow
        title="Flat"
        subtitle="Ravi paid"
        amount="INR 500.00"
        onPress={noop}
      />,
      2.0,
    );
    expect(r.getByText('INR 500.00').props.numberOfLines).toBeUndefined();
    expect(r.getByText('Flat').props.numberOfLines).toBe(1);
    r.restore();
  });
});

describe('SUI-M-03 SectionHeader', () => {
  it('caption variant, 32dp, header role', async () => {
    const { SectionHeader } = load('components/SectionHeader');
    const r = await both(<SectionHeader title="Recent" />);
    for (const s of SCHEMES) {
      const h = r[s].getByRole('header');
      expect(styleOf(h).minHeight ?? styleOf(h).height).toBe(32);
      const t = styleOf(r[s].getByText('Recent'));
      expect(t.fontSize).toBe(typography.caption.fontSize);
      expect(t.color).toBe(C(s).textSecondary);
    }
  });
});

describe('SUI-M-03 Avatar', () => {
  it.each([
    ['Ravi Kumar', 'RK'],
    ['Asha', 'A'],
  ])(
    'initials for %s are %s on avatarBackground/avatarText',
    async (name, initials) => {
      const { Avatar } = load('components/Avatar');
      const r = await both(<Avatar name={name} size={40} testID="avatar" />);
      for (const s of SCHEMES) {
        const t = r[s].getByText(initials, { exact: true });
        expect(styleOf(t).color).toBe(C(s).avatarText);
        expect(styleOf(r[s].getByTestId('avatar')).backgroundColor).toBe(
          C(s).avatarBackground,
        );
      }
    },
  );

  it.each([32, 40, 56, 80])('size %i is a circle of that size', async size => {
    const { Avatar } = load('components/Avatar');
    const { getByTestId } = await render(
      themed(<Avatar name="Asha" size={size} testID="avatar" />, 'light'),
    );
    const st = styleOf(getByTestId('avatar'));
    expect(st.width).toBe(size);
    expect(st.height).toBe(size);
    expect(st.borderRadius).toBeGreaterThanOrEqual(size / 2);
  });

  it('placeholder: dashed borderStrong ring; "invited" only when size >= 56', async () => {
    const { Avatar } = load('components/Avatar');
    const r = await both(
      <>
        <Avatar name="Meera" size={56} placeholder testID="big" />
        <Avatar name="Meera" size={40} placeholder testID="small" />
      </>,
    );
    for (const s of SCHEMES) {
      const ring = styleOf(r[s].getByTestId('big'));
      expect(ring.borderStyle).toBe('dashed');
      expect(ring.borderColor).toBe(C(s).borderStrong);
      expect(r[s].getAllByText('invited')).toHaveLength(1);
    }
  });

  it('group with no image shows a type glyph', async () => {
    const { Avatar } = load('components/Avatar');
    const { getByTestId } = await render(
      themed(<Avatar name="Goa" size={40} groupType="trip" />, 'light'),
    );
    expect(getByTestId('avatar-glyph-trip')).toBeTruthy();
  });
});

// ======================================================================================================== M-04
describe('SUI-M-04 BalanceChip', () => {
  it.each([
    [50000, '+INR 500.00 owed', 'owedText', 'owedSubtle', /owed|owes you/],
    [-50000, '−INR 500.00 owe', 'oweText', 'oweSubtle', /owe/],
    [0, 'settled up', 'textSecondary', 'fieldBackground', /settled up/],
  ] as const)(
    'amount %i renders "%s" with its tone tokens',
    async (amount, text, fg, bg, spoken) => {
      const { BalanceChip } = load('components/BalanceChip');
      const r = await both(<BalanceChip amountMinor={amount} currency="INR" />);
      for (const s of SCHEMES) {
        const t = r[s].getByText(text);
        expect(styleOf(t).color).toBe(C(s)[fg]);
        const chip = r[s].getByTestId('balance-chip');
        const label = String(chip.props.accessibilityLabel ?? '');
        expect(label).toMatch(spoken);
        expect(label).not.toMatch(/[+−]/); // sentence, not glyphs
        if (amount !== 0) {
          expect(label).toContain('INR 500.00');
        }
        const pill = r[s].getByTestId('balance-chip-pill');
        const ps = styleOf(pill);
        expect(ps.backgroundColor).toBe(C(s)[bg]);
        expect(ps.height).toBe(28);
        expect(ps.paddingHorizontal).toBe(10);
        expect(ps.borderRadius).toBe(radius.pill);
        expect(styleOf(chip).minHeight).toBe(48);
        expectColorsInScheme(r[s], s);
      }
    },
  );

  it('grayscale: the three tones differ by text alone', async () => {
    const { BalanceChip } = load('components/BalanceChip');
    const texts = new Set<string>();
    for (const amount of [50000, -50000, 0]) {
      const r = await render(
        themed(<BalanceChip amountMinor={amount} currency="INR" />, 'light'),
      );
      texts.add(textOf(r.toJSON() as Any));
    }
    expect(texts.size).toBe(3);
  });

  it('BalanceLines renders one chip per currency, never summed', async () => {
    const { BalanceLines } = load('components/BalanceLines');
    const lines = [
      { currency: 'INR', amount_minor: 1000 },
      { currency: 'USD', amount_minor: -250 },
      { currency: 'JPY', amount_minor: 40 },
    ];
    const r = await both(<BalanceLines lines={lines} />);
    for (const s of SCHEMES) {
      expect(r[s].getAllByTestId('balance-chip')).toHaveLength(3);
    }
  });

  it('MemberNetLines renders one chip per currency', async () => {
    const { MemberNetLines } = load('components/BalanceLines');
    const lines = [
      { currency: 'INR', amount_minor: 1000 },
      { currency: 'USD', amount_minor: -250 },
    ];
    const r = await both(<MemberNetLines lines={lines} />);
    for (const s of SCHEMES) {
      expect(r[s].getAllByTestId('balance-chip')).toHaveLength(2);
    }
  });
});

// ======================================================================================================== M-05
describe('SUI-M-05 Skeleton', () => {
  it('SkeletonRow: label "Loading", polite live region, blocks hidden, skeletonBase', async () => {
    const { SkeletonRow } = load('components/Skeleton');
    const r = await both(<SkeletonRow />);
    for (const s of SCHEMES) {
      const c = r[s].getByLabelText('Loading');
      expect(c.props.accessibilityLiveRegion).toBe('polite');
      const blocks = r[s].getAllByTestId('skeleton-block');
      expect(blocks.length).toBeGreaterThanOrEqual(4); // avatar circle, two text bars, trailing bar
      for (const b of blocks) {
        expect(styleOf(b).backgroundColor).toBe(C(s).skeletonBase);
        expect(
          b.props.importantForAccessibility === 'no' ||
            b.props.accessibilityElementsHidden === true,
        ).toBe(true);
      }
      expect(r[s].queryByText(/\d/)).toBeNull(); // never fake amounts
      expectColorsInScheme(r[s], s);
    }
  });

  it('shimmer uses skeletonHighlight, and is absent with reduced motion', async () => {
    const { Skeleton } = load('components/Skeleton');
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(false);
    const on = await render(themed(<Skeleton />, 'light'));
    await act(async () => {});
    expect(on.queryByTestId('skeleton-shimmer')).not.toBeNull();
    expect(resolvedColors(on).has(C('light').skeletonHighlight)).toBe(true);
    on.unmount();

    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(true);
    const off = await render(themed(<Skeleton />, 'light'));
    await act(async () => {});
    expect(off.queryByTestId('skeleton-shimmer')).toBeNull();
  });
});

describe('SUI-M-05 useLoadingPhase', () => {
  const phaseAt = async (isLoading: boolean, hasData: boolean, ms: number) => {
    const { useLoadingPhase } = load('components/useLoadingPhase');
    jest.useFakeTimers();
    const { result } = await renderHook(() =>
      useLoadingPhase(isLoading, hasData),
    );
    await act(async () => {
      jest.advanceTimersByTime(ms);
    });
    return result.current;
  };

  it('is skeleton by 100 ms', async () =>
    expect(await phaseAt(true, false, 100)).toBe('skeleton'));
  it('is still skeleton just before 300 ms', async () =>
    expect(await phaseAt(true, false, 299)).toBe('skeleton'));
  it('adds the spinner at 300 ms', async () =>
    expect(await phaseAt(true, false, 300)).toBe('spinner'));
  it('is none when not loading', async () =>
    expect(await phaseAt(false, false, 500)).toBe('none'));
  it('is none while refetching with cached data', async () =>
    expect(await phaseAt(true, true, 500)).toBe('none'));

  it('goes to none once data arrives', async () => {
    const { useLoadingPhase } = load('components/useLoadingPhase');
    jest.useFakeTimers();
    const { result, rerender } = await renderHook(
      ({ l, d }: { l: boolean; d: boolean }) => useLoadingPhase(l, d),
      { initialProps: { l: true, d: false } },
    );
    await act(async () => {
      jest.advanceTimersByTime(400);
    });
    expect(result.current).toBe('spinner');
    await rerender({ l: false, d: true });
    expect(result.current).toBe('none');
  });
});

describe('SUI-M-05 EmptyView', () => {
  it('96dp illustration, title2 headline, body hint, one primary button', async () => {
    const { EmptyView } = load('components/StateViews');
    const onAction = jest.fn();
    const r = await both(
      <EmptyView
        title="No friends yet"
        hint="Add your first friend"
        actionLabel="Add friend"
        onAction={onAction}
      />,
    );
    for (const s of SCHEMES) {
      const ill = r[s].getByTestId('empty-illustration');
      expect(styleOf(ill).width).toBe(96);
      expect(styleOf(ill).height).toBe(96);
      expect(styleOf(r[s].getByText('No friends yet')).fontSize).toBe(
        typography.title2.fontSize,
      );
      expect(styleOf(r[s].getByText('Add your first friend')).color).toBe(
        C(s).textSecondary,
      );
      expect(r[s].getAllByRole('button')).toHaveLength(1);
      expectColorsInScheme(r[s], s);
    }
    await fireEvent.press(r.dark.getByRole('button', { name: 'Add friend' }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('filter-no-results has no button', async () => {
    const { EmptyView } = load('components/StateViews');
    const { queryAllByRole } = await render(
      themed(<EmptyView title="No results" />, 'light'),
    );
    expect(queryAllByRole('button')).toHaveLength(0);
  });
});

describe('SUI-M-05 ErrorBanner', () => {
  it('role alert, errorSubtle fill, 1dp error outline, errorText lead, Retry fires once at 48dp', async () => {
    const { ErrorBanner } = load('components/StateViews');
    const onRetry = jest.fn();
    const r = await both(
      <ErrorBanner message="Couldn't load groups." onRetry={onRetry} />,
    );
    for (const s of SCHEMES) {
      const banner = r[s].getByRole('alert');
      const st = styleOf(banner);
      expect(st.backgroundColor).toBe(C(s).errorSubtle);
      expect(st.borderColor).toBe(C(s).error);
      expect(st.borderWidth).toBe(1);
      expect(st.borderRadius).toBe(radius.md);
      expect(banner.props.accessibilityLiveRegion).toBe('polite');
      const retry = r[s].getByRole('button', { name: 'Retry' });
      expect(
        Math.max(
          Number(styleOf(retry).minHeight ?? 0),
          Number(styleOf(retry).height ?? 0),
        ),
      ).toBeGreaterThanOrEqual(48);
      expectColorsInScheme(r[s], s);
    }
    onRetry.mockClear();
    await fireEvent.press(r.dark.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('failed saves use an assertive live region', async () => {
    const { ErrorBanner } = load('components/StateViews');
    const { getByRole } = await render(
      themed(
        <ErrorBanner message="Couldn't save." kind="save" onRetry={noop} />,
        'light',
      ),
    );
    expect(getByRole('alert').props.accessibilityLiveRegion).toBe('assertive');
  });
});

describe('SUI-M-05 OfflineBanner', () => {
  it('is neutral (surfaceRaised) and uses no error colors', async () => {
    const { OfflineBanner } = load('components/StateViews');
    const r = await both(<OfflineBanner />);
    for (const s of SCHEMES) {
      const errors = [C(s).error, C(s).errorText, C(s).errorSubtle];
      const used = resolvedColors(r[s]);
      errors.forEach(e => expect(used.has(e)).toBe(false));
      expect(used.has(C(s).surfaceRaised)).toBe(true);
      expect(r[s].queryByRole('alert')).toBeNull();
      expectColorsInScheme(r[s], s);
    }
  });
});

// ======================================================================================================== M-06
describe('SUI-M-06 Segmented', () => {
  it('fieldBackground track, brandSubtle thumb + brandText + check shape on the selected option only', async () => {
    const { Segmented } = load('components/Segmented');
    const r = await both(
      <Segmented
        label="Type"
        options={['Equal', 'Exact'] as const}
        value="Equal"
        onChange={noop}
      />,
    );
    for (const s of SCHEMES) {
      expect(styleOf(r[s].getByTestId('segmented-track')).backgroundColor).toBe(
        C(s).fieldBackground,
      );
      const on = r[s].getByRole('button', { name: 'Type: Equal' });
      expect(styleOf(on).backgroundColor).toBe(C(s).brandSubtle);
      expect(styleOf(r[s].getByText('Equal')).color).toBe(C(s).brandText);
      expect(r[s].getAllByTestId('segmented-check')).toHaveLength(1);
      expectTouchTargets(r[s]);
      expectColorsInScheme(r[s], s);
    }
  });
});

describe('SUI-M-06 FilterChip', () => {
  it('selected = brandSubtle + brandText + check icon node; unselected has no check; 48dp target', async () => {
    const { FilterChip } = load('components/FilterChip');
    const r = await both(
      <>
        <FilterChip label="Food" selected onPress={noop} />
        <FilterChip label="Rent" selected={false} onPress={noop} />
      </>,
    );
    for (const s of SCHEMES) {
      const on = r[s].getByRole('button', { name: /Food/ });
      expect(styleOf(on).backgroundColor).toBe(C(s).brandSubtle);
      expect(styleOf(r[s].getByText('Food')).color).toBe(C(s).brandText);
      expect(on.props.accessibilityState).toMatchObject({ selected: true });
      expect(r[s].getAllByTestId('filter-chip-check')).toHaveLength(1);
      expectTouchTargets(r[s]);
      expectColorsInScheme(r[s], s);
    }
  });
});

describe('SUI-M-06 ConfirmDialog', () => {
  const dialog = (destructive: boolean) => {
    const { ConfirmDialog } = load('components/ConfirmDialog');
    return (
      <ConfirmDialog
        visible
        title="Delete expense?"
        message="This cannot be undone."
        confirmLabel="Delete"
        destructive={destructive}
        onConfirm={noop}
        onClose={noop}
      />
    );
  };

  it('surfaceRaised, radius.xl, elevation 3 in light', async () => {
    const r = await both(dialog(false));
    for (const s of SCHEMES) {
      const st = styleOf(r[s].getByTestId('dialog'));
      expect(st.backgroundColor).toBe(C(s).surfaceRaised);
      expect(st.borderRadius).toBe(radius.xl);
    }
    expect(
      styleOf(r.light.getByTestId('dialog')).elevation,
    ).toBeGreaterThanOrEqual(3);
  });

  it('destructive: no filled red button; the cancel action has initial focus', async () => {
    const r = await both(dialog(true));
    for (const s of SCHEMES) {
      const del = styleOf(r[s].getByRole('button', { name: 'Delete' }));
      expect(del.backgroundColor ?? 'transparent').toBe('transparent');
      const filled = [C(s).error, C(s).errorSubtle, C(s).errorText];
      for (const b of r[s].getAllByRole('button')) {
        expect(filled).not.toContain(styleOf(b).backgroundColor);
      }
      const initial = r[s].getByTestId('dialog-initial-focus');
      expect(
        textOf(initial as Any) || initial.props.accessibilityLabel,
      ).toMatch(/cancel/i);
      expectColorsInScheme(r[s], s);
    }
  });

  it('non-destructive warning: neutral default (confirm is not red)', async () => {
    const { getByRole } = await render(themed(dialog(false), 'light'));
    const st = styleOf(getByRole('button', { name: 'Delete' }));
    expect([
      colorSchemes.light.error,
      colorSchemes.light.errorText,
    ]).not.toContain(st.backgroundColor);
  });
});

describe('SUI-M-06 CurrencyPicker', () => {
  const mount = (extra: object = {}) => {
    const { CurrencyPicker } = load('components/CurrencyPicker');
    return both(
      <CurrencyPicker
        visible
        selected="INR"
        onSelect={noop}
        onClose={noop}
        recent={['JPY', 'USD', 'INR', 'EUR']}
        {...extra}
      />,
    );
  };
  const settle = () =>
    act(async () => {
      await new Promise(r => setTimeout(r, 0));
    });

  it('shows search, Recent (max 3) and All with code, name and symbol', async () => {
    const r = await mount();
    await settle();
    for (const s of SCHEMES) {
      expect(r[s].getByLabelText(/search/i)).toBeTruthy();
      expect(r[s].getByText('Recent')).toBeTruthy();
      expect(r[s].getByText('All')).toBeTruthy();
      expect(r[s].getAllByTestId('recent-row').length).toBeLessThanOrEqual(3);
      expect(r[s].getAllByText(/Indian Rupee/).length).toBeGreaterThan(0);
      expect(r[s].getAllByText(/INR/).length).toBeGreaterThan(0);
      expect(r[s].getAllByText(/Rs/).length).toBeGreaterThan(0);
      expectColorsInScheme(r[s], s);
    }
  });

  it('search with no match shows a "no matching currency" view', async () => {
    const r = await mount();
    await settle();
    await fireEvent.changeText(r.dark.getByLabelText(/search/i), 'zzzz');
    expect(r.dark.getByText(/no matching currency/i)).toBeTruthy();
  });

  it('tap selects and closes', async () => {
    const onSelect = jest.fn();
    const onClose = jest.fn();
    const r = await mount({ onSelect, onClose });
    await settle();
    await fireEvent.press(r.dark.getAllByText(/US Dollar/)[0]);
    expect(onSelect).toHaveBeenCalledWith('USD');
    expect(onClose).toHaveBeenCalled();
  });
});

describe('SUI-M-06 toast / snackbar tokens', () => {
  // ASSUMED API: components/toast exports snackbarTokens(colors) and SNACKBAR_DURATION_MS.
  it.each(SCHEMES)('resolves inverse* tokens in %s', s => {
    const { snackbarTokens } = load('components/toast');
    expect(snackbarTokens(C(s))).toMatchObject({
      backgroundColor: C(s).inverseSurface,
      textColor: C(s).inverseText,
      actionColor: C(s).inverseLink,
    });
  });

  it('lasts 4 s', () => {
    expect(load('components/toast').SNACKBAR_DURATION_MS).toBe(4000);
  });
});

describe('SUI-M-06 Fab', () => {
  const metrics = {
    frame: { x: 0, y: 0, width: 360, height: 800 },
    insets: { top: 0, left: 0, right: 0, bottom: 20 },
  };
  const mount = async (scheme: Scheme) => {
    const { Fab } = load('components/Fab');
    return render(
      <ThemeProvider mode={scheme}>
        <SafeAreaProvider initialMetrics={metrics}>
          <Fab onPress={noop} />
        </SafeAreaProvider>
      </ThemeProvider>,
    );
  };

  it.each(SCHEMES)('56dp pill, brand, labelled "Add expense" (%s)', async s => {
    const r = await mount(s);
    const fab = r.getByRole('button', { name: 'Add expense' });
    const st = styleOf(fab);
    expect(st.height).toBe(layout.fabSize);
    expect(st.backgroundColor).toBe(C(s).brand);
    expect(st.borderRadius).toBe(radius.pill);
    expect(styleOf(r.getByText('Add expense')).color).toBe(C(s).textOnBrand);
    expectColorsInScheme(r, s);
  });

  it('bottom offset = tab bar height + inset + 16, right 16', async () => {
    const r = await mount('light');
    const st = styleOf(r.getByRole('button', { name: 'Add expense' }));
    expect(st.position).toBe('absolute');
    expect(st.bottom).toBe(
      layout.tabBarHeight + metrics.insets.bottom + spacing.lg,
    );
    expect(st.right).toBe(spacing.lg);
  });
});
