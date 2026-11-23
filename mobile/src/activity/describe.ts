import type { ActivityItem, BalanceLine } from '../api/generated/model';
import { balanceTone } from '../theme/balance';

// Pure text helpers for SCR-10. The server order of the feed is never changed here; items are only labelled.

export type Segment = { text: string; strong: boolean };
export type Formatter = (amountMinor: number, currency: string) => string;
export type DescribeContext = {
  meId: string | undefined;
  format: Formatter;
  groupName?: (groupId: string) => string | undefined;
};

const str = (v: unknown): string | undefined =>
  typeof v === 'string' && v.length > 0 ? v : undefined;

function moneyOf(v: unknown, format: Formatter): string | undefined {
  if (v && typeof v === 'object') {
    const m = v as { amount_minor?: unknown; currency?: unknown };
    if (typeof m.amount_minor === 'number' && typeof m.currency === 'string') {
      return format(m.amount_minor, m.currency);
    }
  }
  return undefined;
}

const plain = (text: string): Segment => ({ text, strong: false });
const strong = (text: string): Segment => ({ text, strong: true });

/** "Ravi added Groceries in Flat 4B": actor and object are strong segments. */
export function describeActivity(
  item: ActivityItem,
  ctx: DescribeContext,
): Segment[] {
  const s = item.summary ?? {};
  const actorName = item.actor
    ? item.actor.id === ctx.meId
      ? 'You'
      : item.actor.name
    : 'A recurring rule';
  const who = (id: unknown, name: unknown): string =>
    id === ctx.meId ? 'You' : (str(name) ?? 'Someone');
  const groupId = item.group_id ?? undefined;
  const inGroup = (): Segment[] => {
    const name = groupId ? ctx.groupName?.(groupId) : undefined;
    return name ? [plain(' in '), strong(name)] : [];
  };
  const actor = strong(actorName);
  const verbs: Record<string, string> = {
    created: 'added',
    updated: 'updated',
    deleted: 'deleted',
    restored: 'restored',
  };

  switch (item.action) {
    case 'expense.created':
    case 'expense.updated':
    case 'expense.deleted':
    case 'expense.restored': {
      const verb = verbs[item.action.split('.')[1]];
      return [
        actor,
        plain(` ${verb} `),
        strong(str(s.description) ?? 'an expense'),
        ...inGroup(),
      ];
    }
    case 'settlement.created':
    case 'settlement.updated':
    case 'settlement.deleted':
    case 'settlement.restored': {
      const verb = item.action.endsWith('created')
        ? 'recorded'
        : verbs[item.action.split('.')[1]];
      const amount = moneyOf(s.amount, ctx.format);
      const object = `${who(s.from_user_id, s.from_name)} paid ${who(s.to_user_id, s.to_name)}${amount ? ` ${amount}` : ''}`;
      return [
        actor,
        plain(` ${verb} a payment: `),
        strong(object),
        ...inGroup(),
      ];
    }
    case 'comment.created':
      return [
        actor,
        plain(' commented on '),
        strong(str(s.description) ?? 'an expense'),
        ...inGroup(),
      ];
    case 'group.created':
      return [actor, plain(' created the group '), strong(str(s.name) ?? '')];
    case 'group.updated':
    case 'group.deleted':
    case 'group.restored':
      return [
        actor,
        plain(` ${verbs[item.action.split('.')[1]]} the group `),
        strong(str(s.name) ?? 'a group'),
      ];
    case 'group.member_added':
      return [
        actor,
        plain(' added '),
        strong(who(s.user_id, s.user_name)),
        plain(' to '),
        strong(str(s.name) ?? 'a group'),
      ];
    case 'group.member_removed':
      return s.left === true
        ? [
            strong(who(s.user_id, s.user_name)),
            plain(' left '),
            strong(str(s.name) ?? 'a group'),
          ]
        : [
            actor,
            plain(' removed '),
            strong(who(s.user_id, s.user_name)),
            plain(' from '),
            strong(str(s.name) ?? 'a group'),
          ];
    case 'group.member_joined':
      return [
        strong(who(s.user_id, s.user_name)),
        plain(' joined '),
        strong(str(s.name) ?? 'a group'),
      ];
    case 'group.currency_converted':
      return [
        actor,
        plain(' converted the currency of '),
        strong(str(s.name) ?? 'a group'),
      ];
    case 'friend.added':
      return [
        actor,
        plain(' added '),
        strong(str(s.friend_name) ?? 'a friend'),
        plain(' as a friend'),
      ];
    case 'friend.removed':
      return [
        actor,
        plain(' removed '),
        strong(str(s.friend_name) ?? 'a friend'),
        plain(' from friends'),
      ];
    default:
      return [actor, plain(' made a change')];
  }
}

export const segmentsToText = (segments: Segment[]): string =>
  segments.map(x => x.text).join('');

export type EffectChip = {
  key: string;
  amountMinor: number;
  /** Sentence with sign for the chip face, e.g. "you owe −INR 30.00". */
  text: string;
  /** The same without the glyph, for screen readers. */
  label: string;
};

/** One chip per non-zero currency in the order the server sent them. Sign and word are always present. */
export function effectChips(
  lines: BalanceLine[] | undefined,
  format: Formatter,
): EffectChip[] {
  return (lines ?? [])
    .filter(l => l.amount_minor !== 0)
    .map(l => {
      const tone = balanceTone(l.amount_minor);
      const abs = l.amount_minor < 0 ? -l.amount_minor : l.amount_minor;
      const amount = format(abs, l.currency);
      const owe = tone === 'owe';
      return {
        key: l.currency,
        amountMinor: l.amount_minor,
        text: owe ? `you owe −${amount}` : `you are owed +${amount}`,
        label: owe ? `you owe ${amount}` : `you are owed ${amount}`,
      };
    });
}

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];
const pad2 = (n: number) => String(n).padStart(2, '0');
const localDay = (d: Date) =>
  `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/** "Today", "Yesterday" or "12 Nov 2026" for the device-local calendar day of an RFC 3339 instant. */
export function dayHeading(iso: string, now: Date): string {
  const d = new Date(iso);
  const key = localDay(d);
  if (key === localDay(now)) {
    return 'Today';
  }
  const yesterday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  );
  if (key === localDay(yesterday)) {
    return 'Yesterday';
  }
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Relative time for the row caption: "just now", "5 min ago", "3 h ago", otherwise the day heading. */
export function relativeTime(iso: string, now: Date): string {
  const diffMs = now.getTime() - new Date(iso).getTime();
  const minutes = (diffMs - (diffMs % 60000)) / 60000;
  if (minutes < 1) {
    return 'just now';
  }
  if (minutes < 60) {
    return `${minutes} min ago`;
  }
  const hours = (minutes - (minutes % 60)) / 60;
  if (hours < 24) {
    return `${hours} h ago`;
  }
  return dayHeading(iso, now);
}

export type ActivitySection = { title: string; data: ActivityItem[] };

/** Consecutive items with the same local day share a section; the server order is preserved as is. */
export function sectionsOf(
  items: ActivityItem[],
  now: Date,
): ActivitySection[] {
  const out: ActivitySection[] = [];
  for (const item of items) {
    const title = dayHeading(item.created_at, now);
    const last = out[out.length - 1];
    if (last && last.title === title) {
      last.data.push(item);
    } else {
      out.push({ title, data: [item] });
    }
  }
  return out;
}
