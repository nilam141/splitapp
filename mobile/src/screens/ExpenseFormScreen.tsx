import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  BackHandler,
  Button,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  useCreateExpense,
  useCreateGroupExpense,
  useGetExpense,
  useGetGroup,
  useListCategories,
  useListFriends,
  useUpdateExpense,
} from '../api/generated/splitapp';
import type { Category, Expense } from '../api/generated/model';
import {
  apiErrorOf,
  idempotencyHeaders,
  invalidateExpenses,
  invalidateFriends,
  invalidateGroups,
  newIdempotencyKey,
} from '../api/helpers';
import { useAuth } from '../auth/AuthContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { CurrencyPicker } from '../components/CurrencyPicker';
import { ErrorView, LoadingView } from '../components/StateViews';
import { showToast } from '../components/toast';
import {
  buildRequest,
  canonicalPeople,
  draftFromExpense,
  evaluatePayers,
  evaluateSplit,
  initialDraft,
  isoDate,
  parseAmount,
  type DraftErrors,
  type ExpenseDraft,
  type Person,
} from '../expenses/draft';
import { PayersPanel } from '../expenses/PayersPanel';
import { CategoryPanel, DatePanel, NotePanel } from '../expenses/PickerPanels';
import { SplitPanel } from '../expenses/SplitPanel';
import { useNameOf } from '../expenses/useNames';
import { formatMinorAmount } from '../money/format';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'ExpenseForm'>;
type Panel =
  'main' | 'split' | 'payers' | 'category' | 'currency' | 'date' | 'note';

const OFFLINE = "Can't reach the server. Check your connection and try again.";

// SCR-22 loader: gathers the group / friend / expense the form needs, then mounts the form once.
export function ExpenseFormScreen({ navigation, route }: Props) {
  const { groupId, friendId, expenseId } = route.params;
  const { user } = useAuth();
  const expenseQuery = useGetExpense(expenseId ?? '', {
    query: { enabled: !!expenseId },
  });
  const expense =
    expenseQuery.data?.status === 200 ? expenseQuery.data.data : undefined;
  const effectiveGroupId = groupId ?? expense?.group_id ?? undefined;
  const groupQuery = useGetGroup(effectiveGroupId ?? '', {
    query: { enabled: !!effectiveGroupId },
  });
  const friendsQuery = useListFriends();
  const nameOf = useNameOf(effectiveGroupId ?? null);
  const { exponentOf } = useMoney();
  useListCategories({ query: { staleTime: 24 * 60 * 60 * 1000 } });

  useEffect(() => {
    navigation.setOptions({
      title: expenseId ? 'Edit expense' : 'Add expense',
    });
  }, [navigation, expenseId]);

  if (!user) {
    return <LoadingView label="Loading" />;
  }
  const pending =
    (!!expenseId && expenseQuery.isPending) ||
    (!!effectiveGroupId && groupQuery.isPending) ||
    friendsQuery.isPending;
  if (pending) {
    return <LoadingView label="Loading expense form" />;
  }
  const failed = [expenseQuery, groupQuery, friendsQuery].find(
    (q, i) =>
      (i === 0 ? !!expenseId : i === 1 ? !!effectiveGroupId : true) &&
      q.isError,
  );
  if (failed) {
    return <ErrorView offline onRetry={() => failed.refetch()} />;
  }
  if (expenseId && !expense) {
    return (
      <ErrorView
        offline={false}
        message="Cannot find this expense."
        onRetry={() => expenseQuery.refetch()}
      />
    );
  }
  const group =
    groupQuery.data?.status === 200 ? groupQuery.data.data : undefined;
  if (effectiveGroupId && !group) {
    return (
      <ErrorView
        offline={false}
        message="Cannot open this group."
        onRetry={() => groupQuery.refetch()}
      />
    );
  }

  let people: Person[];
  if (group) {
    people = group.members
      .filter(m => !m.left_at)
      .map(m => ({ id: m.user.id, name: m.user.name }));
  } else {
    const ids = expense
      ? [
          ...new Set([
            ...expense.payers.map(p => p.user_id),
            ...expense.splits.map(s => s.user_id),
          ]),
        ]
      : [user.id, friendId ?? ''].filter(id => id !== '');
    people = canonicalPeople(
      ids.map(id => ({ id, name: nameOf(id) })),
      { isGroup: false, creatorId: expense?.created_by ?? user.id },
    );
  }
  if (!group && !expense && people.length < 2) {
    return (
      <ErrorView
        offline={false}
        message="Pick a group or a friend to add an expense with."
        onRetry={() => navigation.goBack()}
      />
    );
  }
  const currency =
    expense?.total.currency ?? group?.default_currency ?? user.default_currency;

  return (
    <ExpenseForm
      navigation={navigation}
      meId={user.id}
      people={people}
      groupId={effectiveGroupId}
      expense={expense}
      currency={currency}
      nameOf={nameOf}
      exponentOf={exponentOf}
    />
  );
}

