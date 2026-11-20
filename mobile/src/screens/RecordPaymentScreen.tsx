import React, { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Avatar } from '../components/Avatar';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { CurrencyPicker } from '../components/CurrencyPicker';
import { FormField } from '../components/FormField';
import { MoneyField } from '../components/MoneyField';
import { ErrorView, LoadingView } from '../components/StateViews';
import { showSnackbar } from '../components/snackbar';
import {
  deleteSettlement,
  useCreateSettlement,
  useGetGroup,
  useGetSettlement,
  useUpdateSettlement,
} from '../api/generated/splitapp';
import {
  apiErrorOf,
  idempotencyHeaders,
  invalidateAfterPayment,
  newIdempotencyKey,
} from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import { isoDate } from '../expenses/draft';
import { useNameOf } from '../expenses/useNames';
import { DatePanel } from '../expenses/PickerPanels';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';
import { OFFLINE_MESSAGE } from '../payments/messages';
import { flipAmount, isOverpay } from '../payments/rows';
import {
  PAYMENT_NOTE_MAX,
  messageForCreateError,
  validatePaymentAmount,
} from '../payments/validate';

type Props = NativeStackScreenProps<MainStackParamList, 'RecordPayment'>;

// SCR-31: record a payment (prefilled from SCR-30) or edit one (from SCR-32).
export function RecordPaymentScreen(props: Props) {
  const { settlementId } = props.route.params;
  const existing = useGetSettlement(settlementId ?? '', {
    query: { enabled: !!settlementId },
  });
  if (!settlementId) {
    return <PaymentForm {...props} />;
  }
  if (existing.isPending) {
    return <LoadingView label="Loading payment" />;
  }
  if (existing.isError) {
    return <ErrorView offline onRetry={() => existing.refetch()} />;
  }
  if (existing.data?.status !== 200) {
    return (
      <ErrorView
        offline={false}
        message="Cannot find this payment."
        onRetry={() => props.navigation.goBack()}
      />
    );
  }
  const s = existing.data.data;
  return (
    <PaymentForm
      {...props}
      initial={{
        id: s.id,
        version: s.version,
        groupId: s.group_id ?? null,
        fromUserId: s.from_user_id,
        toUserId: s.to_user_id,
        amountMinor: s.amount.amount_minor,
        currency: s.amount.currency,
        date: s.settled_on,
        note: s.note ?? '',
      }}
    />
  );
}

type Initial = {
  id: string;
  version: number;
  groupId: string | null;
  fromUserId: string;
  toUserId: string;
  amountMinor: number;
  currency: string;
  date: string;
  note: string;
};

type Panel = 'main' | 'date';

