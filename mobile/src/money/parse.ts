// Client money input parsing (S3-M-1). Text -> integer minor units, by digit arithmetic only.
// No parseFloat, no Number(text), no float division: the lint rule in .eslintrc.js enforces it.

export const MAX_AMOUNT_MINOR = 9_999_999_999;

export type ParseError =
  'empty' | 'invalid' | 'too_many_decimals' | 'too_large';

export type ParseResult =
  { ok: true; minor: number } | { ok: false; error: ParseError };

const DIGITS = /^[0-9]*$/;

function digitsToInt(digits: string): number {
  let value = 0;
  for (let i = 0; i < digits.length; i += 1) {
    value = value * 10 + (digits.charCodeAt(i) - 48);
  }
  return value;
}

/**
 * "12.34" at exponent 2 -> 1234. Accepts "12", "12.3", ".5" and a trailing "12." (typing); rejects signs,
 * grouping separators, exponents ("1e3"), more decimals than the currency allows and anything that cannot be
 * represented exactly (more than 15 significant digits). Zero is allowed here; range rules are in checkAmount().
 */
export function parseMinor(text: string, exponent: number): ParseResult {
  const t = text.trim();
  if (t === '') {
    return { ok: false, error: 'empty' };
  }
  const dot = t.indexOf('.');
  const whole = dot === -1 ? t : t.slice(0, dot);
  const fraction = dot === -1 ? '' : t.slice(dot + 1);
  if (
    !DIGITS.test(whole) ||
    !DIGITS.test(fraction) ||
    (whole === '' && fraction === '')
  ) {
    return { ok: false, error: 'invalid' };
  }
  if (fraction.length > exponent) {
    return { ok: false, error: 'too_many_decimals' };
  }
  const digits = `${whole}${fraction.padEnd(exponent, '0')}`.replace(
    /^0+(?=.)/,
    '',
  );
  if (digits.length > 15) {
    return { ok: false, error: 'too_large' };
  }
  return { ok: true, minor: digitsToInt(digits) };
}

/** 1 <= amount_minor <= 9,999,999,999 (AMOUNT_OUT_OF_RANGE on the server). */
export function isAmountInRange(minor: number): boolean {
  return minor >= 1 && minor <= MAX_AMOUNT_MINOR;
}

export const PARSE_MESSAGES: Record<ParseError, string> = {
  empty: 'Enter an amount.',
  invalid: 'Enter digits only, for example 12.34.',
  too_many_decimals: 'Too many decimal places for this currency.',
  too_large: 'That amount is too large.',
};
