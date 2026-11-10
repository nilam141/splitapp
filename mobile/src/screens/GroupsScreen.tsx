import React, { useMemo, useState } from 'react';
import {
  Button,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useListGroups } from '../api/generated/splitapp';
import type { GroupSummary } from '../api/generated/model';
import type { MainStackParamList } from '../navigation/types';
import { BalanceLines } from '../components/BalanceLines';
import { EmptyView, ErrorView, LoadingView } from '../components/StateViews';
import { isLongSettledLines } from '../friends/filter';
import { summarizeBalances } from '../money/format';
import { useMoney } from '../money/useMoney';

// SCR-09.
export function GroupsScreen() {
  const nav = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const query = useListGroups();
  const { exponentOf } = useMoney();
  const [showSettled, setShowSettled] = useState(false);

  const body = query.data?.status === 200 ? query.data.data : undefined;
  const groups: GroupSummary[] = useMemo(() => body?.items ?? [], [body]);
  const now = Date.now();
  const collapsed = groups.filter(g =>
    isLongSettledLines(g.my_balances, g.settled_up_since, now),
  );
  const visible = showSettled
    ? groups
    : groups.filter(g => !collapsed.includes(g));
  const create = () => nav.navigate('CreateGroup');

  if (query.isPending) {
    return <LoadingView label="Loading groups" />;
  }
  if (query.isError || !body) {
    return (
      <ErrorView offline={query.isError} onRetry={() => query.refetch()} />
    );
  }
  if (groups.length === 0) {
    return (
      <EmptyView
        title="No groups yet"
        hint="Create a group for your home, a trip or your partner."
        actionLabel="Start a new group"
        onAction={create}
      />
    );
  }

  const summary = summarizeBalances(
    [...groups.flatMap(g => g.my_balances), ...(body.non_group_balances ?? [])],
    exponentOf,
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={visible}
        keyExtractor={g => g.id}
        refreshing={query.isRefetching}
        onRefresh={() => query.refetch()}
        ListHeaderComponent={
          <Text style={styles.summary}>Overall: {summary}</Text>
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Open group ${item.name}`}
            onPress={() => nav.navigate('GroupDetail', { groupId: item.id })}
            style={styles.row}
          >
            <View>
              <Text style={styles.name}>{item.name}</Text>
              {item.member_count !== undefined ? (
                <Text style={styles.meta}>{item.member_count} members</Text>
              ) : null}
            </View>
            <BalanceLines lines={item.my_balances} />
          </Pressable>
        )}
        ListFooterComponent={
          <View>
            {body.non_group_balances && body.non_group_balances.length > 0 ? (
              <View style={styles.row}>
                <Text style={styles.name}>Non-group expenses</Text>
                <BalanceLines lines={body.non_group_balances} />
              </View>
            ) : null}
            {collapsed.length > 0 && !showSettled ? (
              <Button
                title={`Show ${collapsed.length} settled-up groups`}
                onPress={() => setShowSettled(true)}
              />
            ) : null}
          </View>
        }
      />
      <View style={styles.add}>
        <Button title="Start a new group" onPress={create} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  summary: { fontSize: 15, marginBottom: 12 },
  row: {
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  name: { fontSize: 16, fontWeight: '500' },
  meta: { color: '#666' },
  add: { marginTop: 8 },
});
