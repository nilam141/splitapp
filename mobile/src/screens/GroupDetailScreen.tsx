import React, { useLayoutEffect, useMemo } from 'react';
import { Button, FlatList, StyleSheet, Text, View } from 'react-native';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  getListGroupTimelineQueryKey,
  listGroupTimeline,
  useGetGroup,
} from '../api/generated/splitapp';
import type { TimelineItem } from '../api/generated/model';
import { useAuth } from '../auth/AuthContext';
import type { MainStackParamList } from '../navigation/types';
import {
  BalanceLines,
  MemberNetLines,
  visibleLines,
} from '../components/BalanceLines';
import { ErrorView, LoadingView } from '../components/StateViews';
import { ExpenseRow, monthLabel } from '../expenses/ExpenseRow';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';

type Props = NativeStackScreenProps<MainStackParamList, 'GroupDetail'>;

const PAGE_SIZE = 30;

type Row =
  | { type: 'month'; key: string; label: string }
  | { type: 'item'; key: string; item: TimelineItem };

/** Server order is kept as is; a month heading is inserted whenever the month changes. */
function withMonthHeadings(items: TimelineItem[]): Row[] {
  const rows: Row[] = [];
  let last = '';
  for (const item of items) {
    const month = item.date.slice(0, 7);
    if (month !== last) {
      rows.push({
        type: 'month',
        key: `m-${month}-${rows.length}`,
        label: monthLabel(item.date),
      });
      last = month;
    }
    rows.push({
      type: 'item',
      key:
        item.kind === 'expense'
          ? `e-${item.expense.id}`
          : `s-${item.settlement.id}`,
      item,
    });
  }
  return rows;
}

