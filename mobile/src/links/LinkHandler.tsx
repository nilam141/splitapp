import React, { useEffect, useState } from 'react';
import { Linking } from 'react-native';
import type { NavigationContainerRef } from '@react-navigation/native';
import { useAuth } from '../auth/AuthContext';
import type { RootStackParamList } from '../navigation/types';
import { parseDeepLink, type DeepLink } from './parse';

/**
 * F-54 / S6-M-1: routes opened links. A join or add-friend link that arrives while logged out is kept and
 * opened after login (the link survives login). A reset link opens SCR-06 when logged out and is ignored when
 * signed in; unknown links do nothing.
 */
export function LinkHandler({
  navigationRef,
  ready,
}: {
  navigationRef: React.RefObject<NavigationContainerRef<RootStackParamList> | null>;
  /** true once the navigation container has mounted a navigator */
  ready: boolean;
}) {
  const { status } = useAuth();
  const [pending, setPending] = useState<DeepLink | null>(null);

  useEffect(() => {
    let alive = true;
    Linking.getInitialURL().then(url => {
      const link = parseDeepLink(url);
      if (alive && link) {
        setPending(link);
      }
    });
    const sub = Linking.addEventListener('url', e => {
      const link = parseDeepLink(e.url);
      if (link) {
        setPending(link);
      }
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);

  useEffect(() => {
    const navigation = navigationRef.current;
    if (
      !pending ||
      !ready ||
      !navigation ||
      (status !== 'signedIn' && status !== 'signedOut')
    ) {
      return;
    }
    if (pending.kind === 'reset') {
      if (status === 'signedOut') {
        navigation.navigate('Auth', {
          screen: 'PasswordReset',
          params: { token: pending.token },
        });
      }
      setPending(null);
      return;
    }
    if (status === 'signedIn') {
      navigation.navigate('Main', {
        screen: pending.kind === 'join' ? 'JoinGroup' : 'AddFriendByCode',
        params:
          pending.kind === 'join'
            ? { token: pending.token }
            : { code: pending.code },
        initial: false,
      } as never);
      setPending(null);
    }
  }, [pending, status, ready, navigationRef]);

  return null;
}