type FormProps = {
  navigation: Props['navigation'];
  meId: string;
  people: Person[];
  groupId: string | undefined;
  expense: Expense | undefined;
  currency: string;
  nameOf: (id: string) => string;
  exponentOf: (currency: string) => number;
};

function ExpenseForm({
  navigation,
  meId,
  people,
  groupId,
  expense,
  currency,
  nameOf,
  exponentOf,
}: FormProps) {
  const qc = useQueryClient();
  const today = useMemo(() => isoDate(new Date()), []);
  const idemKey = useRef(newIdempotencyKey());
  const createInGroup = useCreateGroupExpense({
    request: idempotencyHeaders(idemKey.current),
  });
  const createNonGroup = useCreateExpense({
    request: idempotencyHeaders(idemKey.current),
  });
  const update = useUpdateExpense();
  const categories = useListCategories({
    query: { staleTime: 24 * 60 * 60 * 1000 },
  });

  const initial = useMemo(
    () =>
      expense
        ? draftFromExpense(expense, exponentOf(expense.total.currency))
        : initialDraft(meId, people, currency, today),
    // seeded once: later refetches must not overwrite what the user typed
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const [draft, setDraft] = useState<ExpenseDraft>(initial);
  const [panel, setPanel] = useState<Panel>('main');
  const [errors, setErrors] = useState<DraftErrors>({});
  const [banner, setBanner] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState<
    | { kind: 'split-gap'; message: string; panel: 'split' | 'payers' }
    | { kind: 'discard'; action: unknown }
    | null
  >(null);
  const leaving = useRef(false);

  const exponent = exponentOf(draft.currency);
  const fmt = useCallback(
    (minor: number) => formatMinorAmount(minor, exponent),
    [exponent],
  );
  const amount = parseAmount(draft.amountText, exponent);
  const total = amount.ok ? amount.minor : undefined;
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  // Back with changes -> "discard changes?" (SCR-22).
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(
    () =>
      navigation.addListener('beforeRemove', e => {
        if (leaving.current || !dirtyRef.current) {
          return;
        }
        e.preventDefault();
        setDialog({ kind: 'discard', action: e.data.action });
      }),
    [navigation],
  );
  // The hardware back button closes a sub-panel first.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (panel !== 'main') {
        setPanel('main');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [panel]);

  const set = (changes: Partial<ExpenseDraft>) => {
    setDraft(d => ({ ...d, ...changes }));
    setErrors({});
  };

  const split = evaluateSplit(draft.split, people, total, exponent, fmt);
  const payers = evaluatePayers(draft.payers, people, total, exponent, fmt);
  const splitSummary =
    draft.split.type === 'equal'
      ? draft.split.included.length === people.length
        ? 'equally'
        : `equally between ${draft.split.included.length}`
      : `by ${draft.split.type}`;
  const payerSummary =
    draft.payers.mode === 'single'
      ? nameOf(draft.payers.payerId)
      : 'multiple people';

  const categoryName = useMemo(() => {
    if (draft.categoryId === undefined) {
      return 'Uncategorized';
    }
    const all: Category[] =
      categories.data?.status === 200
        ? categories.data.data.flatMap(c => [c, ...(c.children ?? [])])
        : [];
    return all.find(c => c.id === draft.categoryId)?.name ?? 'Category';
  }, [draft.categoryId, categories.data]);

  const finish = async () => {
    await Promise.all([
      invalidateExpenses(qc),
      invalidateGroups(qc),
      invalidateFriends(qc),
    ]);
    leaving.current = true;
    navigation.goBack();
  };

  const onSave = async () => {
    setBanner(undefined);
    const built = buildRequest(draft, people, exponent, today, fmt);
    if (!built.ok) {
      setErrors(built.errors);
      if (built.panel) {
        const message =
          (built.panel === 'split'
            ? built.errors.split
            : built.errors.payers) ?? 'This is not valid.';
        setDialog({ kind: 'split-gap', message, panel: built.panel });
      }
      return;
    }
    setSaving(true);
    try {
      if (expense) {
        const res = await update.mutateAsync({
          id: expense.id,
          data: { version: expense.version, ...built.body },
        });
        if (res.status === 200) {
          showToast('Expense updated');
          await finish();
          return;
        }
        handleFailure(res);
        return;
      }
      const res = groupId
        ? await createInGroup.mutateAsync({ id: groupId, data: built.body })
        : await createNonGroup.mutateAsync({
            data: { ...built.body, group_id: null },
          });
      if (res.status === 201) {
        showToast('Expense added');
        await finish();
        return;
      }
      idemKey.current = newIdempotencyKey();
      handleFailure(res);
    } catch {
      setBanner(OFFLINE); // no response: the same key is kept for the retry
    } finally {
      setSaving(false);
    }
  };

  const handleFailure = (res: { status: number; data?: unknown }) => {
    const err = apiErrorOf(res);
    if (res.status === 409 && err?.code === 'VERSION_CONFLICT') {
      invalidateExpenses(qc);
      setBanner(
        'This expense was changed by someone else. Go back and open it again to edit the latest version.',
      );
    } else if (
      res.status === 409 &&
      err?.code === 'EXPENSE_HAS_DEPARTED_MEMBER'
    ) {
      setBanner(
        'This expense includes someone who has left the group, so it cannot be edited.',
      );
    } else if (res.status === 403) {
      setBanner("You can't change this expense.");
    } else if (res.status === 404) {
      setBanner('This expense or group no longer exists.');
    } else if (res.status === 422) {
      setBanner(err?.message ?? 'The server rejected these values.');
    } else {
      setBanner(err?.message ?? 'Something went wrong. Please try again.');
    }
  };

  const close = () => setPanel('main');
  if (panel === 'split') {
    return (
      <SplitPanel
        split={draft.split}
        people={people}
        meId={meId}
        nameOf={nameOf}
        total={total}
        exponent={exponent}
        onCancel={close}
        onDone={r => {
          set(r);
          close();
        }}
      />
    );
  }
  if (panel === 'payers') {
    return (
      <PayersPanel
        payers={draft.payers}
        people={people}
        nameOf={nameOf}
        total={total}
        exponent={exponent}
        onCancel={close}
        onDone={p => {
          set({ payers: p });
          close();
        }}
      />
    );
  }
  if (panel === 'category') {
    return (
      <CategoryPanel
        selected={draft.categoryId}
        onCancel={close}
        onPick={id => {
          set({ categoryId: id });
          close();
        }}
      />
    );
  }
  if (panel === 'date') {
    return (
      <DatePanel
        date={draft.date}
        today={today}
        onCancel={close}
        onDone={d => {
          set({ date: d });
          close();
        }}
      />
    );
  }
  if (panel === 'note') {
    return (
      <NotePanel
        notes={draft.notes}
        onCancel={close}
        onDone={n => {
          set({ notes: n });
          close();
        }}
      />
    );
  }

  const otherNames = people
    .filter(p => p.id !== meId)
    .map(p => nameOf(p.id))
    .join(', ');
  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.with}>
        With you and: {otherNames || 'nobody yet'}
      </Text>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.banner}>
          {banner}
        </Text>
      ) : null}

      <Text style={styles.label}>Description</Text>
      <TextInput
        accessibilityLabel="Description"
        value={draft.description}
        onChangeText={t => set({ description: t })}
        maxLength={200}
        style={[styles.input, errors.description ? styles.inputError : null]}
      />
      {errors.description ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {errors.description}
        </Text>
      ) : null}

      <View style={styles.amountRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Currency: ${draft.currency}`}
          disabled={!!expense}
          onPress={() => setPanel('currency')}
          style={styles.chip}
        >
          <Text>{draft.currency}</Text>
        </Pressable>
        <TextInput
          accessibilityLabel="Amount"
          keyboardType="decimal-pad"
          placeholder="0.00"
          value={draft.amountText}
          onChangeText={t => set({ amountText: t })}
          style={[
            styles.input,
            styles.amount,
            errors.amount ? styles.inputError : null,
          ]}
        />
      </View>
      {errors.amount ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {errors.amount}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Category"
        onPress={() => setPanel('category')}
        style={styles.chip}
      >
        <Text>Category: {categoryName}</Text>
      </Pressable>

      <View style={styles.sentence}>
        <Text>Paid by </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Change payers"
          onPress={() => setPanel('payers')}
        >
          <Text style={styles.link}>{payerSummary}</Text>
        </Pressable>
        <Text> and split </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Change split"
          onPress={() => setPanel('split')}
        >
          <Text style={styles.link}>{splitSummary}</Text>
        </Pressable>
      </View>
      {!split.valid && total !== undefined ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {split.error}
        </Text>
      ) : null}
      {draft.payers.mode === 'multiple' &&
      !payers.valid &&
      total !== undefined ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {payers.error}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Date"
        onPress={() => setPanel('date')}
        style={styles.chip}
      >
        <Text>Date: {draft.date}</Text>
      </Pressable>
      {errors.date ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {errors.date}
        </Text>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Note"
        onPress={() => setPanel('note')}
        style={styles.chip}
      >
        <Text>{draft.notes ? 'Note: added' : 'Add a note'}</Text>
      </Pressable>
      {errors.notes ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {errors.notes}
        </Text>
      ) : null}

      <View style={styles.save}>
        <Button
          title={saving ? 'Saving...' : 'Save'}
          onPress={onSave}
          disabled={saving}
        />
      </View>

      <CurrencyPicker
        visible={panel === 'currency'}
        selected={draft.currency}
        title="Currency"
        onSelect={code => set({ currency: code })}
        onClose={close}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'split-gap'}
        title="Check the split"
        message={dialog?.kind === 'split-gap' ? dialog.message : undefined}
        onClose={() => {
          const target = dialog?.kind === 'split-gap' ? dialog.panel : 'main';
          setDialog(null);
          setPanel(target);
        }}
      />
      <ConfirmDialog
        visible={dialog?.kind === 'discard'}
        title="Discard changes?"
        confirmLabel="Discard"
        onConfirm={() => {
          const action = dialog?.kind === 'discard' ? dialog.action : undefined;
          setDialog(null);
          leaving.current = true;
          if (action) {
            navigation.dispatch(
              action as Parameters<typeof navigation.dispatch>[0],
            );
          } else {
            navigation.goBack();
          }
        }}
        onClose={() => setDialog(null)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  with: { color: '#444', marginBottom: 12 },
  banner: {
    backgroundColor: '#fde8e8',
    color: '#8a1c1c',
    padding: 10,
    borderRadius: 6,
    marginBottom: 12,
  },
  label: { marginBottom: 4, color: '#333' },
  input: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 10,
    fontSize: 16,
  },
  inputError: { borderColor: '#b00020' },
  error: { color: '#b00020', marginTop: 4 },
  amountRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    alignItems: 'center',
  },
  amount: { flex: 1 },
  chip: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 16,
    paddingVertical: 8,
    paddingHorizontal: 14,
    marginTop: 12,
    alignSelf: 'flex-start',
  },
  sentence: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 16 },
  link: { color: '#1b6e5a', fontWeight: '600' },
  save: { marginTop: 24 },
});
