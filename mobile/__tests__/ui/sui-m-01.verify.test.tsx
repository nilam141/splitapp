/**
 * SUI-M-01 verification (QA). Test-only. Covers Text default, Button loading/focus/variant x state in both themes,
 * and Switch focus ring. Focus-ring defects D1/D3/D4 are fixed; their tests now assert the fixed behaviour.
 * The destructive-spinner it.failing remains a known minor defect.
 */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { colorSchemes, control } from '../../src/theme';
import { Button } from '../../src/components/Button';
import { Switch } from '../../src/components/Switch';
import { Text } from '../../src/components/Text';
import { flattenStyle, pressIn, SCHEMES, Scheme, themed } from './harness';

type Any = any;
const noop = () => {};
const st = (el: Any) => flattenStyle(el.props.style);
const C = (s: Scheme) => colorSchemes[s];
const VARIANTS = ['primary', 'secondary', 'outlined', 'destructive'] as const;
type V = (typeof VARIANTS)[number];
const layoutEvt = (width: number) => ({
  nativeEvent: { layout: { x: 0, y: 0, width, height: 52 } },
});
const transparent = (c: unknown) => c == null || c === 'transparent';

describe('SUI-M-01 verify: Text', () => {
  it('plain <Text> with no style is body 16/24/400 in textPrimary, both themes', async () => {
    for (const s of SCHEMES) {
      const r = await render(themed(<Text>plain</Text>, s));
      const x = st(r.getByText('plain'));
      expect(x.fontSize).toBe(16);
      expect(x.lineHeight).toBe(24);
      expect(String(x.fontWeight)).toBe('400');
      expect(x.color).toBe(C(s).textPrimary);
    }
  });
  it('caller style overrides the default', async () => {
    const r = await render(
      themed(
        <Text style={{ fontSize: 30, color: '#123456' }}>x</Text>,
        'light',
      ),
    );
    expect(st(r.getByText('x')).fontSize).toBe(30);
    expect(st(r.getByText('x')).color).toBe('#123456');
  });
});

