import React from 'react';
import { StyleSheet, TextInputProps, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text, TextInput } from './Text';

type Props = TextInputProps & { label: string; error?: string };

export function FormField({ label, error, style, ...rest }: Props) {
  const styles = useThemedStyles(makeStyles);
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

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    wrap: { marginBottom: 14 },
    label: { marginBottom: 4, fontSize: 14, color: colors.textPrimary },
    input: {
      borderWidth: 1,
      borderColor: colors.borderStrong,
      borderRadius: 6,
      padding: 10,
      fontSize: 16,
    },
    inputError: { borderColor: colors.error },
    error: { marginTop: 4, color: colors.errorText, fontSize: 13 },
  });
