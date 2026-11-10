import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';

export function AccountScreen() {
  const { user, signOut } = useAuth();
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Account
      </Text>
      {user ? <Text>{user.name}</Text> : null}
      {user ? <Text style={styles.email}>{user.email}</Text> : null}
      <View style={styles.logout}>
        <Button title="Log out" onPress={signOut} />
      </View>
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
  title: { fontSize: 22, fontWeight: '600', marginBottom: 8 },
  email: { color: '#555' },
  logout: { marginTop: 24 },
});
