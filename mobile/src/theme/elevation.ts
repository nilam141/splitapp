import type { ViewStyle } from 'react-native';
import type { ColorScheme } from './colors';

// Light mode: soft shadows. Dark mode: NO shadows; depth comes from lighter surfaces
// (colors.surface -> surfaceRaised -> surfaceOverlay), plus a hairline border where two surfaces touch.

export type ElevationLevel = 0 | 1 | 2 | 3;

type ShadowStyle = Pick<
  ViewStyle,
  | 'shadowColor'
  | 'shadowOffset'
  | 'shadowOpacity'
  | 'shadowRadius'
  | 'elevation'
>;

const none: ShadowStyle = {
  shadowColor: 'transparent',
  shadowOffset: { width: 0, height: 0 },
  shadowOpacity: 0,
  shadowRadius: 0,
  elevation: 0,
};

const SHADOW = '#14142B';

const lightShadows: Record<ElevationLevel, ShadowStyle> = {
  0: none,
  // 1: cards at rest
  1: {
    shadowColor: SHADOW,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
  // 2: raised on interaction, FAB at rest, sticky header
  2: {
    shadowColor: SHADOW,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 10,
    elevation: 3,
  },
  // 3: dialogs, bottom sheets, menus
  3: {
    shadowColor: SHADOW,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.12,
    shadowRadius: 24,
    elevation: 8,
  },
};

const darkShadows: Record<ElevationLevel, ShadowStyle> = {
  0: none,
  1: none,
  2: none,
  3: none,
};

export function elevationFor(
  scheme: ColorScheme,
): Record<ElevationLevel, ShadowStyle> {
  return scheme === 'dark' ? darkShadows : lightShadows;
}

/** Which surface token a level should be painted with. Light mode keeps one white surface and relies on shadow. */
export const surfaceForLevel = {
  0: 'background',
  1: 'surface',
  2: 'surfaceRaised',
  3: 'surfaceOverlay',
} as const;
