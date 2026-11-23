export const OFFLINE_MESSAGE =
  "Can't reach the server. Check your connection and try again.";

// 409 on a payment edit, delete or restore (the settlement counterpart of EXPENSE_HAS_DEPARTED_MEMBER). The contract
// does not declare a settlement-specific code yet, so any 409 other than ALREADY_DELETED / NOT_DELETED /
// VERSION_CONFLICT shows this neutral text (logged in docs/progress.md).
export const PAYMENT_CONFLICT_MESSAGE =
  'Someone in this payment is no longer in the group or no longer your friend, so it cannot be changed.';
