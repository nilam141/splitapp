// Color tokens for SplitApp. This is the ONLY place hex/rgba literals may appear in mobile/.
// Rules (docs/design_system.md §3, §9):
//  - one brand color; green/red are reserved for status; owing is orange, not an error;
//  - never signal owed vs owing by color alone (see balance.ts: every tone has a sign and a word);
//  - every text token below is >= 4.5:1 on the surfaces it is allowed on (enforced by __tests__/contrast.test.ts).

export type ColorScheme = 'light' | 'dark';

export interface ColorTokens {
  scheme: ColorScheme;

  // Neutral layers (about 60% of any screen)
  background: string; // screen background
  surface: string; // cards, list groups, bottom tabs
  surfaceRaised: string; // sheets, dialogs, menus (dark: one step lighter than surface)
  surfaceOverlay: string; // popovers over a raised surface (dark: another step lighter)
  fieldBackground: string; // text inputs and segmented tracks
  scrim: string; // modal backdrop

  // Text
  textPrimary: string;
  textSecondary: string;
  textDisabled: string; // exempt from contrast (disabled), never use for live content
  textOnBrand: string; // label on a flat brand fill
  textOnGradient: string; // label on the optional gradient (always full-opacity white)

  // Lines
  border: string; // decorative dividers and card outlines (not a control boundary)
  borderStrong: string; // control boundaries: inputs, checkboxes, outlined buttons (>= 3:1)
  focusRing: string;

  // Brand (about 10%): buttons, active tab, links, key highlights only
  brand: string; // flat button fill, active tab, links, focus
  brandPressed: string;
  brandText: string; // brand-colored text on brandSubtle (selected chip, segmented thumb)
  brandSubtle: string; // tinted fill for selected chips / segmented thumb

  // Status. `x` is for icons, bars and fills (>= 3:1 on background and surface); `xText` is for text (>= 4.5:1).
  owed: string;
  owedText: string;
  owedSubtle: string;
  owe: string;
  oweText: string;
  oweSubtle: string;
  error: string; // real errors only: failed save, invalid input
  errorText: string;
  errorSubtle: string;

  // Misc surfaces
  avatarBackground: string;
  avatarText: string;
  skeletonBase: string;
  skeletonHighlight: string;
  inverseSurface: string; // snackbar / toast
  inverseText: string;
  inverseLink: string; // action text on the snackbar

  // Optional gradient for the primary button and the screen header only. Off by default, see brandGradient.
  gradient: readonly [string, string];
}

export const lightColors: ColorTokens = {
  scheme: 'light',

  background: '#F7F7FB',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  surfaceOverlay: '#FFFFFF',
  fieldBackground: '#F0F0F7',
  scrim: 'rgba(20, 20, 43, 0.48)',

  textPrimary: '#14142B',
  textSecondary: '#6B6B85',
  textDisabled: '#A3A3B8',
  textOnBrand: '#FFFFFF',
  textOnGradient: '#FFFFFF',

  border: '#E6E6F0',
  borderStrong: '#80809A',
  focusRing: '#2563EB',

  brand: '#2563EB',
  brandPressed: '#1D4ED8',
  brandText: '#1D4ED8',
  brandSubtle: '#EEF3FD',

  owed: '#12A150',
  owedText: '#0D743A',
  owedSubtle: '#ECF4EF',
  owe: '#E8590C',
  oweText: '#AC4209',
  oweSubtle: '#F8F0EB',
  error: '#E5484D',
  errorText: '#B3383C',
  errorSubtle: '#F9EFEF',

  avatarBackground: '#E6E6F0',
  avatarText: '#14142B',
  skeletonBase: '#EDEDF5',
  skeletonHighlight: '#F7F7FB',
  inverseSurface: '#14142B',
  inverseText: '#F2F2FA',
  inverseLink: '#93C5FD',

  gradient: ['#5B5BD6', '#7C5CE0'],
};

export const darkColors: ColorTokens = {
  scheme: 'dark',

  background: '#0E0F1A',
  surface: '#171828',
  surfaceRaised: '#1F2035',
  surfaceOverlay: '#27283F',
  fieldBackground: '#1F2035',
  scrim: 'rgba(0, 0, 0, 0.6)',

  textPrimary: '#F2F2FA',
  textSecondary: '#9A9AB5',
  textDisabled: '#5E5F7A',
  textOnBrand: '#0E0F1A', // white on #60A5FA is only 2.5:1, so the label goes dark
  textOnGradient: '#FFFFFF',

  border: '#262740',
  borderStrong: '#6A6B90',
  focusRing: '#60A5FA',

  brand: '#60A5FA',
  brandPressed: '#4B93F0',
  brandText: '#60A5FA',
  brandSubtle: '#212C45',

  owed: '#4ADE80',
  owedText: '#4ADE80',
  owedSubtle: '#1E3434',
  owe: '#FF9A5C',
  oweText: '#FF9A5C',
  oweSubtle: '#372A2F',
  error: '#FF8A8F',
  errorText: '#FF8A8F',
  errorSubtle: '#372836',

  avatarBackground: '#2A2B45',
  avatarText: '#F2F2FA',
  skeletonBase: '#1F2035',
  skeletonHighlight: '#2A2B45',
  inverseSurface: '#F2F2FA',
  inverseText: '#14142B',
  inverseLink: '#2563EB',

  gradient: ['#5B5BD6', '#7C5CE0'],
};

/**
 * The gradient is optional and OFF by default: indigo/violet next to the blue brand reads as a second brand color
 * (design_system.md §3.4). Flip this once the owner decides; components must check it and fall back to `brand`.
 */
export const brandGradient = {
  enabled: false,
  start: { x: 0, y: 0 },
  end: { x: 1, y: 1 },
} as const;

export const colorSchemes: Record<ColorScheme, ColorTokens> = {
  light: lightColors,
  dark: darkColors,
};
