import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { touchTarget, useTheme, useThemedStyles } from '../theme';

type Props = {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  /**
   * design_system.md 6.1: one primary per screen. `secondary` is a quiet filled alternative, `outlined` is
   * low emphasis, `destructive` is outlined in the error color (never filled red). `text` is the 6.1 "Text / link"
   * action: no fill or border, brand label, compact visual height (not 52) with hitSlop keeping a 48dp target.
   */
  variant?: 'primary' | 'secondary' | 'outlined' | 'destructive' | 'text';
  /** Shorthand for variant="destructive". */
  destructive?: boolean;
  /** Replaces the label with a spinner, keeps the width, disables the button and announces "loading". */
  loading?: boolean;
  /** Stretches to the container width (forms). */
  fullWidth?: boolean;
  accessibilityLabel?: string;
};

/** Themed replacement for react-native's Button: 52dp, token colors, focus ring, light and dark. */
export function Button({
  title,
  onPress,
  disabled = false,
  destructive = false,
  variant: variantProp,
  loading = false,
  fullWidth = false,
  accessibilityLabel,
}: Props) {
  const variant = variantProp ?? (destructive ? 'destructive' : 'primary');
  const { maxFontScale, colors, control } = useTheme();
  const [focused, setFocused] = useState(false);
  const measured = useRef<number | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  const inactive = disabled || loading;
  const styles = useThemedStyles(({ colors: c, radius, spacing, typography }) =>
    StyleSheet.create({
      base: {
        height: control.height,
        minHeight: control.height,
        minWidth: control.height,
        paddingHorizontal: spacing.xl,
        borderRadius: radius.md,
        alignItems: 'center',
        justifyContent: 'center',
      },
      full: { alignSelf: 'stretch' },
      primary: { backgroundColor: c.brand },
      primaryPressed: { backgroundColor: c.brandPressed },
      primaryText: { ...typography.label, color: c.textOnBrand },
      secondary: { backgroundColor: c.fieldBackground },
      secondaryPressed: { backgroundColor: c.border },
      secondaryText: { ...typography.label, color: c.textPrimary },
      outlined: { borderWidth: 1, borderColor: c.borderStrong },
      outlinedPressed: { backgroundColor: c.fieldBackground },
      destructive: { borderWidth: 1, borderColor: c.error },
      text: {
        height: control.textHeight,
        minHeight: control.textHeight,
        minWidth: control.textHeight,
        paddingHorizontal: spacing.md,
      },
      textLabel: { ...typography.label, color: c.brand },
      textLabelPressed: { color: c.brandPressed },
      destructiveText: { ...typography.label, color: c.errorText },
      // Overlay ring outside the button edge: focus never changes layout size.
      ring: {
        position: 'absolute',
        top: -(control.focusRingOffset + control.focusRingWidth),
        bottom: -(control.focusRingOffset + control.focusRingWidth),
        left: -(control.focusRingOffset + control.focusRingWidth),
        right: -(control.focusRingOffset + control.focusRingWidth),
        borderWidth: control.focusRingWidth,
        borderColor: c.focusRing,
        borderRadius:
          radius.md + control.focusRingOffset + control.focusRingWidth,
      },
      disabled: { backgroundColor: c.fieldBackground, borderColor: c.border },
      disabledText: { color: c.textDisabled },
    }),
  );
  const label = loading
    ? `${accessibilityLabel ?? title}, loading`
    : accessibilityLabel;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: inactive, busy: loading }}
      accessibilityLiveRegion={loading ? 'polite' : 'none'}
      disabled={inactive}
      hitSlop={
        variant === 'text'
          ? (touchTarget.min - control.textHeight) / 2
          : undefined
      }
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onLayout={e => {
        if (!loading) {
          measured.current = e.nativeEvent.layout.width;
          setWidth(measured.current);
        }
      }}
      style={({ pressed }) => [
        styles.base,
        fullWidth ? styles.full : null,
        styles[variant],
        pressed && !inactive && variant === 'primary'
          ? styles.primaryPressed
          : null,
        pressed && !inactive && variant === 'secondary'
          ? styles.secondaryPressed
          : null,
        pressed && !inactive && variant === 'outlined'
          ? styles.outlinedPressed
          : null,
        disabled ? (variant === 'text' ? null : styles.disabled) : null,
        loading && width != null ? { width, minWidth: width } : null,
      ]}
    >
      {({ pressed }) => (
        <>
          {loading ? (
            <ActivityIndicator
              accessible
              accessibilityRole="progressbar"
              size={control.spinner}
              color={variant === 'primary' ? colors.textOnBrand : colors.brand}
            />
          ) : (
            <Text
              maxFontSizeMultiplier={maxFontScale.fixedControl}
              style={[
                variant === 'text'
                  ? styles.textLabel
                  : variant === 'destructive'
                    ? styles.destructiveText
                    : variant === 'primary'
                      ? styles.primaryText
                      : styles.secondaryText,
                variant === 'text' && pressed && !inactive
                  ? styles.textLabelPressed
                  : null,
                disabled ? styles.disabledText : null,
              ]}
            >
              {title}
            </Text>
          )}
          {focused ? <View pointerEvents="none" style={styles.ring} /> : null}
        </>
      )}
    </Pressable>
  );
}
