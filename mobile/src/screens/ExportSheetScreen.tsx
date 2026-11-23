import React, { useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  Share,
  StyleSheet,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { Theme, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { useRefreshPlan } from '../premium/gate';
import { useNameOf } from '../expenses/useNames';
import { useExportJob } from '../exports/useExportJob';
import type { MainStackParamList } from '../navigation/types';

type Props = NativeStackScreenProps<MainStackParamList, 'ExportSheet'>;

// SCR-38: premium CSV export of one group or one friend. Opens the share sheet when the file is ready.
export function ExportSheetScreen({ navigation, route }: Props) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const { groupId, friendId } = route.params;
  const nameOf = useNameOf(groupId ? groupId : null);
  const { phase, retry } = useExportJob(
    groupId
      ? { scope: 'group', group_id: groupId }
      : { scope: 'friend', friend_user_id: friendId },
  );
  const shared = useRef<string | null>(null);
  const refreshPlan = useRefreshPlan();

  const shareFile = (url: string, name?: string | null) => {
    Share.share({ message: name ?? 'SplitApp export', url }).catch(
      () => undefined,
    );
  };

  useEffect(() => {
    if (phase.name === 'paywall') {
      refreshPlan().then(() =>
        navigation.replace('Paywall', { reason: 'export' }),
      );
    }
    if (
      phase.name === 'ready' &&
      phase.file.download_url &&
      shared.current !== phase.file.id
    ) {
      shared.current = phase.file.id;
      shareFile(phase.file.download_url, phase.file.file_name);
    }
  }, [phase, navigation, refreshPlan]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="callout" style={styles.label}>
        Exporting
      </Text>
      <Text variant="headline">
        {groupId ? 'This group' : friendId ? nameOf(friendId) : 'Friend'}
      </Text>
      {phase.name === 'working' ? (
        <View style={styles.row} accessibilityLiveRegion="polite">
          <ActivityIndicator
            accessibilityLabel="Generating export"
            color={colors.brand}
          />
          <Text style={styles.progress}>Generating your file...</Text>
        </View>
      ) : null}
      {phase.name === 'failed' ? (
        <View style={styles.banner} accessibilityRole="alert">
          <Text style={styles.error}>{phase.message}</Text>
          <Button title="Retry" onPress={retry} />
        </View>
      ) : null}
      {phase.name === 'ready' ? (
        <View style={styles.row}>
          <Text>Your file is ready.</Text>
          {phase.file.download_url ? (
            <Button
              title="Share file"
              onPress={() =>
                shareFile(phase.file.download_url ?? '', phase.file.file_name)
              }
            />
          ) : null}
        </View>
      ) : null}
    </ScrollView>
  );
}

const makeStyles = ({ colors, spacing, radius }: Theme) =>
  StyleSheet.create({
    container: { padding: spacing.lg },
    label: { color: colors.textSecondary },
    row: { marginTop: spacing.xl, gap: spacing.md },
    progress: { color: colors.textSecondary },
    banner: {
      marginTop: spacing.xl,
      backgroundColor: colors.errorSubtle,
      borderRadius: radius.md,
      padding: spacing.md,
      gap: spacing.sm,
    },
    error: { color: colors.errorText },
  });
