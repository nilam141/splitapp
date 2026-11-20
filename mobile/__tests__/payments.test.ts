import {
  defaultPayer,
  flipAmount,
  isOverpay,
  rowsFromFriend,
  rowsFromTransfers,
} from '../src/payments/rows';
import {
  messageForCreateError,
  validatePaymentAmount,
} from '../src/payments/validate';
import { MAX_AMOUNT_MINOR } from '../src/money/parse';

describe('validatePaymentAmount (SCR-31: 1 <= amount_minor <= 9,999,999,999)', () => {
  it('rejects empty and zero with the "greater than 0" message', () => {
    expect(validatePaymentAmount(null)).toBe('Enter an amount greater than 0.');
    expect(validatePaymentAmount(0)).toBe('Enter an amount greater than 0.');
  });
  it('accepts the bounds and rejects above the maximum', () => {
    expect(validatePaymentAmount(1)).toBeUndefined();
    expect(validatePaymentAmount(MAX_AMOUNT_MINOR)).toBeUndefined();
    expect(validatePaymentAmount(MAX_AMOUNT_MINOR + 1)).toBe(
      'That amount is too large.',
    );
  });
  it('maps server 422 codes to a message with the fix', () => {
    expect(messageForCreateError('SAME_PARTY')).toMatch(/different people/);
    expect(messageForCreateError('CURRENCY_UNKNOWN')).toMatch(/currency/);
    expect(messageForCreateError('AMOUNT_OUT_OF_RANGE')).toMatch(/amount/);
    expect(messageForCreateError('PARTICIPANT_NOT_MEMBER')).toMatch(/group/);
    expect(messageForCreateError(undefined)).toMatch(/try again/);
  });
});

describe('overpay (integer arithmetic only)', () => {
  const owed = { amountMinor: 1333, currency: 'INR' };
  it('is false at or below what is owed', () => {
    expect(isOverpay(1333, 'INR', owed)).toBe(false);
    expect(isOverpay(1, 'INR', owed)).toBe(false);
  });
  it('is true above it, in the same currency only', () => {
    expect(isOverpay(1334, 'INR', owed)).toBe(true);
    expect(isOverpay(5000, 'USD', owed)).toBe(false);
  });
  it('is false when nothing is known about the balance', () => {
    expect(isOverpay(5000, 'INR', undefined)).toBe(false);
  });
  it('flip amount: 50.00 against 13.33 leaves 36.67 the other way', () => {
    expect(flipAmount(5000, 1333)).toBe(3667);
  });
});

describe('pay rows', () => {
  const t = (from: string, to: string, n: number) => ({
    from_user_id: from,
    to_user_id: to,
    amount_minor: n,
    currency: 'INR',
  });
  it('group transfers keep the server order', () => {
    const rows = rowsFromTransfers(
      [t('a', 'b', 300), t('c', 'b', 100), t('a', 'd', 200)],
      'g',
      'Trip',
    );
    expect(rows.map(r => [r.fromUserId, r.toUserId, r.amountMinor])).toEqual([
      ['a', 'b', 300],
      ['c', 'b', 100],
      ['a', 'd', 200],
    ]);
    expect(rows.every(r => r.groupId === 'g' && r.groupName === 'Trip')).toBe(
      true,
    );
  });

  const friend = (breakdown: any[], balances: any[] = []) =>
    ({
      user: { id: 'f', name: 'Ravi', is_registered: true },
      balances,
      breakdown,
    }) as any;

  it('friend breakdown: negative = I pay, positive = they pay, zero lines dropped', () => {
    const rows = rowsFromFriend(
      friend([
        {
          scope: 'group',
          group_id: 'g',
          group_name: 'Flat',
          balances: [
            { amount_minor: -3333, currency: 'INR' },
            { amount_minor: 0, currency: 'USD' },
          ],
        },
        {
          scope: 'non_group',
          group_id: null,
          group_name: null,
          balances: [{ amount_minor: 500, currency: 'USD' }],
        },
      ]),
      'me',
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      fromUserId: 'me',
      toUserId: 'f',
      amountMinor: 3333,
      groupId: 'g',
      groupName: 'Flat',
    });
    expect(rows[1]).toMatchObject({
      fromUserId: 'f',
      toUserId: 'me',
      amountMinor: 500,
      groupId: null,
    });
  });

  it('without a breakdown the totals are treated as non-group', () => {
    const rows = rowsFromFriend(
      friend([], [{ amount_minor: -100, currency: 'INR' }]),
      'me',
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].groupId).toBeNull();
  });

  it('default payer is me when I owe, else the first debtor, else undefined', () => {
    const mine = rowsFromTransfers(
      [t('x', 'me', 5), t('me', 'x', 5)],
      'g',
      null,
    );
    expect(defaultPayer(mine, 'me')).toBe('me');
    const theirs = rowsFromTransfers([t('x', 'me', 5)], 'g', null);
    expect(defaultPayer(theirs, 'me')).toBe('x');
    expect(defaultPayer([], 'me')).toBeUndefined();
  });
});
