import {
  applyShortcut,
  buildRequest,
  canonicalPeople,
  evaluatePayers,
  evaluateSplit,
  formatBp,
  initialDraft,
  validateDate,
} from '../src/expenses/draft';
import { formatMinorAmount } from '../src/money/format';

const people = [
  { id: 'a', name: 'A' },
  { id: 'b', name: 'B' },
  { id: 'c', name: 'C' },
];
const fmt = (m: number) => formatMinorAmount(m, 2);

describe('expense draft logic', () => {
  it('formats basis points without float maths', () => {
    expect(formatBp(100)).toBe('1');
    expect(formatBp(3333)).toBe('33.33');
    expect(formatBp(50)).toBe('0.5');
    expect(formatBp(10000)).toBe('100');
  });

  it('canonical order: group = join order; non-group = creator first, then by id', () => {
    const shuffled = [people[2], people[0], people[1]];
    expect(
      canonicalPeople(shuffled, { isGroup: true, creatorId: 'b' }).map(
        p => p.id,
      ),
    ).toEqual(['c', 'a', 'b']);
    expect(
      canonicalPeople(shuffled, { isGroup: false, creatorId: 'b' }).map(
        p => p.id,
      ),
    ).toEqual(['b', 'a', 'c']);
  });

  it('percent: previews and the exact gap', () => {
    const ev = evaluateSplit(
      { type: 'percent', included: [], values: { a: '50', b: '30', c: '19' } },
      people,
      10000,
      2,
      fmt,
    );
    expect(ev.valid).toBe(false);
    expect(ev.footer).toEqual(['99% of 100%', '1% left']);
    const ok = evaluateSplit(
      {
        type: 'percent',
        included: [],
        values: { a: '33.33', b: '33.33', c: '33.34' },
      },
      people,
      1000,
      2,
      fmt,
    );
    expect(ok.rows.map(r => r.owed)).toEqual([333, 333, 334]);
  });

  it('shares 1/2/3 on 600.00', () => {
    const ev = evaluateSplit(
      { type: 'shares', included: [], values: { a: '1', b: '2', c: '3' } },
      people,
      60000,
      2,
      fmt,
    );
    expect(ev.rows.map(r => r.owed)).toEqual([10000, 20000, 30000]);
    expect(ev.footer).toEqual(['6 total shares']);
  });

  it('shares above 999 and negative or float text are rejected per person', () => {
    const ev = evaluateSplit(
      {
        type: 'shares',
        included: [],
        values: { a: '1000', b: '-1', c: '1.5' },
      },
      people,
      100,
      2,
      fmt,
    );
    expect(ev.valid).toBe(false);
    expect(ev.rows.every(r => r.inputError)).toBe(true);
  });

  it('payers must sum to the total', () => {
    const ev = evaluatePayers(
      { mode: 'multiple', amounts: { a: '60', b: '20' } },
      people,
      9000,
      2,
      fmt,
    );
    expect(ev.valid).toBe(false);
    expect(ev.error).toBe('Payments are under by 10.00');
  });

  it('shortcuts', () => {
    const t = applyShortcut('they_owed_full', 'a', 'b', 9000, 2);
    expect(t.payers).toEqual({ mode: 'single', payerId: 'b' });
    expect(t.split.values).toEqual({ a: '90.00', b: '0' });
  });

  it('date range: 2000-01-01 to today + 365 days, real dates only', () => {
    expect(validateDate('2000-01-01', '2026-11-10')).toBeUndefined();
    expect(validateDate('1999-12-31', '2026-11-10')).toBeDefined();
    expect(validateDate('2027-11-10', '2026-11-10')).toBeUndefined();
    expect(validateDate('2027-11-11', '2026-11-10')).toBeDefined();
    expect(validateDate('2026-02-30', '2026-11-10')).toBe(
      'That date does not exist.',
    );
    expect(validateDate('10/11/2026', '2026-11-10')).toBeDefined();
  });

  it('buildRequest: integer minor units, no float anywhere in the body', () => {
    const draft = {
      ...initialDraft('a', people, 'INR', '2026-11-10'),
      description: ' Dinner ',
      amountText: '99999999.99',
    };
    const r = buildRequest(draft, people, 2, '2026-11-10', fmt);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.body.total).toEqual({
        amount_minor: 9999999999,
        currency: 'INR',
      });
      expect(r.body.description).toBe('Dinner');
      expect(r.body.payers).toEqual([
        { user_id: 'a', paid_amount_minor: 9999999999 },
      ]);
      expect(JSON.stringify(r.body)).not.toMatch(/\.\d/);
    }
  });
});
