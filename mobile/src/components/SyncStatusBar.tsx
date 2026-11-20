import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from './Text';
import { Button } from './Button';
import { useIsOffline } from '../offline/connectivity';
import { discardWrite } from '../offline/queue';
import { useQueueSync } from '../offline/useQueueSync';

/**
 * Offline and unsynced state (F-53): "N unsynced" while saved changes wait for a connection, a Discard for changes
 * the server rejected, and a quiet notice when offline. Neutral colours: being offline is not an error.
 */
export function SyncStatusBar() {
  const styles = useThemedStyles(makeStyles);
  const offline = useIsOffline();
  const { queue, syncNow } = useQueueSync();
  const pending = queue.filter(i => i.state === 'pending');
  const failed = queue.filter(i => i.state === 'failed');

  if (!offline && pending.length === 0 && failed.length === 0) {
    return null;
  }
  return (
    <View style={styles.bar}>
      {offline ? (
        <Text accessibilityLiveRegion="polite" style={styles.text}>
          You're offline. Showing saved data.
        </Text>
      ) : null}
      {pending.length > 0 ? (
        <View style={styles.row}>
          <Text
            testID="unsynced-badge"
            accessibilityLabel={`${pending.length} unsynced ${pending.length === 1 ? 'change' : 'changes'}`}
            style={styles.text}
          >
            {pending.length} unsynced
          </Text>
          <Button title="Sync now" variant="text" onPress={() => syncNow()} />
        </View>
      ) : null}
      {failed.map(f => (
        <View key={f.id} style={styles.row} accessibilityRole="alert">
          <Text style={styles.error}>
            A saved change could not be synced: {f.error}
          </Text>
          <Button
            title="Discard"
            variant="text"
            onPress={() => discardWrite(f.id)}
          />
        </View>
      ))}
    </View>
  );
}

const makeStyles = ({ colors, spacing }: Theme) =>
  StyleSheet.create({
    bar: {
      backgroundColor: colors.fieldBackground,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.xs,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    text: { color: colors.textPrimary, flexShrink: 1 },
    error: { color: colors.errorText, flexShrink: 1 },
  });
