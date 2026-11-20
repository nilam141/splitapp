import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, balanceStyle, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Avatar } from '../components/Avatar';
import { Card } from '../components/Card';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { showSnackbar } from '../components/snackbar';
import {
  deleteSettlement,
  useGetFriend,
  useGetGroup,
  useGetGroupBalances,
  useSettleAll,
} from '../api/generated/splitapp';
import { apiErrorOf, invalidateAfterPayment } from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';
import {
  PayRow,
  defaultPayer,
  rowsFromFriend,
  rowsFromTransfers,
} from '../payments/rows';
import { OFFLINE_MESSAGE } from '../payments/messages';

type Props = NativeStackScreenProps<MainStackParamList, 'SettleUp'>;

// SCR-30: choose who pays and which balance, then continue to SCR-31 prefilled. Group scope reads the server's
// transfers (GET /groups/{id}/balances); friend scope reads the per-scope breakdown (GET /friends/{id}).
export function SettleUpScreen({ navigation, route }: Props) {
  const { groupId, friendId } = route.params;
  return groupId ? (
    <GroupScope navigation={navigation} groupId={groupId} />
  ) : (
    <FriendScope navigation={navigation} friendId={friendId ?? ''} />
  );
}

type Nav = Props['navigation'];

function GroupScope({
  navigation,
  groupId,
}: {
  navigation: Nav;
  groupId: string;
}) {
  const group = useGetGroup(groupId);
  const balances = useGetGroupBalances(groupId);
  const g = group.data?.status === 200 ? group.data.data : undefined;
  const b = balances.data?.status === 200 ? balances.data.data : undefined;
  const rows = useMemo(
    () => (b && g ? rowsFromTransfers(b.transfers, groupId, g.name) : []),
    [b, g, groupId],
  );
  const people = useMemo(
    () =>
      (g?.members ?? [])
        .filter(m => !m.left_at)
        .map(m => ({ id: m.user.id, name: m.user.name })),
    [g],
  );
  if (group.isPending || balances.isPending) {
    return <LoadingView label="Loading balances" />;
  }
  if (group.isError || balances.isError) {
    return (
      <ErrorView
        offline
        onRetry={() => {
          group.refetch();
          balances.refetch();
        }}
      />
    );
  }
  if (!g || !b) {
    const status = (group.data ?? balances.data)?.status;
    return (
      <ErrorView
        offline={false}
        message={
          status === 403 ? "You're not a member of this group." : undefined
        }
        onRetry={() => {
          group.refetch();
          balances.refetch();
        }}
      />
    );
  }
  return (
    <SettleList
      navigation={navigation}
      rows={rows}
      people={people}
      groupId={groupId}
      friendId={undefined}
    />
  );
}

