import React, { useState } from 'react';
import {
  Button,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  useGetFriend,
  useListGroups,
  useRemoveFriend,
} from '../api/generated/splitapp';
import {
  apiErrorOf,
  invalidateExpenses,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { formatMoney } from '../money/format';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'FriendSettings'>;
const OFFLINE = "Can't reach the server. Check your connection and try again.";

type Dialog = { kind: 'confirm' } | { kind: 'shared'; groups: string[] } | null;

/** details.group_ids of a 409 SHARED_GROUPS_EXIST, when well formed. */
function sharedGroupIds(details: unknown): string[] {
  const ids = (details as { group_ids?: unknown } | undefined)?.group_ids;
  return Array.isArray(ids)
    ? ids.filter((x): x is string => typeof x === 'string')
    : [];
}

// SCR-20: shared groups and the Remove friend flow. Removing is never blocked by a balance (OQ-32), so the
// confirmation warns what will be deleted and shows the current non-group balance.
export function FriendSettingsScreen({ navigation, route }: Props) {
  const { friendId } = route.params;
  const qc = useQueryClient();
  const { exponentOf } = useMoney();
  const query = useGetFriend(friendId);
  const groupsQuery = useListGroups();
  const remove = useRemoveFriend();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [banner, setBanner] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const friend = query.data?.status === 200 ? query.data.data : undefined;

  if (query.isPending) {
    return <LoadingView label="Loading friend" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!friend) {
    return (
      <ErrorView
        offline={false}
        message={
          query.data?.status === 404
            ? 'This person is no longer in your friends list.'
            : undefined
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const sharedGroups = friend.breakdown.filter(
    b => b.scope === 'group' && b.group_id,
  );
  const groupNames = new Map<string, string>();
  sharedGroups.forEach(b =>
    groupNames.set(b.group_id as string, b.group_name ?? 'Group'),
  );
  if (groupsQuery.data?.status === 200) {
    groupsQuery.data.data.items.forEach(g => groupNames.set(g.id, g.name));
  }

  const nonGroup = friend.breakdown
    .filter(b => b.scope === 'non_group')
    .flatMap(b => b.balances)
    .filter(l => l.amount_minor !== 0);

  const confirmRemove = async () => {
    setDialog(null);
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await remove.mutateAsync({ userId: friendId });
      if (res.status === 204) {
        await Promise.all([
          invalidateFriends(qc),
          invalidateGroups(qc),
          invalidateExpenses(qc),
        ]);
        navigation.navigate('Tabs', { screen: 'Friends' });
        return;
      }
      if (res.status === 409) {
        const ids = sharedGroupIds(apiErrorOf(res)?.details);
        setDialog({
          kind: 'shared',
          groups: ids.map(id => groupNames.get(id) ?? 'A shared group'),
        });
      } else if (res.status === 404) {
        await invalidateFriends(qc);
        setBanner('This person is already removed from your friends.');
      } else {
        setBanner(
          apiErrorOf(res)?.message ?? 'Something went wrong. Please try again.',
        );
      }
    } catch {
      setBanner(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  const balanceText = nonGroup
    .map(l =>
      formatMoney(Math.abs(l.amount_minor), l.currency, exponentOf(l.currency)),
    )
    .join(' and ');
  const warning =
    `Non-group expenses, non-group payments and any balance with ${friend.user.name} will be deleted for both of you.` +
    (nonGroup.length > 0
      ? ` The current non-group balance is ${balanceText}.`
      : '') +
    ' Group expenses are not affected.';

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        {friend.user.name}
      </Text>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}

      <Text style={styles.section}>Shared groups</Text>
      {sharedGroups.length === 0 ? (
        <Text style={styles.muted}>No shared groups</Text>
      ) : (
        sharedGroups.map(b => (
          <Pressable
            key={b.group_id as string}
            accessibilityRole="button"
            accessibilityLabel={`Group: ${b.group_name ?? 'Group'}`}
            onPress={() =>
              navigation.navigate('GroupDetail', {
                groupId: b.group_id as string,
              })
            }
            style={styles.row}
          >
            <Text>{b.group_name ?? 'Group'}</Text>
          </Pressable>
        ))
      )}

      <View style={styles.remove}>
        <Button
          title="Remove friend"
          color="#b00020"
          disabled={busy}
          onPress={() => setDialog({ kind: 'confirm' })}
        />
      </View>

      <ConfirmDialog
        visible={dialog?.kind === 'confirm'}
        title={`Remove ${friend.user.name}?`}
        message={warning}
        confirmLabel="Remove"
        onConfirm={confirmRemove}
        onClose={() => setDialog(null)}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'shared'}
        title={`Can't remove ${friend.user.name} yet`}
        message={
          dialog?.kind === 'shared'
            ? `You still share ${dialog.groups.length === 1 ? 'this group' : 'these groups'}:\n${dialog.groups.map(g => `- ${g}`).join('\n')}\nLeave ${dialog.groups.length === 1 ? 'it' : 'them'} first, then remove this friend.`
            : undefined
        }
        onClose={() => setDialog(null)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
  banner: {
    backgroundColor: '#fde8e8',
    color: '#8a1c1c',
    padding: 10,
    borderRadius: 6,
    marginBottom: 12,
  },
  section: { fontSize: 16, fontWeight: '600', marginTop: 16, marginBottom: 6 },
  muted: { color: '#666' },
  row: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  remove: { marginTop: 32, alignItems: 'flex-start' },
});
