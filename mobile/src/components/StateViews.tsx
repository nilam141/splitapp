import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { Theme, useTheme, useThemedStyles } from '../theme';
import { Text } from './Text';
import { Button } from './Button';

export function LoadingView({ label }: { label: string }) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      <ActivityIndicator accessibilityLabel={label} color={colors.brand} />
    </View>
  );
}

type ErrorProps = {
  /** true when the request itself failed (no response): treated as offline. */
  offline: boolean;
  message?: string;
  onRetry: () => void;
};

export function ErrorView({ offline, message, onRetry }: ErrorProps) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.center}>
      <Text accessibilityRole="alert" style={styles.text}>
        {offline
          ? "You're offline or the server can't be reached."
          : (message ?? 'Something went wrong. Please try again.')}
      </Text>
      <Button title="Retry" onPress={onRetry} />
    </View>
  );
}

export function EmptyView({
  title,
  hint,
  actionLabel,
  onAction,
}: {
  title: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{title}</Text>
      {hint ? <Text style={styles.text}>{hint}</Text> : null}
      {actionLabel && onAction ? (
        <Button title={actionLabel} onPress={onAction} />
      ) : null}
    </View>
  );
}

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    center: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    title: {
      fontSize: 18,
      fontWeight: '600',
      marginBottom: 6,
      textAlign: 'center',
    },
    text: { color: colors.textPrimary, textAlign: 'center', marginBottom: 12 },
  });
