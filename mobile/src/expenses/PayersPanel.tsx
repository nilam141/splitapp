import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { formatMinorAmount } from '../money/format';
import { Panel } from './Panel';
import { evaluatePayers, type PayersDraft, type Person } from './draft';

type Props = {
  payers: PayersDraft;
  people: Person[];
  nameOf: (id: string) => string;
  total: number | undefined;
  exponent: number;
  onDone: (payers: PayersDraft) => void;
  onCancel: () => void;
};

// SCR-24: one payer, or several with an amount each that must add up to the total.
export function PayersPanel({
  payers: initial,
  people,
  nameOf,
  total,
  exponent,
  onDone,
  onCancel,
}: Props) {
  const [payers, setPayers] = useState<PayersDraft>(initial);
  const fmt = (minor: number) => formatMinorAmount(minor, exponent);
  const evaluation = useMemo(
    () => evaluatePayers(payers, people, total, exponent, fmt),
    // fmt is derived from exponent
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [payers, people, total, exponent],
  );
  const multiple = payers.mode === 'multiple';

  return (
    <Panel
      title="Who paid?"
      onCancel={onCancel}
      onDone={() => onDone(payers)}
      doneDisabled={multiple && !evaluation.valid}
    >
      {!multiple
        ? people.map(p => {
            const selected =
              payers.mode === 'single' && payers.payerId === p.id;
            return (
              <Pressable
                key={p.id}
                accessibilityRole="radio"
                accessibilityLabel={`Paid by ${nameOf(p.id)}`}
                accessibilityState={{ selected }}
                onPress={() => onDone({ mode: 'single', payerId: p.id })}
                style={styles.row}
              >
                <Text style={selected ? styles.selected : undefined}>
                  {selected ? '(x) ' : '( ) '}
                  {nameOf(p.id)}
                </Text>
              </Pressable>
            );
          })
        : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={multiple ? 'Use a single payer' : 'Multiple people'}
        onPress={() =>
          setPayers(
            multiple
              ? { mode: 'single', payerId: people[0].id }
              : { mode: 'multiple', amounts: {} },
          )
        }
        style={styles.row}
      >
        <Text style={styles.link}>
          {multiple ? 'Use a single payer' : 'Multiple people'}
        </Text>
      </Pressable>
      {payers.mode === 'multiple'
        ? people.map(p => (
            <View key={p.id} style={styles.amountRow}>
              <Text style={styles.name}>{nameOf(p.id)}</Text>
              <TextInput
                accessibilityLabel={`${nameOf(p.id)} paid`}
                keyboardType="decimal-pad"
                placeholder="0"
                value={payers.amounts[p.id] ?? ''}
                onChangeText={t =>
                  setPayers({
                    mode: 'multiple',
                    amounts: { ...payers.amounts, [p.id]: t },
                  })
                }
                style={styles.input}
              />
            </View>
          ))
        : null}
      {multiple ? (
        <View>
          {evaluation.footer.map(l => (
            <Text key={l} style={evaluation.valid ? styles.ok : styles.error}>
              {l}
            </Text>
          ))}
          {Object.entries(evaluation.inputErrors).map(([id, msg]) => (
            <Text key={id} accessibilityRole="alert" style={styles.error}>
              {nameOf(id)}: {msg}
            </Text>
          ))}
        </View>
      ) : null}
    </Panel>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  selected: { fontWeight: '700' },
  link: { color: '#1b6e5a' },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
  },
  name: { flex: 1, fontSize: 16 },
  input: {
    width: 120,
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 6,
    textAlign: 'right',
  },
  ok: { color: '#1b7f3b' },
  error: { color: '#b00020' },
});
