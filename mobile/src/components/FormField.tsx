import React from 'react';
import {
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';

type Props = TextInputProps & { label: string; error?: string };

export function FormField({ label, error, style, ...rest }: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        autoCapitalize="none"
        style={[styles.input, error ? styles.inputError : null, style]}
        {...rest}
      />
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: 14 },
  label: { marginBottom: 4, fontSize: 14, color: '#333' },
  input: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 10,
    fontSize: 16,
  },
  inputError: { borderColor: '#b00020' },
  error: { marginTop: 4, color: '#b00020', fontSize: 13 },
});
