import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { FormField } from '../components/FormField';
import { useConfirmPasswordReset } from '../api/generated/splitapp';
import { apiErrorOf } from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import type { AuthStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<AuthStackParamList, 'PasswordReset'>;

// SCR-06: set a new password from a reset link. 410 = link expired.
export function PasswordResetScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { startSession } = useAuth();
  const confirm = useConfirmPasswordReset();
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [banner, setBanner] = useState<string | undefined>();
  const [expired, setExpired] = useState(false);

  const submit = async () => {
    setBanner(undefined);
    if (password.length < 8 || password.length > 128) {
      setError('Password must be 8 to 128 characters.');
      return;
    }
    setError(undefined);
    try {
      const res = await confirm.mutateAsync({
        data: { token: route.params.token, new_password: password },
      });
      if (res.status === 200) {
        await startSession(res.data);
      } else if (res.status === 410) {
        setExpired(true);
      } else {
        setBanner(
          apiErrorOf(res)?.message ?? 'Could not set the password. Try again.',
        );
      }
    } catch {
      setBanner("Can't reach the server. Check your connection and try again.");
    }
  };

  if (expired) {
    return (
      <View style={styles.container}>
        <Text accessibilityRole="alert" variant="title2">
          This link has expired
        </Text>
        <Text style={styles.hint}>
          Reset links work once and for a short time. Ask for a new one.
        </Text>
        <Button
          title="Request a new link"
          onPress={() => navigation.navigate('LogIn', undefined)}
        />
      </View>
    );
  }

  const busy = confirm.isPending;
  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <FormField
        label="New password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry={!show}
        autoComplete="new-password"
        editable={!busy}
        error={error}
      />
      <Button
        title={show ? 'Hide password' : 'Show password'}
        variant="text"
        onPress={() => setShow(v => !v)}
      />
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.submit}>
        <Button
          title="Save password"
          onPress={submit}
          loading={busy}
          disabled={busy}
        />
      </View>
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.xxl },
    hint: { color: colors.textSecondary, marginVertical: spacing.md },
    banner: { color: colors.errorText, marginTop: spacing.md },
    submit: { marginTop: spacing.xl },
  });
