import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { AuthStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<AuthStackParamList, 'SessionExpired'>;

// SCR-44: shown when the refresh token was rejected while the app was in use.
export function SessionExpiredScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Session expired
      </Text>
      <Text style={styles.text}>
        For your security you have been signed out. Log in again to continue.
      </Text>
      <Button
        title="Log in"
        onPress={() =>
          navigation.navigate('LogIn', { email: route.params.email })
        }
      />
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
    title: { fontSize: 24, fontWeight: '700', marginBottom: 8 },
    text: { color: colors.textPrimary, textAlign: 'center', marginBottom: 20 },
  });
