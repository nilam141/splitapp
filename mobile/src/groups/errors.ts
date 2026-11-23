import type { BalanceLine } from '../api/generated/model';

/** details.balances of a 409 OUTSTANDING_BALANCE, if present and well-formed. */
export function outstandingBalances(details: unknown): BalanceLine[] {
  const list = (details as { balances?: unknown } | undefined)?.balances;
  if (!Array.isArray(list)) {
    return [];
  }
  return list.filter(
    (b): b is BalanceLine =>
      !!b &&
      typeof (b as BalanceLine).amount_minor === 'number' &&
      Number.isInteger((b as BalanceLine).amount_minor) &&
      typeof (b as BalanceLine).currency === 'string',
  );
}
