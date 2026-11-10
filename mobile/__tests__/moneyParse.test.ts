import { readFileSync } from 'fs';
import { join } from 'path';
import { formatMinorAmount } from '../src/money/format';
import { isAmountInRange, parseMinor } from '../src/money/parse';

// eslint ships no types here; the shapes used below are declared locally.
type LintMessage = { ruleId: string | null; severity: number };
const { ESLint } = require('eslint');

const ok = (minor: number) => ({ ok: true, minor });
const bad = (error: string) => ({ ok: false, error });

describe('S3-M-1 parseMinor (integer-only)', () => {
  it('parses per currency exponent', () => {
    expect(parseMinor('12.34', 2)).toEqual(ok(1234));
    expect(parseMinor('12', 2)).toEqual(ok(1200));
    expect(parseMinor('12.3', 2)).toEqual(ok(1230));
    expect(parseMinor('.5', 2)).toEqual(ok(50));
    expect(parseMinor('0.05', 2)).toEqual(ok(5));
    expect(parseMinor('1500', 0)).toEqual(ok(1500));
    expect(parseMinor('1.234', 3)).toEqual(ok(1234));
  });
  it('rejects more decimals than the exponent', () => {
    expect(parseMinor('12.345', 2)).toEqual(bad('too_many_decimals'));
    expect(parseMinor('1500.5', 0)).toEqual(bad('too_many_decimals'));
  });
  it('rejects malformed input', () => {
    for (const text of [
      '',
      ' ',
      'abc',
      '-5',
      '+5',
      '1e3',
      '1,000',
      '1.2.3',
      '.',
      '0x10',
    ]) {
      expect(parseMinor(text, 2).ok).toBe(false);
    }
    expect(parseMinor('', 2)).toEqual(bad('empty'));
  });
  it('9,999,999,999 round-trips through format and parse', () => {
    const text = formatMinorAmount(9999999999, 2).replace(/,/g, '');
    expect(text).toBe('99999999.99');
    expect(parseMinor(text, 2)).toEqual(ok(9999999999));
    expect(parseMinor('9999999999', 0)).toEqual(ok(9999999999));
    expect(parseMinor('99999999.99', 2)).toEqual(ok(9999999999));
  });
  it('is exact where floats drift', () => {
    expect(parseMinor('0.29', 2)).toEqual(ok(29)); // 0.29 * 100 = 28.999... in floats
    expect(parseMinor('1.15', 2)).toEqual(ok(115));
  });
  it('rejects values that cannot be represented exactly', () => {
    expect(parseMinor('99999999999999999', 0)).toEqual(bad('too_large'));
  });
  it('range check is 1..9,999,999,999', () => {
    expect(isAmountInRange(0)).toBe(false);
    expect(isAmountInRange(1)).toBe(true);
    expect(isAmountInRange(9999999999)).toBe(true);
    expect(isAmountInRange(10000000000)).toBe(false);
  });
  it('round-trips format -> parse for many values', () => {
    for (const exp of [0, 2, 3]) {
      for (const n of [1, 9, 10, 99, 100, 101, 12345, 999999, 9999999999]) {
        const text = formatMinorAmount(n, exp).replace(/,/g, '');
        expect(parseMinor(text, exp)).toEqual(ok(n));
      }
    }
  });
});

describe('S3-M-1 lint rule: no floating point in money modules', () => {
  const lint = async (filePath: string, code: string) => {
    const eslint = new ESLint({ cwd: join(__dirname, '..') });
    const [result] = await eslint.lintText(code, { filePath });
    return (result.messages as LintMessage[]).filter(m => m.ruleId !== null);
  };
  const file = join(__dirname, '..', 'src', 'money', 'probe.ts');

  it('flags parseFloat, Number(), toFixed and Math.round in src/money', async () => {
    const messages = await lint(
      file,
      [
        "export const a = parseFloat('1.5');",
        "export const b = Number('1.5');",
        'export const c = (1).toFixed(2);',
        'export const d = Math.round(1.5);',
        "export const e = Number.parseFloat('1');",
      ].join('\n'),
    );
    expect(messages.length).toBeGreaterThanOrEqual(5);
  });
  it('does not flag the same code outside money paths', async () => {
    const messages = await lint(
      join(__dirname, '..', 'src', 'screens', 'probe.ts'),
      "export const a = parseFloat('1.5');",
    );
    expect(messages).toHaveLength(0);
  });
  it('the real money modules are clean', async () => {
    const eslint = new ESLint({ cwd: join(__dirname, '..') });
    const results = await eslint.lintFiles([
      'src/money',
      'src/splits',
      'src/expenses',
    ]);
    const errors = (results as { messages: LintMessage[] }[]).flatMap(r =>
      r.messages.filter(m => m.severity === 2),
    );
    expect(errors).toEqual([]);
  });
  it('the module source contains no parseFloat call', () => {
    const src = readFileSync(
      join(__dirname, '..', 'src', 'money', 'parse.ts'),
      'utf8',
    );
    expect(src.replace(/\/\/.*$/gm, '')).not.toMatch(/parseFloat\(/);
  });
});
