import React, { useEffect, useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useUpdateCurrentUser } from '../api/generated/splitapp';
import type { UserUpdate } from '../api/generated/model';
import { apiErrorOf } from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import { normalizeEmail } from '../auth/validation';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { CurrencyPicker } from '../components/CurrencyPicker';
import { FormField } from '../components/FormField';
import { isE164, normalizePhone } from '../people/validation';

type Field = 'name' | 'email' | 'phone' | 'currency' | 'timeZone';
const OFFLINE = "Can't reach the server. Try again.";

// SCR-11. Each field saves on its own with PATCH /users/me.
export function AccountScreen() {
  const { user, signOut, setUser } = useAuth();
  const update = useUpdateCurrentUser();
  const [name, setName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [phone, setPhone] = useState(user?.phone_e164 ?? '');
  const [timeZone, setTimeZone] = useState(user?.time_zone ?? '');
  const [saving, setSaving] = useState<Field | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [saved, setSaved] = useState<Field | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);

  // Keep the inputs in step with the stored profile (e.g. after a save).
  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
      setPhone(user.phone_e164 ?? '');
      setTimeZone(user.time_zone);
    }
  }, [user]);

  if (!user) {
    return null;
  }

  const save = async (field: Field, changes: UserUpdate) => {
    setSaving(field);
    setSaved(null);
    setErrors(e => ({ ...e, [field]: undefined }));
    try {
      const res = await update.mutateAsync({ data: changes });
      if (res.status === 200) {
        setUser(res.data);
        setSaved(field);
        return;
      }
      const err = apiErrorOf(res);
      let message = err?.message ?? 'Could not save. Try again.';
      if (res.status === 409) {
        message =
          field === 'phone'
            ? 'This phone number is used by another account.'
            : 'This email is used by another account.';
      } else if (res.status === 401) {
        message = 'Your session has ended. Log in again.';
      }
      setErrors(e => ({ ...e, [field]: message }));
    } catch {
      setErrors(e => ({ ...e, [field]: OFFLINE }));
    } finally {
      setSaving(null);
    }
  };

  const fail = (field: Field, message: string) =>
    setErrors(e => ({ ...e, [field]: message }));

  const saveName = () => {
    const n = name.trim();
    if (n.length < 1 || n.length > 100) {
      return fail('name', 'Enter your name (1 to 100 characters).');
    }
    return save('name', { name: n });
  };
  const saveEmail = () => {
    const v = normalizeEmail(email);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || v.length > 254) {
      return fail('email', 'Enter a valid email address.');
    }
    return save('email', { email: v });
  };
  const savePhone = () => {
    const v = normalizePhone(phone);
    if (v === '') {
      return save('phone', { phone_e164: null });
    }
    if (!isE164(v)) {
      return fail('phone', 'Use the format +919876543210.');
    }
    return save('phone', { phone_e164: v });
  };
  const saveTimeZone = () => {
    const v = timeZone.trim();
    if (!v) {
      return fail('timeZone', 'Enter a time zone such as Asia/Kolkata.');
    }
    return save('timeZone', { time_zone: v });
  };

  const row = (
    field: Field,
    label: string,
    value: string,
    set: (v: string) => void,
    onSave: () => void,
    original: string,
    extra: object = {},
  ) => (
    <View>
      <FormField
        label={label}
        value={value}
        onChangeText={set}
        editable={saving === null}
        error={errors[field]}
        {...extra}
      />
      {value !== original ? (
        <Button
          title={saving === field ? 'Saving...' : `Save ${label.toLowerCase()}`}
          onPress={onSave}
          disabled={saving !== null}
        />
      ) : saved === field ? (
        <Text style={styles.saved}>Saved</Text>
      ) : null}
    </View>
  );

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <Text accessibilityRole="header" style={styles.title}>
        Your profile
      </Text>
      {row('name', 'Name', name, setName, saveName, user.name, {
        autoCapitalize: 'words',
        maxLength: 100,
      })}
      {row('email', 'Email', email, setEmail, saveEmail, user.email, {
        keyboardType: 'email-address',
      })}
      {row(
        'phone',
        'Phone',
        phone,
        setPhone,
        savePhone,
        user.phone_e164 ?? '',
        { keyboardType: 'phone-pad', placeholder: '+919876543210' },
      )}
      {row(
        'timeZone',
        'Time zone',
        timeZone,
        setTimeZone,
        saveTimeZone,
        user.time_zone,
      )}

      <View style={styles.block}>
        <Text style={styles.label}>Default currency</Text>
        <Text accessibilityLabel="Default currency value">
          {user.default_currency}
        </Text>
        <Button
          title={saving === 'currency' ? 'Saving...' : 'Change currency'}
          onPress={() => setPickerOpen(true)}
          disabled={saving !== null}
        />
        {errors.currency ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {errors.currency}
          </Text>
        ) : null}
        {saved === 'currency' ? <Text style={styles.saved}>Saved</Text> : null}
      </View>

      <View style={styles.block}>
        <Text style={styles.label}>Plan</Text>
        <Text>
          {user.plan === 'premium' && user.premium_until
            ? `Premium until ${user.premium_until.slice(0, 10)}`
            : user.plan === 'premium'
              ? 'Premium'
              : 'Free'}
        </Text>
      </View>

      <View style={styles.logout}>
        <Button title="Log out" onPress={() => setConfirmLogout(true)} />
      </View>

      <CurrencyPicker
        visible={pickerOpen}
        selected={user.default_currency}
        onSelect={code => {
          if (code !== user.default_currency) {
            save('currency', { default_currency: code });
          }
        }}
        onClose={() => setPickerOpen(false)}
      />
      <ConfirmDialog
        visible={confirmLogout}
        title="Log out?"
        confirmLabel="Log out"
        onClose={() => setConfirmLogout(false)}
        onConfirm={() => {
          setConfirmLogout(false);
          signOut();
        }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24 },
  title: { fontSize: 22, fontWeight: '600', marginBottom: 16 },
  block: { marginTop: 12, marginBottom: 8 },
  label: { fontSize: 14, color: '#333', marginBottom: 4 },
  saved: { color: '#1b7f3b', marginBottom: 8 },
  error: { color: '#b00020', marginTop: 4 },
  logout: { marginTop: 24 },
});
