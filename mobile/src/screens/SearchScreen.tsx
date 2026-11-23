import React, { useEffect, useMemo, useState } from 'react';
import { FlatList, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useInfiniteQuery } from '@tanstack/react-query';
import { cursorOf } from '../api/helpers';
import { Theme, useThemedStyles } from '../theme';
import { Text, TextInput } from '../components/Text';
import { EmptyView, ErrorView, LoadingView } from '../components/StateViews';
import {
  getListExpensesQueryKey,
  listExpenses,
} from '../api/generated/splitapp';
import type { Expense } from '../api/generated/model';
import { ExpenseRow } from '../expenses/ExpenseRow';
import { useNameOf } from '../expenses/useNames';
import { useMoney } from '../money/useMoney';
import { useRefreshPlan } from '../premium/gate';
import { SEARCH_DEBOUNCE_MS, useDebounced } from '../search/useDebounced';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'Search'>;
export const SEARCH_PAGE_SIZE = 25;
export const SEARCH_MIN_CHARS = 2;

// SCR-36: premium search. At least 2 characters, a 300 ms debounce, 25 per page. A 402 sends a free user to SCR-39.
export function SearchScreen({ navigation }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { exponentOf } = useMoney();
  const nameOf = useNameOf(null);
  const [text, setText] = useState('');
  const q = useDebounced(text.trim(), SEARCH_DEBOUNCE_MS);
  const active = q.length >= SEARCH_MIN_CHARS;

  const results = useInfiniteQuery({
    queryKey: [
      ...getListExpensesQueryKey({ q, limit: SEARCH_PAGE_SIZE }),
      'search',
    ],
    queryFn: ({ pageParam }) =>
      listExpenses({ q, limit: SEARCH_PAGE_SIZE, cursor: cursorOf(pageParam) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last =>
      last.status === 200 ? (last.data.next_cursor ?? undefined) : undefined,
    enabled: active,
  });

  const refreshPlan = useRefreshPlan();
  const paywalled = results.data?.pages.some(p => p.status === 402);
  useEffect(() => {
    if (paywalled) {
      refreshPlan().then(() =>
        navigation.replace('Paywall', { reason: 'search' }),
      );
    }
  }, [paywalled, navigation, refreshPlan]);

  const items: Expense[] = useMemo(
    () =>
      (results.data?.pages ?? []).flatMap(p =>
        p.status === 200 ? p.data.items : [],
      ),
    [results.data],
  );
  const failed =
    results.isError || results.data?.pages.some(p => p.status !== 200);

  let body: React.ReactElement;
  if (!active) {
    body = (
      <EmptyView
        title="Search your expenses"
        hint={`Type at least ${SEARCH_MIN_CHARS} characters.`}
      />
    );
  } else if (results.isPending) {
    body = <LoadingView label="Searching" />;
  } else if (failed && !paywalled) {
    body = (
      <ErrorView offline={results.isError} onRetry={() => results.refetch()} />
    );
  } else {
    body = (
      <FlatList
        testID="search-results"
        data={items}
        keyExtractor={e => e.id}
        ListEmptyComponent={<EmptyView title="No results" />}
        onEndReached={() => {
          if (results.hasNextPage && !results.isFetchingNextPage) {
            results.fetchNextPage();
          }
        }}
        renderItem={({ item }) => (
          <ExpenseRow
            expense={item}
            nameOf={nameOf}
            exponentOf={exponentOf}
            onPress={() =>
              navigation.navigate('ExpenseDetail', { expenseId: item.id })
            }
          />
        )}
      />
    );
  }
  return (
    <View style={styles.flex}>
      <View style={styles.bar}>
        <TextInput
          accessibilityLabel="Search expenses"
          placeholder="Search expenses"
          value={text}
          onChangeText={setText}
          autoFocus
          autoCapitalize="none"
          style={styles.input}
        />
        {text.trim().length > 0 && !active ? (
          <Text style={styles.hint}>
            Type at least {SEARCH_MIN_CHARS} characters.
          </Text>
        ) : null}
      </View>
      {body}
    </View>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    bar: { padding: spacing.lg },
    input: { borderRadius: radius.md, padding: spacing.md },
    hint: { color: colors.textSecondary, marginTop: spacing.xs },
  });
