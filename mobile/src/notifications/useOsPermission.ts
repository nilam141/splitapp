import { useEffect, useState } from 'react';
import { AppState, PermissionsAndroid, Platform } from 'react-native';

const ANDROID_13 = 33;

/**
 * True when the OS notification permission is known to be denied (Android 13+). Only reads the status; asking
 * for the permission belongs to push registration, which is Blocked (decision D-C). Re-checks when the app
 * returns to the foreground, so the banner clears after the user fixes it in system settings.
 */
export function useNotificationPermissionDenied(): boolean {
  const [denied, setDenied] = useState(false);
  useEffect(() => {
    if (Platform.OS !== 'android' || Number(Platform.Version) < ANDROID_13) {
      return;
    }
    let alive = true;
    const check = () => {
      PermissionsAndroid.check(
        PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
      )
        .then(granted => alive && setDenied(!granted))
        .catch(() => undefined);
    };
    check();
    const sub = AppState.addEventListener('change', s => {
      if (s === 'active') {
        check();
      }
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return denied;
}
