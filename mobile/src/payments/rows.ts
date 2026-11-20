import type { Friend, Transfer } from '../api/generated/model';

// Pure helpers for SCR-30 (Settle up). Amounts stay integer minor units; the server's order is kept.

/** One payable line: `fromUserId` pays `toUserId` `amountMinor` (always > 0) in `currency`. */
export type PayRow = {
  key: string;
  fromUserId: string;
  toUserId: string;
  /** null = non-group balance. */
  groupId: string | null;
  groupName: string | null;
  amountMinor: number;
  currency: string;
};

/** Group scope: the server's transfers (simplified or pairwise), in the order the server returns them. */
export function rowsFromTransfers(
  transfers: Transfer[],
  groupId: string,
  groupName: string | null,
): PayRow[] {
  return transfers
    .filter(t => t.amount_minor > 0)
    .map((t, i) => ({
      key: `t-${i}-${t.from_user_id}-${t.to_user_id}-${t.currency}`,
      fromUserId: t.from_user_id,
      toUserId: t.to_user_id,
      groupId,
      groupName,
      amountMinor: t.amount_minor,
      currency: t.currency,
    }));
}

/**
 * Friend scope: one row per scope (group or non-group) and currency that is not zero.
 * A negative line means the viewer owes the friend, so the viewer pays; a positive line means the friend pays.
 */
export function rowsFromFriend(friend: Friend, meId: string): PayRow[] {
  const scopes =
    friend.breakdown.length > 0
      ? friend.breakdown
      : [
          {
            scope: 'non_group' as const,
            group_id: null,
            group_name: null,
            balances: friend.balances,
          },
        ];
  const rows: PayRow[] = [];
  scopes.forEach((s, si) => {
    for (const line of s.balances) {
      if (line.amount_minor === 0) {
        continue;
      }
      const viewerPays = line.amount_minor < 0;
      const abs = viewerPays ? -line.amount_minor : line.amount_minor;
      rows.push({
        key: `f-${si}-${s.group_id ?? 'ng'}-${line.currency}`,
        fromUserId: viewerPays ? meId : friend.user.id,
        toUserId: viewerPays ? friend.user.id : meId,
        groupId: s.scope === 'group' ? (s.group_id ?? null) : null,
        groupName: s.scope === 'group' ? (s.group_name ?? null) : null,
        amountMinor: abs,
        currency: line.currency,
      });
    }
  });
  return rows;
}

/** Default payer: the viewer when they owe something, otherwise the first person who owes. */
export function defaultPayer(rows: PayRow[], meId: string): string | undefined {
  if (rows.some(r => r.fromUserId === meId)) {
    return meId;
  }
  return rows[0]?.fromUserId;
}

/** Payment direction check used by the overpay confirmation: amount above what the payer owes. */
export function isOverpay(
  amountMinor: number,
  currency: string,
  owed: { amountMinor: number; currency: string } | undefined,
): boolean {
  return (
    owed !== undefined &&
    owed.currency === currency &&
    amountMinor > owed.amountMinor
  );
}

/** What the receiver will owe the payer afterwards (integer subtraction). */
export function flipAmount(amountMinor: number, owedMinor: number): number {
  return amountMinor - owedMinor;
}
