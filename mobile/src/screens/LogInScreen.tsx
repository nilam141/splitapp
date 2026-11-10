import React, { useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLogin } from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';
import { FormField } from '../components/FormField';
import { normalizeEmail, validateLogIn, FieldErrors } from '../auth/validation';
import { AuthFormError, mapAuthError, networkError } from '../auth/errors';

export function LogInScreen() {
  const { startSession } = useAuth();
  const login = useLogin();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [banner, setBanner] = useState<string | undefined>();
  const [showPassword, setShowPassword] = useState(false);

  const apply = (e: AuthFormError) => {
    setErrors(e.field ? { [e.field.name]: e.field.message } : {});
    setBanner(e.banner);
  };

  const submit = async () => {
    const found = validateLogIn({ email, password });
    setErrors(found);
    setBanner(undefined);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      const res = await login.mutateAsync({
        data: { email: normalizeEmail(email), password },
      });
      if (res.status === 200) {
        await startSession(res.data);
      } else {
        apply(mapAuthError(res));
      }
    } catch {
      apply(networkError());
    }
  };

  const busy = login.isPending;
  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <FormField
        label="Email"
        value={email}
        onChangeText={setEmail}
        keyboardType="email-address"
        autoComplete="email"
        editable={!busy}
        error={errors.email}
      />
      <FormField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry={!showPassword}
        autoComplete="current-password"
        editable={!busy}
        error={errors.password}
      />
      <Button
        title={showPassword ? 'Hide password' : 'Show password'}
        onPress={() => setShowPassword(v => !v)}
      />
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.submit}>
        <Button
          title={busy ? 'Logging in...' : 'Log in'}
          onPress={submit}
          disabled={busy}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24 },
  banner: { color: '#b00020', marginTop: 12 },
  submit: { marginTop: 20 },
});
