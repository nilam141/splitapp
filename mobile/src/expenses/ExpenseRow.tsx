import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { Expense } from '../api/generated/model';
import { formatMinorAmount } from '../money/format';
import { parseMinor } from '../money/parse';

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];
const SHORT = MONTHS.map(m => m.slice(0, 3));

function monthIndex(isoDate: string): number {
  const r = parseMinor(isoDate.slice(5, 7), 0);
  return (r.ok ? r.minor : 1) - 1;
}

/** "November 2026" for 2026-11-05. */
export function monthLabel(isoDate: string): string {
  return `${MONTHS[monthIndex(isoDate)] ?? ''} ${isoDate.slice(0, 4)}`;
}

function dayLabel(isoDate: string): string {
  return `${SHORT[monthIndex(isoDate)] ?? ''} ${isoDate.slice(8, 10).replace(/^0/, '')}`;
}

type Props = {
  expense: Expense;
  nameOf: (id: string) => string;
  exponentOf: (currency: string) => number;
  onPress: () => void;
};

// One expense row (SCR-13 timeline, SCR-19 list): date, description, payer + amount, the viewer's effect.
export function ExpenseRow({ expense, nameOf, exponentOf, onPress }: Props) {
  const exponent = exponentOf(expense.total.currency);
  const fmt = (minor: number) => formatMinorAmount(minor, exponent);
  const payer =
    expense.payers.length === 1
      ? nameOf(expense.payers[0].user_id)
      : `${expense.payers.length} people`;
  const net = expense.my_net?.amount_minor ?? 0;
  const effect =
    net > 0
      ? `you lent ${fmt(net)}`
      : net < 0
        ? `you owe ${fmt(-net)}`
        : 'no balance change';
  const deleted = !!expense.deleted_at;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Expense: ${expense.description}`}
      onPress={onPress}
      style={styles.row}
    >
      <Text style={styles.date}>{dayLabel(expense.expense_date)}</Text>
      <View style={styles.middle}>
        <Text style={[styles.title, deleted ? styles.deleted : null]}>
          {expense.description}
        </Text>
        <Text style={styles.sub}>
          {`${payer} paid ${expense.total.currency} ${fmt(expense.total.amount_minor)}`}
        </Text>
      </View>
      <Text style={[styles.effect, net < 0 ? styles.owe : styles.lent]}>
        {effect}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 10,
  },
  date: { width: 52, color: '#666' },
  middle: { flex: 1 },
  title: { fontSize: 16, fontWeight: '500' },
  deleted: { textDecorationLine: 'line-through' },
  sub: { color: '#555', fontSize: 13 },
  effect: { fontSize: 13, maxWidth: 120, textAlign: 'right' },
  lent: { color: '#1b7f3b' },
  owe: { color: '#c25e00' },
});
