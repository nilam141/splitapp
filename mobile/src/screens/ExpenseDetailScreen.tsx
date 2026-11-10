import React, { useLayoutEffect, useMemo, useState } from 'react';
import {
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  getListExpenseCommentsQueryKey,
  listExpenseComments,
  useCreateExpenseComment,
  useDeleteExpense,
  useGetExpense,
  useListCategories,
  useRestoreExpense,
} from '../api/generated/splitapp';
import {
  apiErrorOf,
  invalidateExpenses,
  invalidateFriends,
  invalidateGroups,
} from '../api/helpers';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { useNameOf } from '../expenses/useNames';
import { formatMinorAmount } from '../money/format';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'ExpenseDetail'>;
const OFFLINE = "Can't reach the server. Check your connection and try again.";
const COMMENT_PAGE = 50;

// SCR-29: expense, payers, splits, notes, comments, delete / restore and the edit entry point.
export function ExpenseDetailScreen({ navigation, route }: Props) {
  const { expenseId } = route.params;
  const qc = useQueryClient();
  const { exponentOf } = useMoney();
  const query = useGetExpense(expenseId);
  const expense = query.data?.status === 200 ? query.data.data : undefined;
  const nameOf = useNameOf(expense ? (expense.group_id ?? null) : undefined);
  const categories = useListCategories({
    query: { staleTime: 24 * 60 * 60 * 1000 },
  });
  const deleteExpense = useDeleteExpense();
  const restoreExpense = useRestoreExpense();
  const postComment = useCreateExpenseComment();

  const comments = useInfiniteQuery({
    queryKey: [
      ...getListExpenseCommentsQueryKey(expenseId, { limit: COMMENT_PAGE }),
      'infinite',
    ],
    queryFn: ({ pageParam }) =>
      listExpenseComments(expenseId, {
        limit: COMMENT_PAGE,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last =>
      last.status === 200 ? (last.data.next_cursor ?? undefined) : undefined,
    enabled: !!expense,
  });
  const commentList = useMemo(
    () =>
      (comments.data?.pages ?? []).flatMap(p =>
        p.status === 200 ? p.data.items : [],
      ),
    [comments.data],
  );

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [banner, setBanner] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');
  const [commentError, setCommentError] = useState<string | undefined>();

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight:
        expense && !expense.deleted_at
          ? () => (
              <Button
                title="Edit"
                onPress={() =>
                  navigation.navigate('ExpenseForm', { expenseId })
                }
              />
            )
          : undefined,
    });
  }, [navigation, expense, expenseId]);

  if (query.isPending) {
    return <LoadingView label="Loading expense" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (!expense) {
    return (
      <ErrorView
        offline={false}
        message={
          query.data?.status === 404 || query.data?.status === 403
            ? 'Cannot find expense.'
            : undefined
        }
        onRetry={() => navigation.goBack()}
      />
    );
  }

  const exponent = exponentOf(expense.total.currency);
  const fmt = (minor: number) =>
    `${expense.total.currency} ${formatMinorAmount(minor, exponent)}`;
  const categoryName = (
    categories.data?.status === 200
      ? categories.data.data.flatMap(c => [c, ...(c.children ?? [])])
      : []
  ).find(c => c.id === expense.category_id)?.name;

  const refresh = async () => {
    await Promise.all([
      invalidateExpenses(qc),
      invalidateGroups(qc),
      invalidateFriends(qc),
    ]);
  };

  const run = async (
    action: () => Promise<{ status: number; data?: unknown }>,
    okStatus: number,
  ) => {
    setBanner(undefined);
    setBusy(true);
    try {
      const res = await action();
      if (res.status === okStatus) {
        await refresh();
      } else if (res.status === 409) {
        await refresh();
        setBanner(
          apiErrorOf(res)?.message ?? 'The expense changed. We reloaded it.',
        );
      } else {
        setBanner(
          apiErrorOf(res)?.message ?? 'Something went wrong. Please try again.',
        );
      }
    } catch {
      setBanner(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    const body = text.trim();
    if (body.length < 1) {
      setCommentError('Write a comment first.');
      return;
    }
    if (body.length > 1000) {
      setCommentError('A comment can be at most 1000 characters.');
      return;
    }
    setCommentError(undefined);
    setBusy(true);
    try {
      const res = await postComment.mutateAsync({
        id: expenseId,
        data: { body },
      });
      if (res.status === 201) {
        setText('');
        await comments.refetch();
      } else {
        setCommentError(
          apiErrorOf(res)?.message ?? 'Could not post the comment.',
        );
      }
    } catch {
      setCommentError(OFFLINE);
    } finally {
      setBusy(false);
    }
  };

  const deleted = !!expense.deleted_at;
  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      {deleted ? (
        <View style={styles.deleted}>
          <Text accessibilityRole="alert">
            {`deleted by ${expense.deleted_by ? nameOf(expense.deleted_by) : 'someone'} on ${(expense.deleted_at ?? '').slice(0, 10)}`}
          </Text>
          <Button
            title="Restore"
            disabled={busy}
            onPress={() =>
              run(() => restoreExpense.mutateAsync({ id: expenseId }), 200)
            }
          />
        </View>
      ) : null}
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}

      <Text accessibilityRole="header" style={styles.title}>
        {expense.description}
      </Text>
      <Text style={styles.total}>{fmt(expense.total.amount_minor)}</Text>
      <Text style={styles.meta}>
        {expense.expense_date}
        {categoryName ? ` - ${categoryName}` : ''}
      </Text>
      <Text style={styles.meta}>
        {`added by ${nameOf(expense.created_by)} on ${expense.created_at.slice(0, 10)}`}
      </Text>
      {expense.updated_by ? (
        <Text style={styles.meta}>
          {`updated by ${nameOf(expense.updated_by)} on ${(expense.updated_at ?? '').slice(0, 10)}`}
        </Text>
      ) : null}

      {expense.payers.map(p => (
        <Text key={p.user_id} style={styles.line}>
          {`${nameOf(p.user_id)} paid ${fmt(p.paid_amount_minor)}`}
        </Text>
      ))}
      <Text style={styles.section}>Split</Text>
      {expense.splits.map(s => (
        <Text key={s.user_id} style={styles.line}>
          {`${nameOf(s.user_id)} ${nameOf(s.user_id) === 'You' ? 'owe' : 'owes'} ${fmt(s.owed_amount_minor)}`}
        </Text>
      ))}
      {expense.notes ? (
        <>
          <Text style={styles.section}>Notes</Text>
          <Text>{expense.notes}</Text>
        </>
      ) : null}

      {!deleted ? (
        <View style={styles.actions}>
          <Button
            title="Delete"
            color="#b00020"
            disabled={busy}
            onPress={() => setConfirmDelete(true)}
          />
        </View>
      ) : null}

      <Text style={styles.section}>Comments</Text>
      {comments.isPending ? (
        <LoadingView label="Loading comments" />
      ) : comments.isError ||
        comments.data?.pages.some(p => p.status !== 200) ? (
        <ErrorView
          offline={comments.isError}
          onRetry={() => comments.refetch()}
        />
      ) : commentList.length === 0 ? (
        <Text style={styles.meta}>No comments yet</Text>
      ) : (
        commentList.map(c => (
          <View
            key={c.id}
            style={[styles.comment, c.kind === 'system' ? styles.system : null]}
          >
            {c.kind === 'user' ? (
              <Text style={styles.author}>{c.user?.name ?? 'Someone'}</Text>
            ) : null}
            <Text style={c.kind === 'system' ? styles.systemText : undefined}>
              {c.body}
            </Text>
          </View>
        ))
      )}
      {comments.hasNextPage ? (
        <Button
          title="Load more comments"
          onPress={() => comments.fetchNextPage()}
        />
      ) : null}

      <TextInput
        accessibilityLabel="Comment"
        placeholder="Add a comment"
        value={text}
        onChangeText={setText}
        maxLength={1000}
        style={styles.input}
      />
      {commentError ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {commentError}
        </Text>
      ) : null}
      <Button title="Send" disabled={busy} onPress={send} />

      <ConfirmDialog
        visible={confirmDelete}
        title="Delete this expense?"
        message="It is removed from balances for everyone. You can restore it afterwards."
        confirmLabel="Delete"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          run(() => deleteExpense.mutateAsync({ id: expenseId }), 200);
        }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  deleted: {
    backgroundColor: '#fff3cd',
    padding: 10,
    borderRadius: 6,
    marginBottom: 12,
  },
  banner: {
    backgroundColor: '#fde8e8',
    color: '#8a1c1c',
    padding: 10,
    borderRadius: 6,
    marginBottom: 12,
  },
  title: { fontSize: 22, fontWeight: '700' },
  total: { fontSize: 20, marginVertical: 4 },
  meta: { color: '#666', marginBottom: 2 },
  line: { paddingVertical: 3, fontSize: 15 },
  section: { fontSize: 16, fontWeight: '600', marginTop: 18, marginBottom: 6 },
  actions: { marginTop: 16, alignItems: 'flex-start' },
  comment: {
    backgroundColor: '#f1f3f4',
    borderRadius: 8,
    padding: 8,
    marginBottom: 6,
  },
  system: { backgroundColor: 'transparent' },
  systemText: { fontStyle: 'italic', color: '#666' },
  author: { fontWeight: '600', marginBottom: 2 },
  input: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 10,
    marginTop: 12,
    marginBottom: 8,
  },
  error: { color: '#b00020', marginBottom: 6 },
});
