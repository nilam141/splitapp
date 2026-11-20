import React, { useState } from 'react';
import { Image, Modal, Pressable, StyleSheet, View } from 'react-native';
import { Theme, useThemedStyles } from '../theme';
import { Button } from '../components/Button';
import { API_BASE_URL } from '../config';

/** The server may return a path; make it absolute against the configured API host. */
export const receiptUri = (url: string): string =>
  url.startsWith('/') ? `${API_BASE_URL}${url}` : url;

// SCR-29: receipt thumbnail, full screen on tap. Uploading needs an image-picker module that is not installed yet.
export function ReceiptThumb({ url }: { url: string }) {
  const styles = useThemedStyles(makeStyles);
  const [open, setOpen] = useState(false);
  const uri = receiptUri(url);
  return (
    <View>
      <Pressable
        accessibilityRole="imagebutton"
        accessibilityLabel="Receipt, tap to enlarge"
        onPress={() => setOpen(true)}
      >
        <Image source={{ uri }} style={styles.thumb} resizeMode="cover" />
      </Pressable>
      <Modal
        visible={open}
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        <View style={styles.full}>
          <Image
            accessibilityLabel="Receipt"
            source={{ uri }}
            style={styles.image}
            resizeMode="contain"
          />
          <Button title="Close" onPress={() => setOpen(false)} />
        </View>
      </Modal>
    </View>
  );
}

const makeStyles = ({ colors, spacing, radius, layout }: Theme) =>
  StyleSheet.create({
    thumb: {
      width: layout.avatar.xl,
      height: layout.avatar.xl,
      borderRadius: radius.md,
      backgroundColor: colors.fieldBackground,
    },
    full: { flex: 1, backgroundColor: colors.background, padding: spacing.lg },
    image: { flex: 1 },
  });
