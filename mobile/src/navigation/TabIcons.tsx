import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTheme } from '../theme';

// Original 24dp tab glyphs drawn from plain Views (no icon library is installed, and none is added here).
// A proper icon library is a follow-up decision. Icons are decorative: the tab button carries the label.

export type TabIconName = 'Friends' | 'Groups' | 'Activity' | 'Account';

const SIZE = 24;
const INDICATOR_WIDTH = 24;
const INDICATOR_HEIGHT = 3;

function Person({
  color,
  head,
  bodyWidth,
  bodyHeight,
  style,
}: {
  color: string;
  head: number;
  bodyWidth: number;
  bodyHeight: number;
  style?: object;
}) {
  return (
    <View style={[styles.personBox, style]}>
      <View
        style={{
          width: head,
          height: head,
          borderRadius: head / 2,
          backgroundColor: color,
        }}
      />
      <View
        style={{
          width: bodyWidth,
          height: bodyHeight,
          borderTopLeftRadius: bodyWidth / 2,
          borderTopRightRadius: bodyWidth / 2,
          backgroundColor: color,
        }}
      />
    </View>
  );
}

function Glyph({ name, color }: { name: TabIconName; color: string }) {
  switch (name) {
    case 'Friends':
      return <Person color={color} head={9} bodyWidth={16} bodyHeight={8} />;
    case 'Groups':
      return (
        <View style={styles.glyph}>
          <Person
            color={color}
            head={7}
            bodyWidth={11}
            bodyHeight={6}
            style={styles.groupBack}
          />
          <Person
            color={color}
            head={9}
            bodyWidth={14}
            bodyHeight={7}
            style={styles.groupFront}
          />
        </View>
      );
    case 'Activity':
      return (
        <View style={[styles.clock, { borderColor: color }]}>
          <View style={[styles.handLong, { backgroundColor: color }]} />
          <View style={[styles.handShort, { backgroundColor: color }]} />
        </View>
      );
    default:
      return (
        <View style={[styles.ring, { borderColor: color }]}>
          <Person color={color} head={6} bodyWidth={11} bodyHeight={5} />
        </View>
      );
  }
}

/** 24dp icon; when focused a 3dp x 24dp bar sits above it so the active state is not hue-only. */
export function TabIcon({
  name,
  color,
  focused,
}: {
  name: TabIconName;
  color: string;
  focused: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={styles.wrap}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <View
        style={[
          styles.indicator,
          focused ? { backgroundColor: colors.brand } : styles.indicatorOff,
        ]}
      />
      <View style={styles.glyph}>
        <Glyph name={name} color={color} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center' },
  indicator: {
    width: INDICATOR_WIDTH,
    height: INDICATOR_HEIGHT,
    borderRadius: INDICATOR_HEIGHT / 2,
    marginBottom: 4,
  },
  indicatorOff: { opacity: 0 },
  glyph: {
    width: SIZE,
    height: SIZE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  personBox: { alignItems: 'center', justifyContent: 'center' },
  groupBack: { position: 'absolute', left: 0, top: 2, opacity: 0.7 },
  groupFront: { position: 'absolute', right: 1, top: 4 },
  clock: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    alignItems: 'center',
  },
  handLong: { position: 'absolute', top: 3, width: 2, height: 6 },
  handShort: { position: 'absolute', top: 8, left: 8, width: 5, height: 2 },
  ring: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
});
