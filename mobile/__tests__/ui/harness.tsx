/**
 * SUI-Q-1 UI harness (UI-DoD 2 and 4). Tests import from here; the harness's own tests live in
 * harness.test.tsx. Application code never imports this file.
 *
 * The harness filename sits under __tests__, so Jest collects it as a suite. The guard below registers one
 * trivial test only when this file is the entry point, so importing it from other suites adds nothing.
 */
import React from 'react';
import { Dimensions, PixelRatio } from 'react-native';
import { fireEvent, render, RenderResult } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  ColorScheme,
  ColorTokens,
  colorSchemes,
  maxFontScale,
  ThemeProvider,
} from '../../src/theme';

export type Scheme = ColorScheme;
export const SCHEMES: readonly Scheme[] = ['light', 'dark'];

const initialMetrics = {
  frame: { x: 0, y: 0, width: 360, height: 800 },
  insets: { top: 0, left: 0, right: 0, bottom: 0 },
};

/** Wraps `ui` in ThemeProvider (forced scheme) and SafeAreaProvider. */
export function themed(ui: React.ReactElement, scheme: Scheme) {
  return (
    <ThemeProvider mode={scheme}>
      <SafeAreaProvider initialMetrics={initialMetrics}>{ui}</SafeAreaProvider>
    </ThemeProvider>
  );
}

/**
 * Mounts `ui` under ThemeProvider mode="light" and mode="dark". Both trees stay mounted so a test can query and
 * compare them; use the returned queries (result.getByText), not the global `screen`.
 * `ui` may be a function of the scheme when the element needs it (for example a per-scheme QueryClient).
 */
export async function renderBothThemes(
  ui: React.ReactElement | ((scheme: Scheme) => React.ReactElement),
): Promise<Record<Scheme, RenderResult>> {
  const make = (s: Scheme) => (typeof ui === 'function' ? ui(s) : ui);
  const light = await render(themed(make('light'), 'light'));
  const dark = await render(themed(make('dark'), 'dark'));
  return { light, dark };
}

// ---- colors ---------------------------------------------------------------------------------------------

type Json = ReturnType<RenderResult['toJSON']>;
type Node = NonNullable<Exclude<Json, unknown[]>>;

function nodesOf(tree: Json | RenderResult): Node[] {
  const root: Json =
    tree && 'toJSON' in (tree as object)
      ? (tree as RenderResult).toJSON()
      : (tree as Json);
  const out: Node[] = [];
  const visit = (n: unknown) => {
    if (n == null || typeof n === 'string') {
      return;
    }
    if (Array.isArray(n)) {
      n.forEach(visit);
      return;
    }
    const node = n as Node;
    out.push(node);
    (node.children ?? []).forEach(visit);
  };
  visit(root);
  return out;
}

function flattenStyle(style: unknown): Record<string, unknown> {
  if (style == null || style === false) {
    return {};
  }
  if (Array.isArray(style)) {
    return style.reduce<Record<string, unknown>>(
      (acc, s) => ({ ...acc, ...flattenStyle(s) }),
      {},
    );
  }
  return typeof style === 'object' ? (style as Record<string, unknown>) : {};
}

const COLOR_STYLE_KEY = /color$/i;
// Props that carry a color outside `style` (ActivityIndicator, Switch, TextInput, icons).
const COLOR_PROPS = [
  'color',
  'tintColor',
  'thumbColor',
  'placeholderTextColor',
  'selectionColor',
  'underlineColorAndroid',
  'cursorColor',
];

/**
 * Every color string found in rendered styles and color props. A color that is not a design token (a literal
 * such as '#fff') shows up here and makes expectColorsInScheme fail.
 */
