// Pure logic behind SCR-22 to SCR-28: the draft, live split previews and the request body.
// Money is integer minor units throughout; user text goes through parseMinor() only.
import type {
  Expense,
  ExpenseCreate,
  SplitEntryInput,
} from '../api/generated/model';
import { formatMinorAmount } from '../money/format';
import { isAmountInRange, parseMinor, PARSE_MESSAGES } from '../money/parse';
import {
  computeSplit,
  validatePayers,
  type SplitEntry,
  type SplitType,
} from '../splits/engine';

export type Person = { id: string; name: string };

export type SplitDraft = {
  type: SplitType;
  /** user ids ticked on the equal tab */
  included: string[];
  /** typed values for exact / percent / shares / adjustment, keyed by user id */
  values: Record<string, string>;
};

export type PayersDraft =
  | { mode: 'single'; payerId: string }
  | { mode: 'multiple'; amounts: Record<string, string> };

export type ExpenseDraft = {
  description: string;
  amountText: string;
  currency: string;
  categoryId: number | undefined;
  date: string; // YYYY-MM-DD
  notes: string;
  payers: PayersDraft;
  split: SplitDraft;
};

export const MAX_SHARES = 999;

/** "1234.50" without grouping, for text inputs. */
export const plainAmount = (minor: number, exponent: number): string =>
  formatMinorAmount(minor, exponent).replace(/,/g, '');

/** Basis points as a percentage without trailing zeros: 100 -> "1", 3333 -> "33.33", 50 -> "0.5". */
export function formatBp(bp: number): string {
  const sign = bp < 0 ? '-' : '';
  const abs = bp < 0 ? -bp : bp;
  const frac = abs % 100;
  const whole = (abs - frac) / 100;
  const fracText = String(frac).padStart(2, '0').replace(/0+$/, '');
  return `${sign}${whole}${fracText ? `.${fracText}` : ''}`;
}

export function initialDraft(
  me: string,
  people: Person[],
  currency: string,
  today: string,
): ExpenseDraft {
  return {
    description: '',
    amountText: '',
    currency,
    categoryId: undefined,
    date: today,
    notes: '',
    payers: { mode: 'single', payerId: me },
    split: { type: 'equal', included: people.map(p => p.id), values: {} },
  };
}

/** Canonical order for previews (business_rules section 1): group = join order; non-group = creator, then by id. */
export function canonicalPeople(
  people: Person[],
  opts: { isGroup: boolean; creatorId: string },
): Person[] {
  if (opts.isGroup) {
    return people;
  }
  const others = people
    .filter(p => p.id !== opts.creatorId)
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const creator = people.filter(p => p.id === opts.creatorId);
  return [...creator, ...others];
}

// ---------------------------------------------------------------- amount

export type AmountState =
  { ok: true; minor: number } | { ok: false; message: string };

export function parseAmount(text: string, exponent: number): AmountState {
  const r = parseMinor(text, exponent);
  if (!r.ok) {
    return { ok: false, message: PARSE_MESSAGES[r.error] };
  }
  if (!isAmountInRange(r.minor)) {
    return {
      ok: false,
      message:
        r.minor < 1
          ? 'The amount must be greater than zero.'
          : `The amount can be at most ${formatMinorAmount(9999999999, exponent)}.`,
    };
  }
  return { ok: true, minor: r.minor };
}

// ---------------------------------------------------------------- split preview

export type SplitRow = {
  userId: string;
  /** computed owed amount, when the split is valid */
  owed?: number;
  /** a typed value that cannot be parsed */
  inputError?: string;
};

export type SplitEvaluation = {
  rows: SplitRow[];
  valid: boolean;
  /** footer lines (SCR-23) */
  footer: string[];
  /** the exact gap, for the invalid-split dialog */
  error?: string;
};

type Fmt = (minor: number) => string;

