import type { BalanceLine } from '../api/generated/model';

// The single place where integer minor units become display text. Integer arithmetic only:
// no division that produces fractions, no parseFloat, no toFixed.

// Used only until GET /currencies has loaded (the server list is authoritative).
const FALLBACK_EXPONENTS: Record<string, number> = {
  JPY: 0,
  KRW: 0,
  VND: 0,
  CLP: 0,
  ISK: 0,
  UGX: 0,
  KWD: 3,
  BHD: 3,
  OMR: 3,
  JOD: 3,
  TND: 3,
};

export function fallbackExponent(currency: string): number {
  return FALLBACK_EXPONENTS[currency] ?? 2;
}

function pow10(exponent: number): number {
  let result = 1;
  for (let i = 0; i < exponent; i += 1) {
    result *= 10;
  }
  return result;
}

function groupThousands(digits: string): string {
  let out = '';
  for (let i = 0; i < digits.length; i += 1) {
    if (i > 0 && (digits.length - i) % 3 === 0) {
      out += ',';
    }
    out += digits[i];
  }
  return out;
}

/** "1,234.50" for (123450, 2); "-0.05" for (-5, 2); "1,200" for (1200, 0). No currency code. */
export function formatMinorAmount(
  amountMinor: number,
  exponent: number,
): string {
  const negative = amountMinor < 0;
  const abs = Math.abs(amountMinor);
  const base = pow10(exponent);
  const remainder = abs % base;
  const whole = (abs - remainder) / base; // exact: both are safe integers
  let text = groupThousands(String(whole));
  if (exponent > 0) {
    text += `.${String(remainder).padStart(exponent, '0')}`;
  }
  return negative ? `-${text}` : text;
}

/** "INR 1,234.50". */
export function formatMoney(
  amountMinor: number,
  currency: string,
  exponent: number = fallbackExponent(currency),
): string {
  return `${currency} ${formatMinorAmount(amountMinor, exponent)}`;
}

/** Sums balance lines per currency (never across currencies); zero totals are dropped. */
export function sumByCurrency(lines: BalanceLine[]): BalanceLine[] {
  const totals = new Map<string, number>();
  for (const line of lines) {
    totals.set(
      line.currency,
      (totals.get(line.currency) ?? 0) + line.amount_minor,
    );
  }
  return [...totals.entries()]
    .filter(([, amount]) => amount !== 0)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([currency, amount_minor]) => ({ amount_minor, currency }));
}

export type ExponentOf = (currency: string) => number;

/**
 * Overall summary per SCR-08 / SCR-09: "you owe X", "you are owed Y", both, or "settled up".
 * Positive = owed to the viewer. Currencies are reported separately.
 */
export function summarizeBalances(
  lines: BalanceLine[],
  exponentOf: ExponentOf = fallbackExponent,
): string {
  const totals = sumByCurrency(lines);
  const owed = totals.filter(t => t.amount_minor > 0);
  const owe = totals.filter(t => t.amount_minor < 0);
  const fmt = (t: BalanceLine) =>
    formatMoney(Math.abs(t.amount_minor), t.currency, exponentOf(t.currency));
  const parts: string[] = [];
  if (owe.length > 0) {
    parts.push(`you owe ${owe.map(fmt).join(' + ')}`);
  }
  if (owed.length > 0) {
    parts.push(`you are owed ${owed.map(fmt).join(' + ')}`);
  }
  return parts.length > 0 ? parts.join(', ') : 'settled up';
}
