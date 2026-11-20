import React, { useCallback, useMemo, useRef } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  SectionList,
  StyleSheet,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { cursorOf } from '../api/helpers';
import { Theme, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
import { Button } from '../components/Button';
import { SectionHeader } from '../components/SectionHeader';
import { EmptyView, ErrorView } from '../components/StateViews';
import {
  getListActivityQueryKey,
  listActivity,
  useListGroups,
  useMarkActivityRead,
} from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';
import { useMoney } from '../money/useMoney';
import type { MainStackParamList } from '../navigation/types';
import { ActivityRow } from '../activity/ActivityRow';
import { sectionsOf } from '../activity/describe';
import { activityTarget } from '../activity/target';
import { setUnreadCount } from '../activity/useUnreadBadge';

const PAGE_SIZE = 50;
const SKELETON_ROWS = 5;

function ActivitySkeleton() {
  const { colors, spacing, radius, layout } = useTheme();
  const s = StyleSheet.create({
    row: {
      minHeight: layout.listRowMinHeight,
      paddingHorizontal: spacing.lg,
      flexDirection: 'row',
      alignItems: 'center',
    },
    circle: {
      width: layout.avatar.md,
      height: layout.avatar.md,
      borderRadius: radius.pill,
      backgroundColor: colors.skeletonBase,
      marginRight: spacing.md,
    },
    bars: { flex: 1 },
    barLong: {
      height: spacing.md,
      borderRadius: radius.xs,
      backgroundColor: colors.skeletonBase,
    },
    barShort: {
      marginRight: spacing.giant,
      height: spacing.md,
      borderRadius: radius.xs,
      backgroundColor: colors.skeletonBase,
      marginTop: spacing.sm,
    },
  });
  return (
    <View
      accessible
      accessibilityLabel="Loading"
      accessibilityLiveRegion="polite"
      testID="activity-skeleton"
    >
      {Array.from({ length: SKELETON_ROWS }, (_, i) => (
        <View
          key={i}
          style={s.row}
          importantForAccessibility="no-hide-descendants"
        >
          <View style={s.circle} />
          <View style={s.bars}>
            <View style={s.barLong} />
            <View style={s.barShort} />
          </View>
        </View>
      ))}
    </View>
  );
}

// SCR-10: the feed from GET /activity (cursor paged, newest first), grouped by day. Opening the tab calls
// POST /activity/read (after the feed is fresh, so unread rows still show as unread) and sets the badge to 0.
export function ActivityScreen() {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  const nav = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const qc = useQueryClient();
  const { user } = useAuth();
  const { format } = useMoney();
  const groups = useListGroups();
  const markRead = useMarkActivityRead();

  const feed = useInfiniteQuery({
    queryKey: [...getListActivityQueryKey({ limit: PAGE_SIZE }), 'infinite'],
    queryFn: ({ pageParam }) =>
      listActivity({ limit: PAGE_SIZE, cursor: cursorOf(pageParam) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: last =>
      last.status === 200 ? (last.data.next_cursor ?? undefined) : undefined,
    // Loaded by the focus effect below, so one open of the tab is exactly one load and one read.
    enabled: false,
  });

  const refreshAndRead = useCallback(async () => {
    const res = await feed.refetch();
    if (res.data?.pages[0]?.status === 200) {
      setUnreadCount(qc, 0);
      markRead.mutate();
    }
  }, [feed, qc, markRead]);
  const latest = useRef(refreshAndRead);
  latest.current = refreshAndRead;
  useFocusEffect(
    useCallback(() => {
      latest.current();
    }, []),
  );

  const groupNames = useMemo(() => {
    const map = new Map<string, string>();
    if (groups.data?.status === 200) {
      groups.data.data.items.forEach(g => map.set(g.id, g.name));
    }
    return map;
  }, [groups.data]);
  const ctx = useMemo(
    () => ({
      meId: user?.id,
      format,
      groupName: (id: string) => groupNames.get(id),
    }),
    [user?.id, format, groupNames],
  );

  const items = useMemo(
    () =>
      (feed.data?.pages ?? []).flatMap(p =>
        p.status === 200 ? p.data.items : [],
      ),
    [feed.data],
  );
  const now = new Date();
  const sections = useMemo(() => sectionsOf(items, now), [items]); // eslint-disable-line react-hooks/exhaustive-deps
  const failedPage = feed.data?.pages.find(p => p.status !== 200);
  const hasData = items.length > 0;

  const header = (
    <Text variant="title1" accessibilityRole="header" style={styles.title}>
      Activity
    </Text>
  );

  let body: React.ReactElement;
  if (feed.isPending && !feed.isError) {
    body = <ActivitySkeleton />;
  } else if (!hasData && (feed.isError || failedPage)) {
    body = (
      <ErrorView offline={feed.isError} onRetry={() => refreshAndRead()} />
    );
  } else if (!hasData) {
    body = (
      <EmptyView
        title="No activity yet"
        hint="When you or the people you share with add expenses or payments, they show up here."
      />
    );
  } else {
    body = (
      <SectionList
        testID="activity-list"
        sections={sections}
        keyExtractor={item => item.id}
        stickySectionHeadersEnabled
        renderSectionHeader={({ section }) => (
          <SectionHeader title={section.title} />
        )}
        renderItem={({ item }) => {
          const target = activityTarget(item);
          return (
            <ActivityRow
              item={item}
              ctx={ctx}
              now={now}
              onPress={
                target
                  ? () =>
                      (nav.navigate as (...args: unknown[]) => void)(
                        target.name,
                        target.params,
                      )
                  : undefined
              }
            />
          );
        }}
        refreshControl={
          <RefreshControl
            refreshing={feed.isRefetching && !feed.isFetchingNextPage}
            onRefresh={() => refreshAndRead()}
            colors={[colors.brand]}
          />
        }
        onEndReachedThreshold={0.5}
        onEndReached={() => {
          if (feed.hasNextPage && !feed.isFetchingNextPage) {
            feed.fetchNextPage();
          }
        }}
        ListHeaderComponent={
          feed.isError || failedPage ? (
            <View style={styles.banner}>
              <Text variant="callout" style={styles.bannerText}>
                Can't refresh right now. Showing what was loaded.
              </Text>
              <Button
                variant="text"
                title="Retry"
                onPress={() => refreshAndRead()}
              />
            </View>
          ) : undefined
        }
        ListFooterComponent={
          feed.isFetchingNextPage ? (
            <View style={styles.footer}>
              <ActivityIndicator
                accessibilityLabel="Loading more activity"
                color={colors.brand}
              />
            </View>
          ) : feed.isFetchNextPageError ? (
            <Button
              variant="text"
              title="Retry loading more"
              onPress={() => feed.fetchNextPage()}
            />
          ) : undefined
        }
      />
    );
  }

  return (
    <View style={styles.flex}>
      {header}
      {body}
    </View>
  );
}

const makeStyles = ({ colors, spacing, radius, touchTarget }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1, backgroundColor: colors.background },
    title: {
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    footer: {
      minHeight: touchTarget.min,
      alignItems: 'center',
      justifyContent: 'center',
    },
    banner: {
      margin: spacing.lg,
      padding: spacing.md,
      borderRadius: radius.md,
      backgroundColor: colors.surfaceRaised,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    bannerText: { color: colors.textSecondary, flex: 1 },
  });
