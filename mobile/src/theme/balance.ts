import type { ColorTokens } from './colors';

// Owed vs owing is NEVER color alone. Each tone carries a sign glyph AND a word; components must render both.
// The amount text itself comes from the shared helper in src/money/format.ts (integer minor units in, text out).
// Sign convention matches the API: positive amount_minor = owed to the viewer, negative = the viewer owes.

export type BalanceTone = 'owed' | 'owe' | 'settled';

export function balanceTone(amountMinor: number): BalanceTone {
  if (amountMinor > 0) {
    return 'owed';
  }
  if (amountMinor < 0) {
    return 'owe';
  }
  return 'settled';
}

export interface BalanceStyle {
  tone: BalanceTone;
  /** Text color (>= 4.5:1 on the chip fill and on background/surface). */
  text: string;
  /** Chip fill. */
  fill: string;
  /** Icon / bar color (>= 3:1). */
  accent: string;
  /** Prefix drawn before the amount so the meaning survives grayscale: "+" owed, "−" owe (U+2212). */
  sign: '+' | '−' | '';
  /** Words for chips. Rows addressed to the viewer use the longer "you owe" / "you are owed" forms. */
  word: 'owed' | 'owe' | 'settled up';
}

export function balanceStyle(
  colors: ColorTokens,
  amountMinor: number,
): BalanceStyle {
  const tone = balanceTone(amountMinor);
  switch (tone) {
    case 'owed':
      return {
        tone,
        text: colors.owedText,
        fill: colors.owedSubtle,
        accent: colors.owed,
        sign: '+',
        word: 'owed',
      };
    case 'owe':
      return {
        tone,
        text: colors.oweText,
        fill: colors.oweSubtle,
        accent: colors.owe,
        sign: '−',
        word: 'owe',
      };
    default:
      return {
        tone,
        text: colors.textSecondary,
        fill: colors.fieldBackground,
        accent: colors.textSecondary,
        sign: '',
        word: 'settled up',
      };
  }
}
