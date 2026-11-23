import React, { useState } from 'react';
import { Linking, ScrollView, StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { Switch } from '../components/Switch';
import { useUpdateCurrentUser } from '../api/generated/splitapp';
import type { NotificationPrefs } from '../api/generated/model';
import { apiErrorOf } from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import {
  NOTIFICATION_TYPES,
  NOT_SENT_CAPTION,
  prefValue,
} from '../notifications/types';
import { useNotificationPermissionDenied } from '../notifications/useOsPermission';

// SCR-34: one switch per notification type. Each toggle sends only its own key (the server merges key by key).
export function NotificationSettingsScreen() {
  const styles = useThemedStyles(makeStyles);
  const { user, setUser } = useAuth();
  const update = useUpdateCurrentUser();
  const osDenied = useNotificationPermissionDenied();
  const [pending, setPending] = useState<Partial<NotificationPrefs>>({});
  const [error, setError] = useState<string | undefined>();

  if (!user) {
    return null;
  }

  const toggle = async (key: keyof NotificationPrefs, value: boolean) => {
    setError(undefined);
    setPending(p => ({ ...p, [key]: value }));
    try {
      const res = await update.mutateAsync({
        data: { notification_prefs: { [key]: value } },
      });
      if (res.status === 200) {
        setUser(res.data);
      } else {
        setError(
          apiErrorOf(res)?.message ?? 'Could not save. Try again in a moment.',
        );
      }
    } catch {
      setError("Can't reach the server. The setting was not changed.");
    } finally {
      setPending(p => {
        const next = { ...p };
        delete next[key];
        return next;
      });
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      {osDenied ? (
        <View style={styles.notice} accessibilityRole="alert">
          <Text>
            Notifications are turned off for this app in system settings.
          </Text>
          <Button
            title="Open settings"
            variant="text"
            onPress={() => Linking.openSettings()}
          />
        </View>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      {NOTIFICATION_TYPES.map(t => {
        const value =
          pending[t.key] ?? prefValue(user.notification_prefs, t.key);
        return (
          <View key={t.key} style={styles.row}>
            <View style={styles.labelBox}>
              <Text>{t.label}</Text>
              {t.notSent ? (
                <Text variant="caption" style={styles.helper}>
                  {NOT_SENT_CAPTION}
                </Text>
              ) : null}
            </View>
            <Switch
              accessibilityLabel={t.label}
              value={value}
              onValueChange={v => toggle(t.key, v)}
            />
          </View>
        );
      })}
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius, touchTarget }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    notice: {
      backgroundColor: colors.fieldBackground,
      borderRadius: radius.md,
      padding: spacing.md,
      marginBottom: spacing.md,
    },
    error: { color: colors.errorText, marginBottom: spacing.md },
    row: {
      minHeight: touchTarget.min,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    labelBox: { flex: 1, marginRight: spacing.md, paddingVertical: spacing.sm },
    helper: { color: colors.textSecondary },
  });
