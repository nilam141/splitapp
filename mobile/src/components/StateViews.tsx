import React from 'react';
import {
  ActivityIndicator,
  Button,
  StyleSheet,
  Text,
  View,
} from 'react-native';

export function LoadingView({ label }: { label: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator accessibilityLabel={label} />
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

const styles = StyleSheet.create({
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
  text: { color: '#444', textAlign: 'center', marginBottom: 12 },
});
