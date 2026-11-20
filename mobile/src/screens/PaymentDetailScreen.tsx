import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Avatar } from '../components/Avatar';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { showSnackbar } from '../components/snackbar';
import {
  useDeleteSettlement,
  useGetGroup,
  useGetSettlement,
  useRestoreSettlement,
} from '../api/generated/splitapp';
import { apiErrorOf, invalidateAfterPayment } from '../api/helpers';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';
import {
  OFFLINE_MESSAGE,
  PAYMENT_CONFLICT_MESSAGE,
} from '../payments/messages';

type Props = NativeStackScreenProps<MainStackParamList, 'PaymentDetail'>;

// SCR-32: "X paid Y amount", date, group; Edit, Delete (confirmed) and Restore.
export function PaymentDetailScreen({ navigation, route }: Props) {
  const { settlementId } = route.params;
  const styles = useThemedStyles(makeStyles);
  const qc = useQueryClient();
  const { format } = useMoney();
  const query = useGetSettlement(settlementId);
  const s = query.data?.status === 200 ? query.data.data : undefined;
  const nameOf = useNameOf(s ? (s.group_id ?? null) : undefined);
  const group = useGetGroup(s?.group_id ?? '', {
    query: { enabled: !!s?.group_id },
  });
  const groupName =
    group.data?.status === 200 ? group.data.data.name : undefined;
  const del = useDeleteSettlement();
  const restore = useRestoreSettlement();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | undefined>();

  if (query.isPending) {
    return <LoadingView label="Loading payment" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!s) {
    return (
      <ErrorView
        offline={false}
        message={
          query.data?.status === 404 ? 'Cannot find this payment.' : undefined
        }
        onRetry={() => navigation.goBack()}
      />
    );
  }

  const deleted = !!s.deleted_at;
  const from = nameOf(s.from_user_id);
  const to = nameOf(s.to_user_id);
  const amount = format(s.amount.amount_minor, s.amount.currency);
  const summary = `${from} paid ${to} ${amount}`;

  const run = async (
    action: () => Promise<{ status: number; data?: unknown }>,
    message: string,
  ) => {
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await action();
      if (res.status === 200) {
        await invalidateAfterPayment(qc);
        showSnackbar(message);
      } else if (res.status === 409) {
        const code = apiErrorOf(res)?.code;
        await invalidateAfterPayment(qc);
        if (code !== 'ALREADY_DELETED' && code !== 'NOT_DELETED') {
          setBanner(apiErrorOf(res)?.message ?? PAYMENT_CONFLICT_MESSAGE);
        }
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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      {deleted ? (
        <View style={styles.deleted} testID="deleted-banner">
          <Text accessibilityRole="alert">
            {`This payment was deleted on ${(s.deleted_at ?? '').slice(0, 10)}. It is not counted in balances.`}
          </Text>
          <Button
            title="Restore"
            variant="secondary"
            disabled={busy}
            onPress={() =>
              run(
                () => restore.mutateAsync({ id: settlementId }),
                'Payment restored',
              )
            }
          />
        </View>
      ) : null}
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}

      <View style={styles.parties}>
        <Avatar name={from} size={56} testID="avatar-from" />
        <Text variant="title2" style={styles.arrow}>
          →
        </Text>
        <Avatar name={to} size={56} testID="avatar-to" />
      </View>
      <Text
        variant="title2"
        accessibilityRole="header"
        style={[styles.summary, deleted ? styles.struck : null]}
      >
        {summary}
      </Text>
      <Text variant="callout" style={styles.meta}>
        {s.settled_on}
      </Text>
      <Text variant="callout" style={styles.meta}>
        {s.group_id ? (groupName ?? 'Group') : 'Non-group'}
      </Text>
      {s.note ? <Text style={styles.note}>{s.note}</Text> : null}
      <Text variant="caption" style={styles.meta}>
        {`recorded by ${nameOf(s.created_by)} on ${s.created_at.slice(0, 10)}`}
      </Text>

      {!deleted ? (
        <View style={styles.actions}>
          <Button
            title="Edit"
            variant="secondary"
            disabled={busy}
            onPress={() =>
              navigation.navigate('RecordPayment', { settlementId })
            }
          />
          <View style={styles.gap} />
          <Button
            title="Delete"
            destructive
            disabled={busy}
            onPress={() => setConfirmDelete(true)}
          />
        </View>
      ) : null}

      <ConfirmDialog
        visible={confirmDelete}
        title="Delete this payment?"
        message="Balances go back to what they were before this payment. You can restore it afterwards."
        confirmLabel="Delete"
        destructive
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          run(() => del.mutateAsync({ id: settlementId }), 'Payment deleted');
        }}
      />
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    deleted: {
      backgroundColor: colors.fieldBackground,
      padding: spacing.md,
      borderRadius: radius.md,
      marginBottom: spacing.lg,
    },
    banner: {
      backgroundColor: colors.errorSubtle,
      color: colors.errorText,
      padding: spacing.md,
      borderRadius: radius.md,
      marginBottom: spacing.md,
    },
    parties: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.lg,
    },
    arrow: { color: colors.textSecondary, marginHorizontal: spacing.lg },
    summary: { textAlign: 'center' },
    struck: { textDecorationLine: 'line-through' },
    meta: {
      color: colors.textSecondary,
      textAlign: 'center',
      marginTop: spacing.xs,
    },
    note: { marginTop: spacing.md },
    actions: { marginTop: spacing.xxl },
    gap: { height: spacing.md },
  });
