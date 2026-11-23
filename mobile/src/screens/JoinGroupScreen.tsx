import React, { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { showToast } from '../components/toast';
import { useJoinGroup } from '../api/generated/splitapp';
import {
  apiErrorOf,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'JoinGroup'>;

// SCR-18 without the preview: the group name, member list and placeholder claim need the invite-preview
// endpoint, which is not in the contract yet (decision D-C). Joining sends no placeholder claim.
export function JoinGroupScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const qc = useQueryClient();
  const join = useJoinGroup();
  const [banner, setBanner] = useState<string | undefined>();

  const submit = async () => {
    setBanner(undefined);
    try {
      const res = await join.mutateAsync({
        data: { token: route.params.token },
      });
      if (res.status === 200) {
        await Promise.all([invalidateGroups(qc), invalidateFriends(qc)]);
        navigation.replace('GroupDetail', { groupId: res.data.id });
      } else if (res.status === 410) {
        // FLOW-10: an expired link goes to SCR-07 with a toast.
        showToast('Invite no longer valid');
        navigation.popToTop();
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Could not join the group.');
      }
    } catch {
      setBanner("Can't reach the server. Check your connection and try again.");
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" variant="title2">
        Join this group?
      </Text>
      <Text style={styles.hint}>
        You were invited with a link. Joining lets you see the group's expenses
        and balances.
      </Text>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}
      <Button
        title="Join group"
        onPress={submit}
        loading={join.isPending}
        disabled={join.isPending}
      />
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.xxl },
    hint: { color: colors.textSecondary, marginVertical: spacing.md },
    error: { color: colors.errorText, marginBottom: spacing.md },
  });
