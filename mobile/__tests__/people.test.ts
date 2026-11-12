import { parseContact, validateName } from '../src/people/validation';
import { validateGroupForm } from '../src/groups/validation';
import { splitFriends } from '../src/friends/filter';
import { outstandingBalances } from '../src/groups/errors';
import { newIdempotencyKey } from '../src/api/helpers';

describe('contact validation', () => {
  it('accepts email and E.164 phone, rejects junk', () => {
    expect(parseContact(' Ravi@Example.com ')).toEqual({
      ok: true,
      value: { email: 'ravi@example.com' },
    });
    expect(parseContact('+91 98765-43210')).toEqual({
      ok: true,
      value: { phone_e164: '+919876543210' },
    });
    expect(parseContact('abc').ok).toBe(false);
    expect(parseContact('a@b').ok).toBe(false);
    expect(parseContact('9876543210').ok).toBe(false);
  });
  it('name rules', () => {
    expect(validateName('', true)).not.toBeNull();
    expect(validateName('', false)).toBeNull();
    expect(validateName('x'.repeat(101), false)).not.toBeNull();
  });
});

describe('group form validation', () => {
  const ok = {
    name: 'Goa Trip',
    isTrip: true,
    start: '',
    end: '',
    otherMembers: 2,
  };
  it('passes a valid trip', () => expect(validateGroupForm(ok)).toEqual({}));
  it('rejects empty and 101-char names', () => {
    expect(validateGroupForm({ ...ok, name: ' ' }).name).toBeDefined();
    expect(
      validateGroupForm({ ...ok, name: 'x'.repeat(101) }).name,
    ).toBeDefined();
  });
  it('end before start and bad dates', () => {
    expect(
      validateGroupForm({ ...ok, start: '2026-12-10', end: '2026-12-01' }).end,
    ).toBeDefined();
    expect(
      validateGroupForm({ ...ok, start: '2026-02-30' }).start,
    ).toBeDefined();
  });
  it('ignores dates for non-trips and caps members at 199 others', () => {
    expect(validateGroupForm({ ...ok, isTrip: false, start: 'junk' })).toEqual(
      {},
    );
    expect(
      validateGroupForm({ ...ok, otherMembers: 200 }).members,
    ).toBeDefined();
  });
});

describe('friend filters', () => {
  const now = Date.parse('2026-11-10T00:00:00Z');
  const f = (id: string, amounts: number[], since: string | null = null) => ({
    user: { id, name: id, is_registered: true },
    balances: amounts.map(a => ({ amount_minor: a, currency: 'INR' })),
    breakdown: [],
    settled_up_since: since,
  });
  const list = [
    f('owes', [500]),
    f('owed', [-500]),
    f('old', [], '2026-09-01T00:00:00Z'),
    f('recent', [], '2026-11-01T00:00:00Z'),
  ];
  it('filters', () => {
    expect(
      splitFriends(list, 'owes_me', now).visible.map(x => x.user.id),
    ).toEqual(['owes']);
    expect(
      splitFriends(list, 'i_owe', now).visible.map(x => x.user.id),
    ).toEqual(['owed']);
    expect(
      splitFriends(list, 'outstanding', now).visible.map(x => x.user.id),
    ).toEqual(['owes', 'owed']);
  });
  it('collapses friends settled for more than 30 days', () => {
    const r = splitFriends(list, 'all', now);
    expect(r.collapsed.map(x => x.user.id)).toEqual(['old']);
    expect(r.visible.map(x => x.user.id)).toEqual(['owes', 'owed', 'recent']);
  });
});

describe('helpers', () => {
  it('reads OUTSTANDING_BALANCE details defensively', () => {
    expect(
      outstandingBalances({
        balances: [
          { amount_minor: -1, currency: 'INR' },
          { amount_minor: 1.5, currency: 'INR' },
          'x',
        ],
      }),
    ).toEqual([{ amount_minor: -1, currency: 'INR' }]);
    expect(outstandingBalances(undefined)).toEqual([]);
  });
  it('idempotency keys look like UUID v4 and differ', () => {
    const a = newIdempotencyKey();
    expect(a).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(newIdempotencyKey()).not.toBe(a);
  });
});
