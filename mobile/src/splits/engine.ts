// Split engine for live previews (S3-M-2). A line-for-line port of backend app/splits.py semantics from
// docs/business_rules.md section 2 and 3. Integer arithmetic only (all products stay below 2^53: 9,999,999,999 x
// 10,000 is about 1e14). Verified against the shared vector table backend/tests/rules/vectors.json.
// Entries must be passed in canonical order (docs/business_rules.md section 1); this module never reorders.

export type SplitType = 'equal' | 'exact' | 'percent' | 'shares' | 'adjustment';

export type SplitEntry = { userId: string; value?: number | null };
export type Owed = { userId: string; owed: number };

export type SplitErrorCode =
  | 'SPLIT_NO_PARTICIPANTS'
  | 'SPLIT_SUM_MISMATCH'
  | 'SPLIT_PERCENT_MISMATCH'
  | 'SPLIT_NO_SHARES'
  | 'SPLIT_ADJUSTMENT_EXCEEDS_TOTAL'
  | 'PAYER_SUM_MISMATCH'
  | 'DUPLICATE_PARTICIPANT'
  | 'DUPLICATE_PAYER'
  | 'VALIDATION_ERROR';

export type SplitError = {
  code: SplitErrorCode;
  /** expected / actual / difference (minor units), or difference_bp for SPLIT_PERCENT_MISMATCH. */
  details: Record<string, number> & { fields?: FieldIssue[] };
};

/** Same shape as the backend's VALIDATION_ERROR details.fields entries. */
export type FieldIssue = { field: string; message: string };

export type SplitResult =
  { ok: true; owed: Owed[] } | { ok: false; error: SplitError };

const fail = (
  code: SplitErrorCode,
  details: Record<string, number> = {},
  fields?: FieldIssue[],
): { ok: false; error: SplitError } => ({
  ok: false,
  error: { code, details: fields ? { fields } : details } as SplitError,
});

const outOfRange = (): { ok: false; error: SplitError } =>
  fail('VALIDATION_ERROR', undefined, [
    { field: 'split.entries', message: 'value out of range' },
  ]);

const MAX_SHARES = 999;
const TOTAL_BP = 10000;

const sum = (values: number[]): number => values.reduce((a, b) => a + b, 0);

/** Integer floor division for non-negative a and positive b. */
const divFloor = (a: number, b: number): number => (a - (a % b)) / b;

function equalAmounts(total: number, n: number): number[] {
  const base = divFloor(total, n);
  const r = total % n;
  return Array.from({ length: n }, (_, i) => base + (i < r ? 1 : 0));
}

/** Largest remainder (Hamilton); ties by canonical order. */
function weightedAmounts(total: number, weights: number[]): number[] {
  const w = sum(weights);
  const floors = weights.map(x => divFloor(total * x, w));
  const fracs = weights.map((x, i) => ({ frac: (total * x) % w, i }));
  const leftover = total - sum(floors);
  fracs
    .sort((a, b) => b.frac - a.frac || a.i - b.i)
    .slice(0, leftover)
    .forEach(f => {
      floors[f.i] += 1;
    });
  return floors;
}

const val = (e: SplitEntry): number => e.value ?? 0;

export function computeSplit(
  type: SplitType,
  total: number,
  entries: SplitEntry[],
): SplitResult {
  if (entries.length === 0) {
    return fail('SPLIT_NO_PARTICIPANTS');
  }
  if (new Set(entries.map(e => e.userId)).size !== entries.length) {
    return fail('DUPLICATE_PARTICIPANT');
  }
  // backend _check_entries: negative, and above 10000 bp (percent) or 999 (shares), is VALIDATION_ERROR
  const upper =
    type === 'percent' ? TOTAL_BP : type === 'shares' ? MAX_SHARES : undefined;
  if (
    type !== 'equal' &&
    entries.some(e => val(e) < 0 || (upper !== undefined && val(e) > upper))
  ) {
    return outOfRange();
  }
  const pack = (amounts: number[]): SplitResult => ({
    ok: true,
    owed: entries.map((e, i) => ({ userId: e.userId, owed: amounts[i] })),
  });

  switch (type) {
    case 'equal':
      return pack(equalAmounts(total, entries.length));
    case 'exact': {
      const actual = sum(entries.map(val));
      if (actual !== total) {
        return fail('SPLIT_SUM_MISMATCH', {
          expected: total,
          actual,
          difference: actual - total,
        });
      }
      return pack(entries.map(val));
    }
    case 'percent': {
      const actual = sum(entries.map(val));
      if (actual !== TOTAL_BP) {
        return fail('SPLIT_PERCENT_MISMATCH', {
          difference_bp: actual - TOTAL_BP,
        });
      }
      return pack(weightedAmounts(total, entries.map(val)));
    }
    case 'shares': {
      if (sum(entries.map(val)) < 1) {
        return fail('SPLIT_NO_SHARES');
      }
      return pack(weightedAmounts(total, entries.map(val)));
    }
    case 'adjustment': {
      const adj = sum(entries.map(val));
      if (adj > total) {
        return fail('SPLIT_ADJUSTMENT_EXCEEDS_TOTAL', {
          expected: total,
          actual: adj,
          difference: adj - total,
        });
      }
      const eq = equalAmounts(total - adj, entries.length);
      return pack(entries.map((e, i) => val(e) + eq[i]));
    }
  }
}

export type Payer = { userId: string; paid: number };

/** Payers must be unique and sum to the total (business_rules section 3). */
export function validatePayers(
  total: number,
  payers: Payer[],
): { ok: true } | { ok: false; error: SplitError } {
  if (new Set(payers.map(p => p.userId)).size !== payers.length) {
    return fail('DUPLICATE_PAYER');
  }
  const actual = sum(payers.map(p => p.paid));
  if (actual !== total) {
    return fail('PAYER_SUM_MISMATCH', {
      expected: total,
      actual,
      difference: actual - total,
    });
  }
  return { ok: true };
}

/** net = paid - owed per user (positive = the others owe this person). Users keep first-seen order. */
export function netBalances(
  payers: Payer[],
  owed: Owed[],
): Record<string, number> {
  const nets: Record<string, number> = {};
  for (const p of payers) {
    nets[p.userId] = (nets[p.userId] ?? 0) + p.paid;
  }
  for (const o of owed) {
    nets[o.userId] = (nets[o.userId] ?? 0) - o.owed;
  }
  return nets;
}
