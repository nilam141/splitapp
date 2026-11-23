import React from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { layout, useTheme } from '../theme';
import { Text } from './Text';

export type AvatarSize = 32 | 40 | 56 | 80;
export type GroupType = 'home' | 'trip' | 'couple' | 'other';

type Props = {
  name: string;
  size?: AvatarSize;
  /** Photo when present; otherwise initials (or the group glyph). */
  imageUri?: string | null;
  /** Invited, not registered: dashed ring, and the word "invited" when size >= 56. */
  placeholder?: boolean;
  /** Group with no image: shows a type glyph instead of initials. */
  groupType?: GroupType;
  testID?: string;
};

const GLYPH: Record<GroupType, string> = {
  home: '⌂',
  trip: '✈',
  couple: '♥',
  other: '★',
};

/** Up to two initials: first letters of the first and last word. */
export function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return '';
  }
  const first = Array.from(words[0])[0] ?? '';
  const last =
    words.length > 1 ? (Array.from(words[words.length - 1])[0] ?? '') : '';
  return (first + last).toUpperCase();
}

const styles = StyleSheet.create({ wrap: { alignItems: 'center' } });

/** design_system 6.5: neutral circle, photo or initials, dashed ring for placeholders. */
export function Avatar({
  name,
  size = layout.avatar.md,
  imageUri,
  placeholder = false,
  groupType,
  testID = 'avatar',
}: Props) {
  const { colors, spacing, radius } = useTheme();
  const showInvited = placeholder && size >= layout.avatar.lg;
  const circle = StyleSheet.flatten([
    {
      width: size,
      height: size,
      borderRadius: radius.pill,
      backgroundColor: colors.avatarBackground,
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
    },
    placeholder
      ? {
          borderWidth: 1,
          borderStyle: 'dashed' as const,
          borderColor: colors.borderStrong,
        }
      : null,
  ]);
  const label = placeholder ? `${name}, invited` : name;
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      style={styles.wrap}
    >
      <View testID={testID} style={circle}>
        {imageUri ? (
          <Image
            source={{ uri: imageUri }}
            accessibilityIgnoresInvertColors
            style={{ width: size, height: size }}
          />
        ) : groupType ? (
          <Text
            testID={`avatar-glyph-${groupType}`}
            variant={size >= layout.avatar.lg ? 'title2' : 'label'}
            style={{ color: colors.avatarText }}
            maxFontSizeMultiplier={1.3}
          >
            {GLYPH[groupType]}
          </Text>
        ) : (
          <Text
            variant="label"
            style={{ color: colors.avatarText }}
            maxFontSizeMultiplier={1.3}
          >
            {initialsOf(name)}
          </Text>
        )}
      </View>
      {showInvited ? (
        <Text
          variant="caption"
          style={{ color: colors.textSecondary, marginTop: spacing.xs }}
        >
          invited
        </Text>
      ) : null}
    </View>
  );
}
