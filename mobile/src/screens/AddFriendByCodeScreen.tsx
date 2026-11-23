import React, { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { showSnackbar } from '../components/snackbar';
import { useAddFriend } from '../api/generated/splitapp';
import { apiErrorOf, invalidateFriends } from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'AddFriendByCode'>;

// Add-friend link: sends the code in POST /friends. There is no lookup endpoint (decision D-C), so the person
// is not previewed before adding.
export function AddFriendByCodeScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const qc = useQueryClient();
  const add = useAddFriend();
  const [banner, setBanner] = useState<string | undefined>();

  const submit = async () => {
    setBanner(undefined);
    try {
      const res = await add.mutateAsync({
        data: { friend_code: route.params.code },
      });
      if (res.status === 200 || res.status === 201) {
        await invalidateFriends(qc);
        showSnackbar(`${res.data.friend.user.name} is now your friend`);
        navigation.replace('FriendDetail', {
          friendId: res.data.friend.user.id,
        });
      } else if (res.status === 410) {
        setBanner('This code is no longer valid.');
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Could not add this friend.');
      }
    } catch {
      setBanner("Can't reach the server. Check your connection and try again.");
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text accessibilityRole="header" variant="title2">
        Add this friend?
      </Text>
      <Text style={styles.hint}>
        Friend code {route.params.code}. You will see each other's shared
        expenses.
      </Text>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}
      <Button
        title="Add friend"
        onPress={submit}
        loading={add.isPending}
        disabled={add.isPending}
      />
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.xxl },
    hint: { color: colors.textSecondary, marginVertical: spacing.md },
    error: { color: colors.errorText, marginBottom: spacing.md },
  });
