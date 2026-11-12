import React, { useMemo, useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { formatMinorAmount } from '../money/format';
import type { SplitType } from '../splits/engine';
import { Panel } from './Panel';
import {
  applyShortcut,
  evaluateSplit,
  type ExpenseDraft,
  type Person,
  type Shortcut,
  type SplitDraft,
} from './draft';

const TABS: { type: SplitType; label: string }[] = [
  { type: 'equal', label: 'Equal' },
  { type: 'exact', label: 'Exact' },
  { type: 'percent', label: 'Percent' },
  { type: 'shares', label: 'Shares' },
  { type: 'adjustment', label: 'Adjustment' },
];

const SHORTCUTS: { key: Shortcut; label: string }[] = [
  { key: 'you_paid_equal', label: 'You paid, split equally' },
  { key: 'they_paid_equal', label: 'They paid, split equally' },
  { key: 'you_owed_full', label: 'You are owed the full amount' },
  { key: 'they_owed_full', label: 'They are owed the full amount' },
];

type Props = {
  split: SplitDraft;
  people: Person[];
  meId: string;
  nameOf: (id: string) => string;
  total: number | undefined;
  exponent: number;
  onDone: (result: Partial<Pick<ExpenseDraft, 'split' | 'payers'>>) => void;
  onCancel: () => void;
};

// SCR-23. Amounts recompute on every keystroke with the pure engine in src/splits.
export function SplitPanel({
  split: initial,
  people,
  meId,
  nameOf,
  total,
  exponent,
  onDone,
  onCancel,
}: Props) {
  const [split, setSplit] = useState<SplitDraft>(initial);
  const [shortcutNote, setShortcutNote] = useState<string | undefined>();
  const fmt = (minor: number) => formatMinorAmount(minor, exponent);
  const evaluation = useMemo(
    () => evaluateSplit(split, people, total, exponent, fmt),
    // fmt is derived from exponent
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [split, people, total, exponent],
  );
  const other =
    people.length === 2 ? people.find(p => p.id !== meId) : undefined;

  const setValue = (id: string, text: string) =>
    setSplit(s => ({ ...s, values: { ...s.values, [id]: text } }));
  const toggle = (id: string) =>
    setSplit(s => ({
      ...s,
      included: s.included.includes(id)
        ? s.included.filter(x => x !== id)
        : [...s.included, id],
    }));

  const shortcut = (key: Shortcut) => {
    if (total === undefined || !other) {
      setShortcutNote('Enter the amount first.');
      return;
    }
    const applied = applyShortcut(key, meId, other.id, total, exponent);
    onDone(applied);
  };

  const keyboard = split.type === 'shares' ? 'number-pad' : 'decimal-pad';
  const unit =
    split.type === 'percent' ? '%' : split.type === 'shares' ? 'shares' : '';

  return (
    <Panel
      title="Adjust split"
      onCancel={onCancel}
      onDone={() => onDone({ split })}
      doneDisabled={!evaluation.valid}
    >
      {other ? (
        <View style={styles.shortcuts}>
          {SHORTCUTS.map(s => (
            <Pressable
              key={s.key}
              accessibilityRole="button"
              accessibilityLabel={s.label}
              onPress={() => shortcut(s.key)}
              style={styles.shortcut}
            >
              <Text>
                {s.label
                  .replace('They', other.name)
                  .replace('they', other.name)}
              </Text>
            </Pressable>
          ))}
          {shortcutNote ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {shortcutNote}
            </Text>
          ) : null}
        </View>
      ) : null}

      <View style={styles.tabs}>
        {TABS.map(t => (
          <Pressable
            key={t.type}
            accessibilityRole="tab"
            accessibilityLabel={`Split tab: ${t.label}`}
            accessibilityState={{ selected: split.type === t.type }}
            onPress={() => setSplit(s => ({ ...s, type: t.type }))}
            style={[styles.tab, split.type === t.type ? styles.tabOn : null]}
          >
            <Text style={split.type === t.type ? styles.tabTextOn : undefined}>
              {t.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {people.map((p, i) => {
        const row = evaluation.rows[i];
        const owedText =
          row.owed === undefined ? '' : formatMinorAmount(row.owed, exponent);
        return (
          <View key={p.id} style={styles.row}>
            {split.type === 'equal' ? (
              <Switch
                accessibilityLabel={`Include ${nameOf(p.id)}`}
                value={split.included.includes(p.id)}
                onValueChange={() => toggle(p.id)}
              />
            ) : null}
            <Text style={styles.name}>{nameOf(p.id)}</Text>
            {split.type !== 'equal' ? (
              <TextInput
                accessibilityLabel={`${nameOf(p.id)} value`}
                keyboardType={keyboard}
                // shares max 999; percent max 100.00 (6 characters)
                maxLength={
                  split.type === 'shares'
                    ? 3
                    : split.type === 'percent'
                      ? 6
                      : undefined
                }
                value={split.values[p.id] ?? ''}
                onChangeText={t => setValue(p.id, t)}
                placeholder="0"
                style={[
                  styles.input,
                  row.inputError ? styles.inputError : null,
                ]}
              />
            ) : null}
            {unit ? <Text style={styles.unit}>{unit}</Text> : null}
            <Text
              accessibilityLabel={`${nameOf(p.id)} owes`}
              style={styles.owed}
            >
              {owedText}
            </Text>
          </View>
        );
      })}
      {evaluation.rows.map(r =>
        r.inputError ? (
          <Text key={r.userId} accessibilityRole="alert" style={styles.error}>
            {nameOf(r.userId)}: {r.inputError}
          </Text>
        ) : null,
      )}

      <View style={styles.footerBox}>
        {evaluation.footer.map(line => (
          <Text key={line} style={evaluation.valid ? styles.ok : styles.error}>
            {line}
          </Text>
        ))}
        {!evaluation.valid &&
        evaluation.footer.length === 0 &&
        evaluation.error &&
        !shortcutNote ? (
          <Text style={styles.error}>{evaluation.error}</Text>
        ) : null}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  shortcuts: { marginBottom: 12, gap: 6 },
  shortcut: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 10,
  },
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  tab: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 16,
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  tabOn: { backgroundColor: '#1b6e5a', borderColor: '#1b6e5a' },
  tabTextOn: { color: '#fff' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
  },
  name: { flex: 1, fontSize: 16 },
  input: {
    width: 90,
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 6,
    textAlign: 'right',
  },
  inputError: { borderColor: '#b00020' },
  unit: { color: '#666' },
  owed: { width: 90, textAlign: 'right', fontVariant: ['tabular-nums'] },
  footerBox: { marginTop: 12 },
  ok: { color: '#1b7f3b' },
  error: { color: '#b00020' },
});
