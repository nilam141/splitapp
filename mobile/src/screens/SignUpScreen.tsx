import React, { useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRegisterUser } from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';
import { FormField } from '../components/FormField';
import { CurrencyPicker } from '../components/CurrencyPicker';
import {
  normalizeEmail,
  validateSignUp,
  FieldErrors,
} from '../auth/validation';
import { AuthFormError, mapAuthError, networkError } from '../auth/errors';

const DEFAULT_CURRENCY = 'INR';
const DEFAULT_TIME_ZONE = 'Asia/Kolkata';

function deviceTimeZone(): string {
  try {
    return (
      Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_TIME_ZONE
    );
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

export function SignUpScreen() {
  const { startSession } = useAuth();
  const register = useRegisterUser();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [currency, setCurrency] = useState(DEFAULT_CURRENCY);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [banner, setBanner] = useState<string | undefined>();

  const apply = (e: AuthFormError) => {
    setErrors(e.field ? { [e.field.name]: e.field.message } : {});
    setBanner(e.banner);
  };

  const submit = async () => {
    const found = validateSignUp({ name, email, password });
    setErrors(found);
    setBanner(undefined);
    if (Object.keys(found).length > 0) {
      return;
    }
    try {
      const res = await register.mutateAsync({
        data: {
          name: name.trim(),
          email: normalizeEmail(email),
          password,
          default_currency: currency,
          time_zone: deviceTimeZone(),
        },
      });
      if (res.status === 201) {
        await startSession(res.data);
      } else {
        apply(mapAuthError(res));
      }
    } catch {
      apply(networkError());
    }
  };

  const busy = register.isPending;
  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <FormField
        label="Full name"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        autoComplete="name"
        editable={!busy}
        error={errors.name}
      />
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
        autoComplete="new-password"
        editable={!busy}
        error={errors.password}
      />
      <Button
        title={showPassword ? 'Hide password' : 'Show password'}
        onPress={() => setShowPassword(v => !v)}
      />
      <View style={styles.currency}>
        <Text>Default currency: {currency}</Text>
        <Button
          title="Change"
          onPress={() => setPickerOpen(true)}
          disabled={busy}
        />
      </View>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.submit}>
        <Button
          title={busy ? 'Signing up...' : 'Sign up'}
          onPress={submit}
          disabled={busy}
        />
      </View>
      <CurrencyPicker
        visible={pickerOpen}
        selected={currency}
        onSelect={setCurrency}
        onClose={() => setPickerOpen(false)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24 },
  currency: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 16,
  },
  banner: { color: '#b00020', marginTop: 12 },
  submit: { marginTop: 20 },
});
