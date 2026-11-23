import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { REMINDER_CHOICES, type RepeatChoice } from './draft';
import { REPEAT_CHOICES, REPEAT_LABEL, reminderLabel } from './repeatLabels';

type Props = {
  repeat: RepeatChoice;
  reminderDays: number | null;
  onChange: (repeat: RepeatChoice, reminderDays: number | null) => void;
};

function Option({
  group,
  label,
  selected,
  onPress,
}: {
  group: string;
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  const styles = useThemedStyles(makeStyles);
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={`${group}: ${label}`}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={styles.row}
    >
      <View style={[styles.dot, selected ? styles.dotOn : null]} />
      <Text>{label}</Text>
    </Pressable>
  );
}

// SCR-27: Repeat (never / weekly / fortnightly / monthly / yearly) and, only while repeating, Reminder (OQ-22).
export function RepeatSection({ repeat, reminderDays, onChange }: Props) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View>
      <Text accessibilityRole="header" variant="headline" style={styles.head}>
        Repeat
      </Text>
      {REPEAT_CHOICES.map(c => (
        <Option
          key={c}
          group="Repeat"
          label={REPEAT_LABEL[c]}
          selected={c === repeat}
          onPress={() => onChange(c, c === 'never' ? null : reminderDays)}
        />
      ))}
      {repeat !== 'never' ? (
        <View>
          <Text
            accessibilityRole="header"
            variant="headline"
            style={styles.head}
          >
            Reminder
          </Text>
          {REMINDER_CHOICES.map(d => (
            <Option
              key={String(d)}
              group="Reminder"
              label={reminderLabel(d)}
              selected={d === reminderDays}
              onPress={() => onChange(repeat, d)}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

const makeStyles = ({ colors, spacing, touchTarget }: Theme) =>
  StyleSheet.create({
    head: { marginTop: spacing.lg, marginBottom: spacing.xs },
    row: {
      minHeight: touchTarget.min,
      flexDirection: 'row',
      alignItems: 'center',
    },
    dot: {
      width: spacing.xl,
      height: spacing.xl,
      borderRadius: spacing.md,
      borderWidth: 2,
      borderColor: colors.borderStrong,
      marginRight: spacing.md,
    },
    dotOn: { borderColor: colors.brand, backgroundColor: colors.brand },
  });
