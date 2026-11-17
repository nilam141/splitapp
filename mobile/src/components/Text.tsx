import React from 'react';
import {
  StyleSheet,
  Text as RNText,
  TextInput as RNTextInput,
  TextInputProps,
  TextProps,
} from 'react-native';
import { TypographyVariant, useTheme } from '../theme';

type Props = TextProps & {
  /** Typography token (design_system 4). Defaults to `body`. */
  variant?: TypographyVariant;
};

/** Text with a typography variant and the theme's primary color so it stays readable in dark mode. */
export function Text({ style, variant = 'body', ...rest }: Props) {
  const { colors, typography } = useTheme();
  return (
    <RNText
      {...rest}
      style={StyleSheet.flatten([
        typography[variant],
        { color: colors.textPrimary },
        style,
      ])}
    />
  );
}

/** TextInput with themed text, placeholder, caret and field fill (design_system.md 6.2). */
export function TextInput({ style, ...rest }: TextInputProps) {
  const { colors, touchTarget } = useTheme();
  return (
    <RNTextInput
      placeholderTextColor={colors.textSecondary}
      selectionColor={colors.brand}
      {...rest}
      style={StyleSheet.flatten([
        {
          color: colors.textPrimary,
          backgroundColor: colors.fieldBackground,
          minHeight: touchTarget.min,
        },
        style,
      ])}
    />
  );
}
