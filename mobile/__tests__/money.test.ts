import {
  formatMinorAmount,
  formatMoney,
  summarizeBalances,
  sumByCurrency,
} from '../src/money/format';

describe('money formatting (integer minor units)', () => {
  it('formats 2-decimal amounts with grouping', () => {
    expect(formatMinorAmount(123450, 2)).toBe('1,234.50');
    expect(formatMinorAmount(5, 2)).toBe('0.05');
    expect(formatMinorAmount(0, 2)).toBe('0.00');
    expect(formatMinorAmount(100000000, 2)).toBe('1,000,000.00');
  });
  it('handles 0 and 3 decimal currencies', () => {
    expect(formatMinorAmount(1200, 0)).toBe('1,200');
    expect(formatMinorAmount(1234, 3)).toBe('1.234');
    expect(formatMoney(7, 'KWD', 3)).toBe('KWD 0.007');
    expect(formatMoney(1200, 'JPY')).toBe('JPY 1,200'); // fallback exponent for JPY
  });
  it('keeps the sign and is exact at the largest allowed amount', () => {
    expect(formatMinorAmount(-1, 2)).toBe('-0.01');
    expect(formatMoney(9999999999, 'INR', 2)).toBe('INR 99,999,999.99');
  });
  it('no floating point drift for values like 0.1 + 0.2', () => {
    expect(formatMinorAmount(10 + 20, 2)).toBe('0.30');
  });
  it('sums per currency and never across currencies', () => {
    expect(
      sumByCurrency([
        { amount_minor: 100, currency: 'INR' },
        { amount_minor: -100, currency: 'INR' },
        { amount_minor: 5, currency: 'USD' },
        { amount_minor: 7, currency: 'USD' },
      ]),
    ).toEqual([{ amount_minor: 12, currency: 'USD' }]);
  });
  it('summarises owe / owed / both / settled', () => {
    expect(summarizeBalances([])).toBe('settled up');
    expect(summarizeBalances([{ amount_minor: -5000, currency: 'INR' }])).toBe(
      'you owe INR 50.00',
    );
    expect(summarizeBalances([{ amount_minor: 5000, currency: 'INR' }])).toBe(
      'you are owed INR 50.00',
    );
    expect(
      summarizeBalances([
        { amount_minor: -5000, currency: 'INR' },
        { amount_minor: 250, currency: 'USD' },
      ]),
    ).toBe('you owe INR 50.00, you are owed USD 2.50');
  });
});
