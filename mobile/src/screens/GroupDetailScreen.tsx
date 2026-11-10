import React, { useLayoutEffect } from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useGetGroup } from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';
import type { MainStackParamList } from '../navigation/types';
import { BalanceLines } from '../components/BalanceLines';
import { ErrorView, LoadingView } from '../components/StateViews';

type Props = NativeStackScreenProps<MainStackParamList, 'GroupDetail'>;

// SCR-13 shell: header, members and the empty states. The expense timeline arrives with S3-M-3.
export function GroupDetailScreen({ navigation, route }: Props) {
  const { groupId } = route.params;
  const { user } = useAuth();
  const query = useGetGroup(groupId);
  const group = query.data?.status === 200 ? query.data.data : undefined;

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
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        {group.name}
      </Text>
      <Text style={styles.meta}>
        {group.group_type} - {members.length}{' '}
        {members.length === 1 ? 'member' : 'members'}
      </Text>
      <BalanceLines lines={group.my_balances ?? []} />

      <Text style={styles.section}>Members</Text>
      {members.map(m => (
        <Text key={m.user.id} style={styles.member}>
          {m.user.name}
          {m.user.id === user?.id ? ' (you)' : ''}
        </Text>
      ))}

      <View style={styles.empty}>
        {members.length <= 1 ? (
          <>
            <Text style={styles.emptyTitle}>It's just you here</Text>
            <Button
              title="Add people"
              onPress={() =>
                navigation.navigate('AddPeople', {
                  mode: { kind: 'group-members', groupId },
                })
              }
            />
          </>
        ) : (
          <Text style={styles.emptyTitle}>No expenses yet</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { fontSize: 22, fontWeight: '700' },
  meta: { color: '#666', marginBottom: 8 },
  section: { fontSize: 16, fontWeight: '600', marginTop: 20, marginBottom: 6 },
  member: { paddingVertical: 6, fontSize: 15 },
  empty: { marginTop: 32, alignItems: 'center' },
  emptyTitle: { fontSize: 16, marginBottom: 8 },
});