export function resolvedColors(tree: Json | RenderResult): Set<string> {
  const found = new Set<string>();
  for (const node of nodesOf(tree)) {
    const props = (node.props ?? {}) as Record<string, unknown>;
    for (const [k, v] of Object.entries(flattenStyle(props.style))) {
      if (COLOR_STYLE_KEY.test(k) && typeof v === 'string') {
        found.add(v);
      }
    }
    for (const k of COLOR_PROPS) {
      if (typeof props[k] === 'string') {
        found.add(props[k] as string);
      }
    }
    for (const k of ['trackColor']) {
      const t = props[k] as Record<string, unknown> | undefined;
      if (t && typeof t === 'object') {
        Object.values(t).forEach(v => typeof v === 'string' && found.add(v));
      }
    }
  }
  return found;
}

/** Every string value of a scheme's tokens ('transparent' is always allowed: it is not a palette color). */
export function schemeValues(scheme: Scheme): Set<string> {
  const values = new Set<string>(['transparent']);
  const add = (v: unknown) => {
    if (typeof v === 'string') {
      values.add(v);
    } else if (Array.isArray(v)) {
      v.forEach(add);
    }
  };
  Object.values(colorSchemes[scheme] as ColorTokens).forEach(add);
  return values;
}

/** Colors in the tree that are not values of colorSchemes[scheme]. Empty means the tree is token-only. */
export function colorsOutsideScheme(
  tree: Json | RenderResult,
  scheme: Scheme,
): string[] {
  const allowed = schemeValues(scheme);
  return [...resolvedColors(tree)].filter(c => !allowed.has(c)).sort();
}

export function expectColorsInScheme(
  tree: Json | RenderResult,
  scheme: Scheme,
): void {
  expect(colorsOutsideScheme(tree, scheme)).toEqual([]);
}

/** The first color style found on the root-most node that sets backgroundColor. */
export function screenBackground(
  tree: Json | RenderResult,
): string | undefined {
  for (const node of nodesOf(tree)) {
    const bg = flattenStyle(
      (node.props as Record<string, unknown>)?.style,
    ).backgroundColor;
    if (typeof bg === 'string') {
      return bg;
    }
  }
  return undefined;
}

// ---- touch targets --------------------------------------------------------------------------------------

const PRESS_HANDLERS = ['onPress', 'onClick', 'onResponderRelease'];
const MIN_DP = 48;

function isPressable(props: Record<string, unknown>): boolean {
  return PRESS_HANDLERS.some(h => typeof props[h] === 'function');
}

function textOf(node: Node): string {
  return (node.children ?? [])
    .map(c => (typeof c === 'string' ? c : textOf(c as Node)))
    .join('');
}

function slop(hit: unknown, a: string, b: string): number {
  if (typeof hit === 'number') {
    return hit * 2;
  }
  const h = (hit ?? {}) as Record<string, number>;
  return (h[a] ?? 0) + (h[b] ?? 0);
}

/**
 * Problems with pressables in the tree: missing role, missing label (accessibilityLabel or visible text), or a
 * size below 48dp (height/minHeight plus vertical hitSlop; width/minWidth plus horizontal hitSlop). A size that
 * is not declared at all is reported too: the 48dp must be explicit so it does not depend on content.
 * A pressable with accessible={false} or importantForAccessibility="no" is skipped.
 */
export function touchTargetProblems(tree: Json | RenderResult): string[] {
  const problems: string[] = [];
  for (const node of nodesOf(tree)) {
    const props = (node.props ?? {}) as Record<string, unknown>;
    if (!isPressable(props) || props.accessible === false) {
      continue;
    }
    const name = `${String(node.type)} "${
      (props.accessibilityLabel as string) || textOf(node).slice(0, 30)
    }"`;
    const role = props.accessibilityRole ?? props.role;
    if (!role) {
      problems.push(`${name}: no accessibilityRole`);
    }
    if (!props.accessibilityLabel && !textOf(node)) {
      problems.push(`${name}: no accessibilityLabel and no text`);
    }
    const s = flattenStyle(
      typeof props.style === 'function' ? undefined : props.style,
    );
    const h =
      Math.max(Number(s.height ?? 0), Number(s.minHeight ?? 0)) +
      slop(props.hitSlop, 'top', 'bottom');
    const w =
      Math.max(Number(s.width ?? 0), Number(s.minWidth ?? 0)) +
      slop(props.hitSlop, 'left', 'right');
    if (h < MIN_DP) {
      problems.push(`${name}: height ${h} < ${MIN_DP}`);
    }
    // width is allowed to come from the container (full-width rows); only an explicit narrow one fails
    const explicitW = s.width != null || s.minWidth != null;
    if (explicitW && w < MIN_DP) {
      problems.push(`${name}: width ${w} < ${MIN_DP}`);
    }
  }
  return problems;
}