function entriesFor(
  split: SplitDraft,
  people: Person[],
  exponent: number,
): { entries: SplitEntry[]; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const entries: SplitEntry[] = [];
  if (split.type === 'equal') {
    people
      .filter(p => split.included.includes(p.id))
      .forEach(p => entries.push({ userId: p.id }));
    return { entries, errors };
  }
  const exp =
    split.type === 'percent' ? 2 : split.type === 'shares' ? 0 : exponent;
  for (const p of people) {
    const text = (split.values[p.id] ?? '').trim();
    if (text === '') {
      entries.push({ userId: p.id, value: 0 });
      continue;
    }
    const r = parseMinor(text, exp);
    if (!r.ok) {
      errors[p.id] = PARSE_MESSAGES[r.error];
      entries.push({ userId: p.id, value: 0 });
    } else if (split.type === 'shares' && r.minor > MAX_SHARES) {
      errors[p.id] = `Shares are 0 to ${MAX_SHARES}.`;
      entries.push({ userId: p.id, value: 0 });
    } else if (split.type === 'percent' && r.minor > 10000) {
      errors[p.id] = 'A percentage is at most 100.';
      entries.push({ userId: p.id, value: 0 });
    } else {
      entries.push({ userId: p.id, value: r.minor });
    }
  }
  return { entries, errors };
}

/** Live preview for the adjust-split screen. Pure and fast: it runs on every keystroke. */
export function evaluateSplit(
  split: SplitDraft,
  people: Person[],
  total: number | undefined,
  exponent: number,
  fmt: Fmt,
): SplitEvaluation {
  const { entries, errors } = entriesFor(split, people, exponent);
  const baseRows: SplitRow[] = people.map(p => ({
    userId: p.id,
    inputError: errors[p.id],
  }));
  const hasInputError = Object.keys(errors).length > 0;
  const footer: string[] = [];

  if (split.type === 'equal' && entries.length === 0) {
    return {
      rows: baseRows,
      valid: false,
      footer: ['Select at least 1 person.'],
      error: 'Select at least 1 person.',
    };
  }
  const sumValues = entries.reduce((a, e) => a + (e.value ?? 0), 0);
  // Footers that do not need the total.
  if (split.type === 'percent') {
    const diff = sumValues - 10000;
    footer.push(`${formatBp(sumValues)}% of 100%`);
    if (diff < 0) {
      footer.push(`${formatBp(-diff)}% left`);
    } else if (diff > 0) {
      footer.push(`${formatBp(diff)}% over`);
    }
  } else if (split.type === 'shares') {
    footer.push(`${sumValues} total shares`);
  }

  if (total === undefined) {
    return {
      rows: baseRows,
      valid: false,
      footer,
      error: 'Enter the amount first.',
    };
  }

  if (split.type === 'exact') {
    footer.push(`${fmt(sumValues)} of ${fmt(total)}`);
    if (sumValues < total) {
      footer.push(`${fmt(total - sumValues)} left`);
    } else if (sumValues > total) {
      footer.push(`over by ${fmt(sumValues - total)}`);
    }
  }
  if (split.type === 'adjustment' && sumValues <= total) {
    footer.push(`${fmt(total - sumValues)} split equally after adjustments`);
  }

  const result = computeSplit(split.type, total, entries);
  if (hasInputError) {
    return {
      rows: baseRows,
      valid: false,
      footer,
      error: 'Fix the highlighted values.',
    };
  }
  if (!result.ok) {
    const d = result.error.details;
    let error: string;
    switch (result.error.code) {
      case 'SPLIT_SUM_MISMATCH':
        error =
          d.difference < 0
            ? `Split is under by ${fmt(-d.difference)}`
            : `Split is over by ${fmt(d.difference)}`;
        break;
      case 'SPLIT_PERCENT_MISMATCH':
        error =
          d.difference_bp < 0
            ? `Percentages are ${formatBp(-d.difference_bp)}% short of 100%`
            : `Percentages are ${formatBp(d.difference_bp)}% over 100%`;
        break;
      case 'SPLIT_NO_SHARES':
        error = 'Assign at least 1 share.';
        footer.push(error);
        break;
      case 'SPLIT_ADJUSTMENT_EXCEEDS_TOTAL':
        error = `Adjustments are over the total by ${fmt(d.difference)}`;
        footer.push(
          'Adjustments cannot exceed the total.',
          `over by ${fmt(d.difference)}`,
        );
        break;
      default:
        error = 'This split is not valid.';
    }
    return { rows: baseRows, valid: false, footer, error };
  }
  const owedById = new Map(result.owed.map(o => [o.userId, o.owed]));
  return {
    rows: baseRows.map(r => ({ ...r, owed: owedById.get(r.userId) })),
    valid: true,
    footer,
  };
}

// ---------------------------------------------------------------- payers

