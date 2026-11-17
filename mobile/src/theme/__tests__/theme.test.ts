import { colorSchemes, brandGradient } from '../colors';
import { elevationFor } from '../elevation';
import { balanceStyle, balanceTone } from '../balance';
import { touchTarget } from '../spacing';
import { typography } from '../typography';
import { contrast, pairs } from '../testing/contrast';

const schemes = ['light', 'dark'] as const;

describe.each(schemes)('%s contrast', scheme => {
  const colors = colorSchemes[scheme];
  it.each(pairs)('$name', ({ fg, bg, min }) => {
    const ratio = contrast(colors[fg] as string, colors[bg] as string);
    expect(ratio).toBeGreaterThanOrEqual(min);
  });

  it('white label on both gradient stops passes 4.5:1', () => {
    for (const stop of colors.gradient) {
      expect(contrast(colors.textOnGradient, stop)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe('structure', () => {
  it('uses the same token keys in light and dark', () => {
    expect(Object.keys(colorSchemes.dark).sort()).toEqual(
      Object.keys(colorSchemes.light).sort(),
    );
  });

  it('dark mode has no shadows (depth comes from lighter surfaces)', () => {
    const dark = elevationFor('dark');
    for (const level of [0, 1, 2, 3] as const) {
      expect(dark[level].elevation).toBe(0);
      expect(dark[level].shadowOpacity).toBe(0);
    }
  });

  it('light mode shadows grow with level', () => {
    const light = elevationFor('light');
    expect(light[1].elevation).toBeLessThan(light[2].elevation as number);
    expect(light[2].elevation).toBeLessThan(light[3].elevation as number);
  });

  it('touch targets are at least 48dp', () => {
    expect(touchTarget.min).toBeGreaterThanOrEqual(48);
  });

  it('body text is at least 14sp and nothing is under 12sp', () => {
    for (const style of Object.values(typography)) {
      expect(style.fontSize as number).toBeGreaterThanOrEqual(12);
    }
    expect(typography.body.fontSize).toBeGreaterThanOrEqual(16);
  });

  it('gradient is off by default', () => {
    expect(brandGradient.enabled).toBe(false);
  });
});

describe('balance tones never rely on color alone', () => {
  it.each(schemes)(
    '%s: every tone has a word, and owed/owe have different signs',
    scheme => {
      const colors = colorSchemes[scheme];
      const owed = balanceStyle(colors, 500);
      const owe = balanceStyle(colors, -500);
      const settled = balanceStyle(colors, 0);
      expect(owed.sign).toBe('+');
      expect(owe.sign).toBe('−');
      expect(owed.sign).not.toBe(owe.sign);
      expect([owed.word, owe.word, settled.word]).toEqual([
        'owed',
        'owe',
        'settled up',
      ]);
    },
  );

  it('maps the API sign convention (positive = owed to the viewer)', () => {
    expect(balanceTone(1)).toBe('owed');
    expect(balanceTone(-1)).toBe('owe');
    expect(balanceTone(0)).toBe('settled');
  });

  it('settled chip text passes 4.5:1 on its fill', () => {
    for (const scheme of schemes) {
      const colors = colorSchemes[scheme];
      const s = balanceStyle(colors, 0);
      expect(contrast(s.text, s.fill)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
