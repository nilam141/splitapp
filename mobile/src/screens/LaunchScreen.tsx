import React from 'react';
import {
  ActivityIndicator,
  Button,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useAuth } from '../auth/AuthContext';

// SCR-01 while the session is being restored; error with Retry if the server is unreachable.
export function LaunchScreen() {
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
        <ActivityIndicator accessibilityLabel="Loading" />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: { fontSize: 32, fontWeight: '700', marginBottom: 16 },
  msg: { marginBottom: 12 },
});