export type PayersEvaluation = {
  payers: { userId: string; paid: number }[];
  valid: boolean;
  footer: string[];
  error?: string;
  inputErrors: Record<string, string>;
};

export function evaluatePayers(
  payers: PayersDraft,
  people: Person[],
  total: number | undefined,
  exponent: number,
  fmt: Fmt,
): PayersEvaluation {
  if (payers.mode === 'single') {
    return {
      payers:
        total === undefined ? [] : [{ userId: payers.payerId, paid: total }],
      valid: total !== undefined,
      footer: [],
      error: total === undefined ? 'Enter the amount first.' : undefined,
      inputErrors: {},
    };
  }
  const inputErrors: Record<string, string> = {};
  const list: { userId: string; paid: number }[] = [];
  for (const p of people) {
    const text = (payers.amounts[p.id] ?? '').trim();
    if (text === '') {
      continue;
    }
    const r = parseMinor(text, exponent);
    if (!r.ok) {
      inputErrors[p.id] = PARSE_MESSAGES[r.error];
    } else if (r.minor > 0) {
      list.push({ userId: p.id, paid: r.minor });
    }
  }
  const paid = list.reduce((a, p) => a + p.paid, 0);
  if (total === undefined) {
    return {
      payers: list,
      valid: false,
      footer: [],
      error: 'Enter the amount first.',
      inputErrors,
    };
  }
  const footer = [`${fmt(paid)} of ${fmt(total)}`];
  if (Object.keys(inputErrors).length > 0) {
    return {
      payers: list,
      valid: false,
      footer,
      error: 'Fix the highlighted values.',
      inputErrors,
    };
  }
  const checked = validatePayers(total, list);
  if (!checked.ok) {
    const diff = checked.error.details.difference ?? 0;
    const error =
      list.length === 0
        ? 'Enter who paid.'
        : diff < 0
          ? `Payments are under by ${fmt(-diff)}`
          : `Payments are over by ${fmt(diff)}`;
    footer.push(diff < 0 ? `${fmt(-diff)} left` : `over by ${fmt(diff)}`);
    return { payers: list, valid: false, footer, error, inputErrors };
  }
  return { payers: list, valid: true, footer, inputErrors };
}

// ---------------------------------------------------------------- two-person shortcuts

export type Shortcut =
  'you_paid_equal' | 'they_paid_equal' | 'you_owed_full' | 'they_owed_full';

export function applyShortcut(
  shortcut: Shortcut,
  meId: string,
  otherId: string,
  total: number,
  exponent: number,
): Pick<ExpenseDraft, 'payers' | 'split'> {
  const both = [meId, otherId];
  const t = plainAmount(total, exponent);
  switch (shortcut) {
    case 'you_paid_equal':
      return {
        payers: { mode: 'single', payerId: meId },
        split: { type: 'equal', included: both, values: {} },
      };
    case 'they_paid_equal':
      return {
        payers: { mode: 'single', payerId: otherId },
        split: { type: 'equal', included: both, values: {} },
      };
    case 'you_owed_full':
      return {
        payers: { mode: 'single', payerId: meId },
        split: {
          type: 'exact',
          included: both,
          values: { [meId]: '0', [otherId]: t },
        },
      };
    case 'they_owed_full':
      return {
        payers: { mode: 'single', payerId: otherId },
        split: {
          type: 'exact',
          included: both,
          values: { [meId]: t, [otherId]: '0' },
        },
      };
  }
}

// ---------------------------------------------------------------- date

const pad2 = (n: number) => String(n).padStart(2, '0');

/** Local calendar date as YYYY-MM-DD. */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso
    .split('-')
    .map(part => parseMinor(part, 0))
    .map(r => (r.ok ? r.minor : 0));
  return isoDate(new Date(y, m - 1, d + days));
}

export const MIN_DATE = '2000-01-01';

/** Real calendar date between 2000-01-01 and today + 365 days (SCR-27). */
export function validateDate(text: string, today: string): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return 'Enter the date as YYYY-MM-DD.';
  }
  const [y, m, d] = text
    .split('-')
    .map(part => parseMinor(part, 0))
    .map(r => (r.ok ? r.minor : 0));
  const real = new Date(y, m - 1, d);
  if (
    real.getFullYear() !== y ||
    real.getMonth() !== m - 1 ||
    real.getDate() !== d
  ) {
    return 'That date does not exist.';
  }
  if (text < MIN_DATE || text > addDays(today, 365)) {
    return 'Pick a date from 2000-01-01 to one year from today.';
  }
  return undefined;
}

