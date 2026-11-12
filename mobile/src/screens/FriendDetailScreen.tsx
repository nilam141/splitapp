import React, { useLayoutEffect, useMemo } from 'react';
import { Button, FlatList, StyleSheet, Text, View } from 'react-native';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  getListExpensesQueryKey,
  listExpenses,
  useGetFriend,
} from '../api/generated/splitapp';
import type { Expense } from '../api/generated/model';
import type { MainStackParamList } from '../navigation/types';
import { BalanceLines } from '../components/BalanceLines';
import { EmptyView, ErrorView, LoadingView } from '../components/StateViews';
import { ExpenseRow, monthLabel } from '../expenses/ExpenseRow';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';

type Props = NativeStackScreenProps<MainStackParamList, 'FriendDetail'>;
const PAGE_SIZE = 30;

type Row =
  | { type: 'month'; key: string; label: string }
  | { type: 'item'; key: string; expense: Expense };

// SCR-19: balance with one friend (total and breakdown) and every expense shared with them.
export function FriendDetailScreen({ navigation, route }: Props) {
  const { friendId } = route.params;
  const { exponentOf } = useMoney();
  const nameOf = useNameOf(null);
  const query = useGetFriend(friendId);
  const friend = query.data?.status === 200 ? query.data.data : undefined;

  const expenses = useInfiniteQuery({
    queryKey: [
      ...getListExpensesQueryKey({
        friend_user_id: friendId,
        limit: PAGE_SIZE,
      }),
      'infinite',
    ],
    queryFn: ({ pageParam }) =>
      listExpenses({
        friend_user_id: friendId,
        limit: PAGE_SIZE,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last =>
      last.status === 200 ? (last.data.next_cursor ?? undefined) : undefined,
    enabled: !!friend,
  });
  const rows = useMemo(() => {
    const out: Row[] = [];
    let last = '';
    for (const page of expenses.data?.pages ?? []) {
      if (page.status !== 200) {
        continue;
      }
      for (const e of page.data.items) {
        const month = e.expense_date.slice(0, 7);
        if (month !== last) {
          out.push({
            type: 'month',
            key: `m-${month}-${out.length}`,
            label: monthLabel(e.expense_date),
          });
          last = month;
        }
        out.push({ type: 'item', key: e.id, expense: e });
      }
    }
    return out;
  }, [expenses.data]);

  useLayoutEffect(() => {
    navigation.setOptions({
      title: friend?.user.name ?? 'Friend',
      headerRight: friend
        ? () => (
            <Button
              title="Settings"
              onPress={() =>
                navigation.navigate('FriendSettings', { friendId })
              }
            />
          )
        : undefined,
    });
  }, [navigation, friend, friendId]);

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

  const failed =
    expenses.isError || expenses.data?.pages.some(p => p.status !== 200);
  const header = (
    <View>
      <Text accessibilityRole="header" style={styles.title}>
        {friend.user.name}
      </Text>
      <BalanceLines lines={friend.balances} />
      {friend.breakdown.map((b, i) => (
        <View
          key={`${b.scope}-${b.group_id ?? 'ng'}-${i}`}
          style={styles.breakdown}
        >
          <Text style={styles.scope}>
            {b.scope === 'group'
              ? (b.group_name ?? 'Group')
              : 'Non-group expenses'}
          </Text>
          <BalanceLines lines={b.balances} />
        </View>
      ))}
    </View>
  );

  let empty: React.ReactElement | undefined;
  if (expenses.isPending) {
    empty = <LoadingView label="Loading expenses" />;
  } else if (failed) {
    empty = (
      <ErrorView
        offline={expenses.isError}
        onRetry={() => expenses.refetch()}
      />
    );
  } else {
    empty = <EmptyView title="No expenses with this friend" />;
  }

  return (
    <View style={styles.flex}>
      <FlatList
        testID="friend-expenses"
        data={rows}
        keyExtractor={r => r.key}
        contentContainerStyle={styles.container}
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        onEndReached={() => {
          if (expenses.hasNextPage && !expenses.isFetchingNextPage) {
            expenses.fetchNextPage();
          }
        }}
        renderItem={({ item: row }) =>
          row.type === 'month' ? (
            <Text style={styles.month}>{row.label}</Text>
          ) : (
            <ExpenseRow
              expense={row.expense}
              nameOf={nameOf}
              exponentOf={exponentOf}
              onPress={() =>
                navigation.navigate('ExpenseDetail', {
                  expenseId: row.expense.id,
                })
              }
            />
          )
        }
      />
      <View style={styles.add}>
        <Button
          title="Add expense"
          onPress={() => navigation.navigate('ExpenseForm', { friendId })}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16 },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 4 },
  breakdown: { marginTop: 8 },
  scope: { fontWeight: '600', color: '#444' },
  month: { fontWeight: '700', marginTop: 14, marginBottom: 2, color: '#444' },
  add: { padding: 12, borderTopWidth: StyleSheet.hairlineWidth },
});
