import React, { useEffect, useState } from 'react';
import {
  Button,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  useDeleteGroup,
  useGetGroup,
  useRemoveGroupMember,
  useUpdateGroup,
} from '../api/generated/splitapp';
import type {
  GroupType as GroupTypeT,
  GroupUpdate,
} from '../api/generated/model';
import { GroupType } from '../api/generated/model';
import {
  apiErrorOf,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import type { MainStackParamList } from '../navigation/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { FormField } from '../components/FormField';
import { Segmented } from '../components/Segmented';
import { ErrorView, LoadingView } from '../components/StateViews';
import { outstandingBalances } from '../groups/errors';
import { useMoney } from '../money/useMoney';

type Props = NativeStackScreenProps<MainStackParamList, 'GroupSettings'>;
const TYPES = [
  GroupType.home,
  GroupType.trip,
  GroupType.couple,
  GroupType.other,
] as const;
const OFFLINE = "Can't reach the server. Check your connection and try again.";

type Dialog =
  | { kind: 'remove'; userId: string; name: string }
  | { kind: 'leave' }
  | { kind: 'delete1' }
  | { kind: 'delete2' }
  | { kind: 'info'; title: string; message: string };

// SCR-14.
export function GroupSettingsScreen({ navigation, route }: Props) {
  const { groupId } = route.params;
  const qc = useQueryClient();
  const { user } = useAuth();
  const { format } = useMoney();
  const query = useGetGroup(groupId);
  const update = useUpdateGroup();
  const removeMember = useRemoveGroupMember();
  const deleteGroup = useDeleteGroup();
  const group = query.data?.status === 200 ? query.data.data : undefined;

  const [name, setName] = useState('');
  const [nameError, setNameError] = useState<string | undefined>();
  const [banner, setBanner] = useState<string | undefined>();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [busy, setBusy] = useState(false);

  // Seed the field once the group arrives (and when someone else renames it).
  useEffect(() => {
    if (group) {
      setName(group.name);
    }
  }, [group?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  if (query.isPending) {
    return <LoadingView label="Loading group" />;
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
  const afterMembershipEnds = async () => {
    // Former co-members become explicit friends server side, so the friend queries must refetch.
    await Promise.all([invalidateGroups(qc), invalidateFriends(qc)]);
  };

  const patch = async (changes: Omit<GroupUpdate, 'version'>) => {
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await update.mutateAsync({
        id: groupId,
        data: { version: group.version, ...changes },
      });
      if (res.status === 200) {
        await invalidateGroups(qc);
      } else if (res.status === 409) {
        await invalidateGroups(qc);
        setBanner(
          'This group was changed by someone else. We reloaded it; try again.',
        );
      } else if (res.status === 422) {
        setNameError(apiErrorOf(res)?.message ?? 'That value is not allowed.');
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Could not save the change.');
      }
    } catch {
      setBanner(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  const saveName = () => {
    const n = name.trim();
    if (n.length < 1 || n.length > 100) {
      setNameError('Enter a group name (1 to 100 characters).');
      return;
    }
    setNameError(undefined);
    if (n !== group.name) {
      patch({ name: n });
    }
  };

  // Shared by remove-member and leave. A refused call (409) writes nothing server side.
  const endMembership = async (userId: string, leaving: boolean) => {
    setDialog(null);
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await removeMember.mutateAsync({ id: groupId, userId });
      if (res.status === 204) {
        await afterMembershipEnds();
        if (leaving) {
          navigation.popToTop();
        }
      } else if (res.status === 409) {
        const err = apiErrorOf(res);
        const lines = outstandingBalances(err?.details);
        const amount = lines
          .map(l => format(Math.abs(l.amount_minor), l.currency))
          .join(', ');
        setDialog({
          kind: 'info',
          title: leaving
            ? "You can't leave yet"
            : "You can't remove this member yet",
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

  const doDelete = async () => {
    setDialog(null);
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await deleteGroup.mutateAsync({ id: groupId });
      // 409 ALREADY_DELETED means the goal is already met.
      if (res.status === 204 || res.status === 409) {
        await afterMembershipEnds();
        navigation.popToTop();
      } else if (res.status === 403) {
        setBanner("You're not allowed to delete this group.");
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Could not delete the group.');
      }
    } catch {
      setBanner(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <FormField
        label="Group name"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        maxLength={100}
        editable={!busy}
        error={nameError}
      />
      <Button title="Save name" onPress={saveName} disabled={busy} />

      <View style={styles.gap} />
      <Segmented
        label="Type"
        options={TYPES}
        value={group.group_type}
        onChange={(t: GroupTypeT) =>
          t !== group.group_type && patch({ group_type: t })
        }
      />
      <View style={styles.switchRow}>
        <Text>Simplify debts</Text>
        <Switch
          accessibilityLabel="Simplify debts"
          value={group.simplify_debts}
          disabled={busy}
          onValueChange={v => patch({ simplify_debts: v })}
        />
      </View>

      <Text style={styles.section}>Members</Text>
      {members.map(m => (
        <View key={m.user.id} style={styles.memberRow}>
          <Text>
            {m.user.name}
            {m.user.id === user?.id ? ' (you)' : ''}
          </Text>
          {m.user.id !== user?.id ? (
            <Button
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
          ) : null}
        </View>
      ))}
      <Button
        title="Add people"
        onPress={() =>
          navigation.navigate('AddPeople', {
            mode: { kind: 'group-members', groupId },
          })
        }
      />

      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}

      <View style={styles.danger}>
        <Button
          title="Leave group"
          color="#b00020"
          disabled={busy}
          onPress={() => setDialog({ kind: 'leave' })}
        />
        <View style={styles.gap} />
        <Button
          title="Delete group"
          color="#b00020"
          disabled={busy}
          onPress={() => setDialog({ kind: 'delete1' })}
        />
      </View>

      <ConfirmDialog
        visible={dialog?.kind === 'remove'}
        title={dialog?.kind === 'remove' ? `Remove ${dialog.name}?` : ''}
        confirmLabel="Remove"
        onClose={() => setDialog(null)}
        onConfirm={() =>
          dialog?.kind === 'remove' && endMembership(dialog.userId, false)
        }
      />
      <ConfirmDialog
        visible={dialog?.kind === 'leave'}
        title="Leave this group?"
        message="You will stay friends with the other members."
        confirmLabel="Leave"
        onClose={() => setDialog(null)}
        onConfirm={() => endMembership('me', true)}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'delete1'}
        title="Delete this group?"
        message="It will be deleted for everyone in it."
        confirmLabel="Continue"
        onClose={() => setDialog(null)}
        onConfirm={() => setDialog({ kind: 'delete2' })}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'delete2'}
        title={`Really delete "${group.name}"?`}
        message="Members stay on your friends list."
        confirmLabel="Delete group"
        onClose={() => setDialog(null)}
        onConfirm={doDelete}
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

const styles = StyleSheet.create({
  container: { padding: 16 },
  gap: { height: 12 },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  section: { fontSize: 16, fontWeight: '600', marginTop: 16, marginBottom: 6 },
  memberRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  error: { color: '#b00020', marginVertical: 8 },
  danger: { marginTop: 32 },
});
