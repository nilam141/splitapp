import React, { useLayoutEffect, useMemo } from 'react';
import {
  FlatList,
  Pressable,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { cursorOf } from '../api/helpers';
import { Theme, balanceStyle, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  getListGroupTimelineQueryKey,
  listGroupTimeline,
  useGetGroup,
} from '../api/generated/splitapp';
import type { BalanceLine, TimelineItem } from '../api/generated/model';
import type { MainStackParamList } from '../navigation/types';
import { visibleLines } from '../components/BalanceLines';
import { Card } from '../components/Card';
import { ErrorView, LoadingView } from '../components/StateViews';
import { ExpenseRow, monthLabel } from '../expenses/ExpenseRow';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';
import { PaymentRow } from '../payments/PaymentRow';

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

// SCR-13: header, members entry (opens GroupMembers) and the timeline from GET /groups/{id}/timeline (cursor paged, newest first).
export function GroupDetailScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const { groupId } = route.params;
  const { fontScale } = useWindowDimensions();
  const { exponentOf, format } = useMoney();
  const nameOf = useNameOf(groupId);
  const query = useGetGroup(groupId);
  const group = query.data?.status === 200 ? query.data.data : undefined;

  const timeline = useInfiniteQuery({
    queryKey: [
      ...getListGroupTimelineQueryKey(groupId, { limit: PAGE_SIZE }),
      'infinite',
    ],
    queryFn: ({ pageParam }) =>
      listGroupTimeline(groupId, {
        limit: PAGE_SIZE,
        cursor: cursorOf(pageParam),
      }),
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
              variant="text"
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
  const memberWord = members.length === 1 ? 'member' : 'members';
  const lines = visibleLines([...(group.my_balances ?? [])]);
  const settled = lines.length === 0;
  const owedLines = lines.filter(l => l.amount_minor > 0);
  const oweLines = lines.filter(l => l.amount_minor < 0);
  const amountOf = (l: BalanceLine) =>
    format(Math.abs(l.amount_minor), l.currency);
  const spoken = settled
    ? `Your balance in ${group.name}. You are all settled up.`
    : `Your balance in ${group.name}. ` +
      [
        owedLines.length > 0
          ? `You are owed ${owedLines.map(amountOf).join(' and ')}.`
          : '',
        oweLines.length > 0
          ? `You owe ${oweLines.map(amountOf).join(' and ')}.`
          : '',
      ]
        .filter(Boolean)
        .join(' ');
  const stacked = fontScale >= 1.5;
  // Pairwise counterparties are not in GET /groups/{id} (members carry only their own net), so no counterparty lines.
  const header = (
    <View>
      <View style={styles.subtitleRow}>
        <Text variant="callout" style={styles.metaText}>
          {group.group_type}
        </Text>
        <Text
          variant="callout"
          style={styles.metaText}
          importantForAccessibility="no"
          accessibilityElementsHidden
        >
          {'\u00B7'}
        </Text>
        <Pressable
          testID="members-entry"
          accessibilityRole="button"
          accessibilityLabel={`${members.length} ${memberWord}, show list`}
          android_ripple={{ color: colors.border }}
          onPress={() => navigation.navigate('GroupMembers', { groupId })}
          style={styles.membersEntry}
        >
          <Text variant="callout" style={styles.metaText}>
            {members.length} {memberWord}
          </Text>
          <Text
            variant="callout"
            style={styles.metaText}
            importantForAccessibility="no"
            accessibilityElementsHidden
          >
            {'\u203A'}
          </Text>
        </Pressable>
      </View>

      <Card
        testID="balance-card"
        accessible
        accessibilityLabel={spoken}
        style={styles.card}
      >
        <Text variant="caption" style={styles.metaText}>
          Your balance
        </Text>
        {settled ? (
          <View testID="balance-settled" style={styles.balanceRow}>
            <View
              testID="balance-settled-icon"
              accessible={false}
              importantForAccessibility="no-hide-descendants"
              style={styles.icon}
            >
              <Text
                variant="callout"
                style={{ color: balanceStyle(colors, 0).accent }}
              >
                {'\u2713'}
              </Text>
            </View>
            <Text variant="headline" style={styles.settledText}>
              You are all settled up in this group
            </Text>
          </View>
        ) : (
          lines.map(l => {
            const b = balanceStyle(colors, l.amount_minor);
            const owed = l.amount_minor > 0;
            return (
              <View
                key={l.currency}
                testID={`balance-row-${l.currency}`}
                style={styles.balanceBlock}
              >
                <View style={styles.balanceRow}>
                  <View
                    testID={`balance-icon-${l.currency}`}
                    accessible={false}
                    importantForAccessibility="no-hide-descendants"
                    style={styles.icon}
                  >
                    <Text variant="callout" style={{ color: b.accent }}>
                      {owed ? '\u2191' : '\u2193'}
                    </Text>
                  </View>
                  <Text variant="callout" style={styles.metaText}>
                    {owed ? 'You are owed' : 'You owe'}
                  </Text>
                </View>
                <Text
                  variant={lines.length > 1 ? 'title1' : 'display'}
                  style={{ color: b.text }}
                >
                  {amountOf(l)}
                </Text>
              </View>
            );
          })
        )}
      </Card>

      <View
        testID="group-actions"
        style={stacked ? styles.actionsStacked : styles.actions}
      >
        <View style={stacked ? undefined : styles.action}>
          <Button
            title="Settle up"
            variant={settled ? 'secondary' : 'primary'}
            fullWidth
            onPress={() => navigation.navigate('SettleUp', { groupId })}
          />
        </View>
        <View style={stacked ? undefined : styles.action}>
          <Button
            title="Balances"
            variant={settled ? 'outlined' : 'secondary'}
            fullWidth
            onPress={() => navigation.navigate('GroupBalances', { groupId })}
          />
        </View>
      </View>

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
          // kind: settlement renders as a payment row in the position the server gave it (S5-M-3, no merging).
          const st = t.settlement;
          return (
            <PaymentRow
              settlement={st}
              nameOf={nameOf}
              amountText={format(st.amount.amount_minor, st.amount.currency)}
              onPress={() =>
                navigation.navigate('PaymentDetail', { settlementId: st.id })
              }
            />
          );
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

const makeStyles = ({ colors, spacing, touchTarget, typography }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    container: { padding: spacing.lg },
    subtitleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      flexWrap: 'wrap',
      columnGap: spacing.sm,
    },
    metaText: { color: colors.textSecondary },
    membersEntry: {
      minHeight: touchTarget.min,
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
    },
    card: { gap: spacing.sm },
    balanceBlock: { gap: spacing.xs },
    balanceRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
    },
    icon: {
      width: spacing.xl,
      height: spacing.xl,
      alignItems: 'center',
      justifyContent: 'center',
    },
    settledText: { color: colors.textPrimary, flexShrink: 1 },
    actions: {
      flexDirection: 'row',
      gap: spacing.md,
      marginTop: spacing.lg,
    },
    actionsStacked: {
      flexDirection: 'column',
      gap: spacing.md,
      marginTop: spacing.lg,
    },
    action: { flex: 1 },
    section: {
      ...typography.headline,
      marginTop: spacing.xl,
      marginBottom: spacing.sm,
    },
    month: {
      ...typography.headline,
      marginTop: spacing.md,
      marginBottom: spacing.xxs,
      color: colors.textPrimary,
    },
    empty: { marginTop: spacing.xxxl, alignItems: 'center' },
    emptyTitle: { ...typography.body, marginBottom: spacing.sm },
    add: {
      padding: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
    },
  });
