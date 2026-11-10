import React, { useEffect, useRef, useState } from 'react';
import {
  Button,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { NavigationAction } from '@react-navigation/native';
import { useCreateGroup } from '../api/generated/splitapp';
import type { GroupCreate } from '../api/generated/model';
import { GroupType } from '../api/generated/model';
import {
  apiErrorOf,
  idempotencyHeaders,
  invalidateFriends,
  invalidateGroups,
  newIdempotencyKey,
} from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { FormField } from '../components/FormField';
import { Segmented } from '../components/Segmented';
import {
  MAX_OTHER_MEMBERS,
  validateGroupForm,
  GroupFormErrors,
} from '../groups/validation';
import type { PersonDraft } from '../people/types';

type Props = NativeStackScreenProps<MainStackParamList, 'CreateGroup'>;

const TYPES = [
  GroupType.home,
  GroupType.trip,
  GroupType.couple,
  GroupType.other,
] as const;

const label = (p: PersonDraft) =>
  p.kind === 'new' ? p.name || p.email || p.phone_e164 || '' : p.name;

// SCR-12.
export function CreateGroupScreen({ navigation, route }: Props) {
  const qc = useQueryClient();
  // One key per form: a retry after a timeout cannot create a second group.
  const idemKey = useRef(newIdempotencyKey());
  const create = useCreateGroup({
    request: idempotencyHeaders(idemKey.current),
  });
  const [name, setName] = useState('');
  const [type, setType] = useState<GroupType>(GroupType.other);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [simplify, setSimplify] = useState(true);
  const [members, setMembers] = useState<PersonDraft[]>([]);
  const [errors, setErrors] = useState<GroupFormErrors>({});
  const [banner, setBanner] = useState<string | undefined>();
  const [pendingLeave, setPendingLeave] = useState<NavigationAction | null>(
    null,
  );
  const leaving = useRef(false);

  useEffect(() => {
    if (route.params?.picked) {
      setMembers(route.params.picked);
    }
  }, [route.params?.picked]);

  const dirty =
    name.trim() !== '' || members.length > 0 || start !== '' || end !== '';
  useEffect(
    () =>
      navigation.addListener('beforeRemove', e => {
        if (!dirty || leaving.current) {
          return;
        }
        e.preventDefault();
        setPendingLeave(e.data.action);
      }),
    [navigation, dirty],
  );

  const submit = async () => {
    const isTrip = type === GroupType.trip;
    const found = validateGroupForm({
      name,
      isTrip,
      start,
      end,
      otherMembers: members.length,
    });
    setErrors(found);
    setBanner(undefined);
    if (Object.keys(found).length > 0) {
      return;
    }
    const body: GroupCreate = {
      name: name.trim(),
      group_type: type,
      simplify_debts: simplify,
      ...(isTrip && start.trim() ? { trip_start_date: start.trim() } : {}),
      ...(isTrip && end.trim() ? { trip_end_date: end.trim() } : {}),
      member_user_ids: members.flatMap(p =>
        p.kind === 'user' ? [p.userId] : [],
      ),
      new_members: members.flatMap(p =>
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
    try {
      const res = await create.mutateAsync({ data: body });
      if (res.status === 201) {
        leaving.current = true;
        await Promise.all([invalidateGroups(qc), invalidateFriends(qc)]);
        navigation.replace('GroupDetail', { groupId: res.data.id });
        return;
      }
      const err = apiErrorOf(res);
      if (err?.code === 'INVALID_DATE_RANGE') {
        setErrors({ end: 'The end date cannot be before the start date.' });
      } else if (err?.code === 'GROUP_TOO_LARGE') {
        setErrors({
          members: 'A group can have at most 200 members including you.',
        });
      } else {
        setBanner(err?.message ?? 'Could not create the group. Try again.');
      }
    } catch {
      setBanner("Can't reach the server. Check your connection and try again.");
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <FormField
        label="Group name"
        value={name}
        onChangeText={setName}
        autoCapitalize="words"
        maxLength={100}
        error={errors.name}
      />
      <Segmented label="Type" options={TYPES} value={type} onChange={setType} />
      {type === GroupType.trip ? (
        <>
          <FormField
            label="Trip start (YYYY-MM-DD)"
            value={start}
            onChangeText={setStart}
            error={errors.start}
          />
          <FormField
            label="Trip end (YYYY-MM-DD)"
            value={end}
            onChangeText={setEnd}
            error={errors.end}
          />
        </>
      ) : null}
      <View style={styles.switchRow}>
        <Text>Simplify debts</Text>
        <Switch
          accessibilityLabel="Simplify debts"
          value={simplify}
          onValueChange={setSimplify}
        />
      </View>
      <Text style={styles.section}>
        Members ({members.length} of {MAX_OTHER_MEMBERS} others)
      </Text>
      <View style={styles.chips}>
        {members.map(m => (
          <Text key={m.key} style={styles.chip}>
            {label(m)}
          </Text>
        ))}
      </View>
      {errors.members ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {errors.members}
        </Text>
      ) : null}
      <Button
        title="Add members"
        onPress={() =>
          navigation.navigate('AddPeople', {
            mode: { kind: 'group-create' },
            selected: members,
          })
        }
      />
      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.submit}>
        <Button
          title={create.isPending ? 'Creating...' : 'Done'}
          onPress={submit}
          disabled={create.isPending}
        />
      </View>
      <ConfirmDialog
        visible={pendingLeave !== null}
        title="Discard this group?"
        message="Your changes will be lost."
        confirmLabel="Discard"
        onClose={() => setPendingLeave(null)}
        onConfirm={() => {
          const action = pendingLeave;
          setPendingLeave(null);
          leaving.current = true;
          if (action) {
            navigation.dispatch(action);
          }
        }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  section: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  chip: {
    backgroundColor: '#e6f2ee',
    borderRadius: 16,
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  error: { color: '#b00020', fontSize: 13, marginVertical: 4 },
  submit: { marginTop: 20 },
});
