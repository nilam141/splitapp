import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useThemedStyles } from '../theme';
import { Text } from './Text';

type Props<T extends string> = {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
};

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: Props<T>) {
  const styles = useThemedStyles(({ colors, touchTarget }) =>
    StyleSheet.create({
      wrap: { marginBottom: 14 },
      label: { marginBottom: 4, fontSize: 14, color: colors.textSecondary },
      row: { flexDirection: 'row', gap: 8 },
      seg: {
        borderWidth: 1,
        borderColor: colors.borderStrong,
        borderRadius: 16,
        paddingVertical: 6,
        paddingHorizontal: 12,
        minHeight: touchTarget.min,
        justifyContent: 'center',
      },
      segOn: { backgroundColor: colors.brand, borderColor: colors.brand },
      textOn: { color: colors.textOnBrand },
    }),
  );
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.row}>
        {options.map(o => (
          <Pressable
            key={o}
            accessibilityRole="button"
            accessibilityLabel={`${label}: ${o}`}
            accessibilityState={{ selected: o === value }}
            onPress={() => onChange(o)}
            style={[styles.seg, o === value ? styles.segOn : null]}
          >
            <Text style={o === value ? styles.textOn : undefined}>{o}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}
