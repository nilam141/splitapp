// Helpers + the pair list shared by the test and by docs/design_system.md (the doc table was generated from it).
import type { ColorTokens } from '../colors';

function channel(v: number): number {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function luminance(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrast(a: string, b: string): number {
  const x = luminance(a);
  const y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

export interface Pair {
  name: string;
  fg: keyof ColorTokens;
  bg: keyof ColorTokens;
  min: 4.5 | 3; // 4.5 text, 3 non-text (icons, control boundaries, focus)
}

const hosts: (keyof ColorTokens)[] = ['background', 'surface'];

export const pairs: Pair[] = [
  ...hosts.flatMap(bg =>
    (
      [
        'textPrimary',
        'textSecondary',
        'brand',
        'owedText',
        'oweText',
        'errorText',
      ] as const
    ).map(fg => ({ name: `${fg} on ${bg}`, fg, bg, min: 4.5 as const })),
  ),
  {
    name: 'textPrimary on surfaceRaised',
    fg: 'textPrimary',
    bg: 'surfaceRaised',
    min: 4.5,
  },
  {
    name: 'textSecondary on surfaceRaised',
    fg: 'textSecondary',
    bg: 'surfaceRaised',
    min: 4.5,
  },
  {
    name: 'textPrimary on surfaceOverlay',
    fg: 'textPrimary',
    bg: 'surfaceOverlay',
    min: 4.5,
  },
  {
    name: 'textSecondary on surfaceOverlay',
    fg: 'textSecondary',
    bg: 'surfaceOverlay',
    min: 4.5,
  },
  {
    name: 'textPrimary on fieldBackground',
    fg: 'textPrimary',
    bg: 'fieldBackground',
    min: 4.5,
  },
  {
    name: 'textSecondary on fieldBackground (placeholder, settled chip)',
    fg: 'textSecondary',
    bg: 'fieldBackground',
    min: 4.5,
  },
  {
    name: 'textOnBrand on brand (button label)',
    fg: 'textOnBrand',
    bg: 'brand',
    min: 4.5,
  },
  {
    name: 'textOnBrand on brandPressed (pressed label)',
    fg: 'textOnBrand',
    bg: 'brandPressed',
    min: 4.5,
  },
  {
    name: 'brandText on brandSubtle (selected chip)',
    fg: 'brandText',
    bg: 'brandSubtle',
    min: 4.5,
  },
  {
    name: 'owedText on owedSubtle (balance chip)',
    fg: 'owedText',
    bg: 'owedSubtle',
    min: 4.5,
  },
  {
    name: 'oweText on oweSubtle (balance chip)',
    fg: 'oweText',
    bg: 'oweSubtle',
    min: 4.5,
  },
  {
    name: 'errorText on errorSubtle (error banner)',
    fg: 'errorText',
    bg: 'errorSubtle',
    min: 4.5,
  },
  {
    name: 'textPrimary on errorSubtle (banner body)',
    fg: 'textPrimary',
    bg: 'errorSubtle',
    min: 4.5,
  },
  {
    name: 'avatarText on avatarBackground',
    fg: 'avatarText',
    bg: 'avatarBackground',
    min: 4.5,
  },
  {
    name: 'inverseText on inverseSurface (toast)',
    fg: 'inverseText',
    bg: 'inverseSurface',
    min: 4.5,
  },
  {
    name: 'inverseLink on inverseSurface (toast action)',
    fg: 'inverseLink',
    bg: 'inverseSurface',
    min: 4.5,
  },
  // Non-text (WCAG 1.4.11): icons, bars, control boundaries, focus ring
  { name: 'owed (icon/bar) on surface', fg: 'owed', bg: 'surface', min: 3 },
  {
    name: 'owed (icon/bar) on background',
    fg: 'owed',
    bg: 'background',
    min: 3,
  },
  { name: 'owe (icon/bar) on surface', fg: 'owe', bg: 'surface', min: 3 },
  { name: 'owe (icon/bar) on background', fg: 'owe', bg: 'background', min: 3 },
  {
    name: 'error (icon/border) on surface',
    fg: 'error',
    bg: 'surface',
    min: 3,
  },
  {
    name: 'error (icon/border) on background',
    fg: 'error',
    bg: 'background',
    min: 3,
  },
  {
    name: 'borderStrong on surface (input outline)',
    fg: 'borderStrong',
    bg: 'surface',
    min: 3,
  },
  {
    name: 'borderStrong on fieldBackground',
    fg: 'borderStrong',
    bg: 'fieldBackground',
    min: 3,
  },
  { name: 'focusRing on surface', fg: 'focusRing', bg: 'surface', min: 3 },
  {
    name: 'focusRing on background',
    fg: 'focusRing',
    bg: 'background',
    min: 3,
  },
];
