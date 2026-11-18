import React from 'react';
import {
  Pressable,
  StyleProp,
  StyleSheet,
  View,
  ViewProps,
  ViewStyle,
} from 'react-native';
import { useTheme } from '../theme';

type Props = ViewProps & {
  children?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Makes the whole card pressable with the Android ripple (no tinted overlay). Needs a label. */
  onPress?: () => void;
  accessibilityLabel?: string;
};

/** design_system 6.3: surface, radius.lg, 16dp padding, elevation 1; 1dp border in dark only. */
export function Card({
  children,
  style,
  onPress,
  accessibilityLabel,
  ...rest
}: Props) {
  const { colors, spacing, radius, elevation, isDark, touchTarget } =
    useTheme();
  const base = StyleSheet.flatten([
    {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      padding: spacing.lg,
    },
    elevation[1],
    isDark ? { borderWidth: 1, borderColor: colors.border } : null,
    style,
  ]);
  if (onPress) {
    return (
      <Pressable
        {...rest}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        android_ripple={{ color: colors.border }}
        onPress={onPress}
        style={StyleSheet.flatten([base, { minHeight: touchTarget.min }])}
      >
        {children}
      </Pressable>
    );
  }
  return (
    <View {...rest} style={base}>
      {children}
    </View>
  );
}
