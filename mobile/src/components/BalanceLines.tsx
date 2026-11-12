import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { BalanceLine } from '../api/generated/model';
import { useMoney } from '../money/useMoney';

/** Non-zero lines only, one per currency (never summed across currencies), ordered by currency code. */
export function visibleLines(lines: BalanceLine[]): BalanceLine[] {
  return lines
    .filter(l => l.amount_minor !== 0)
    .sort((a, b) =>
      a.currency < b.currency ? -1 : a.currency > b.currency ? 1 : 0,
    );
}

// Green = owed to the viewer, orange = the viewer owes (positive amount_minor = owed to the viewer).
export function BalanceLines({ lines }: { lines: BalanceLine[] }) {
  const { format } = useMoney();
  const nonZero = visibleLines(lines);
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

/**
 * A member's own net in a group ("gets back X" / "owes X"), per currency. Positive = gets back.
 * Same colours as BalanceLines.
 */
export function MemberNetLines({
  lines,
  isViewer = false,
}: {
  lines: BalanceLine[];
  /** True when the member is the signed-in user ("You" owe / get back). */
  isViewer?: boolean;
}) {
  const { format } = useMoney();
  const nonZero = visibleLines(lines);
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
          {l.amount_minor > 0
            ? isViewer
              ? 'get back '
              : 'gets back '
            : isViewer
              ? 'owe '
              : 'owes '}
          {format(Math.abs(l.amount_minor), l.currency)} in total
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
