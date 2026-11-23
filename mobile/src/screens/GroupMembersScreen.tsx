import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { Avatar } from '../components/Avatar';
import { ListRow } from '../components/ListRow';
import { MemberNetLines } from '../components/BalanceLines';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { useGetGroup, useRemoveGroupMember } from '../api/generated/splitapp';
import {
  apiErrorOf,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import { outstandingBalances } from '../groups/errors';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'GroupMembers'>;
const OFFLINE = "Can't reach the server. Check your connection and try again.";

type Dialog =
  | { kind: 'remove'; userId: string; name: string }
  | { kind: 'info'; title: string; message: string };

// SCR-13 members view (CR-UI-1): a stack screen above Group detail, so Group detail stays mounted underneath and
// its scroll position survives. It reads the same GET /groups/{id} query and does not refetch when data exists.
export function GroupMembersScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { groupId } = route.params;
  const qc = useQueryClient();
  const { user } = useAuth();
  const { format } = useMoney();
  const query = useGetGroup(groupId, { query: { refetchOnMount: false } });
  const removeMember = useRemoveGroupMember();
  const group = query.data?.status === 200 ? query.data.data : undefined;
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [banner, setBanner] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  if (query.isPending) {
    return <LoadingView label="Loading members" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!group) {
    return (
      <ErrorView
        offline={false}
        message={
          query.data?.status === 403
            ? "You're not a member of this group."
            : undefined
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const members = group.members.filter(m => !m.left_at);

  // Same call, refusal handling and invalidation as group settings. A refused call (409) writes nothing.
  const remove = async (userId: string) => {
    setDialog(null);
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await removeMember.mutateAsync({ id: groupId, userId });
      if (res.status === 204) {
        await Promise.all([invalidateGroups(qc), invalidateFriends(qc)]);
      } else if (res.status === 409) {
        const err = apiErrorOf(res);
        const amount = outstandingBalances(err?.details)
          .map(l => format(Math.abs(l.amount_minor), l.currency))
          .join(', ');
        setDialog({
          kind: 'info',
          title: "You can't remove this member yet",
          message: amount
            ? `${err?.message ?? 'Settle all debts first.'} Outstanding: ${amount}.`
            : (err?.message ?? 'Settle all debts first.'),
        });
      } else if (res.status === 403) {
        setBanner("You're not allowed to do that in this group.");
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Something went wrong.');
      }
    } catch {
      setBanner(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      testID="group-members-view"
      contentContainerStyle={styles.container}
    >
      <Text variant="title2" accessibilityRole="header">
        {members.length} {members.length === 1 ? 'member' : 'members'}
      </Text>
      {members.map(m => {
        const isViewer = m.user.id === user?.id;
        const title = `${m.user.name}${isViewer ? ' (you)' : ''}`;
        return (
          <View key={m.user.id} testID={`member-${m.user.id}`}>
            <ListRow
              title={title}
              leading={<Avatar name={m.user.name} />}
              onPress={() =>
                isViewer
                  ? undefined
                  : setDialog({
                      kind: 'remove',
                      userId: m.user.id,
                      name: m.user.name,
                    })
              }
            />
            <View style={styles.chips}>
              <MemberNetLines lines={m.balances} isViewer={isViewer} />
              {isViewer ? null : (
                <Button
                  variant="text"
                  title="Remove"
                  accessibilityLabel={`Remove ${m.user.name}`}
                  disabled={busy}
                  onPress={() =>
                    setDialog({
                      kind: 'remove',
                      userId: m.user.id,
                      name: m.user.name,
                    })
                  }
                />
              )}
            </View>
          </View>
        );
      })}

      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}

      <View style={styles.actions}>
        <Button
          title="Add people"
          onPress={() =>
            navigation.navigate('AddPeople', {
              mode: { kind: 'group-members', groupId },
            })
          }
        />
        <Button
          title="Invite via link"
          variant="outlined"
          onPress={() => navigation.navigate('InviteLink', { groupId })}
        />
      </View>

      <ConfirmDialog
        visible={dialog?.kind === 'remove'}
        title={dialog?.kind === 'remove' ? `Remove ${dialog.name}?` : ''}
        confirmLabel="Remove"
        destructive
        onClose={() => setDialog(null)}
        onConfirm={() => dialog?.kind === 'remove' && remove(dialog.userId)}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'info'}
        title={dialog?.kind === 'info' ? dialog.title : ''}
        message={dialog?.kind === 'info' ? dialog.message : undefined}
        onClose={() => setDialog(null)}
      />
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, layout }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg, paddingBottom: spacing.xxxl },
    chips: {
      paddingLeft: spacing.lg + layout.avatar.md + spacing.md,
      paddingRight: spacing.lg,
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    error: { color: colors.errorText, marginVertical: spacing.sm },
    actions: { marginTop: spacing.xxl, gap: spacing.md },
  });
