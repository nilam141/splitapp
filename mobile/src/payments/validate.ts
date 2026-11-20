import { MAX_AMOUNT_MINOR } from '../money/parse';

/** SCR-31 amount rule: 1 <= amount_minor <= 9,999,999,999. Returns the message to show, or undefined when valid. */
export function validatePaymentAmount(
  amountMinor: number | null,
): string | undefined {
  if (amountMinor === null || amountMinor < 1) {
    return 'Enter an amount greater than 0.';
  }
  if (amountMinor > MAX_AMOUNT_MINOR) {
    return 'That amount is too large.';
  }
  return undefined;
}

export const PAYMENT_NOTE_MAX = 500;

/** Server 422 codes for POST /settlements, mapped to a message that states the fix. */
export function messageForCreateError(code: string | undefined): string {
  switch (code) {
    case 'AMOUNT_OUT_OF_RANGE':
      return 'Enter an amount greater than 0 that is within the allowed range.';
    case 'SAME_PARTY':
      return 'The payer and the receiver must be different people.';
    case 'PARTICIPANT_NOT_MEMBER':
      return 'Both people must be in the group.';
    case 'CURRENCY_UNKNOWN':
      return 'That currency is not supported. Choose another one.';
    default:
      return 'Something went wrong. Please try again.';
  }
}
