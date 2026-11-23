const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isCalendarDate(s: string): boolean {
  if (!DATE_RE.test(s)) {
    return false;
  }
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return (
    dt.getUTCFullYear() === y &&
    dt.getUTCMonth() === m - 1 &&
    dt.getUTCDate() === d
  );
}

export type GroupFormErrors = Partial<
  Record<'name' | 'start' | 'end' | 'members', string>
>;

export const MAX_OTHER_MEMBERS = 199;

export function validateGroupForm(input: {
  name: string;
  isTrip: boolean;
  start: string;
  end: string;
  otherMembers: number;
}): GroupFormErrors {
  const errors: GroupFormErrors = {};
  const name = input.name.trim();
  if (name.length < 1 || name.length > 100) {
    errors.name = 'Enter a group name (1 to 100 characters).';
  }
  if (input.isTrip) {
    const start = input.start.trim();
    const end = input.end.trim();
    if (start && !isCalendarDate(start)) {
      errors.start = 'Use the format YYYY-MM-DD.';
    }
    if (end && !isCalendarDate(end)) {
      errors.end = 'Use the format YYYY-MM-DD.';
    }
    if (!errors.start && !errors.end && start && end && end < start) {
      errors.end = 'The end date cannot be before the start date.';
    }
  }
  if (input.otherMembers > MAX_OTHER_MEMBERS) {
    errors.members = 'A group can have at most 200 members including you.';
  }
  return errors;
}
