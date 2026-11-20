import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { balanceStyle, fontWeight, useTheme } from '../theme';
import { Text } from '../components/Text';
import type { ActivityItem } from '../api/generated/model';
import {
  DescribeContext,
  describeActivity,
  effectChips,
  relativeTime,
  segmentsToText,
} from './describe';

// Decorative glyphs (our own set, plain characters until the icon set is decided, OQ-46). Hidden from TalkBack.
const GLYPH: Record<ActivityItem['entity_type'], string> = {
  expense: '≡',
  settlement: '⇄',
  group: '★',
  friendship: '+',
  comment: '“',
};

type Props = {
  item: ActivityItem;
  ctx: DescribeContext;
  now: Date;
  onPress?: () => void;
};

/** design_system 8.5: 40dp glyph, sentence with strong actor and object, effect chips, relative time, unread dot. */
export function ActivityRow({ item, ctx, now, onPress }: Props) {
  const { colors, spacing, radius, layout } = useTheme();
  const unread = item.is_unread === true;
  const segments = describeActivity(item, ctx);
  const chips = effectChips(item.my_effect, ctx.format);
  const deleted = item.action.endsWith('.deleted');
  const time = relativeTime(item.created_at, now);
  const label = [
    segmentsToText(segments),
    ...chips.map(c => c.label),
    deleted && item.entity_type !== 'group' ? 'deleted' : null,
    time,
    unread ? 'unread' : null,
  ]
    .filter(Boolean)
    .join(', ');

  const s = StyleSheet.create({
    row: {
      minHeight: layout.listRowMinHeight,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      flexDirection: 'row',
      alignItems: 'center',
    },
    glyph: {
      width: layout.avatar.md,
      height: layout.avatar.md,
      borderRadius: radius.pill,
      backgroundColor: colors.fieldBackground,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: spacing.md,
    },
    glyphText: { color: colors.textSecondary },
    body: { flex: 1, flexShrink: 1 },
    unreadText: { fontWeight: fontWeight.bold },
    chips: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      marginTop: spacing.xs,
    },
    chip: {
      borderRadius: radius.pill,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.xs,
      marginRight: spacing.sm,
      marginTop: spacing.xs,
    },
    caption: { color: colors.textSecondary, marginTop: spacing.xs },
    tag: { color: colors.textSecondary },
    dot: {
      width: spacing.sm,
      height: spacing.sm,
      borderRadius: spacing.xs,
      backgroundColor: colors.brand,
      marginLeft: spacing.sm,
    },
  });

  const content = (
    <>
      <View style={s.glyph} importantForAccessibility="no-hide-descendants">
        <Text variant="label" style={s.glyphText}>
          {GLYPH[item.entity_type]}
        </Text>
      </View>
      <View style={s.body}>
        <Text variant="body" style={unread ? s.unreadText : undefined}>
          {segments.map((seg, i) => (
            <Text
              key={`${i}-${seg.text}`}
              variant={seg.strong ? 'bodyStrong' : 'body'}
              style={unread ? s.unreadText : undefined}
            >
              {seg.text}
            </Text>
          ))}
        </Text>
        {chips.length > 0 ? (
          <View style={s.chips}>
            {chips.map(c => {
              const tone = balanceStyle(colors, c.amountMinor);
              return (
                <View
                  key={c.key}
                  testID="effect-chip"
                  style={[s.chip, { backgroundColor: tone.fill }]}
                >
                  <Text variant="label" style={{ color: tone.text }}>
                    {c.text}
                  </Text>
                </View>
              );
            })}
          </View>
        ) : null}
        <Text variant="caption" style={s.caption}>
          {time}
          {deleted && item.entity_type !== 'group' ? (
            <Text variant="caption" style={s.tag}>
              {' · deleted'}
            </Text>
          ) : null}
        </Text>
      </View>
      {unread ? (
        <View
          testID="unread-dot"
          importantForAccessibility="no"
          style={s.dot}
        />
      ) : null}
    </>
  );

  if (!onPress) {
    return (
      <View
        testID="activity-row"
        accessible
        accessibilityLabel={label}
        style={s.row}
      >
        {content}
      </View>
    );
  }
  return (
    <Pressable
      testID="activity-row"
      accessibilityRole="button"
      accessibilityLabel={label}
      android_ripple={{ color: colors.border }}
      onPress={onPress}
      style={s.row}
    >
      {content}
    </Pressable>
  );
}
