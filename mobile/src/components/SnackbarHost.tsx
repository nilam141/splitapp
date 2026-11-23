import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../theme';
import { Text } from './Text';
import {
  SNACKBAR_MS,
  Snack,
  dismissSnackbar,
  subscribeSnackbar,
} from './snackbar';

/** Bottom snackbar on the snackbar tokens, one action at most, gone after 4 s. Mounted once above the navigator. */
export function SnackbarHost() {
  const { colors, spacing, radius, touchTarget } = useTheme();
  const insets = useSafeAreaInsets();
  const [snack, setSnack] = useState<Snack | null>(null);
  useEffect(() => subscribeSnackbar(setSnack), []);
  const id = snack?.id;
  useEffect(() => {
    if (id === undefined) {
      return undefined;
    }
    const timer = setTimeout(dismissSnackbar, SNACKBAR_MS);
    return () => clearTimeout(timer);
  }, [id]);
  if (!snack) {
    return null;
  }
  const s = StyleSheet.create({
    wrap: {
      position: 'absolute',
      left: spacing.lg,
      right: spacing.lg,
      bottom: spacing.lg + insets.bottom,
    },
    bar: {
      backgroundColor: colors.inverseSurface,
      borderRadius: radius.md,
      paddingLeft: spacing.lg,
      flexDirection: 'row',
      alignItems: 'center',
      minHeight: touchTarget.min,
    },
    message: {
      color: colors.inverseText,
      flex: 1,
      paddingVertical: spacing.md,
    },
    action: {
      minHeight: touchTarget.min,
      minWidth: touchTarget.min,
      paddingHorizontal: spacing.lg,
      alignItems: 'center',
      justifyContent: 'center',
    },
    actionText: { color: colors.inverseLink },
  });
  return (
    <View style={s.wrap} pointerEvents="box-none">
      <View testID="snackbar" accessibilityLiveRegion="polite" style={s.bar}>
        <Text variant="callout" style={s.message}>
          {snack.message}
        </Text>
        {snack.actionLabel ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={snack.actionLabel}
            style={s.action}
            onPress={() => {
              const act = snack.onAction;
              dismissSnackbar();
              act?.();
            }}
          >
            <Text variant="label" style={s.actionText}>
              {snack.actionLabel}
            </Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}
