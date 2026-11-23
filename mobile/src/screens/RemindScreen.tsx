import React, { useState } from 'react';
import { ScrollView, Share, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Theme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { FormField } from '../components/FormField';
import { showSnackbar } from '../components/snackbar';
import { useCreateReminder } from '../api/generated/splitapp';
import { apiErrorOf } from '../api/helpers';
import { useMoney } from '../money/useMoney';
import { MAX_REMINDER_MESSAGE, reminderText } from '../remind/message';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'Remind'>;

// SCR-33: remind someone who owes you, by email through the server or through the share sheet.
export function RemindScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { toUserId, toName, groupId, amountMinor, currency } = route.params;
  const { format } = useMoney();
  const send = useCreateReminder();
  const [message, setMessage] = useState(() =>
    reminderText(
      toName,
      amountMinor !== undefined && currency
        ? format(amountMinor, currency)
        : undefined,
    ),
  );
  const [notice, setNotice] = useState<
    { tone: 'neutral' | 'error'; text: string } | undefined
  >();
  const tooLong = message.length > MAX_REMINDER_MESSAGE;

  const sendViaApp = async () => {
    setNotice(undefined);
    if (tooLong) {
      return;
    }
    try {
      const res = await send.mutateAsync({
        data: {
          to_user_id: toUserId,
          group_id: groupId ?? null,
          message: message.trim() === '' ? null : message,
        },
      });
      if (res.status === 202) {
        showSnackbar('Reminder sent');
        navigation.goBack();
      } else if (res.status === 429) {
        setNotice({
          tone: 'neutral',
          text: 'Wait 1 minute before sending another reminder.',
        });
      } else if ((res.status as number) === 501) {
        setNotice({
          tone: 'error',
          text: 'Reminders are not available yet. You can share the text instead.',
        });
      } else {
        setNotice({
          tone: 'error',
          text: apiErrorOf(res)?.message ?? 'Could not send the reminder.',
        });
      }
    } catch {
      setNotice({
        tone: 'error',
        text: "Can't reach the server. Check your connection and try again.",
      });
    }
  };

  const share = () => {
    Share.share({ message }).catch(() => undefined);
  };

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <Text variant="callout" style={styles.label}>
        To
      </Text>
      <Text accessibilityLabel={`To ${toName}`} variant="headline">
        {toName}
      </Text>
      <View style={styles.gap} />
      <FormField
        label="Message"
        value={message}
        onChangeText={setMessage}
        multiline
        error={
          tooLong
            ? `The message can be at most ${MAX_REMINDER_MESSAGE} characters.`
            : undefined
        }
      />
      {notice ? (
        <Text
          accessibilityRole="alert"
          style={notice.tone === 'error' ? styles.error : styles.neutral}
        >
          {notice.text}
        </Text>
      ) : null}
      <View style={styles.buttons}>
        <Button
          title="Send via app"
          onPress={sendViaApp}
          loading={send.isPending}
          disabled={send.isPending || tooLong}
        />
        <Button title="Share" variant="secondary" onPress={share} />
      </View>
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    label: { color: colors.textSecondary },
    gap: { height: spacing.lg },
    error: { color: colors.errorText, marginTop: spacing.sm },
    neutral: {
      backgroundColor: colors.fieldBackground,
      borderRadius: radius.md,
      padding: spacing.md,
      marginTop: spacing.sm,
    },
    buttons: { marginTop: spacing.lg, gap: spacing.sm },
  });
