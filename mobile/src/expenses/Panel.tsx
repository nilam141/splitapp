import React from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';

type Props = {
  title: string;
  children: React.ReactNode;
  onDone?: () => void;
  doneDisabled?: boolean;
  onCancel: () => void;
};

// Shared frame for SCR-23 to SCR-28: they are panels of the expense form so the draft stays in one place.
export function Panel({
  title,
  children,
  onDone,
  doneDisabled,
  onCancel,
}: Props) {
  return (
    <View style={styles.flex}>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
      >
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        {children}
      </ScrollView>
      <View style={styles.footer}>
        <Button title="Cancel" onPress={onCancel} />
        {onDone ? (
          <Button title="Done" onPress={onDone} disabled={doneDisabled} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  body: { padding: 16 },
  title: { fontSize: 20, fontWeight: '600', marginBottom: 12 },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
