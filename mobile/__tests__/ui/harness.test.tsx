/** SUI-Q-1: self-tests for the UI harness, so a broken harness cannot give a false green. */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { darkColors, lightColors, useTheme } from '../../src/theme';
import { Button } from '../../src/components/Button';
import {
  colorsOutsideScheme,
  expectColorsInScheme,
  renderAtFontScale,
  renderBothThemes,
  resolvedColors,
  schemeValues,
  screenBackground,
  touchTargetProblems,
} from './harness';

function Themed() {
  const { colors } = useTheme();
  return (
    <View style={{ backgroundColor: colors.background }}>
      <Text style={{ color: colors.textPrimary }}>hello</Text>
    </View>
  );
}

describe('renderBothThemes / resolvedColors', () => {
  it('mounts the same element under light and dark and resolves each scheme', async () => {
    const { light, dark } = await renderBothThemes(<Themed />);
    expect(screenBackground(light)).toBe(lightColors.background);
    expect(screenBackground(dark)).toBe(darkColors.background);
    expect(resolvedColors(light)).toEqual(
      new Set([lightColors.background, lightColors.textPrimary]),
    );
    expectColorsInScheme(light, 'light');
    expectColorsInScheme(dark, 'dark');
  });

  it('a light token in the dark tree is reported', async () => {
    const { light } = await renderBothThemes(<Themed />);
    expect(colorsOutsideScheme(light, 'dark')).toContain(
      lightColors.background,
    );
  });

  // Known limit: a literal equal to a token value (for example '#FFFFFF' is light surface) cannot be told apart
  // at render time; the source guard noColorLiterals.test.ts covers that case.
  it.each(['#fff', '#FEFEFE', 'rgba(0,0,0,0.5)', 'red'])(
    'a literal %s fails the scheme check',
    async literal => {
      const { light } = await renderBothThemes(
        <View style={{ backgroundColor: literal }} />,
      );
      expect(colorsOutsideScheme(light, 'light')).toEqual([literal]);
      expect(() => expectColorsInScheme(light, 'light')).toThrow();
    },
  );

  it('finds colors in color props and nested style arrays, and allows transparent', async () => {
    const { light } = await renderBothThemes(
      <View
        style={[{ borderColor: '#123456' }, [{ shadowColor: 'transparent' }]]}
      >
        <Text style={StyleSheet.flatten({ color: '#abcdef' })}>x</Text>
      </View>,
    );
    expect(colorsOutsideScheme(light, 'light')).toEqual(['#123456', '#abcdef']);
  });

  it('schemeValues covers the gradient tuple and excludes the other scheme', () => {
    expect(schemeValues('light').has(lightColors.gradient[0])).toBe(true);
    expect(schemeValues('light').has(darkColors.surfaceRaised)).toBe(false);
  });
});

describe('touchTargetProblems / expectTouchTargets', () => {
  it('passes the shared Button (role, text label, 48dp)', async () => {
    const { light } = await renderBothThemes(
      <Button title="Save" onPress={() => {}} />,
    );
    expect(touchTargetProblems(light)).toEqual([]);
  });

  it('reports a small pressable with no role and no label', async () => {
    const { light } = await renderBothThemes(
      <Pressable onPress={() => {}} style={{ width: 20, height: 20 }} />,
    );
    const problems = touchTargetProblems(light).join('\n');
    expect(problems).toMatch(/no accessibilityRole/);
    expect(problems).toMatch(/no accessibilityLabel/);
    expect(problems).toMatch(/height 20 < 48/);
    expect(problems).toMatch(/width 20 < 48/);
  });

  it('accepts a 24dp icon with a 12dp hitSlop on every side', async () => {
    const { light } = await renderBothThemes(
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Close"
        hitSlop={12}
        onPress={() => {}}
        style={{ width: 24, height: 24 }}
      />,
    );
    expect(touchTargetProblems(light)).toEqual([]);
  });

  it('reports a pressable whose height is not declared', async () => {
    const { light } = await renderBothThemes(
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Go"
        onPress={() => {}}
      />,
    );
    expect(touchTargetProblems(light).join()).toMatch(/height 0 < 48/);
  });
});

describe('renderAtFontScale', () => {
  it('renders at 2.0 and caps fixed controls', async () => {
    const r = await renderAtFontScale(
      <Button title="Save" onPress={() => {}} />,
      2,
    );
    expect(r.getByText('Save')).toBeTruthy();
    expect(r.effectiveScale(1.3)).toBe(1.3);
    expect(r.effectiveScale(undefined)).toBe(2);
    expect(r.getByText('Save').props.maxFontSizeMultiplier).toBe(1.3);
    r.restore();
  });
});
