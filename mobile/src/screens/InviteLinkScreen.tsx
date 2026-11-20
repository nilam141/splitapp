import React, { useState } from 'react';
import { ScrollView, Share, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorView, LoadingView } from '../components/StateViews';
import { showSnackbar } from '../components/snackbar';
import {
  getGetGroupInviteLinkQueryKey,
  useGetGroupInviteLink,
  useResetGroupInviteLink,
} from '../api/generated/splitapp';
import { apiErrorOf } from '../api/helpers';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'InviteLink'>;

// SCR-17: share or reset the group's join link. Copy needs a clipboard module that is not installed yet, so the
// link is selectable text plus the share sheet.
export function InviteLinkScreen({ route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { groupId } = route.params;
  const qc = useQueryClient();
  const query = useGetGroupInviteLink(groupId);
  const reset = useResetGroupInviteLink();
  const [confirm, setConfirm] = useState(false);
  const [banner, setBanner] = useState<string | undefined>();

  if (query.isPending) {
    return <LoadingView label="Loading invite link" />;
  }
  if (query.isError) {
    return <ErrorView offline onRetry={() => query.refetch()} />;
  }
  if (query.data?.status !== 200) {
    return (
      <ErrorView
        offline={false}
        message={
          query.data?.status === 404 || query.data?.status === 409
            ? 'This group is not available.'
            : undefined
        }
        onRetry={() => query.refetch()}
      />
    );
  }
  const link = query.data.data;

  const doReset = async () => {
    setConfirm(false);
    setBanner(undefined);
    try {
      const res = await reset.mutateAsync({ id: groupId });
      if (res.status === 201) {
        qc.setQueryData(getGetGroupInviteLinkQueryKey(groupId), {
          status: 200,
          data: res.data,
          headers: new Headers(),
        });
        showSnackbar('New link created. The old link no longer works.');
      } else {
        setBanner(apiErrorOf(res)?.message ?? 'Could not reset the link.');
      }
    } catch {
      setBanner("Can't reach the server. Try again.");
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="callout" style={styles.label}>
        Invite link
      </Text>
      <Text
        selectable
        accessibilityLabel={`Invite link ${link.url}`}
        style={styles.link}
      >
        {link.url}
      </Text>
      <Text style={styles.warning}>
        Anyone with the link can join this group.
      </Text>
      {banner ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {banner}
        </Text>
      ) : null}
      <View style={styles.buttons}>
        <Button
          title="Share"
          onPress={() => {
            Share.share({ message: link.url }).catch(() => undefined);
          }}
        />
        <Button
          title="Reset link"
          variant="outlined"
          loading={reset.isPending}
          disabled={reset.isPending}
          onPress={() => setConfirm(true)}
        />
      </View>
      <ConfirmDialog
        visible={confirm}
        title="Reset the invite link?"
        message="The current link stops working. People who already joined stay in the group."
        confirmLabel="Reset"
        onClose={() => setConfirm(false)}
        onConfirm={doReset}
      />
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    label: { color: colors.textSecondary, marginBottom: spacing.xs },
    link: {
      backgroundColor: colors.fieldBackground,
      borderRadius: radius.md,
      padding: spacing.md,
    },
    warning: { color: colors.textSecondary, marginTop: spacing.md },
    error: { color: colors.errorText, marginTop: spacing.md },
    buttons: { marginTop: spacing.xl, gap: spacing.sm },
  });
