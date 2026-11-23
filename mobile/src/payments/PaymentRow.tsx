import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { fontWeight, useTheme } from '../theme';
import { Text } from '../components/Text';
import type { Settlement } from '../api/generated/model';

type Props = {
  settlement: Settlement;
  nameOf: (id: string) => string;
  /** Pre-formatted money text from the shared money helper. */
  amountText: string;
  onPress: () => void;
};

/**
 * SCR-13 payment row (design_system 8.2): an arrow glyph and a neutral `fieldBackground` fill so it is never taken
 * for an expense. Deleted payments are struck through and tagged "deleted".
 */
export function PaymentRow({ settlement, nameOf, amountText, onPress }: Props) {
  const { colors, spacing, radius, layout } = useTheme();
  const deleted = !!settlement.deleted_at;
  const sentence = `${nameOf(settlement.from_user_id)} paid ${nameOf(settlement.to_user_id)}`;
  const s = StyleSheet.create({
    row: {
      minHeight: layout.listRowMinHeight,
      marginVertical: spacing.xs,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      borderRadius: radius.md,
      backgroundColor: colors.fieldBackground,
      flexDirection: 'row',
      alignItems: 'center',
    },
    glyph: {
      width: layout.avatar.sm,
      alignItems: 'center',
      marginRight: spacing.md,
    },
    glyphText: { color: colors.textSecondary, fontWeight: fontWeight.bold },
    middle: { flex: 1 },
    secondary: { color: colors.textSecondary },
    struck: { textDecorationLine: 'line-through' },
    amount: { marginLeft: spacing.sm, textAlign: 'right' },
  });
  return (
    <Pressable
      testID="payment-row"
      accessibilityRole="button"
      accessibilityLabel={`Payment: ${sentence} ${amountText}, ${settlement.settled_on}${deleted ? ', deleted' : ''}`}
      android_ripple={{ color: colors.border }}
      onPress={onPress}
      style={s.row}
    >
      <View style={s.glyph} importantForAccessibility="no-hide-descendants">
        <Text variant="title2" style={s.glyphText}>
          →
        </Text>
      </View>
      <View style={s.middle}>
        <Text variant="headline" style={deleted ? s.struck : undefined}>
          {sentence}
        </Text>
        <Text variant="callout" style={s.secondary}>
          {settlement.settled_on}
          {deleted ? ' · deleted' : ''}
        </Text>
      </View>
      <Text variant="amount" style={[s.amount, deleted ? s.struck : null]}>
        {amountText}
      </Text>
    </Pressable>
  );
}
