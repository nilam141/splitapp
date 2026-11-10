import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import {
  useAddGroupMembers,
  useGetGroup,
  useListFriends,
} from '../api/generated/splitapp';
import type { MembersAdd } from '../api/generated/model';
import {
  apiErrorOf,
  invalidateFriends,
  invalidateGroups,
  newIdempotencyKey,
} from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';
import { FormField } from '../components/FormField';
import {
  checkContactsPermission,
  DeviceContact,
  loadDeviceContacts,
  requestContactsPermission,
  ContactsPermission,
} from '../people/contacts';
import { addFriends } from '../people/submit';
import type { PersonDraft } from '../people/types';
import { parseContact, validateName } from '../people/validation';

type Props = NativeStackScreenProps<MainStackParamList, 'AddPeople'>;

// SCR-21. Collects people locally; nothing is sent until Done.
export function AddPeopleScreen({ navigation, route }: Props) {
  const { mode } = route.params;
  const qc = useQueryClient();
  const isFriendMode = mode.kind === 'friend';
  const nameRequired = !isFriendMode; // NewMember.name is required, FriendCreate.name is optional

  const [selected, setSelected] = useState<PersonDraft[]>(
    route.params.selected ?? [],
  );
  const [search, setSearch] = useState('');
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [nameError, setNameError] = useState<string | undefined>();
  const [contactError, setContactError] = useState<string | undefined>();
  const [banner, setBanner] = useState<string | undefined>();
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const [permission, setPermission] =
    useState<ContactsPermission>('undetermined');
  const [deviceContacts, setDeviceContacts] = useState<DeviceContact[]>([]);

  const friendsQuery = useListFriends(undefined, {
    query: { enabled: !isFriendMode },
  });
  const groupQuery = useGetGroup(
    mode.kind === 'group-members' ? mode.groupId : '',
    { query: { enabled: mode.kind === 'group-members' } },
  );
  const addMembers = useAddGroupMembers();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const p = await checkContactsPermission();
      if (cancelled) {
        return;
      }
      setPermission(p);
      if (p === 'granted') {
        const list = await loadDeviceContacts().catch(() => []);
        if (!cancelled) {
          setDeviceContacts(list);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const allowContacts = async () => {
    const p = await requestContactsPermission();
    setPermission(p);
    if (p === 'granted') {
      setDeviceContacts(await loadDeviceContacts().catch(() => []));
    }
  };

  const existingMemberIds = useMemo(() => {
    const g = groupQuery.data?.status === 200 ? groupQuery.data.data : null;
    return new Set(
      (g?.members ?? []).filter(m => !m.left_at).map(m => m.user.id),
    );
  }, [groupQuery.data]);

  const friends =
    friendsQuery.data?.status === 200 ? friendsQuery.data.data.items : [];
  const q = search.trim().toLowerCase();
  const isSelected = (key: string) => selected.some(s => s.key === key);

  const friendRows = isFriendMode
    ? []
    : friends.filter(
        f =>
          !existingMemberIds.has(f.user.id) &&
          (!q || f.user.name.toLowerCase().includes(q)),
      );
  const contactRows = deviceContacts.filter(
    c => !q || c.name.toLowerCase().includes(q),
  );

  const toggle = (p: PersonDraft) =>
    setSelected(cur =>
      cur.some(s => s.key === p.key)
        ? cur.filter(s => s.key !== p.key)
        : [...cur, p],
    );

  // Validates the typed form. Invalid input shows errors and returns null: nothing reaches the network.
  const buildTyped = (): PersonDraft | null => {
    const parsed = parseContact(contact);
    const nErr = validateName(name, nameRequired);
    setNameError(nErr ?? undefined);
    setContactError(parsed.ok ? undefined : parsed.error);
    if (!parsed.ok || nErr) {
      return null;
    }
    const handle = parsed.value.email ?? parsed.value.phone_e164 ?? '';
    return {
      kind: 'new',
      key: `new:${handle}`,
      name: name.trim(),
      ...parsed.value,
      idempotencyKey: newIdempotencyKey(),
    };
  };

  const addTyped = () => {
    const draft = buildTyped();
    if (!draft) {
      return;
    }
    setSelected(cur =>
      cur.some(s => s.key === draft.key) ? cur : [...cur, draft],
    );
    setName('');
    setContact('');
  };

  const done = async () => {
    setBanner(undefined);
    setRowErrors({});
    // Text still sitting in the form counts as "add this person too".
    let people = selected;
    if (contact.trim() || name.trim()) {
      const typed = buildTyped();
      if (!typed) {
        return;
      }
      people = people.some(p => p.key === typed.key)
        ? people
        : [...people, typed];
      setSelected(people);
      setName('');
      setContact('');
    }
    if (mode.kind === 'group-create') {
      navigation.popTo('CreateGroup', { picked: people }, { merge: true });
      return;
    }
    if (people.length === 0) {
      navigation.goBack();
      return;
    }
    setBusy(true);
    try {
      if (mode.kind === 'friend') {
        const outcomes = await addFriends(people);
        await invalidateFriends(qc);
        const failed = outcomes.filter(o => o.error);
        if (failed.length === 0) {
          navigation.goBack();
          return;
        }
        setRowErrors(
          Object.fromEntries(failed.map(o => [o.key, o.error ?? ''])),
        );
        setSelected(people.filter(p => failed.some(f => f.key === p.key)));
        return;
      }
      const body: MembersAdd = {
        user_ids: people.flatMap(p => (p.kind === 'user' ? [p.userId] : [])),
        new_members: people.flatMap(p =>
          p.kind === 'new'
            ? [
                {
                  name: p.name,
                  ...(p.email ? { email: p.email } : {}),
                  ...(p.phone_e164 ? { phone_e164: p.phone_e164 } : {}),
                },
              ]
            : [],
        ),
      };
      const res = await addMembers.mutateAsync({
        id: mode.groupId,
        data: body,
      });
      if (res.status === 200) {
        await Promise.all([invalidateGroups(qc), invalidateFriends(qc)]);
        navigation.goBack();
      } else {
        setBanner(
          res.status === 403
            ? "You can't add people to this group."
            : (apiErrorOf(res)?.message ?? 'Could not add these people.'),
        );
      }
    } catch {
      setBanner("Can't reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      {selected.length > 0 ? (
        <View style={styles.chips}>
          {selected.map(p => (
            <Pressable
              key={p.key}
              accessibilityRole="button"
              accessibilityLabel={`Remove ${p.name || (p.kind === 'new' ? (p.email ?? p.phone_e164) : '')}`}
              onPress={() => toggle(p)}
              style={styles.chip}
            >
              <Text>
                {p.kind === 'new' ? p.name || p.email || p.phone_e164 : p.name}{' '}
                x
              </Text>
              {rowErrors[p.key] ? (
                <Text accessibilityRole="alert" style={styles.error}>
                  {rowErrors[p.key]}
                </Text>
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : null}

      <Text style={styles.section}>Add someone new</Text>
      <FormField
        label={nameRequired ? 'Name' : 'Name (optional)'}
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        error={nameError}
      />
      <FormField
        label="Email or phone"
        value={contact}
        onChangeText={setContact}
        keyboardType="email-address"
        error={contactError}
      />
      <Text style={styles.hint}>
        We will send an invite to this email or number if they are not on the
        app yet.
      </Text>
      <Button title="Add to list" onPress={addTyped} />

      {!isFriendMode ? (
        <View style={styles.block}>
          <Text style={styles.section}>Your friends</Text>
          {friendsQuery.isPending ? (
            <Text accessibilityLabel="Loading friends">Loading...</Text>
          ) : friendsQuery.isError || friendsQuery.data?.status !== 200 ? (
            <View>
              <Text accessibilityRole="alert">Couldn't load your friends.</Text>
              <Button title="Retry" onPress={() => friendsQuery.refetch()} />
            </View>
          ) : friendRows.length === 0 ? (
            <Text style={styles.hint}>No friends to add yet.</Text>
          ) : (
            friendRows.map(f => {
              const draft: PersonDraft = {
                kind: 'user',
                key: `user:${f.user.id}`,
                userId: f.user.id,
                name: f.user.name,
                email: f.user.email,
              };
              return (
                <Pressable
                  key={draft.key}
                  accessibilityRole="button"
                  accessibilityState={{ selected: isSelected(draft.key) }}
                  onPress={() => toggle(draft)}
                  style={styles.row}
                >
                  <Text>
                    {isSelected(draft.key) ? '[x] ' : '[ ] '}
                    {f.user.name}
                  </Text>
                </Pressable>
              );
            })
          )}
        </View>
      ) : null}

      <View style={styles.block}>
        <Text style={styles.section}>Contacts</Text>
        {permission === 'granted' ? (
          <>
            <FormField
              label="Search contacts"
              value={search}
              onChangeText={setSearch}
            />
            {contactRows.length === 0 ? (
              <Text style={styles.hint}>
                No contacts with an email or phone number found.
              </Text>
            ) : (
              contactRows.map(c => {
                const handle = c.email ?? c.phone_e164 ?? '';
                const draft: PersonDraft = {
                  kind: 'new',
                  key: `new:${handle}`,
                  name: c.name,
                  email: c.email,
                  phone_e164: c.phone_e164,
                  idempotencyKey: newIdempotencyKey(),
                };
                return (
                  <Pressable
                    key={c.id}
                    accessibilityRole="button"
                    accessibilityState={{ selected: isSelected(draft.key) }}
                    onPress={() => toggle(draft)}
                    style={styles.row}
                  >
                    <Text>
                      {isSelected(draft.key) ? '[x] ' : '[ ] '}
                      {c.name} ({handle})
                    </Text>
                  </Pressable>
                );
              })
            )}
          </>
        ) : (
          <View>
            <Text style={styles.hint}>
              {permission === 'denied'
                ? 'Contacts access is off. You can still type an email or phone above, or turn contacts on in system settings.'
                : 'Allow contacts so you can pick people you already know. We only read them on this screen to let you choose, and we do not upload your address book.'}
            </Text>
            {permission === 'undetermined' ? (
              <Button title="Allow contacts access" onPress={allowContacts} />
            ) : null}
          </View>
        )}
      </View>

      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.done}>
        <Button
          title={
            busy
              ? 'Adding...'
              : `Done${selected.length ? ` (${selected.length})` : ''}`
          }
          onPress={done}
          disabled={busy}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  section: { fontSize: 16, fontWeight: '600', marginTop: 8, marginBottom: 8 },
  block: { marginTop: 16 },
  hint: { color: '#555', marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  chip: {
    backgroundColor: '#e6f2ee',
    borderRadius: 16,
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  row: { paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  error: { color: '#b00020', fontSize: 13, marginTop: 4 },
  done: { marginTop: 24 },
});
