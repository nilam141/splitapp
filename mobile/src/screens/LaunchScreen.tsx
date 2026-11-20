import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { Theme, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { useAuth } from '../auth/AuthContext';

// SCR-01 while the session is being restored; error with Retry if the server is unreachable.
export function LaunchScreen() {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const { status, retryRestore } = useAuth();
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        SplitApp
      </Text>
      {status === 'error' ? (
        <>
          <Text style={styles.msg}>Can't reach the server.</Text>
          <Button title="Retry" onPress={retryRestore} />
        </>
      ) : (
        <ActivityIndicator accessibilityLabel="Loading" color={colors.brand} />
      )}
    </View>
  );
}

const makeStyles = (_theme: Theme) =>
  StyleSheet.create({
    container: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    title: { fontSize: 32, fontWeight: '700', marginBottom: 16 },
    msg: { marginBottom: 12 },
  });
