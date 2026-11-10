import React from 'react';
import { Button, Modal, StyleSheet, Text, View } from 'react-native';

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
}: Props) {
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
                color="#b00020"
                onPress={onConfirm}
              />
            ) : null}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    padding: 24,
  },
  card: { backgroundColor: '#fff', borderRadius: 8, padding: 20 },
  title: { fontSize: 18, fontWeight: '600', marginBottom: 8 },
  message: { fontSize: 15, color: '#333', marginBottom: 16 },
  buttons: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12 },
});