// ---------------------------------------------------------------- validation + request body

export type DraftErrors = {
  description?: string;
  amount?: string;
  date?: string;
  notes?: string;
  split?: string;
  payers?: string;
};

export type BuildResult =
  | { ok: true; body: Omit<ExpenseCreate, 'group_id'>; total: number }
  | { ok: false; errors: DraftErrors; panel?: 'split' | 'payers' };

export function buildRequest(
  draft: ExpenseDraft,
  people: Person[],
  exponent: number,
  today: string,
  fmt: Fmt,
): BuildResult {
  const errors: DraftErrors = {};
  const description = draft.description.trim();
  if (description === '') {
    errors.description = 'Enter a description.';
  } else if (description.length > 200) {
    errors.description = 'The description can be at most 200 characters.';
  }
  const amount = parseAmount(draft.amountText, exponent);
  if (!amount.ok) {
    errors.amount = amount.message;
  }
  const dateError = validateDate(draft.date, today);
  if (dateError) {
    errors.date = dateError;
  }
  if (draft.notes.length > 2000) {
    errors.notes = 'Notes can be at most 2000 characters.';
  }
  if (Object.keys(errors).length > 0 || !amount.ok) {
    return { ok: false, errors };
  }
  const total = amount.minor;
  const split = evaluateSplit(draft.split, people, total, exponent, fmt);
  if (!split.valid) {
    return { ok: false, errors: { split: split.error }, panel: 'split' };
  }
  const payers = evaluatePayers(draft.payers, people, total, exponent, fmt);
  if (!payers.valid) {
    return { ok: false, errors: { payers: payers.error }, panel: 'payers' };
  }
  const entries: SplitEntryInput[] = people
    .filter(
      p => draft.split.type !== 'equal' || draft.split.included.includes(p.id),
    )
    .map(p => {
      if (draft.split.type === 'equal') {
        return { user_id: p.id };
      }
      const text = (draft.split.values[p.id] ?? '').trim();
      const exp =
        draft.split.type === 'percent'
          ? 2
          : draft.split.type === 'shares'
            ? 0
            : exponent;
      const parsed =
        text === '' ? { ok: true as const, minor: 0 } : parseMinor(text, exp);
      return { user_id: p.id, value: parsed.ok ? parsed.minor : 0 };
    });
  const body: Omit<ExpenseCreate, 'group_id'> = {
    description,
    total: { amount_minor: total, currency: draft.currency },
    expense_date: draft.date,
    notes: draft.notes.trim() === '' ? null : draft.notes,
    payers: payers.payers.map(p => ({
      user_id: p.userId,
      paid_amount_minor: p.paid,
    })),
    split: { type: draft.split.type, entries },
    ...(draft.categoryId === undefined
      ? {}
      : { category_id: draft.categoryId }),
  };
  return { ok: true, body, total };
}

// ---------------------------------------------------------------- edit

/** Seeds the draft from an existing expense (SCR-22 edit). */
export function draftFromExpense(e: Expense, exponent: number): ExpenseDraft {
  const values: Record<string, string> = {};
  for (const s of e.splits) {
    const raw = s.input_value ?? s.owed_amount_minor;
    if (e.split_type === 'percent') {
      values[s.user_id] = formatBp(raw);
    } else if (e.split_type === 'shares') {
      values[s.user_id] = String(raw);
    } else if (e.split_type !== 'equal') {
      values[s.user_id] = plainAmount(raw, exponent);
    }
  }
  const single =
    e.payers.length === 1 &&
    e.payers[0].paid_amount_minor === e.total.amount_minor;
  const amounts: Record<string, string> = {};
  for (const p of e.payers) {
    amounts[p.user_id] = plainAmount(p.paid_amount_minor, exponent);
  }
  return {
    description: e.description,
    amountText: plainAmount(e.total.amount_minor, exponent),
    currency: e.total.currency,
    categoryId: e.category_id,
    date: e.expense_date,
    notes: e.notes ?? '',
    payers: single
      ? { mode: 'single', payerId: e.payers[0].user_id }
      : { mode: 'multiple', amounts },
    split: {
      type: e.split_type,
      included: e.splits.map(s => s.user_id),
      values,
    },
  };
}
