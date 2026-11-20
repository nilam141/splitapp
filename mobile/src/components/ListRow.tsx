import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { fontWeight, useTheme } from '../theme';
import { Text } from './Text';

type Props = {
  title: string;
  subtitle?: string;
  /** Pre-formatted money text from the shared money helper. */
  amount?: string;
  /** Spoken form of the amount ("you owe 500 rupees"); defaults to `amount`. */
  amountLabel?: string;
  caption?: string;
  /** Leading slot (40dp): an Avatar or category icon. */
  leading?: React.ReactNode;
  unread?: boolean;
  onPress: () => void;
  testID?: string;
};

/** design_system 6.4: 64dp min, leading 40dp, text column, right-aligned trailing column; one pressable. */
export function ListRow({
  title,
  subtitle,
  amount,
  amountLabel,
  caption,
  leading,
  unread = false,
  onPress,
  testID,
}: Props) {
  const { colors, spacing, layout } = useTheme();
  const label = [
    title,
    subtitle,
    amountLabel ?? amount,
    caption,
    unread ? 'unread' : null,
  ]
    .filter(Boolean)
    .join(', ');
  const s = StyleSheet.create({
    row: {
      minHeight: layout.listRowMinHeight,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      flexDirection: 'row',
      alignItems: 'center',
    },
    leading: {
      width: layout.avatar.md,
      height: layout.avatar.md,
      marginRight: spacing.md,
      alignItems: 'center',
      justifyContent: 'center',
    },
    text: { flex: 1, flexShrink: 1 },
    trailing: {
      alignItems: 'flex-end',
      marginLeft: spacing.md,
      flexShrink: 1,
    },
    dot: {
      width: spacing.sm,
      height: spacing.sm,
      borderRadius: spacing.xs,
      backgroundColor: colors.brand,
      marginLeft: spacing.sm,
    },
    unreadTitle: { fontWeight: fontWeight.bold },
    secondary: { color: colors.textSecondary },
    amountText: { textAlign: 'right' },
  });
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      android_ripple={{ color: colors.border }}
      onPress={onPress}
      style={s.row}
    >
      {leading ? <View style={s.leading}>{leading}</View> : null}
      <View style={s.text}>
        <Text
          variant="headline"
          numberOfLines={1}
          style={unread ? s.unreadTitle : undefined}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text variant="callout" numberOfLines={1} style={s.secondary}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {amount || caption || unread ? (
        <View style={s.trailing}>
          {amount ? (
            <Text variant="amount" style={s.amountText}>
              {amount}
            </Text>
          ) : null}
          {caption ? (
            <Text variant="caption" style={[s.secondary, s.amountText]}>
              {caption}
            </Text>
          ) : null}
        </View>
      ) : null}
      {unread ? (
        <View
          testID="unread-dot"
          importantForAccessibility="no"
          style={s.dot}
        />
      ) : null}
    </Pressable>
  );
}
