import React, { useMemo, useState } from 'react';
import {
  Button,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useListCategories } from '../api/generated/splitapp';
import type { Category } from '../api/generated/model';
import { ErrorView, LoadingView } from '../components/StateViews';
import { Panel } from './Panel';
import { addDays, validateDate } from './draft';

// SCR-25: search + parent headings with child rows.
export function CategoryPanel({
  selected,
  onPick,
  onCancel,
}: {
  selected: number | undefined;
  onPick: (id: number) => void;
  onCancel: () => void;
}) {
  const query = useListCategories({
    query: { staleTime: 24 * 60 * 60 * 1000 },
  });
  const [search, setSearch] = useState('');
  const tree: Category[] = useMemo(
    () => (query.data?.status === 200 ? query.data.data : []),
    [query.data],
  );
  const needle = search.trim().toLowerCase();
  const sections = useMemo(
    () =>
      tree
        .map(parent => {
          const children = (parent.children ?? []).filter(c =>
            c.name.toLowerCase().includes(needle),
          );
          const parentMatches =
            (parent.children ?? []).length === 0 &&
            parent.name.toLowerCase().includes(needle);
          return { parent, children, parentMatches };
        })
        .filter(s => s.children.length > 0 || s.parentMatches),
    [tree, needle],
  );

  let body: React.ReactNode;
  if (query.isPending) {
    body = <LoadingView label="Loading categories" />;
  } else if (query.isError || query.data?.status !== 200) {
    body = (
      <ErrorView offline={query.isError} onRetry={() => query.refetch()} />
    );
  } else {
    body = (
      <>
        <TextInput
          accessibilityLabel="Search categories"
          value={search}
          onChangeText={setSearch}
          placeholder="Search"
          style={styles.input}
        />
        {sections.length === 0 ? (
          <Text style={styles.none}>No matching category</Text>
        ) : (
          sections.map(({ parent, children, parentMatches }) => (
            <View key={parent.id}>
              {parentMatches ? (
                <CategoryRow cat={parent} selected={selected} onPick={onPick} />
              ) : (
                <>
                  <Text style={styles.heading}>{parent.name}</Text>
                  {children.map(c => (
                    <CategoryRow
                      key={c.id}
                      cat={c}
                      selected={selected}
                      onPick={onPick}
                    />
                  ))}
                </>
              )}
            </View>
          ))
        )}
      </>
    );
  }
  return (
    <Panel title="Category" onCancel={onCancel}>
      {body}
    </Panel>
  );
}

function CategoryRow({
  cat,
  selected,
  onPick,
}: {
  cat: Category;
  selected: number | undefined;
  onPick: (id: number) => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Category: ${cat.name}`}
      accessibilityState={{ selected: cat.id === selected }}
      onPress={() => onPick(cat.id)}
      style={styles.row}
    >
      <Text style={cat.id === selected ? styles.selected : undefined}>
        {cat.name}
      </Text>
    </Pressable>
  );
}

// SCR-27: a typed date (no calendar dependency yet) within 2000-01-01 and today + 365 days. Repeat is V2.
export function DatePanel({
  date,
  today,
  onDone,
  onCancel,
}: {
  date: string;
  today: string;
  onDone: (date: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(date);
  const error = validateDate(text, today);
  const shift = (days: number) => {
    if (!error) {
      setText(addDays(text, days));
    }
  };
  return (
    <Panel
      title="Date"
      onCancel={onCancel}
      onDone={() => onDone(text)}
      doneDisabled={!!error}
    >
      <TextInput
        accessibilityLabel="Expense date (YYYY-MM-DD)"
        value={text}
        onChangeText={setText}
        autoCapitalize="none"
        style={[styles.input, error ? styles.inputError : null]}
      />
      {error ? (
        <Text accessibilityRole="alert" style={styles.errorText}>
          {error}
        </Text>
      ) : null}
      <View style={styles.dateButtons}>
        <Button title="Previous day" onPress={() => shift(-1)} />
        <Button title="Today" onPress={() => setText(today)} />
        <Button title="Next day" onPress={() => shift(1)} />
      </View>
    </Panel>
  );
}

// SCR-28: note text only (images come later).
export function NotePanel({
  notes,
  onDone,
  onCancel,
}: {
  notes: string;
  onDone: (notes: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(notes);
  const tooLong = text.length > 2000;
  return (
    <Panel
      title="Note"
      onCancel={onCancel}
      onDone={() => onDone(text)}
      doneDisabled={tooLong}
    >
      <TextInput
        accessibilityLabel="Note"
        multiline
        value={text}
        onChangeText={setText}
        style={[styles.input, styles.multiline]}
      />
      <Text style={tooLong ? styles.errorText : styles.count}>
        {text.length} / 2000
      </Text>
    </Panel>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 6,
    padding: 10,
    fontSize: 16,
    marginBottom: 8,
  },
  inputError: { borderColor: '#b00020' },
  multiline: { minHeight: 120, textAlignVertical: 'top' },
  none: { color: '#666', textAlign: 'center', marginTop: 24 },
  heading: { fontWeight: '700', marginTop: 12, marginBottom: 4 },
  row: { paddingVertical: 10, paddingLeft: 8 },
  selected: { fontWeight: '700' },
  errorText: { color: '#b00020' },
  count: { color: '#666', textAlign: 'right' },
  dateButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 12,
  },
});