describe('SUI-M-01 verify: Button loading', () => {
  const ui = (p: Partial<React.ComponentProps<typeof Button>>) =>
    themed(<Button title="Save changes" onPress={noop} {...p} />, 'light');

  it('keeps width while loading, returns to natural width after, ignores presses, a11y props', async () => {
    const onPress = jest.fn();
    const r = await render(ui({ onPress }));
    await fireEvent(r.getByRole('button'), 'layout', layoutEvt(180));
    await r.rerender(ui({ onPress, loading: true }));
    const b = r.getByRole('button', { name: 'Save changes, loading' });
    expect(st(b).width).toBe(180);
    expect(st(b).minWidth).toBe(180);
    expect(b.props.accessibilityState).toMatchObject({
      busy: true,
      disabled: true,
    });
    expect(b.props.accessibilityLiveRegion).toBe('polite');
    // a layout pass during loading (spinner is narrower) must not overwrite the stored width
    await fireEvent(b, 'layout', layoutEvt(72));
    expect(st(r.getByRole('button')).width).toBe(180);
    await fireEvent.press(b);
    expect(onPress).not.toHaveBeenCalled();

    await r.rerender(ui({ onPress, loading: false }));
    const after = r.getByRole('button', { name: 'Save changes' });
    expect(st(after).width).toBeUndefined();
    expect(st(after).minWidth).toBe(control.height);
    expect(after.props.accessibilityState).toMatchObject({
      busy: false,
      disabled: false,
    });
    expect(after.props.accessibilityLiveRegion).toBe('none');
    await fireEvent.press(after);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('custom accessibilityLabel is used for "<label>, loading"', async () => {
    const r = await render(
      ui({ loading: true, accessibilityLabel: 'Save group' }),
    );
    expect(r.getByRole('button', { name: 'Save group, loading' })).toBeTruthy();
  });

  it('a changed title (not loading) re-measures: new layout width is what loading then keeps', async () => {
    const r = await render(ui({ title: 'Go' }));
    await fireEvent(r.getByRole('button'), 'layout', layoutEvt(90));
    await r.rerender(ui({ title: 'Save all the things' }));
    await fireEvent(r.getByRole('button'), 'layout', layoutEvt(220));
    await r.rerender(ui({ title: 'Save all the things', loading: true }));
    expect(st(r.getByRole('button')).width).toBe(220);
  });

  it('loading from the very first render has no measured width (nothing to keep)', async () => {
    const r = await render(ui({ loading: true }));
    expect(st(r.getByRole('button')).width).toBeUndefined();
  });

  it('title change across a loading cycle: next layout refreshes the stored width (benign)', async () => {
    // Characterisation: after loading ends, the next onLayout refreshes it, so this is benign. Assert benign path.
    const r = await render(ui({ title: 'Go' }));
    await fireEvent(r.getByRole('button'), 'layout', layoutEvt(90));
    await r.rerender(ui({ title: 'Go', loading: true }));
    await r.rerender(ui({ title: 'Go and continue', loading: false }));
    await fireEvent(r.getByRole('button'), 'layout', layoutEvt(200));
    await r.rerender(ui({ title: 'Go and continue', loading: true }));
    expect(st(r.getByRole('button')).width).toBe(200);
  });
});

describe('SUI-M-01 verify: Button focus ring', () => {
  const ringOf = (btn: Any) =>
    btn.children.find(
      (c: Any) =>
        typeof c !== 'string' &&
        st(c).borderColor !== undefined &&
        st(c).position === 'absolute',
    );
  it.each(SCHEMES)(
    'focus shows a 2dp focusRing overlay child, blur removes it (%s)',
    async s => {
      const r = await render(themed(<Button title="Go" onPress={noop} />, s));
      expect(ringOf(r.getByRole('button'))).toBeUndefined();
      await fireEvent(r.getByRole('button'), 'focus');
      const ring = st(ringOf(r.getByRole('button')));
      expect(ring.position).toBe('absolute');
      expect(ring.borderWidth).toBe(2);
      expect(ring.borderColor).toBe(C(s).focusRing);
      // the button's own border is untouched
      expect(st(r.getByRole('button')).borderWidth).toBeUndefined();
      expect(st(r.getByRole('button')).borderColor).toBeUndefined();
      await fireEvent(r.getByRole('button'), 'blur');
      expect(ringOf(r.getByRole('button'))).toBeUndefined();
    },
  );
  it.each(SCHEMES)(
    'outlined stays 1dp borderStrong at rest and while focused (%s)',
    async s => {
      const r = await render(
        themed(<Button title="Go" variant="outlined" onPress={noop} />, s),
      );
      const check = () => {
        const b = st(r.getByRole('button'));
        expect(b.borderWidth).toBe(1);
        expect(b.borderColor).toBe(C(s).borderStrong);
      };
      check();
      await fireEvent(r.getByRole('button'), 'focus');
      check();
      expect(st(ringOf(r.getByRole('button'))).borderColor).toBe(
        C(s).focusRing,
      );
      await fireEvent(r.getByRole('button'), 'blur');
      check();
    },
  );
  it('focus does not change the button width, height or border width', async () => {
    const r = await render(
      themed(<Button title="Go" onPress={noop} />, 'light'),
    );
    const dims = () => {
      const b = st(r.getByRole('button'));
      return [
        b.width,
        b.height,
        b.minWidth,
        b.minHeight,
        b.borderWidth,
        b.padding,
        b.paddingHorizontal,
      ];
    };
    const before = dims();
    await fireEvent(r.getByRole('button'), 'focus');
    expect(dims()).toEqual(before);
    await fireEvent(r.getByRole('button'), 'blur');
    expect(dims()).toEqual(before);
  });
});

describe('SUI-M-01 verify: Button variant x state x theme (design_system 6.1)', () => {
  const fillOf = (v: V, s: Scheme) =>
    v === 'primary'
      ? C(s).brand
      : v === 'secondary'
        ? C(s).fieldBackground
        : undefined;
  const labelOf = (v: V, s: Scheme) =>
    v === 'primary'
      ? C(s).textOnBrand
      : v === 'destructive'
        ? C(s).errorText
        : C(s).textPrimary;
  const borderOf = (v: V, s: Scheme) =>
    v === 'outlined'
      ? C(s).borderStrong
      : v === 'destructive'
        ? C(s).error
        : undefined;

  const cases: [V, Scheme][] = VARIANTS.flatMap(v =>
    SCHEMES.map(s => [v, s] as [V, Scheme]),
  );

  it.each(cases)('%s rest state, %s', async (v, s) => {
    const r = await render(
      themed(<Button title="Go" variant={v} onPress={noop} />, s),
    );
    const b = st(r.getByRole('button'));
    if (fillOf(v, s)) expect(b.backgroundColor).toBe(fillOf(v, s));
    else expect(transparent(b.backgroundColor)).toBe(true);
    expect(b.borderColor).toBe(borderOf(v, s));
    expect(b.borderWidth).toBe(borderOf(v, s) ? 1 : undefined);
    expect(st(r.getByText('Go')).color).toBe(labelOf(v, s));
  });

  it.each(cases)('%s pressed, %s', async (v, s) => {
    const r = await render(
      themed(<Button title="Go" variant={v} onPress={noop} />, s),
    );
    await pressIn(r.getByRole('button'));
    const b = st(r.getByRole('button'));
    if (v === 'primary') expect(b.backgroundColor).toBe(C(s).brandPressed);
    else if (v === 'secondary') expect(b.backgroundColor).toBe(C(s).border);
    else if (v === 'outlined') {
      // design_system.md 8.2 item 7.5 (CR-UI-2): visible pressed feedback
      expect(b.backgroundColor).toBe(C(s).fieldBackground);
      // no layout shift: border unchanged from rest state
      expect(b.borderColor).toBe(borderOf(v, s));
      expect(b.borderWidth).toBe(1);
    } else expect(transparent(b.backgroundColor)).toBe(true);
    expect(st(r.getByText('Go')).color).toBe(labelOf(v, s)); // label stays legible
  });

  it.each(cases)(
    '%s disabled, %s: fieldBackground fill, textDisabled label, no press',
    async (v, s) => {
      const onPress = jest.fn();
      const r = await render(
        themed(<Button title="Go" variant={v} disabled onPress={onPress} />, s),
      );
      const b = st(r.getByRole('button'));
      expect(b.backgroundColor).toBe(C(s).fieldBackground);
      expect(st(r.getByText('Go')).color).toBe(C(s).textDisabled);
      if (v === 'outlined' || v === 'destructive') {
        expect(b.borderWidth).toBe(1);
        expect(b.borderColor).toBe(C(s).border);
      }
      expect(r.getByRole('button').props.accessibilityState).toMatchObject({
        disabled: true,
      });
      await pressIn(r.getByRole('button'));
      expect(st(r.getByRole('button')).backgroundColor).toBe(
        C(s).fieldBackground,
      );
      await fireEvent.press(r.getByRole('button'));
      expect(onPress).not.toHaveBeenCalled();
    },
  );

  it.each(cases)(
    '%s loading, %s: variant fill kept, spinner token color, no label',
    async (v, s) => {
      const r = await render(
        themed(<Button title="Go" variant={v} loading onPress={noop} />, s),
      );
      const b = st(r.getByRole('button'));
      if (fillOf(v, s)) expect(b.backgroundColor).toBe(fillOf(v, s));
      else expect(transparent(b.backgroundColor)).toBe(true);
      expect(b.borderColor).toBe(borderOf(v, s));
      expect(r.queryByText('Go')).toBeNull();
      const spinner = r.getByRole('progressbar');
      expect(spinner.props.size).toBe(control.spinner);
      expect(spinner.props.color).toBe(
        v === 'primary' ? C(s).textOnBrand : C(s).brand,
      );
    },
  );

  it.failing(
    'DEFECT (minor): destructive loading spinner is brand blue, not error/errorText',
    async () => {
      const r = await render(
        themed(
          <Button
            title="Delete"
            variant="destructive"
            loading
            onPress={noop}
          />,
          'light',
        ),
      );
      const spinner = r.getByRole('progressbar');
      expect([C('light').error, C('light').errorText]).toContain(
        spinner.props.color,
      );
    },
  );
});

describe('SUI-M-01 verify: Switch focus ring', () => {
  const ui = (value: boolean, onValueChange = noop, onFocus?: () => void) =>
    themed(
      <Switch
        value={value}
        onValueChange={onValueChange}
        onFocus={onFocus}
        accessibilityLabel="S"
      />,
      'light',
    );

  it('wrapper appears only while focused, with focusRing 2dp pill border', async () => {
    const r = await render(ui(true));
    expect(r.queryByTestId('focus-ring')).toBeNull();
    await fireEvent(r.getByRole('switch'), 'focus');
    const ring = st(r.getByTestId('focus-ring'));
    expect(ring.borderWidth).toBe(2);
    expect(ring.borderColor).toBe(colorSchemes.light.focusRing);
    await fireEvent(r.getByRole('switch'), 'blur');
    expect(r.queryByTestId('focus-ring')).toBeNull();
  });

  it('user onFocus is forwarded', async () => {
    const f = jest.fn();
    const r = await render(ui(true, noop, f));
    await fireEvent(r.getByRole('switch'), 'focus');
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('value is preserved across focus and blur (controlled)', async () => {
    const r = await render(ui(true));
    await fireEvent(r.getByRole('switch'), 'focus');
    expect(r.getByRole('switch').props.value).toBe(true);
    await fireEvent(r.getByRole('switch'), 'blur');
    expect(r.getByRole('switch').props.value).toBe(true);
  });

  it('focusing keeps the same native switch host instance and parent', async () => {
    const r = await render(ui(true));
    const before = r.getByRole('switch');
    const parent = before.parent;
    await fireEvent(r.getByRole('switch'), 'focus');
    expect(r.getByRole('switch')).toBe(before);
    expect(r.getByRole('switch').parent).toBe(parent);
    await fireEvent(r.getByRole('switch'), 'blur');
    expect(r.getByRole('switch')).toBe(before);
    expect(r.getByRole('switch').parent).toBe(parent);
  });

  it('the ring is an absolute overlay that does not add 4dp to the wrapper size', async () => {
    const r = await render(ui(true));
    await fireEvent(r.getByRole('switch'), 'focus');
    const ring = st(r.getByTestId('focus-ring'));
    expect(ring.position).toBe('absolute');
    expect(ring.borderWidth).toBe(2);
    expect(ring.borderColor).toBe(colorSchemes.light.focusRing);
    // wrapper (ring's parent) has no explicit size/border/padding that focus could grow
    const wrapper = st(r.getByTestId('focus-ring').parent);
    expect(wrapper.borderWidth).toBeUndefined();
    expect(wrapper.padding).toBeUndefined();
    expect(wrapper.width).toBeUndefined();
    expect(wrapper.height).toBeUndefined();
    // the native switch's own style is unchanged by focus
    expect(st(r.getByRole('switch')).borderWidth).toBeUndefined();
  });
});
