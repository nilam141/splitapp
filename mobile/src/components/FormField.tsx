import React, { ReactNode, useState } from 'react';
import { Pressable, StyleSheet, TextInputProps, View } from 'react-native';
import { Theme, touchTarget, useTheme, useThemedStyles } from '../theme';
import { Text, TextInput } from './Text';

type Props = TextInputProps & {
  label: string;
  error?: string;
  /** Helper text; shares one slot with the error, which replaces it (design_system 6.2). */
  helper?: string;
  /** Fixed content drawn inside the field at the start (the money currency chip). */
  prefix?: ReactNode;
};

/**
 * Labelled input (design_system 6.2): label above, 56dp, 1dp borderStrong outline, 2dp brand outline on focus,
 * 2dp error outline plus icon plus errorText message on error. Password fields get a Show/Hide toggle.
 */
export function FormField({
  label,
  error,
  helper,
  prefix,
  style,
  secureTextEntry,
  editable,
  onFocus,
  onBlur,
  ...rest
}: Props) {
  const styles = useThemedStyles(makeStyles);
  const { control, spacing, maxFontScale } = useTheme();
  const [focused, setFocused] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [prefixWidth, setPrefixWidth] = useState(0);
  const disabled = editable === false;
  const isPassword = secureTextEntry === true;
  const message = error ?? helper;
  // A 2dp outline replaces the 1dp one; trim the padding by the difference so the text does not shift.
  const wide = focused || Boolean(error);
  const edge = wide ? control.focusRingWidth - 1 : 0;

  return (
    <View style={styles.wrap}>
      <Text variant="callout" style={styles.label}>
        {label}
      </Text>
      <View>
        <TextInput
          accessibilityLabel={label}
          autoCapitalize="none"
          editable={editable}
          secureTextEntry={isPassword && !revealed}
          onFocus={e => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={e => {
            setFocused(false);
            onBlur?.(e);
          }}
          maxFontSizeMultiplier={maxFontScale.fixedControl}
          {...rest}
          style={[
            styles.input,
            rest.multiline ? styles.inputMultiline : null,
            wide ? styles.inputWide : null,
            focused && !error ? styles.inputFocused : null,
            error ? styles.inputError : null,
            disabled ? styles.inputDisabled : null,
            {
              paddingLeft: spacing.lg - edge + (prefix ? prefixWidth : 0),
              paddingRight:
                spacing.lg - edge + (isPassword ? touchTarget.min : 0),
            },
            style,
          ]}
        />
        {prefix ? (
          <View
            style={styles.prefix}
            pointerEvents="none"
            onLayout={e => setPrefixWidth(e.nativeEvent.layout.width)}
          >
            {prefix}
          </View>
        ) : null}
        {isPassword ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={revealed ? 'Hide password' : 'Show password'}
            disabled={disabled}
            onPress={() => setRevealed(v => !v)}
            style={styles.toggle}
          >
            <Text variant="label" style={styles.toggleText}>
              {revealed ? 'Hide' : 'Show'}
            </Text>
          </Pressable>
        ) : null}
      </View>
      {message ? (
        <View
          testID="field-message"
          accessibilityLiveRegion={error ? 'assertive' : 'polite'}
          style={styles.message}
        >
          {error ? (
            <View
              testID="field-error-icon"
              accessible={false}
              style={styles.icon}
            >
              <Text
                variant="caption"
                importantForAccessibility="no"
                style={styles.iconGlyph}
              >
                !
              </Text>
            </View>
          ) : null}
          <Text
            variant="callout"
            style={[styles.messageText, error ? styles.errorText : null]}
          >
            {message}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const makeStyles = ({ colors, spacing, radius, control, typography }: Theme) =>
  StyleSheet.create({
    wrap: { marginBottom: spacing.md },
    label: { marginBottom: spacing.xs, color: colors.textSecondary },
    input: {
      ...typography.body,
      height: control.fieldHeight,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      borderRadius: radius.md,
      backgroundColor: colors.fieldBackground,
      color: colors.textPrimary,
    },
    inputMultiline: { height: undefined, minHeight: control.fieldHeight },
    inputWide: { borderWidth: control.focusRingWidth },
    inputFocused: { borderColor: colors.brand },
    inputError: { borderColor: colors.error },
    inputDisabled: { color: colors.textDisabled },
    prefix: {
      position: 'absolute',
      left: spacing.lg,
      top: 0,
      bottom: 0,
      justifyContent: 'center',
    },
    toggle: {
      position: 'absolute',
      right: 0,
      top: 0,
      height: control.fieldHeight,
      minHeight: touchTarget.min,
      minWidth: touchTarget.min,
      paddingHorizontal: spacing.sm,
      alignItems: 'center',
      justifyContent: 'center',
    },
    toggleText: { color: colors.brand },
    message: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      marginTop: spacing.xs,
    },
    messageText: { flexShrink: 1, color: colors.textSecondary },
    errorText: { color: colors.errorText },
    icon: {
      width: spacing.lg,
      height: spacing.lg,
      borderRadius: radius.pill,
      backgroundColor: colors.error,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: spacing.sm,
      marginTop: spacing.xxs,
    },
    iconGlyph: { color: colors.textOnBrand },
  });
