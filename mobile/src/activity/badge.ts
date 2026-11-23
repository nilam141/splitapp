/** Tab badge text (design_system 6.7, SCR-07): hidden at 0, the number up to 99, "99+" above. */
export function formatBadge(
  count: number | undefined | null,
): string | undefined {
  if (!count || count <= 0) {
    return undefined;
  }
  return count > 99 ? '99+' : String(count);
}
