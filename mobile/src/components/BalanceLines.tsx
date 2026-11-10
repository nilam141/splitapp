import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { BalanceLine } from '../api/generated/model';
import { useMoney } from '../money/useMoney';

// Green = owed to the viewer, orange = the viewer owes (positive amount_minor = owed to the viewer).
export function BalanceLines({ lines }: { lines: BalanceLine[] }) {
  const { format } = useMoney();
  const nonZero = lines.filter(l => l.amount_minor !== 0);
  if (nonZero.length === 0) {
    return <Text style={styles.settled}>settled up</Text>;
  }
  return (
    <View>
      {nonZero.map(l => (
        <Text
          key={l.currency}
          style={l.amount_minor > 0 ? styles.owed : styles.owe}
        >
          {l.amount_minor > 0 ? 'owes you ' : 'you owe '}
          {format(Math.abs(l.amount_minor), l.currency)}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  owed: { color: '#1b7f3b' },
  owe: { color: '#c25e00' },
  settled: { color: '#666' },
});
