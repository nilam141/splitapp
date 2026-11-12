import { Platform, ToastAndroid } from 'react-native';

/** Short confirmation toast (Android). A no-op elsewhere. */
export function showToast(message: string): void {
  if (Platform.OS === 'android') {
    ToastAndroid.show(message, ToastAndroid.SHORT);
  }
}
