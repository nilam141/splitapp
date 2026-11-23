import type { NotificationPrefs } from '../api/generated/model';

// F-38: the 10 notification types, in screen order, each a boolean preference that defaults to on.
export const NOTIFICATION_TYPES: readonly {
  key: keyof NotificationPrefs;
  label: string;
  /** True when no producer sends this type yet (business_rules 10.4, OQ-47). */
  notSent?: boolean;
}[] = [
  { key: 'expense_added', label: 'Expense added' },
  { key: 'expense_updated', label: 'Expense updated or deleted' },
  { key: 'comment_added', label: 'Comment added' },
  { key: 'added_to_group', label: 'Added to a group', notSent: true },
  { key: 'removed_from_group', label: 'Removed from a group', notSent: true },
  { key: 'group_updated', label: 'Group updated or deleted', notSent: true },
  { key: 'friend_added', label: 'Added as a friend', notSent: true },
  { key: 'friend_removed', label: 'Friend removed', notSent: true },
  { key: 'payment_recorded', label: 'Payment recorded' },
  { key: 'reminder', label: 'Reminder to settle up' },
];

export const NOT_SENT_CAPTION = 'Not sent yet.';

export const prefValue = (
  prefs: NotificationPrefs | undefined,
  key: keyof NotificationPrefs,
): boolean => prefs?.[key] !== false;
