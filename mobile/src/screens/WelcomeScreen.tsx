import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AuthStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<AuthStackParamList, 'Welcome'>;

export function WelcomeScreen({ navigation }: Props) {
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        SplitApp
      </Text>
      <Text style={styles.subtitle}>Share expenses, settle up.</Text>
      <View style={styles.buttons}>
        <Button title="Sign up" onPress={() => navigation.navigate('SignUp')} />
        <View style={styles.gap} />
        <Button title="Log in" onPress={() => navigation.navigate('LogIn')} />
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
  title: { fontSize: 32, fontWeight: '700' },
  subtitle: { marginTop: 8, fontSize: 16, color: '#555' },
  buttons: { marginTop: 32, width: '100%' },
  gap: { height: 12 },
});
