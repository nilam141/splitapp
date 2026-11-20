import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';

type Props = { title: string; subtitle?: string };

export function PlaceholderScreen({ title, subtitle }: Props) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
    </View>
  );
}

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    title: { fontSize: 22, fontWeight: '600' },
    subtitle: { marginTop: 8, fontSize: 14, color: colors.textSecondary },
  });