function FriendScope({
  navigation,
  friendId,
}: {
  navigation: Nav;
  friendId: string;
}) {
  const { user } = useAuth();
  const query = useGetFriend(friendId);
  const friend = query.data?.status === 200 ? query.data.data : undefined;
  const rows = useMemo(
    () => (friend && user ? rowsFromFriend(friend, user.id) : []),
    [friend, user],
  );
  const people = useMemo(
    () =>
      friend && user
        ? [
            { id: user.id, name: user.name },
            { id: friend.user.id, name: friend.user.name },
          ]
        : [],
    [friend, user],
  );
  if (query.isPending) {
    return <LoadingView label="Loading balances" />;
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
  return (
    <SettleList
      navigation={navigation}
      rows={rows}
      people={people}
      groupId={undefined}
      friendId={friendId}
    />
  );
}

type Person = { id: string; name: string };

function SettleList({
  navigation,
  rows,
  people,
  groupId,
  friendId,
}: {
  navigation: Nav;
  rows: PayRow[];
  people: Person[];
  groupId: string | undefined;
  friendId: string | undefined;
}) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const { user } = useAuth();
  const meId = user?.id ?? '';
  const qc = useQueryClient();
  const { format } = useMoney();
  const nameOf = useNameOf(groupId ?? null);
  const settleAll = useSettleAll();
  const [picked, setPicked] = useState<string | undefined>();
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | undefined>();

  const payer = picked ?? defaultPayer(rows, meId) ?? meId;
  const shown = rows.filter(r => r.fromUserId === payer);
  const nameFor = (id: string) =>
    id === meId ? 'you' : (people.find(p => p.id === id)?.name ?? nameOf(id));

  const sentence = (r: PayRow) =>
    r.fromUserId === meId
      ? `you owe ${nameFor(r.toUserId)}`
      : `${nameFor(r.fromUserId)} owes ${nameFor(r.toUserId)}`;

  const doSettleAll = async () => {
    if (!friendId) {
      return;
    }
    setConfirmAll(false);
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await settleAll.mutateAsync({
        data: { friend_user_id: friendId },
      });
      if (res.status === 201) {
        await invalidateAfterPayment(qc);
        const ids = res.data.items.map(s => s.id);
        showSnackbar(
          ids.length === 0 ? 'Already settled up' : 'Payments recorded',
          ids.length === 0
            ? undefined
            : {
                label: 'Undo',
                onPress: () => {
                  Promise.all(ids.map(id => deleteSettlement(id))).then(() =>
                    invalidateAfterPayment(qc),
                  );
                },
              },
        );
        navigation.goBack();
      } else {
        setBanner(
          apiErrorOf(res)?.message ?? 'Something went wrong. Please try again.',
        );
      }
    } catch {
      setBanner(OFFLINE_MESSAGE);
    } finally {
      setBusy(false);
    }
  };

  const allCount = rows.length;
  return (
    <ScrollView contentContainerStyle={styles.container}>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}
      <Text variant="title2" accessibilityRole="header">
        Who is paying?
      </Text>
      <View style={styles.payers}>
        {people.map(p => {
          const selected = p.id === payer;
          return (
            <Pressable
              key={p.id}
              testID={`payer-${p.id}`}
              accessibilityRole="button"
              accessibilityLabel={`Payer: ${p.id === meId ? 'You' : p.name}`}
              accessibilityState={{ selected }}
              onPress={() => setPicked(p.id)}
              style={[styles.payer, selected ? styles.payerSelected : null]}
            >
              <Avatar name={p.name} size={40} testID={`avatar-${p.id}`} />
              <Text variant="callout" style={styles.payerName}>
                {selected ? '✓ ' : ''}
                {p.id === meId ? 'You' : p.name}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {shown.length === 0 && allCount === 0 ? (
        <View style={styles.settled} testID="settled-up">
          <View style={styles.check}>
            <Text variant="title2" style={styles.checkText}>
              ✓
            </Text>
          </View>
          <Text variant="title2">You are settled up</Text>
        </View>
      ) : shown.length === 0 ? (
        <Text style={styles.hint}>
          {payer === meId ? 'You' : nameFor(payer)} owe
          {payer === meId ? '' : 's'} nothing. Choose who is paying.
        </Text>
      ) : (
        <Card style={styles.card}>
          {shown.map((r, i) => {
            const tone = balanceStyle(
              colors,
              r.fromUserId === meId
                ? -r.amountMinor
                : r.toUserId === meId
                  ? r.amountMinor
                  : 0,
            );
            const amount = format(r.amountMinor, r.currency);
            const chip =
              tone.tone === 'settled'
                ? amount
                : `${tone.sign}${amount} ${tone.word}`;
            const toName = people.find(p => p.id === r.toUserId)?.name ?? '';
            return (
              <Pressable
                key={r.key}
                testID="balance-row"
                accessibilityRole="button"
                accessibilityLabel={`${sentence(r)} ${amount}${r.groupName ? `, ${r.groupName}` : ''}`}
                android_ripple={{ color: colors.border }}
                style={[styles.row, i > 0 ? styles.rowDivider : null]}
                onPress={() =>
                  navigation.navigate('RecordPayment', {
                    groupId: r.groupId,
                    fromUserId: r.fromUserId,
                    toUserId: r.toUserId,
                    amountMinor: r.amountMinor,
                    currency: r.currency,
                    owedMinor: r.amountMinor,
                  })
                }
              >
                <Avatar name={toName || nameFor(r.toUserId)} size={40} />
                <View style={styles.rowText}>
                  <Text variant="headline">{sentence(r)}</Text>
                  <Text variant="callout" style={styles.secondary}>
                    {r.groupName ?? 'Non-group expenses'}
                  </Text>
                </View>
                <View style={[styles.chip, { backgroundColor: tone.fill }]}>
                  <Text variant="amount" style={{ color: tone.text }}>
                    {chip}
                  </Text>
                </View>
              </Pressable>
            );
          })}
          {friendId && allCount > 1 ? (
            <Pressable
              testID="settle-all"
              accessibilityRole="button"
              accessibilityLabel="Settle all balances"
              android_ripple={{ color: colors.border }}
              disabled={busy}
              style={[styles.row, styles.rowDivider]}
              onPress={() => setConfirmAll(true)}
            >
              <Text variant="headline" style={styles.link}>
                Settle all balances
              </Text>
            </Pressable>
          ) : null}
        </Card>
      )}
      {allCount > 0 ? (
        <Text variant="callout" style={styles.hint}>
          Already paid? Tap a balance to record the payment.
        </Text>
      ) : null}

      <ConfirmDialog
        visible={confirmAll}
        title="Settle all balances?"
        message={`This records ${allCount} ${allCount === 1 ? 'payment' : 'payments'} so every balance with this friend is zero. You can undo it afterwards.`}
        confirmLabel="Settle all"
        onClose={() => setConfirmAll(false)}
        onConfirm={doSettleAll}
      />
    </ScrollView>
  );
}

const makeStyles = ({
  colors,
  spacing,
  radius,
  touchTarget,
  layout,
  control,
}: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    banner: {
      backgroundColor: colors.errorSubtle,
      color: colors.errorText,
      padding: spacing.md,
      borderRadius: radius.md,
      marginBottom: spacing.md,
    },
    payers: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      marginVertical: spacing.md,
    },
    payer: {
      minHeight: touchTarget.min,
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.md,
      marginRight: spacing.sm,
      marginBottom: spacing.sm,
      borderRadius: radius.pill,
      backgroundColor: colors.fieldBackground,
    },
    payerSelected: {
      backgroundColor: colors.brandSubtle,
      borderWidth: control.focusRingWidth,
      borderColor: colors.brand,
    },
    payerName: { marginLeft: spacing.sm },
    card: { padding: 0, overflow: 'hidden' },
    row: {
      minHeight: layout.listRowMinHeight,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      flexDirection: 'row',
      alignItems: 'center',
    },
    rowDivider: { borderTopWidth: 1, borderTopColor: colors.border },
    rowText: { flex: 1, marginLeft: spacing.md },
    secondary: { color: colors.textSecondary },
    chip: {
      borderRadius: radius.pill,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.xs,
      marginLeft: spacing.sm,
    },
    link: { color: colors.brand },
    hint: { color: colors.textSecondary, marginTop: spacing.md },
    settled: { alignItems: 'center', marginTop: spacing.xxxl },
    check: {
      width: layout.avatar.lg,
      height: layout.avatar.lg,
      borderRadius: radius.pill,
      backgroundColor: colors.fieldBackground,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.lg,
    },
    checkText: { color: colors.textSecondary },
  });
