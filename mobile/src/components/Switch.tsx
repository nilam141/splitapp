import React, { useState } from 'react';
import {
  StyleSheet,
  Switch as RNSwitch,
  SwitchProps,
  View,
} from 'react-native';
import { useTheme } from '../theme';

/**
 * Switch with theme colors (brand track on, strong border off), a 48dp target and a focus ring that shows
 * while focused (keyboard / switch access). The ring is an overlay, so focus never changes layout and the
 * native Switch keeps the same parent.
 */
export function Switch({
  onFocus,
  onBlur,
  ...props
}: SwitchProps & {
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const { colors, touchTarget, radius, control } = useTheme();
  const [focused, setFocused] = useState(false);
  const inset = -(control.focusRingOffset + control.focusRingWidth);
  return (
    <View>
      <RNSwitch
        accessibilityRole="switch"
        trackColor={{ false: colors.borderStrong, true: colors.brand }}
        thumbColor={colors.surface}
        hitSlop={touchTarget.minGap}
        {...props}
        style={[{ minHeight: touchTarget.min }, props.style]}
        {...({
          onFocus: () => {
            setFocused(true);
            onFocus?.();
          },
          onBlur: () => {
            setFocused(false);
            onBlur?.();
          },
        } as object)}
      />
      {focused ? (
        <View
          testID="focus-ring"
          pointerEvents="none"
          style={[
            StyleSheet.absoluteFill,
            {
              top: inset,
              bottom: inset,
              left: inset,
              right: inset,
              borderWidth: control.focusRingWidth,
              borderColor: colors.focusRing,
              borderRadius: radius.pill,
            },
          ]}
        />
      ) : null}
    </View>
  );
}
