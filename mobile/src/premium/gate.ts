import { useCallback } from 'react';
import { getCurrentUser } from '../api/generated/splitapp';
import { useNavigation } from '@react-navigation/native';
import type { NavigationProp } from '@react-navigation/native';
import type { UserMe } from '../api/generated/model';
import { useAuth } from '../auth/AuthContext';
import type { MainStackParamList } from '../navigation/types';

export const isPremium = (user: UserMe | null | undefined): boolean =>
  user?.plan === 'premium';

type Gated = 'Search' | 'ExportSheet';
type GatedParams = {
  Search: undefined;
  ExportSheet: { groupId?: string; friendId?: string };
};

/**
 * F-46 entry point: a premium user opens the feature, a free user lands on the paywall (SCR-39). The server stays
 * authoritative: a 402 PREMIUM_REQUIRED from the feature itself also leads to the paywall.
 */
export function useGatedNavigate() {
  const { user } = useAuth();
  const navigation = useNavigation<NavigationProp<MainStackParamList>>();
  return useCallback(
    <K extends Gated>(screen: K, params: GatedParams[K]) => {
      if (isPremium(user)) {
        (navigation.navigate as (s: string, p?: object) => void)(
          screen,
          params,
        );
      } else {
        navigation.navigate('Paywall', {
          reason: screen === 'Search' ? 'search' : 'export',
        });
      }
    },
    [navigation, user],
  );
}

/** After a 402 the stored plan is out of date (for example it expired): reload the profile so the paywall is right. */
export function useRefreshPlan() {
  const { setUser } = useAuth();
  return useCallback(async () => {
    try {
      const res = await getCurrentUser();
      if (res.status === 200) {
        setUser(res.data);
      }
    } catch {
      // offline: keep what we have
    }
  }, [setUser]);
}
