import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Theme, balanceStyle, useTheme, useThemedStyles } from '../theme';
import { Text } from './Text';
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

// Colors come from balanceStyle(); the wording ("owes you" / "you owe") carries the meaning, color only reinforces it.
// Positive amount_minor = owed to the viewer.
export function BalanceLines({ lines }: { lines: BalanceLine[] }) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
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
          accessibilityLabel={`${l.amount_minor > 0 ? 'owes you' : 'you owe'} ${format(Math.abs(l.amount_minor), l.currency)}`}
          style={{ color: balanceStyle(colors, l.amount_minor).text }}
        >
          {l.amount_minor > 0 ? 'owes you ' : 'you owe '}
          {balanceStyle(colors, l.amount_minor).sign}
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
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const { format } = useMoney();
  const nonZero = visibleLines(lines);
  if (nonZero.length === 0) {
    return <Text style={styles.settled}>settled up</Text>;
  }
  return (
    <View>
      {nonZero.map(l => {
        const verb =
          l.amount_minor > 0
            ? isViewer
              ? 'get back'
              : 'gets back'
            : isViewer
              ? 'owe'
              : 'owes';
        const amount = format(Math.abs(l.amount_minor), l.currency);
        return (
          <Text
            key={l.currency}
            accessibilityLabel={`${verb} ${amount} in total`}
            style={{ color: balanceStyle(colors, l.amount_minor).text }}
          >
            {verb} {balanceStyle(colors, l.amount_minor).sign}
            {amount} in total
          </Text>
        );
      })}
    </View>
  );
}

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    settled: { color: balanceStyle(colors, 0).text },
  });
