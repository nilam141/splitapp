/**
 * QA cross-check: the TS split engine against 240 seeded random cases (valid and invalid) whose expected values were
 * computed by the backend engine (backend/tests/rules/random_cases.json, also asserted by the backend suite).
 * For VALIDATION_ERROR only the code is compared (backend details are a fields list, the TS engine has none).
 */
import { readFileSync } from 'fs';
import { join } from 'path';
import { computeSplit, type SplitType } from '../src/splits/engine';

type Case = {
  id: string;
  split_type: SplitType;
  total: number;
  entries: [string, number | null][];
  expected: {
    owed?: [string, number][];
    error?: { code: string; details: Record<string, number> | null };
  };
};

const { cases } = JSON.parse(
  readFileSync(
    join(
      __dirname,
      '..',
      '..',
      'backend',
      'tests',
      'rules',
      'random_cases.json',
    ),
    'utf8',
  ),
) as { cases: Case[] };

describe('TS engine vs backend engine on random seeded cases', () => {
  it('has 240 cases', () => {
    expect(cases).toHaveLength(240);
  });

  const check = (c: Case) => {
    const got = computeSplit(
      c.split_type,
      c.total,
      c.entries.map(([userId, value]) => ({ userId, value })),
    );
    if (c.expected.error) {
      expect(got.ok).toBe(false);
      if (!got.ok) {
        expect(got.error.code).toBe(c.expected.error.code);
        if (c.expected.error.code !== 'VALIDATION_ERROR') {
          // the backend sends details: null where the TS engine has an empty object
          expect(got.error.details).toEqual(c.expected.error.details ?? {});
        }
      }
    } else {
      expect(got.ok).toBe(true);
      if (got.ok) {
        expect(got.owed.map(o => [o.userId, o.owed])).toEqual(c.expected.owed);
      }
    }
  };

  it.each(cases.map(c => [c.id, c] as const))('%s', (_id, c) => check(c));
});
