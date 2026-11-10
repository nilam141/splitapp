import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

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

const styles = StyleSheet.create({
  wrap: { marginBottom: 14 },
  label: { marginBottom: 4, fontSize: 14, color: '#333' },
  row: { flexDirection: 'row', gap: 8 },
  seg: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 16,
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  segOn: { backgroundColor: '#1b6e5a', borderColor: '#1b6e5a' },
  textOn: { color: '#fff' },
});
