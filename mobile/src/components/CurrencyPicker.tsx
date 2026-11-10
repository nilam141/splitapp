import React from 'react';
import {
  ActivityIndicator,
  Button,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useListCurrencies } from '../api/generated/splitapp';

type Props = {
  visible: boolean;
  selected: string;
  onSelect: (code: string) => void;
  onClose: () => void;
};

// Modal picker backed by GET /currencies (loading, empty, error + retry states).
export function CurrencyPicker({
  visible,
  selected,
  onSelect,
  onClose,
}: Props) {
  const query = useListCurrencies({
    query: { enabled: visible, staleTime: 24 * 60 * 60 * 1000 },
  });
  const currencies = query.data?.status === 200 ? query.data.data : [];

  let body: React.ReactNode;
  if (query.isPending) {
    body = <ActivityIndicator accessibilityLabel="Loading currencies" />;
  } else if (query.isError || query.data?.status !== 200) {
    body = (
      <View style={styles.center}>
        <Text>Couldn't load currencies.</Text>
        <Button title="Retry" onPress={() => query.refetch()} />
      </View>
    );
  } else if (currencies.length === 0) {
    body = <Text style={styles.center}>No currencies available.</Text>;
  } else {
    body = (
      <FlatList
        data={currencies}
        keyExtractor={c => c.code}
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: item.code === selected }}
            onPress={() => {
              onSelect(item.code);
              onClose();
            }}
            style={styles.row}
          >
            <Text style={item.code === selected ? styles.selected : undefined}>
              {item.code} - {item.name} ({item.symbol})
            </Text>
          </Pressable>
        )}
      />
    );
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.container}>
        <Text accessibilityRole="header" style={styles.title}>
          Default currency
        </Text>
        {body}
        <Button title="Cancel" onPress={onClose} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  title: { fontSize: 20, fontWeight: '600', marginBottom: 12 },
  row: { paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  selected: { fontWeight: '700' },
  center: { padding: 24, alignItems: 'center' },
});
