/**
 * S3-M-2: the TypeScript split engine against the shared vector table (business_rules vectors 1-18 and 13b),
 * read straight from backend/tests/rules/vectors.json (never edited or copied, so the two engines cannot drift).
 */
import { readFileSync } from 'fs';
import { join } from 'path';
import {
  computeSplit,
  netBalances,
  validatePayers,
  type SplitType,
} from '../src/splits/engine';

type Vector = {
  id: string;
  scenario: string;
  kind: string;
  split_type?: SplitType;
  total?: number;
  entries?: [string, number | null][];
  payers?: [string, number][];
  expected: {
    owed?: [string, number][];
    nets?: Record<string, number>;
    error?: { code: string; details: Record<string, number> };
  };
};

const table = JSON.parse(
  readFileSync(
    join(__dirname, '..', '..', 'backend', 'tests', 'rules', 'vectors.json'),
    'utf8',
  ),
) as { vectors: Vector[] };

const runnable = table.vectors.filter(
  v => v.kind === 'split' || v.kind === 'expense',
);

function run(v: Vector) {
  const split = computeSplit(
    v.split_type!,
    v.total!,
    v.entries!.map(([userId, value]) => ({ userId, value })),
  );
  if (!split.ok) {
    return { error: split.error };
  }
  const payers = (v.payers ?? []).map(([userId, paid]) => ({ userId, paid }));
  if (v.kind === 'expense') {
    const checked = validatePayers(v.total!, payers);
    if (!checked.ok) {
      return { error: checked.error };
    }
    return {
      owed: split.owed.map(o => [o.userId, o.owed]),
      nets: netBalances(payers, split.owed),
    };
  }
  return { owed: split.owed.map(o => [o.userId, o.owed]) };
}

describe('S3-M-2 shared vector table', () => {
  it('covers vectors 1-18 and 13b (the split/expense vectors in the table)', () => {
    const ids = runnable.map(v => v.id);
    for (const id of [...Array(18).keys()].map(i => String(i + 1))) {
      expect(ids).toContain(id);
    }
    expect(ids).toContain('13b');
  });

  it.each(runnable.map(v => [v.id, v.scenario, v] as const))(
    'vector %s: %s',
    (_id, _scenario, v) => {
      const got = run(v);
      if (v.expected.error) {
        expect(got.error).toEqual(v.expected.error);
      } else {
        expect(got.error).toBeUndefined();
        expect(got.owed).toEqual(v.expected.owed);
        if (v.expected.nets) {
          expect(got.nets).toEqual(v.expected.nets);
        }
      }
    },
  );
});

describe('split engine invariants', () => {
  it('sum of owed equals the total at the largest amount for every type', () => {
    const total = 9999999999;
    const users = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
    const sumOf = (r: ReturnType<typeof computeSplit>) =>
      r.ok ? r.owed.reduce((a, o) => a + o.owed, 0) : -1;
    expect(
      sumOf(
        computeSplit(
          'equal',
          total,
          users.map(u => ({ userId: u })),
        ),
      ),
    ).toBe(total);
    expect(
      sumOf(
        computeSplit('percent', total, [
          { userId: 'A', value: 3333 },
          { userId: 'B', value: 3333 },
          { userId: 'C', value: 3334 },
        ]),
      ),
    ).toBe(total);
    expect(
      sumOf(
        computeSplit(
          'shares',
          total,
          users.map((u, i) => ({ userId: u, value: 999 - i })),
        ),
      ),
    ).toBe(total);
  });
  it('rejects empty and duplicate participants', () => {
    expect(computeSplit('equal', 100, [])).toEqual({
      ok: false,
      error: { code: 'SPLIT_NO_PARTICIPANTS', details: {} },
    });
    const dup = computeSplit('equal', 100, [{ userId: 'A' }, { userId: 'A' }]);
    expect(dup.ok).toBe(false);
  });
  it('shares with all zeros is SPLIT_NO_SHARES', () => {
    const r = computeSplit('shares', 100, [
      { userId: 'A', value: 0 },
      { userId: 'B', value: 0 },
    ]);
    expect(r).toEqual({
      ok: false,
      error: { code: 'SPLIT_NO_SHARES', details: {} },
    });
  });
  it('duplicate payers are rejected', () => {
    const r = validatePayers(100, [
      { userId: 'A', paid: 50 },
      { userId: 'A', paid: 50 },
    ]);
    expect(r.ok).toBe(false);
  });
});