// SCR-13: header, members and the timeline from GET /groups/{id}/timeline (cursor paged, newest first).
export function GroupDetailScreen({ navigation, route }: Props) {
  const { groupId } = route.params;
  const { user } = useAuth();
  const { exponentOf } = useMoney();
  const nameOf = useNameOf(groupId);
  const query = useGetGroup(groupId);
  const group = query.data?.status === 200 ? query.data.data : undefined;

  const timeline = useInfiniteQuery({
    queryKey: [
      ...getListGroupTimelineQueryKey(groupId, { limit: PAGE_SIZE }),
      'infinite',
    ],
    queryFn: ({ pageParam }) =>
      listGroupTimeline(groupId, { limit: PAGE_SIZE, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last =>
      last.status === 200 ? (last.data.next_cursor ?? undefined) : undefined,
    enabled: !!group,
  });
  const firstFailure = timeline.data?.pages.find(p => p.status !== 200);
  const rows = useMemo(
    () =>
      withMonthHeadings(
        (timeline.data?.pages ?? []).flatMap(p =>
          p.status === 200 ? p.data.items : [],
        ),
      ),
    [timeline.data],
  );

  useLayoutEffect(() => {
    navigation.setOptions({
      title: group?.name ?? 'Group',
      headerRight: group
        ? () => (
            <Button
              title="Settings"
              onPress={() => navigation.navigate('GroupSettings', { groupId })}
            />
          )
        : undefined,
    });
  }, [navigation, group, groupId]);

  if (query.isPending) {
    return <LoadingView label="Loading group" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!group) {
    const status = query.data?.status;
    return (
      <ErrorView
        offline={false}
        message={
          status === 403
            ? "You're not a member of this group."
            : status === 404
              ? 'This group no longer exists.'
              : undefined
        }
        onRetry={() => query.refetch()}
      />
    );
  }

  const members = group.members.filter(m => !m.left_at);
  const memberLines = members.filter(m => visibleLines(m.balances).length > 0);
  const header = (
    <View>
      <Text accessibilityRole="header" style={styles.title}>
        {group.name}
      </Text>
      <Text style={styles.meta}>
        {group.group_type} - {members.length}{' '}
        {members.length === 1 ? 'member' : 'members'}
      </Text>
      <BalanceLines lines={group.my_balances ?? []} />
      {memberLines.slice(0, 3).map(m => (
        <View key={m.user.id} style={styles.memberLine}>
          <Text>{m.user.id === user?.id ? 'You' : m.user.name}</Text>
          <MemberNetLines
            lines={m.balances}
            isViewer={m.user.id === user?.id}
          />
        </View>
      ))}
      {memberLines.length > 3 ? (
        <Text style={styles.meta}>+{memberLines.length - 3} more</Text>
      ) : null}
      {memberLines.length === 0 && rows.length > 0 ? (
        <Text style={styles.meta}>You are all settled up in this group</Text>
      ) : null}
      <Button
        title="Balances"
        onPress={() => navigation.navigate('GroupBalances', { groupId })}
      />

      <Text style={styles.section}>Members</Text>
      {members.map(m => (
        <Text key={m.user.id} style={styles.member}>
          {m.user.name}
          {m.user.id === user?.id ? ' (you)' : ''}
        </Text>
      ))}
      <Text style={styles.section}>Expenses</Text>
    </View>
  );

  let empty: React.ReactElement | undefined;
  if (timeline.isPending) {
    empty = <LoadingView label="Loading expenses" />;
  } else if (timeline.isError || firstFailure) {
    empty = (
      <ErrorView
        offline={timeline.isError}
        onRetry={() => timeline.refetch()}
      />
    );
  } else if (members.length <= 1) {
    empty = (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>It's just you here</Text>
        <Button
          title="Add people"
          onPress={() =>
            navigation.navigate('AddPeople', {
              mode: { kind: 'group-members', groupId },
            })
          }
        />
      </View>
    );
  } else {
    empty = (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>No expenses yet</Text>
      </View>
    );
  }

  return (
    <View style={styles.flex}>
      <FlatList
        testID="timeline"
        data={rows}
        keyExtractor={r => r.key}
        contentContainerStyle={styles.container}
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        refreshing={timeline.isRefetching && !timeline.isFetchingNextPage}
        onRefresh={() => {
          query.refetch();
          timeline.refetch();
        }}
        onEndReachedThreshold={0.5}
        onEndReached={() => {
          if (timeline.hasNextPage && !timeline.isFetchingNextPage) {
            timeline.fetchNextPage();
          }
        }}
        ListFooterComponent={
          timeline.isFetchingNextPage ? (
            <LoadingView label="Loading more expenses" />
          ) : timeline.isFetchNextPageError ? (
            <Button
              title="Retry loading more"
              onPress={() => timeline.fetchNextPage()}
            />
          ) : undefined
        }
        renderItem={({ item: row }) => {
          if (row.type === 'month') {
            return <Text style={styles.month}>{row.label}</Text>;
          }
          const t = row.item;
          if (t.kind === 'expense') {
            return (
              <ExpenseRow
                expense={t.expense}
                nameOf={nameOf}
                exponentOf={exponentOf}
                onPress={() =>
                  navigation.navigate('ExpenseDetail', {
                    expenseId: t.expense.id,
                  })
                }
              />
            );
          }
          // Payment rows are styled and wired in S5-M-3; until then a neutral line keeps the server order visible.
          return <Text style={styles.payment}>Payment recorded</Text>;
        }}
      />
      <View style={styles.add}>
        <Button
          title="Add expense"
          onPress={() => navigation.navigate('ExpenseForm', { groupId })}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16 },
  title: { fontSize: 22, fontWeight: '700' },
  meta: { color: '#666', marginBottom: 8 },
  section: { fontSize: 16, fontWeight: '600', marginTop: 20, marginBottom: 6 },
  memberLine: { flexDirection: 'row', justifyContent: 'space-between' },
  member: { paddingVertical: 6, fontSize: 15 },
  month: { fontWeight: '700', marginTop: 14, marginBottom: 2, color: '#444' },
  payment: { fontStyle: 'italic', color: '#666', paddingVertical: 10 },
  empty: { marginTop: 32, alignItems: 'center' },
  emptyTitle: { fontSize: 16, marginBottom: 8 },
  add: { padding: 12, borderTopWidth: StyleSheet.hairlineWidth },
});
