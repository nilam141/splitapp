import React, { useMemo, useState } from 'react';
import {
  Button,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useGetGroupBalances } from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';
import type { MainStackParamList } from '../navigation/types';
import { MemberNetLines, visibleLines } from '../components/BalanceLines';
import { ErrorView, LoadingView } from '../components/StateViews';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';

type Props = NativeStackScreenProps<MainStackParamList, 'GroupBalances'>;

// SCR-15: every member's net per currency and the suggested payments, in the order the server returns them.
export function GroupBalancesScreen({ navigation, route }: Props) {
  const { groupId } = route.params;
  const { user } = useAuth();
  const { format } = useMoney();
  const nameOf = useNameOf(groupId);
  const query = useGetGroupBalances(groupId);
  const [open, setOpen] = useState<string | null>(null);
  const data = query.data?.status === 200 ? query.data.data : undefined;

  const allZero = useMemo(
    () =>
      (data?.members ?? []).every(m => visibleLines(m.balances).length === 0),
    [data],
  );

  if (query.isPending) {
    return <LoadingView label="Loading balances" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!data) {
    const status = query.data?.status;
    return (
      <ErrorView
        offline={false}
        message={
          status === 403 ? "You're not a member of this group." : undefined
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const line = (t: (typeof data.transfers)[number]) =>
    `${nameOf(t.from_user_id)} ${t.from_user_id === user?.id ? 'owe' : 'owes'} ${nameOf(t.to_user_id)} ${format(t.amount_minor, t.currency)}`;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.noteRow}>
        <Text>Simplify debts is {data.simplified ? 'on' : 'off'}</Text>
        <Button
          title="What is this?"
          onPress={() => navigation.navigate('SimplifyExplainer', { groupId })}
        />
      </View>

      {allZero ? (
        <Text style={styles.settled}>Everyone is settled up</Text>
      ) : null}

      <Text style={styles.section}>Members</Text>
      {data.members.map(m => {
        const mine = data.transfers.filter(
          t => t.from_user_id === m.user_id || t.to_user_id === m.user_id,
        );
        const expanded = open === m.user_id;
        return (
          <View key={m.user_id} style={styles.member}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Member: ${nameOf(m.user_id)}`}
              accessibilityState={{ expanded }}
              onPress={() => setOpen(expanded ? null : m.user_id)}
              style={styles.memberHead}
            >
              <Text style={styles.name}>{nameOf(m.user_id)}</Text>
              <MemberNetLines
                lines={m.balances}
                isViewer={m.user_id === user?.id}
              />
            </Pressable>
            {expanded ? (
              mine.length === 0 ? (
                <Text style={styles.detail}>Nothing to pay</Text>
              ) : (
                mine.map((t, i) => (
                  <Text key={`${i}-${t.currency}`} style={styles.detail}>
                    {line(t)}
                  </Text>
                ))
              )
            ) : null}
          </View>
        );
      })}

      {data.transfers.length > 0 ? (
        <View>
          <Text style={styles.section}>
            {data.simplified ? 'Suggested payments' : 'Who owes whom'}
          </Text>
          {data.transfers.map((t, i) => (
            <Text
              key={`${i}-${t.from_user_id}-${t.to_user_id}-${t.currency}`}
              testID="transfer"
              style={styles.transfer}
            >
              {line(t)}
            </Text>
          ))}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  noteRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settled: { marginVertical: 12, fontSize: 16, color: '#1b7f3b' },
  section: { fontSize: 16, fontWeight: '600', marginTop: 20, marginBottom: 6 },
  member: { borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 8 },
  memberHead: { flexDirection: 'row', justifyContent: 'space-between' },
  name: { fontSize: 16, fontWeight: '500' },
  detail: { marginTop: 4, marginLeft: 12, color: '#444' },
  transfer: { paddingVertical: 6, fontSize: 15 },
});
