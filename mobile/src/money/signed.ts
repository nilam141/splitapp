import type { BalanceLine } from '../api/generated/model';
import { fallbackExponent, formatMoney, sumByCurrency } from './format';
import type { ExponentOf } from './format';

// Sign glyphs for owed / owe (design_system.md 6.6). Amount text still comes from format.ts.
// Form: sign directly before the amount, e.g. "you owe −INR 20.00", "owes you +INR 20.00".
export const SIGN_OWED = '+';
export const SIGN_OWE = '−';

export function signFor(amountMinor: number): '+' | '−' | '' {
  return amountMinor > 0 ? SIGN_OWED : amountMinor < 0 ? SIGN_OWE : '';
}

/** Same as summarizeBalances, with sign glyphs. `label` omits them for screen readers. */
export function summarizeBalancesSigned(
  lines: BalanceLine[],
  exponentOf: ExponentOf = fallbackExponent,
): { text: string; label: string } {
  const totals = sumByCurrency(lines);
  const owed = totals.filter(t => t.amount_minor > 0);
  const owe = totals.filter(t => t.amount_minor < 0);
  const fmt = (t: BalanceLine) =>
    formatMoney(Math.abs(t.amount_minor), t.currency, exponentOf(t.currency));
  const text: string[] = [];
  const label: string[] = [];
  if (owe.length > 0) {
    text.push(`you owe ${owe.map(t => SIGN_OWE + fmt(t)).join(', ')}`);
    label.push(`you owe ${owe.map(fmt).join(', ')}`);
  }
  if (owed.length > 0) {
    text.push(`you are owed ${owed.map(t => SIGN_OWED + fmt(t)).join(', ')}`);
    label.push(`you are owed ${owed.map(fmt).join(', ')}`);
  }
  if (text.length === 0) {
    return { text: 'settled up', label: 'settled up' };
  }
  return { text: text.join(', '), label: label.join(', ') };
}
