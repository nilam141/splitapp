import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AuthStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<AuthStackParamList, 'Welcome'>;

export function WelcomeScreen({ navigation }: Props) {
  const styles = useThemedStyles(makeStyles);
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

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    title: { fontSize: 32, fontWeight: '700' },
    subtitle: { marginTop: 8, fontSize: 16, color: colors.textSecondary },
    buttons: { marginTop: 32, width: '100%' },
    gap: { height: 12 },
  });
