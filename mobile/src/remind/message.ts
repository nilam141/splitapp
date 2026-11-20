export const MAX_REMINDER_MESSAGE = 1000;

/** Prefilled reminder text (SCR-33). `amountText` is already formatted by the money helper. */
export function reminderText(name: string, amountText: string | undefined) {
  return amountText
    ? `Hi ${name}, a friendly reminder that you owe me ${amountText}. I use SplitApp to keep track. Thanks!`
    : `Hi ${name}, a friendly reminder to settle up when you can. Thanks!`;
}
