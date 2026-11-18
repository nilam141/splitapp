import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTheme } from '../theme';
import { Text } from './Text';

/** design_system 6.4: caption, textSecondary, 32dp high. Stickiness comes from the list (stickySectionHeadersEnabled). */
export function SectionHeader({ title }: { title: string }) {
  const { colors, spacing, layout } = useTheme();
  return (
    <View
      accessible
      accessibilityRole="header"
      style={StyleSheet.flatten([
        {
          minHeight: layout.sectionHeaderHeight,
          justifyContent: 'center',
          paddingHorizontal: spacing.lg,
          backgroundColor: colors.background,
        },
      ])}
    >
      <Text variant="caption" style={{ color: colors.textSecondary }}>
        {title}
      </Text>
    </View>
  );
}
