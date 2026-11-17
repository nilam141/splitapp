import React from 'react';
import { Modal, StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Text } from './Text';
import { Button } from './Button';

type Props = {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  /** Omit for an info-only dialog with a single OK button. */
  onConfirm?: () => void;
  onClose: () => void;
  destructive?: boolean;
};

export function ConfirmDialog({
  visible,
  title,
  message,
  confirmLabel = 'Confirm',
  onConfirm,
  onClose,
  destructive = false,
}: Props) {
  const styles = useThemedStyles(makeStyles);
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.backdrop}>
        <View style={styles.card} accessibilityViewIsModal>
          <Text accessibilityRole="header" style={styles.title}>
            {title}
          </Text>
          {message ? <Text style={styles.message}>{message}</Text> : null}
          <View style={styles.buttons}>
            <Button title={onConfirm ? 'Cancel' : 'OK'} onPress={onClose} />
            {onConfirm ? (
              <Button
                title={confirmLabel}
                destructive={destructive}
                onPress={onConfirm}
              />
            ) : null}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const makeStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    backdrop: {
      flex: 1,
      backgroundColor: colors.scrim,
      justifyContent: 'center',
      padding: 24,
    },
    card: {
      backgroundColor: colors.surfaceRaised,
      borderRadius: 8,
      padding: 20,
    },
    title: { fontSize: 18, fontWeight: '600', marginBottom: 8 },
    message: { fontSize: 15, color: colors.textPrimary, marginBottom: 16 },
    buttons: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12 },
  });
