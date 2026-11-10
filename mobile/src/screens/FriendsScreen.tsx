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
import { useListFriends } from '../api/generated/splitapp';
import type { Friend } from '../api/generated/model';
import { ListFriendsFilter } from '../api/generated/model';
import type { MainStackParamList } from '../navigation/types';
import { BalanceLines } from '../components/BalanceLines';
import { EmptyView, ErrorView, LoadingView } from '../components/StateViews';
import { splitFriends, FriendFilter } from '../friends/filter';
import { summarizeBalances } from '../money/format';
import { useMoney } from '../money/useMoney';

const FILTERS: { value: FriendFilter; label: string }[] = [
  { value: ListFriendsFilter.all, label: 'All' },
  { value: ListFriendsFilter.outstanding, label: 'Outstanding' },
  { value: ListFriendsFilter.owes_me, label: 'Owe me' },
  { value: ListFriendsFilter.i_owe, label: 'I owe' },
];

// SCR-08. One GET /friends response, filtered on the client.
export function FriendsScreen() {
  const nav = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const query = useListFriends();
  const { exponentOf } = useMoney();
  const [filter, setFilter] = useState<FriendFilter>('all');
  const [showSettled, setShowSettled] = useState(false);

  const friends: Friend[] = useMemo(
    () => (query.data?.status === 200 ? query.data.data.items : []),
    [query.data],
  );
  const { visible, collapsed, matching } = useMemo(
    () => splitFriends(friends, filter, Date.now()),
    [friends, filter],
  );
  const add = () => nav.navigate('AddPeople', { mode: { kind: 'friend' } });

  if (query.isPending) {
    return <LoadingView label="Loading friends" />;
  }
  if (query.isError || query.data?.status !== 200) {
    return (
      <ErrorView offline={query.isError} onRetry={() => query.refetch()} />
    );
  }
  if (friends.length === 0) {
    return (
      <EmptyView
        title="Add your first friend"
        hint="Friends you add show up here with the balance between you."
        actionLabel="Add friend"
        onAction={add}
      />
    );
  }

  const rows = showSettled ? [...visible, ...collapsed] : visible;
  const summary = summarizeBalances(
    friends.flatMap(f => f.balances),
    exponentOf,
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={rows}
        keyExtractor={f => f.user.id}
        refreshing={query.isRefetching}
        onRefresh={() => query.refetch()}
        ListHeaderComponent={
          <View>
            <Text style={styles.summary}>Overall: {summary}</Text>
            <View style={styles.filters}>
              {FILTERS.map(f => (
                <Pressable
                  key={f.value}
                  accessibilityRole="button"
                  accessibilityLabel={`Filter: ${f.label}`}
                  accessibilityState={{ selected: filter === f.value }}
                  onPress={() => setFilter(f.value)}
                  style={[
                    styles.chip,
                    filter === f.value ? styles.chipOn : null,
                  ]}
                >
                  <Text
                    style={filter === f.value ? styles.chipTextOn : undefined}
                  >
                    {f.label}
                  </Text>
                </Pressable>
              ))}
            </View>
            {matching === 0 ? (
              <Text style={styles.none}>No friends match this filter.</Text>
            ) : null}
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Friend: ${item.user.name}`}
            onPress={() =>
              nav.navigate('FriendDetail', { friendId: item.user.id })
            }
            style={styles.row}
          >
            <Text style={styles.name}>{item.user.name}</Text>
            <BalanceLines lines={item.balances} />
          </Pressable>
        )}
        ListFooterComponent={
          collapsed.length > 0 && !showSettled ? (
            <Button
              title={`Show ${collapsed.length} settled-up friends`}
              onPress={() => setShowSettled(true)}
            />
          ) : undefined
        }
      />
      <View style={styles.add}>
        <Button title="Add friend" onPress={add} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  summary: { fontSize: 15, marginBottom: 12 },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  chip: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 16,
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  chipOn: { backgroundColor: '#1b6e5a', borderColor: '#1b6e5a' },
  chipTextOn: { color: '#fff' },
  none: { color: '#666', marginVertical: 16, textAlign: 'center' },
  row: {
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  name: { fontSize: 16, fontWeight: '500' },
  add: { marginTop: 8 },
});
