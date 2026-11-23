import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Card } from '../components/Card';
import { useAuth } from '../auth/AuthContext';
import { isPremium } from '../premium/gate';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'Paywall'>;

export const PREMIUM_BENEFITS: readonly { title: string; detail: string }[] = [
  { title: 'Search expenses', detail: 'Find any expense by its description.' },
  {
    title: 'Export to CSV',
    detail: 'Share a group or friend as a spreadsheet.',
  },
  {
    title: 'Receipt images',
    detail: 'Keep a photo of the bill with the expense.',
  },
];

// SCR-39. Plans, prices and Restore purchases need Play Billing and the purchase-verification endpoint, which are
// Blocked (decision D-C); the screen explains the benefits and says purchasing is not available yet.
export function PaywallScreen({ route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { user } = useAuth();
  const premium = isPremium(user);
  const reason = route.params?.reason;
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" variant="title1">
        {premium ? 'You have Premium' : 'Upgrade to Premium'}
      </Text>
      {premium && user?.premium_until ? (
        <Text style={styles.hint}>
          Premium until {user.premium_until.slice(0, 10)}.
        </Text>
      ) : null}
      {!premium && reason ? (
        <Text style={styles.hint}>
          {reason === 'search'
            ? 'Search is a Premium feature.'
            : reason === 'export'
              ? 'Export is a Premium feature.'
              : 'Receipt images are a Premium feature.'}
        </Text>
      ) : null}
      <View style={styles.benefits}>
        {PREMIUM_BENEFITS.map(b => (
          <Card key={b.title} accessibilityLabel={`${b.title}. ${b.detail}`}>
            <Text variant="headline">{b.title}</Text>
            <Text style={styles.hint}>{b.detail}</Text>
          </Card>
        ))}
      </View>
      {!premium ? (
        <View style={styles.notice} accessibilityRole="alert">
          <Text>Upgrading is not available in this version yet.</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    hint: { color: colors.textSecondary, marginTop: spacing.xs },
    benefits: { marginTop: spacing.lg, gap: spacing.md },
    notice: {
      marginTop: spacing.xl,
      backgroundColor: colors.fieldBackground,
      borderRadius: radius.md,
      padding: spacing.md,
    },
  });
