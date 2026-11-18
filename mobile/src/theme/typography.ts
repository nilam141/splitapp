import type { TextStyle } from 'react-native';

// System font (Roboto on Android): no bundled font files, so nothing to license or ship, and it renders at
// the user's chosen font scale. Sizes are sp (React Native scales fontSize by the system setting).
// Amounts use tabular figures so columns of money line up.

export type TypographyVariant =
  | 'display' // hero balance
  | 'title1'
  | 'title2'
  | 'headline'
  | 'body'
  | 'bodyStrong'
  | 'callout'
  | 'label' // buttons, tabs, chips
  | 'caption'
  | 'amountLarge'
  | 'amount';

const tabular: TextStyle['fontVariant'] = ['tabular-nums'];

export const typography: Record<TypographyVariant, TextStyle> = {
  display: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '700',
    letterSpacing: -0.5,
    fontVariant: tabular,
  },
  title1: {
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '700',
    letterSpacing: -0.2,
  },
  title2: {
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '600',
    letterSpacing: -0.1,
  },
  headline: { fontSize: 16, lineHeight: 24, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  bodyStrong: { fontSize: 16, lineHeight: 24, fontWeight: '600' },
  callout: { fontSize: 14, lineHeight: 20, fontWeight: '400' },
  label: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    letterSpacing: 0.1,
  },
  caption: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '500',
    letterSpacing: 0.2,
  },
  amountLarge: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '700',
    letterSpacing: -0.3,
    fontVariant: tabular,
  },
  amount: {
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    fontVariant: tabular,
  },
};

/**
 * Fixed-height controls (tab bar, chips, buttons) cap font scaling here so they do not break; everything else
 * grows freely and its container must grow with it. Pass as `maxFontSizeMultiplier`.
 */
export const maxFontScale = {
  fixedControl: 1.3,
  flexible: 2,
} as const;

// Emphasis weight for state changes inside a variant (e.g. an unread row title). Keeps weight literals in the theme.
export const fontWeight = { bold: '700' } as const satisfies Record<
  string,
  TextStyle['fontWeight']
>;