export function expectTouchTargets(tree: Json | RenderResult): void {
  expect(touchTargetProblems(tree)).toEqual([]);
}

// ---- font scale -----------------------------------------------------------------------------------------

/**
 * Renders `ui` (inside ThemeProvider, scheme default light) with the system font scale mocked to `scale`
 * (PixelRatio.getFontScale and Dimensions fontScale), restoring on unmount via the returned `restore`.
 * `effectiveScale(node)` is the scale Text would actually apply: min(scale, maxFontSizeMultiplier).
 */
export async function renderAtFontScale(
  ui: React.ReactElement,
  scale: number,
  scheme: Scheme = 'light',
) {
  const real = Dimensions.get('window');
  const pr = jest.spyOn(PixelRatio, 'getFontScale').mockReturnValue(scale);
  const dim = jest
    .spyOn(Dimensions, 'get')
    .mockImplementation(() => ({ ...real, fontScale: scale }));
  const result = await render(themed(ui, scheme));
  const restore = () => {
    pr.mockRestore();
    dim.mockRestore();
  };
  const effectiveScale = (maxFontSizeMultiplier?: number) =>
    maxFontSizeMultiplier == null
      ? scale
      : Math.min(scale, maxFontSizeMultiplier);
  return { ...result, scale, restore, effectiveScale };
}

/** Text nodes whose label/text matches and whose maxFontSizeMultiplier is above the fixed-control cap. */
export function uncappedFixedControls(
  tree: Json | RenderResult,
  isFixedControl: (node: Node) => boolean,
): string[] {
  return nodesOf(tree)
    .filter(isFixedControl)
    .filter(n => {
      const m = (n.props as Record<string, unknown>).maxFontSizeMultiplier as
        number | undefined;
      return m == null || m > maxFontScale.fixedControl;
    })
    .map(n => textOf(n));
}

/**
 * Interactive tests (focus, press-in, typing): mounts `ui` once per scheme, one at a time, and runs `fn` on each.
 * Use this instead of renderBothThemes when the test changes state after mounting. With two trees mounted at
 * once, RNTL only drives state updates in the most recently mounted one (the first tree goes inert), so
 * renderBothThemes is for render-only assertions.
 */
export async function eachTheme(
  ui: React.ReactElement,
  fn: (r: RenderResult, scheme: Scheme) => void | Promise<void>,
): Promise<void> {
  for (const scheme of SCHEMES) {
    const r = await render(themed(ui, scheme));
    await fn(r, scheme);
    await r.unmount();
  }
}

/**
 * Puts a Pressable into its pressed state (responder grant) so a test can read the pressed style. RNTL's
 * fireEvent('pressIn') does not drive Pressable's style function; the responder events do.
 */
export function pressIn(el: Parameters<typeof fireEvent>[0]) {
  const target = {
    measure: (cb: (...n: number[]) => void) => cb(0, 0, 100, 50, 0, 0),
    measureInWindow: (cb: (...n: number[]) => void) => cb(0, 0, 100, 50),
  };
  return fireEvent(el, 'responderGrant', {
    persist: () => {},
    currentTarget: target,
    nativeEvent: { touches: [{}], changedTouches: [{}], timestamp: 0 },
  });
}

export { nodesOf, flattenStyle, textOf };

// Make Jest accept this file as a suite when it is the entry point.
if (expect.getState().testPath?.endsWith('/ui/harness.tsx')) {
  it('is a helper module (self-tests are in harness.test.tsx)', () => {
    expect(SCHEMES).toEqual(['light', 'dark']);
  });
}
