import React from 'react';
import { ScrollView, Share, StyleSheet } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { useAuth } from '../auth/AuthContext';

// SCR-42, "My code" half. Scanning and code lookup are Blocked (decision D-C); a QR image needs a library that
// is not installed, so the code is shown as text and can be shared.
export function MyCodeScreen() {
  const styles = useThemedStyles(makeStyles);
  const { user } = useAuth();
  const code = user?.friend_code;
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="callout" style={styles.label}>
        Your friend code
      </Text>
      {code ? (
        <>
          <Text
            selectable
            variant="display"
            accessibilityLabel={`Your friend code ${code.split('').join(' ')}`}
          >
            {code}
          </Text>
          <Text style={styles.hint}>Friends can add you with this code.</Text>
          <Button
            title="Share code"
            onPress={() => {
              Share.share({ message: code }).catch(() => undefined);
            }}
          />
        </>
      ) : (
        <Text style={styles.hint}>Your code is not available yet.</Text>
      )}
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.xxl },
    label: { color: colors.textSecondary, marginBottom: spacing.sm },
    hint: { color: colors.textSecondary, marginVertical: spacing.md },
  });