function PaymentForm({
  navigation,
  route,
  initial,
}: Props & { initial?: Initial }) {
  const p = route.params;
  const styles = useThemedStyles(makeStyles);
  const { user } = useAuth();
  const meId = user?.id ?? '';
  const qc = useQueryClient();
  const { format, exponentOf } = useMoney();
  const editing = !!initial;
  const groupId = initial ? initial.groupId : (p.groupId ?? null);
  const nameOf = useNameOf(groupId);
  const group = useGetGroup(groupId ?? '', { query: { enabled: !!groupId } });
  const groupName =
    group.data?.status === 200 ? group.data.data.name : undefined;
  const today = useMemo(() => isoDate(new Date()), []);

  const key = useRef(newIdempotencyKey());
  const create = useCreateSettlement({
    request: idempotencyHeaders(key.current),
  });
  const update = useUpdateSettlement();

  const [from, setFrom] = useState(initial?.fromUserId ?? p.fromUserId ?? '');
  const [to, setTo] = useState(initial?.toUserId ?? p.toUserId ?? '');
  const [currency, setCurrency] = useState(
    initial?.currency ?? p.currency ?? user?.default_currency ?? 'INR',
  );
  const [amount, setAmount] = useState<number | null>(
    initial?.amountMinor ?? p.amountMinor ?? null,
  );
  const [date, setDate] = useState(initial?.date ?? today);
  const [note, setNote] = useState(initial?.note ?? '');
  const [panel, setPanel] = useState<Panel>('main');
  const [pickCurrency, setPickCurrency] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [banner, setBanner] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [overpay, setOverpay] = useState(false);
  // Remounts the money field when the amount is replaced from outside (currency change).
  const [fieldKey, setFieldKey] = useState(0);

  const label = (id: string) => (id === meId ? 'You' : nameOf(id));
  // What the payer owes, in the prefilled currency. Unknown when editing or opened without a balance. Swapping the
  // parties flips who owes, so the swapped payer owes nothing and any amount in that currency is "more than owed".
  const owed: number | undefined =
    editing || p.owedMinor === undefined
      ? undefined
      : from === p.fromUserId
        ? p.owedMinor
        : 0;
  const owedCurrency = p.currency ?? currency;

  const swap = () => {
    setFrom(to);
    setTo(from);
  };

  const submit = async () => {
    setBanner(undefined);
    const problem = validatePaymentAmount(amount);
    if (problem || amount === null) {
      setError(problem);
      return;
    }
    setError(undefined);
    if (
      !editing &&
      isOverpay(
        amount,
        currency,
        owed !== undefined
          ? { amountMinor: owed, currency: owedCurrency }
          : undefined,
      )
    ) {
      setOverpay(true);
      return;
    }
    await save(amount);
  };

  const save = async (minor: number) => {
    setOverpay(false);
    setSaving(true);
    try {
      if (initial) {
        const res = await update.mutateAsync({
          id: initial.id,
          data: {
            version: initial.version,
            amount: { amount_minor: minor, currency },
            settled_on: date,
            note: note.trim() === '' ? null : note.trim(),
          },
        });
        if (res.status === 200) {
          await invalidateAfterPayment(qc);
          showSnackbar('Payment updated');
          navigation.goBack();
        } else if (res.status === 409) {
          await invalidateAfterPayment(qc);
          setBanner(
            apiErrorOf(res)?.message ??
              'The payment changed. We reloaded it, please try again.',
          );
        } else {
          setBanner(
            apiErrorOf(res)?.message ?? messageForCreateError(undefined),
          );
        }
        return;
      }
      const res = await create.mutateAsync({
        data: {
          group_id: groupId,
          from_user_id: from,
          to_user_id: to,
          amount: { amount_minor: minor, currency },
          settled_on: date,
          note: note.trim() === '' ? null : note.trim(),
        },
      });
      if (res.status === 201) {
        const id = res.data.id;
        await invalidateAfterPayment(qc);
        showSnackbar('Payment recorded', {
          label: 'Undo',
          onPress: () => {
            deleteSettlement(id).then(() => invalidateAfterPayment(qc));
          },
        });
        const routes = navigation.getState().routes;
        if (
          routes.length >= 2 &&
          routes[routes.length - 2].name === 'SettleUp'
        ) {
          navigation.pop(2);
        } else {
          navigation.goBack();
        }
      } else {
        setBanner(messageForCreateError(apiErrorOf(res)?.code));
      }
    } catch {
      setBanner(OFFLINE_MESSAGE);
    } finally {
      setSaving(false);
    }
  };

  if (panel === 'date') {
    return (
      <DatePanel
        date={date}
        today={today}
        onCancel={() => setPanel('main')}
        onDone={d => {
          setDate(d);
          setPanel('main');
        }}
      />
    );
  }

  const exponent = exponentOf(currency);
  const flip =
    amount !== null && owed !== undefined ? flipAmount(amount, owed) : 0;
  const overpayMessage = `${label(to)} will then owe ${from === meId ? 'you' : label(from)} ${format(flip, currency)}.`;

  return (
    <View style={styles.flex}>
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
      >
        {banner ? (
          <Text accessibilityRole="alert" style={styles.banner}>
            {banner}
          </Text>
        ) : null}

        <View style={styles.parties}>
          <View style={styles.party}>
            <Avatar name={label(from)} size={56} testID="avatar-from" />
            <Text variant="callout" style={styles.partyName}>
              {label(from)}
            </Text>
            <Text variant="caption" style={styles.secondary}>
              pays
            </Text>
          </View>
          <View style={styles.middle}>
            <Text variant="title2" style={styles.arrow}>
              →
            </Text>
            {editing ? null : (
              <Pressable
                testID="swap"
                accessibilityRole="button"
                accessibilityLabel="Swap payer and receiver"
                onPress={swap}
                style={styles.swap}
              >
                <Text variant="label" style={styles.swapText}>
                  ⇄
                </Text>
              </Pressable>
            )}
          </View>
          <View style={styles.party}>
            <Avatar name={label(to)} size={56} testID="avatar-to" />
            <Text variant="callout" style={styles.partyName}>
              {label(to)}
            </Text>
            <Text variant="caption" style={styles.secondary}>
              receives
            </Text>
          </View>
        </View>

        <MoneyField
          key={fieldKey}
          label="Amount"
          currency={currency}
          exponent={exponent}
          initialMinor={amount}
          onChangeMinor={m => {
            setAmount(m);
            if (error) {
              setError(validatePaymentAmount(m));
            }
          }}
          error={error}
          accessibilityLabel="Amount"
        />

        <View style={styles.rows}>
          <Pressable
            testID="currency-chip"
            accessibilityRole="button"
            accessibilityLabel={`Currency: ${currency}`}
            disabled={editing}
            onPress={() => setPickCurrency(true)}
            style={styles.rowButton}
          >
            <Text variant="callout" style={styles.secondary}>
              Currency
            </Text>
            <Text variant="bodyStrong">{currency}</Text>
          </Pressable>
          <Pressable
            testID="date-row"
            accessibilityRole="button"
            accessibilityLabel={`Date: ${date}`}
            onPress={() => setPanel('date')}
            style={styles.rowButton}
          >
            <Text variant="callout" style={styles.secondary}>
              Date
            </Text>
            <Text variant="bodyStrong">{date}</Text>
          </Pressable>
          <View
            style={styles.rowButton}
            accessible
            accessibilityLabel={`Group: ${groupId ? (groupName ?? 'group') : 'Non-group'}`}
          >
            <Text variant="callout" style={styles.secondary}>
              Group
            </Text>
            <Text variant="bodyStrong">
              {groupId ? (groupName ?? 'Group') : 'Non-group'}
            </Text>
          </View>
        </View>

        <FormField
          label="Note (optional)"
          value={note}
          onChangeText={setNote}
          maxLength={PAYMENT_NOTE_MAX}
          helper={`${note.length} / ${PAYMENT_NOTE_MAX}`}
          accessibilityLabel="Note"
        />
      </ScrollView>

      <View style={styles.footer}>
        <Button
          title="Save payment"
          fullWidth
          loading={saving}
          onPress={submit}
        />
      </View>

      <CurrencyPicker
        visible={pickCurrency}
        selected={currency}
        title="Currency"
        onClose={() => setPickCurrency(false)}
        onSelect={code => {
          setPickCurrency(false);
          if (code !== currency) {
            setCurrency(code);
            setAmount(null);
            setFieldKey(k => k + 1);
          }
        }}
      />
      <ConfirmDialog
        visible={overpay}
        title="This is more than owed"
        message={overpayMessage}
        confirmLabel="Record payment"
        onClose={() => setOverpay(false)}
        onConfirm={() => {
          if (amount !== null) {
            save(amount);
          }
        }}
      />
    </View>
  );
}

const makeStyles = ({ colors, spacing, radius, touchTarget }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    container: { padding: spacing.lg },
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
      justifyContent: 'space-between',
      marginBottom: spacing.xl,
    },
    party: { alignItems: 'center', flex: 1 },
    partyName: { marginTop: spacing.xs },
    secondary: { color: colors.textSecondary },
    middle: { alignItems: 'center' },
    arrow: { color: colors.textSecondary },
    swap: {
      minWidth: touchTarget.min,
      minHeight: touchTarget.min,
      borderRadius: radius.pill,
      backgroundColor: colors.fieldBackground,
      alignItems: 'center',
      justifyContent: 'center',
    },
    swapText: { color: colors.textPrimary },
    rows: { marginVertical: spacing.lg },
    rowButton: {
      minHeight: touchTarget.min,
      borderRadius: radius.md,
      backgroundColor: colors.fieldBackground,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      marginBottom: spacing.sm,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    footer: {
      padding: spacing.lg,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
      backgroundColor: colors.surface,
    },
  });
