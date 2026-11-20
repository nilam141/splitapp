import type { RepeatChoice } from './draft';

export const REPEAT_CHOICES: readonly RepeatChoice[] = [
  'never',
  'weekly',
  'fortnightly',
  'monthly',
  'yearly',
];

export const REPEAT_LABEL: Record<RepeatChoice, string> = {
  never: 'Never',
  weekly: 'Every week',
  fortnightly: 'Every 2 weeks',
  monthly: 'Every month',
  yearly: 'Every year',
};

/** Lower-case adverb for the SCR-29 label ("Repeats monthly"). */
export const REPEAT_ADVERB: Record<Exclude<RepeatChoice, 'never'>, string> = {
  weekly: 'weekly',
  fortnightly: 'fortnightly',
  monthly: 'monthly',
  yearly: 'yearly',
};

export function reminderLabel(days: number | null): string {
  if (days === null) {
    return 'Off';
  }
  if (days === 0) {
    return 'On the day';
  }
  return days === 1 ? '1 day before' : `${days} days before`;
}
