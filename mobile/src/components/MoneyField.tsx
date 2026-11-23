import React, { useState } from 'react';
import { StyleSheet, TextInputProps, View } from 'react-native';
import { formatMinorAmount } from '../money/format';
import { parseMinor } from '../money/parse';
import { Theme, useThemedStyles } from '../theme';
import { FormField } from './FormField';
import { Text } from './Text';

type Props = Omit<
  TextInputProps,
  'value' | 'onChangeText' | 'keyboardType' | 'secureTextEntry'
> & {
  label: string;
  /** ISO code shown as a fixed prefix chip. */
  currency: string;
  /** Currency exponent: 2 for INR, 0 for JPY. Limits the decimals that can be typed. */
  exponent: number;
  /** Integer minor units, or null while the field is empty. Never a float. */
  onChangeMinor: (minor: number | null) => void;
  /** Existing amount in integer minor units to show on first render (edit screens). */
  initialMinor?: number | null;
  error?: string;
  helper?: string;
};

/** Amount input (design_system 6.2): amountLarge, right-aligned, currency chip, decimals capped by exponent. */
export function MoneyField({
  currency,
  exponent,
  onChangeMinor,
  initialMinor,
  ...rest
}: Props) {
  const styles = useThemedStyles(makeStyles);
  const [text, setText] = useState(() =>
    initialMinor == null
      ? ''
      : formatMinorAmount(initialMinor, exponent).replace(/,/g, ''),
  );

  const onChange = (next: string) => {
    if (next.trim() === '') {
      setText('');
      onChangeMinor(null);
      return;
    }
    const parsed = parseMinor(next, exponent);
    // Reject keystrokes that cannot become a valid amount: the field and the emitted value stay unchanged.
    if (!parsed.ok || (exponent === 0 && next.includes('.'))) {
      return;
    }
    setText(next);
    onChangeMinor(parsed.minor);
  };

  return (
    <FormField
      {...rest}
      value={text}
      onChangeText={onChange}
      keyboardType={exponent === 0 ? 'number-pad' : 'decimal-pad'}
      autoCorrect={false}
      style={styles.input}
      prefix={
        <View style={styles.chip}>
          <Text variant="label" style={styles.chipText}>
            {currency}
          </Text>
        </View>
      }
    />
  );
}

const makeStyles = ({ colors, spacing, radius, typography }: Theme) =>
  StyleSheet.create({
    input: { ...typography.amountLarge, textAlign: 'right' },
    chip: {
      paddingHorizontal: spacing.sm,
      paddingVertical: spacing.xs,
      borderRadius: radius.sm,
      backgroundColor: colors.border,
    },
    chipText: { color: colors.textSecondary },
  });
