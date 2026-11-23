import React, { createContext, useContext, useMemo } from 'react';
import { useColorScheme } from 'react-native';
import {
  colorSchemes,
  ColorScheme,
  ColorTokens,
  brandGradient,
} from './colors';
import { elevationFor } from './elevation';
import { control, layout, spacing, touchTarget } from './spacing';
import { radius } from './radius';
import { typography, maxFontScale } from './typography';

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  colors: ColorTokens;
  typography: typeof typography;
  maxFontScale: typeof maxFontScale;
  spacing: typeof spacing;
  touchTarget: typeof touchTarget;
  layout: typeof layout;
  control: typeof control;
  radius: typeof radius;
  elevation: ReturnType<typeof elevationFor>;
  brandGradient: typeof brandGradient;
}

export function buildTheme(scheme: ColorScheme): Theme {
  return {
    scheme,
    isDark: scheme === 'dark',
    colors: colorSchemes[scheme],
    typography,
    maxFontScale,
    spacing,
    touchTarget,
    layout,
    control,
    radius,
    elevation: elevationFor(scheme),
    brandGradient,
  };
}

const ThemeContext = createContext<Theme>(buildTheme('light'));

interface Props {
  children: React.ReactNode;
  /** Defaults to following the system. Only tests and a future in-app toggle (OQ-21) should pass a value. */
  mode?: ColorScheme | 'system';
}

/** Follows the OS light/dark setting live (useColorScheme re-renders on change). */
export function ThemeProvider({ children, mode = 'system' }: Props) {
  const system = useColorScheme();
  const scheme: ColorScheme =
    mode === 'system' ? (system === 'dark' ? 'dark' : 'light') : mode;
  const theme = useMemo(() => buildTheme(scheme), [scheme]);
  return (
    <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

/** Convenience for the common case: build a StyleSheet from the current theme, memoised per scheme. */
export function useThemedStyles<T>(factory: (theme: Theme) => T): T {
  const theme = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => factory(theme), [theme.scheme]);
}
