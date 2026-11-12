import React, { useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useGetGroup, useUpdateGroup } from '../api/generated/splitapp';
import { apiErrorOf, invalidateGroups } from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';
import { ErrorView, LoadingView } from '../components/StateViews';

type Props = NativeStackScreenProps<MainStackParamList, 'SimplifyExplainer'>;

// SCR-40: a worked example with our own 3-person diagram, and a "Turn on" button when it is off.
export function SimplifyExplainerScreen({ navigation, route }: Props) {
  const { groupId } = route.params;
  const qc = useQueryClient();
  const query = useGetGroup(groupId);
  const update = useUpdateGroup();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const group = query.data?.status === 200 ? query.data.data : undefined;

  if (query.isPending) {
    return <LoadingView label="Loading group" />;
  }
  if (query.isError || !group) {
    return (
      <ErrorView offline={query.isError} onRetry={() => query.refetch()} />
    );
  }

  const turnOn = async () => {
    setError(undefined);
    setBusy(true);
    try {
      const res = await update.mutateAsync({
        id: groupId,
        data: { version: group.version, simplify_debts: true },
      });
      if (res.status === 200) {
        await invalidateGroups(qc);
        navigation.goBack();
      } else {
        setError(apiErrorOf(res)?.message ?? 'Could not turn it on.');
      }
    } catch {
      setError("Can't reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        Simplify debts
      </Text>
      <Text style={styles.body}>
        When it is on, the group settles with as few payments as possible, even
        if some of them are between people who never shared an expense.
      </Text>
      <View style={styles.example}>
        <Text style={styles.label}>Without simplifying</Text>
        <Text>Ann pays Ben 10</Text>
        <Text>Ben pays Cy 10</Text>
        <Text style={styles.label}>With simplifying</Text>
        <Text>Ann pays Cy 10</Text>
        <Text style={styles.small}>
          Ben is neither owed nor owing, so Ben has nothing to pay.
        </Text>
      </View>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      {!group.simplify_debts ? (
        <Button title="Turn on" onPress={turnOn} disabled={busy} />
      ) : (
        <Text style={styles.small}>Simplify debts is on for this group.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
  body: { fontSize: 15, marginBottom: 16 },
  example: {
    padding: 12,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    marginBottom: 16,
  },
  label: { fontWeight: '600', marginTop: 8 },
  small: { color: '#666', marginTop: 4 },
  error: { color: '#b00020', marginBottom: 8 },
});
