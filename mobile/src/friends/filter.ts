import type {
  BalanceLine,
  Friend,
  ListFriendsFilter,
} from '../api/generated/model';

export type FriendFilter = ListFriendsFilter;
const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

const hasNonZero = (f: Friend) => f.balances.some(b => b.amount_minor !== 0);

export function matchesFilter(f: Friend, filter: FriendFilter): boolean {
  switch (filter) {
    case 'outstanding':
      return hasNonZero(f);
    // Positive amount_minor = the friend owes the viewer.
    case 'owes_me':
      return f.balances.some(b => b.amount_minor > 0);
    case 'i_owe':
      return f.balances.some(b => b.amount_minor < 0);
    default:
      return true;
  }
}

/** Settled for more than 30 days: hidden behind "show N settled-up friends" (SCR-08). */
export function isLongSettledLines(
  lines: BalanceLine[],
  settledUpSince: string | null | undefined,
  now: number,
): boolean {
  if (!settledUpSince || lines.some(b => b.amount_minor !== 0)) {
    return false;
  }
  const since = Date.parse(settledUpSince);
  return !Number.isNaN(since) && now - since > THIRTY_DAYS_MS;
}

export const isLongSettled = (f: Friend, now: number): boolean =>
  isLongSettledLines(f.balances, f.settled_up_since, now);

export function splitFriends(
  friends: Friend[],
  filter: FriendFilter,
  now: number,
): { visible: Friend[]; collapsed: Friend[]; matching: number } {
  const matching = friends.filter(f => matchesFilter(f, filter));
  // Only the default view collapses; a filter that matches a settled friend (never, for the
  // balance filters) would not hide it.
  const collapsed =
    filter === 'all' ? matching.filter(f => isLongSettled(f, now)) : [];
  return {
    visible: matching.filter(f => !collapsed.includes(f)),
    collapsed,
    matching: matching.length,
  };
}
