/* eslint-env jest */
// A small stateful stand-in for the Slice 2 backend, used by the screen-level (E2E-style) tests.
// It sits behind global.fetch, so the real generated client, auth layer and screens run unchanged.
import * as Keychain from 'react-native-keychain';

export type Req = {
  method: string;
  path: string;
  query: string;
  body?: any;
  headers: Headers;
};
export type Res = { status: number; body?: unknown };
export type Override = (req: Req, server: FakeServer) => Res | undefined;

export const ME = {
  id: 'u-me',
  email: 'asha@example.com',
  name: 'Asha',
  phone_e164: null,
  default_currency: 'INR',
  time_zone: 'Asia/Kolkata',
  avatar_url: null,
  is_registered: true,
  plan: 'free',
  premium_until: null,
  friend_code: 'K7Q2M9XP',
  notification_prefs: {
    expense_added: true,
    expense_updated: true,
    comment_added: true,
    added_to_group: true,
    removed_from_group: true,
    group_updated: true,
    friend_added: true,
    friend_removed: true,
    payment_recorded: true,
    reminder: true,
  },
  created_at: '2026-11-05T14:00:00Z',
};

const CURRENCIES = [
  { code: 'INR', name: 'Indian Rupee', symbol: 'Rs', exponent: 2 },
  { code: 'USD', name: 'US Dollar', symbol: '$', exponent: 2 },
  { code: 'JPY', name: 'Japanese Yen', symbol: 'Y', exponent: 0 },
];

type UserPub = {
  id: string;
  name: string;
  email: string | null;
  is_registered: boolean;
};
type FriendRow = {
  user: UserPub;
  balances: any[];
  breakdown: any[];
  settled_up_since: string | null;
};
type GroupRow = {
  id: string;
  name: string;
  group_type: string;
  simplify_debts: boolean;
  default_currency: string;
  version: number;
  created_at: string;
  members: {
    user: UserPub;
    joined_at: string;
    left_at: string | null;
    balances: any[];
  }[];
  deleted: boolean;
};

const CATEGORIES = [
  {
    id: 1,
    parent_id: null,
    slug: 'food',
    name: 'Food and drink',
    icon: 'fork',
    children: [
      {
        id: 2,
        parent_id: 1,
        slug: 'groceries',
        name: 'Groceries',
        icon: 'cart',
      },
      {
        id: 3,
        parent_id: 1,
        slug: 'dining',
        name: 'Dining out',
        icon: 'plate',
      },
    ],
  },
  {
    id: 4,
    parent_id: null,
    slug: 'transport',
    name: 'Transportation',
    icon: 'bus',
    children: [
      { id: 5, parent_id: 4, slug: 'taxi', name: 'Taxi', icon: 'car' },
    ],
  },
];

const notFound = (): Res => ({
  status: 404,
  body: { code: 'NOT_FOUND', message: 'Not Found' },
});

/** Stand-in for the server split computation (equal and exact only; enough for the screen tests). */
function fakeSplit(body: any): any[] {
  const total: number = body.total.amount_minor;
  const entries: any[] = body.split.entries;
  const n = entries.length;
  return entries.map((e, i) => ({
    user_id: e.user_id,
    owed_amount_minor:
      body.split.type === 'equal'
        ? (total - (total % n)) / n + (i < total % n ? 1 : 0)
        : e.value,
    input_value: body.split.type === 'equal' ? null : (e.value ?? null),
  }));
}

export class FakeServer {
  me: any = { ...ME };
  friends: FriendRow[] = [];
  groups: GroupRow[] = [];
  expenses: any[] = [];
  comments: Record<string, any[]> = {};
  /** When set, timeline and expense lists return this many items per page regardless of ?limit=. */
  pageSize: number | undefined;
  log: Req[] = [];
  overrides: Override[] = [];
  /** Access tokens the server accepts. */
  validAccess = new Set(['acc1']);
  refreshOk = true;
  vault: string | null = null;
  private seq = 0;

  count(method: string, path: RegExp | string): number {
    return this.log.filter(
      r =>
        r.method === method &&
        (typeof path === 'string' ? r.path === path : path.test(r.path)),
    ).length;
  }

  seedTokens() {
    this.vault = JSON.stringify({ accessToken: 'acc1', refreshToken: 'rt1' });
  }

  private pub(
    id: string,
    name: string,
    email: string | null,
    reg = true,
  ): UserPub {
    return { id, name, email, is_registered: reg };
  }
  private meMember(): GroupRow['members'][number] {
    return {
      user: this.pub(this.me.id, this.me.name, this.me.email),
      joined_at: '2026-11-10T00:00:00Z',
      left_at: null,
      balances: [],
    };
  }
  addFriendRow(
    id: string,
    name: string,
    balances: any[] = [],
    settledSince: string | null = null,
  ) {
    this.friends.push({
      user: this.pub(id, name, `${name.toLowerCase()}@example.com`),
      balances,
      breakdown: [],
      settled_up_since: settledSince,
    });
  }
  addGroup(name: string, others: UserPub[], id = `g-${++this.seq}`): GroupRow {
    const g: GroupRow = {
      id,
      name,
      group_type: 'other',
      simplify_debts: true,
      default_currency: 'INR',
      version: 1,
      created_at: '2026-11-10T00:00:00Z',
      members: [
        this.meMember(),
        ...others.map(u => ({
          user: u,
          joined_at: '2026-11-10T00:00:00Z',
          left_at: null,
          balances: [],
        })),
      ],
      deleted: false,
    };
    this.groups.push(g);
    return g;
  }
  user(id: string, name: string): UserPub {
    return this.pub(id, name, `${name.toLowerCase()}@example.com`);
  }

  private groupJson(g: GroupRow) {
    return { ...g, deleted: undefined, my_balances: [] };
  }

  addExpense(e: Partial<any> & { description: string }): any {
    const row = {
      id: `x-${++this.seq}`,
      group_id: null,
      total: { amount_minor: 10000, currency: 'INR' },
      category_id: 1,
      expense_date: '2026-11-10',
      notes: null,
      split_type: 'equal',
      payers: [{ user_id: this.me.id, paid_amount_minor: 10000 }],
      splits: [],
      comment_count: 0,
      created_by: this.me.id,
      updated_by: null,
      created_at: `2026-11-10T00:00:${String(this.seq).padStart(2, '0')}Z`,
      updated_at: '2026-11-10T00:00:00Z',
      deleted_at: null,
      deleted_by: null,
      version: 1,
      ...e,
    };
    this.expenses.push(row);
    return row;
  }

  private expenseJson(e: any) {
    const paid = e.payers
      .filter((p: any) => p.user_id === this.me.id)
      .reduce((a: number, p: any) => a + p.paid_amount_minor, 0);
    const owed = e.splits
      .filter((x: any) => x.user_id === this.me.id)
      .reduce((a: number, x: any) => a + x.owed_amount_minor, 0);
    return {
      ...e,
      my_net: { amount_minor: paid - owed, currency: e.total.currency },
    };
  }

  private page(items: any[], query: string) {
    const params = new URLSearchParams(query);
    const limit = this.pageSize ?? parseInt(params.get('limit') ?? '50', 10);
    const start = params.get('cursor')
      ? parseInt(params.get('cursor')!, 10)
      : 0;
    const slice = items.slice(start, start + limit);
    return {
      items: slice,
      next_cursor: start + limit < items.length ? String(start + limit) : null,
    };
  }

  private sorted(list: any[]) {
    return [...list].sort(
      (a, b) =>
        (a.expense_date < b.expense_date
          ? 1
          : a.expense_date > b.expense_date
            ? -1
            : 0) || (a.created_at < b.created_at ? 1 : -1),
    );
  }

  private handleExpenses(req: Req): Res | undefined {
    const { method, path } = req;
    const create = (groupId: string | null): Res => {
      const b = req.body;
      const e = this.addExpense({
        group_id: groupId,
        description: b.description,
        total: b.total,
        category_id: b.category_id ?? 1,
        expense_date: b.expense_date,
        notes: b.notes ?? null,
        split_type: b.split.type,
        payers: b.payers,
        splits: fakeSplit(b),
      });
      return { status: 201, body: this.expenseJson(e) };
    };
    let m = /^\/groups\/([^/]+)\/(expenses|timeline)$/.exec(path);
    if (m) {
      const g = this.groups.find(x => x.id === m![1]);
      if (!g || g.deleted) {
        return notFound();
      }
      if (m[2] === 'expenses' && method === 'POST') {
        return create(g.id);
      }
      if (m[2] === 'timeline' && method === 'GET') {
        const items = this.sorted(
          this.expenses.filter(e => e.group_id === g.id && !e.deleted_at),
        ).map(e => ({
          kind: 'expense',
          date: e.expense_date,
          expense: this.expenseJson(e),
        }));
        return { status: 200, body: this.page(items, req.query) };
      }
    }
    if (path === '/expenses' && method === 'POST') {
      return create(null);
    }
    if (path === '/expenses' && method === 'GET') {
      const friend = new URLSearchParams(req.query).get('friend_user_id');
      const items = this.sorted(
        this.expenses.filter(
          e =>
            !e.deleted_at &&
            (!friend ||
              e.splits.some((x: any) => x.user_id === friend) ||
              e.payers.some((x: any) => x.user_id === friend)),
        ),
      ).map(e => this.expenseJson(e));
      return { status: 200, body: this.page(items, req.query) };
    }
    if (path === '/categories') {
      return { status: 200, body: CATEGORIES };
    }
    m = /^\/expenses\/([^/]+)(?:\/(restore|comments))?$/.exec(path);
    if (m) {
      const e = this.expenses.find(x => x.id === m![1]);
      if (!e) {
        return notFound();
      }
      if (!m[2]) {
        if (method === 'GET') {
          return { status: 200, body: this.expenseJson(e) };
        }
        if (method === 'PATCH') {
          if (req.body.version !== e.version) {
            return {
              status: 409,
              body: { code: 'VERSION_CONFLICT', message: 'Stale version' },
            };
          }
          const b = req.body;
          Object.assign(e, {
            description: b.description ?? e.description,
            total: b.total ?? e.total,
            category_id: b.category_id ?? e.category_id,
            expense_date: b.expense_date ?? e.expense_date,
            notes: b.notes === undefined ? e.notes : b.notes,
            payers: b.payers ?? e.payers,
            updated_by: this.me.id,
            version: e.version + 1,
          });
          if (b.split) {
            e.split_type = b.split.type;
            e.splits = fakeSplit({ total: e.total, split: b.split });
          }
          return { status: 200, body: this.expenseJson(e) };
        }
        if (method === 'DELETE') {
          if (e.deleted_at) {
            return {
              status: 409,
              body: { code: 'ALREADY_DELETED', message: 'Already deleted' },
            };
          }
          e.deleted_at = '2026-11-10T09:00:00Z';
          e.deleted_by = this.me.id;
          return { status: 200, body: this.expenseJson(e) };
        }
      }
      if (m[2] === 'restore' && method === 'POST') {
        e.deleted_at = null;
        e.deleted_by = null;
        return { status: 200, body: this.expenseJson(e) };
      }
      if (m[2] === 'comments') {
        const list = (this.comments[e.id] ??= []);
        if (method === 'GET') {
          return { status: 200, body: this.page(list, req.query) };
        }
        if (method === 'POST') {
          const c = {
            id: `c-${++this.seq}`,
            kind: 'user',
            user: {
              id: this.me.id,
              name: this.me.name,
              email: this.me.email,
              is_registered: true,
            },
            body: req.body.body,
            created_at: '2026-11-10T10:00:00Z',
          };
          list.push(c);
          return { status: 201, body: c };
        }
      }
    }
    return undefined;
  }

  private handleFriend(req: Req): Res | undefined {
    const m = /^\/friends\/([^/]+)$/.exec(req.path);
    if (!m) {
      return undefined;
    }
    const f = this.friends.find(x => x.user.id === m[1]);
    if (req.method === 'GET') {
      return f ? { status: 200, body: f } : notFound();
    }
    if (req.method === 'DELETE') {
      const shared = this.groups.filter(
        g =>
          !g.deleted &&
          g.members.some(x => x.user.id === m[1] && !x.left_at) &&
          g.members.some(x => x.user.id === this.me.id && !x.left_at),
      );
      if (shared.length > 0) {
        return {
          status: 409,
          body: {
            code: 'SHARED_GROUPS_EXIST',
            message: 'Leave the shared groups first',
            details: { group_ids: shared.map(g => g.id) },
          },
        };
      }
      if (!f) {
        return notFound();
      }
      this.friends = this.friends.filter(x => x !== f);
      this.expenses
        .filter(e => !e.group_id)
        .forEach(e => {
          e.deleted_at = '2026-11-10T09:00:00Z';
        });
      return { status: 204 };
    }
    return undefined;
  }

  /** What the real server does when a shared group ends (OQ-37a): co-members become explicit friends. */
  private befriendCoMembers(g: GroupRow) {
    for (const m of g.members) {
      if (
        m.user.id !== this.me.id &&
        !m.left_at &&
        !this.friends.some(f => f.user.id === m.user.id)
      ) {
        this.friends.push({
          user: m.user,
          balances: [],
          breakdown: [],
          settled_up_since: null,
        });
      }
    }
  }

  handle(req: Req): Res {
    for (const o of this.overrides) {
      const r = o(req, this);
      if (r) {
        return r;
      }
    }
    const { method, path } = req;
    const auth = req.headers.get('Authorization');
    if (path === '/auth/refresh') {
      return this.refreshOk
        ? {
            status: 200,
            body: {
              access_token: 'acc1',
              refresh_token: 'rt2',
              token_type: 'bearer',
              expires_in: 900,
            },
          }
        : {
            status: 401,
            body: { code: 'TOKEN_INVALID', message: 'Invalid token' },
          };
    }
    if (path === '/auth/login' && method === 'POST') {
      return {
        status: 200,
        body: {
          access_token: 'acc1',
          refresh_token: 'rt1',
          token_type: 'bearer',
          expires_in: 900,
          user: this.me,
        },
      };
    }
    if (path === '/currencies') {
      return { status: 200, body: CURRENCIES };
    }
    if (!auth || !this.validAccess.has(auth.replace('Bearer ', ''))) {
      return {
        status: 401,
        body: { code: 'TOKEN_INVALID', message: 'Invalid token' },
      };
    }
    if (path === '/auth/logout') {
      return { status: 204 };
    }
    if (path === '/users/me') {
      if (method === 'PATCH') {
        this.me = { ...this.me, ...req.body };
      }
      return { status: 200, body: this.me };
    }
    const extra = this.handleExpenses(req) ?? this.handleFriend(req);
    if (extra) {
      return extra;
    }
    if (path === '/friends' && method === 'GET') {
      return { status: 200, body: { items: this.friends } };
    }
    if (path === '/friends' && method === 'POST') {
      const email: string | undefined = req.body.email;
      const name =
        req.body.name ?? (email ? email.split('@')[0] : req.body.phone_e164);
      const shown = name.charAt(0).toUpperCase() + name.slice(1);
      const existing = this.friends.find(f => f.user.email === email);
      if (existing) {
        return { status: 200, body: { friend: existing, is_new_user: false } };
      }
      const row: FriendRow = {
        user: this.pub(`u-${++this.seq}`, shown, email ?? null, false),
        balances: [],
        breakdown: [],
        settled_up_since: null,
      };
      this.friends.push(row);
      return { status: 201, body: { friend: row, is_new_user: true } };
    }
    if (path === '/groups' && method === 'GET') {
      const items = this.groups
        .filter(
          g =>
            !g.deleted &&
            g.members.some(m => m.user.id === this.me.id && !m.left_at),
        )
        .map(g => ({
          id: g.id,
          name: g.name,
          group_type: g.group_type,
          member_count: g.members.filter(m => !m.left_at).length,
          my_balances: [],
          settled_up_since: null,
        }));
      return { status: 200, body: { items, non_group_balances: [] } };
    }
    if (path === '/groups' && method === 'POST') {
      const b = req.body;
      const others: UserPub[] = [
        ...(b.member_user_ids ?? []).map(
          (id: string) => this.friends.find(f => f.user.id === id)!.user,
        ),
        ...(b.new_members ?? []).map((m: any) =>
          this.pub(`u-${++this.seq}`, m.name, m.email ?? null, false),
        ),
      ];
      const g = this.addGroup(b.name, others);
      g.group_type = b.group_type ?? 'other';
      g.simplify_debts = b.simplify_debts ?? true;
      return { status: 201, body: this.groupJson(g) };
    }
    const m = /^\/groups\/([^/]+)(?:\/(members)(?:\/([^/]+))?)?$/.exec(path);
    if (m) {
      const g = this.groups.find(x => x.id === m[1]);
      if (!g || g.deleted) {
        return {
          status: 404,
          body: { code: 'NOT_FOUND', message: 'Not Found' },
        };
      }
      const amMember = g.members.some(
        x => x.user.id === this.me.id && !x.left_at,
      );
      if (!amMember) {
        return {
          status: 403,
          body: { code: 'FORBIDDEN', message: 'Not a member' },
        };
      }
      if (!m[2]) {
        if (method === 'GET') {
          return { status: 200, body: this.groupJson(g) };
        }
        if (method === 'PATCH') {
          if (req.body.version !== g.version) {
            return {
              status: 409,
              body: { code: 'VERSION_CONFLICT', message: 'Stale version' },
            };
          }
          Object.assign(g, { ...req.body, version: g.version });
          g.version += 1;
          return { status: 200, body: this.groupJson(g) };
        }
        if (method === 'DELETE') {
          this.befriendCoMembers(g);
          g.deleted = true;
          return { status: 204 };
        }
      } else if (!m[3] && method === 'POST') {
        for (const id of req.body.user_ids ?? []) {
          g.members.push({
            user: this.friends.find(f => f.user.id === id)!.user,
            joined_at: 'x',
            left_at: null,
            balances: [],
          });
        }
        for (const nm of req.body.new_members ?? []) {
          g.members.push({
            user: this.pub(`u-${++this.seq}`, nm.name, nm.email ?? null, false),
            joined_at: 'x',
            left_at: null,
            balances: [],
          });
        }
        g.version += 1;
        return { status: 200, body: this.groupJson(g) };
      } else if (m[3] && method === 'DELETE') {
        this.befriendCoMembers(g);
        const target = g.members.find(x =>
          m[3] === 'me' ? x.user.id === this.me.id : x.user.id === m[3],
        );
        if (target) {
          target.left_at = '2026-11-10T01:00:00Z';
        }
        return { status: 204 };
      }
    }
    return { status: 404, body: { code: 'NOT_FOUND', message: 'Not Found' } };
  }

  install() {
    (global as any).fetch = jest.fn(async (url: string, init: RequestInit) => {
      const full = url.replace('http://10.0.2.2:8000', '');
      const [path, query = ''] = full.split('?');
      const req: Req = {
        method: (init.method ?? 'GET').toUpperCase(),
        path,
        query,
        body: init.body ? JSON.parse(init.body as string) : undefined,
        headers: new Headers(init.headers as Record<string, string>),
      };
      this.log.push(req);
      const res = this.handle(req);
      return {
        status: res.status,
        headers: new Headers(),
        text: async () =>
          res.body === undefined ? '' : JSON.stringify(res.body),
      };
    });
    (Keychain.setGenericPassword as jest.Mock).mockImplementation(
      async (_u, pw) => {
        this.vault = pw;
        return true;
      },
    );
    (Keychain.getGenericPassword as jest.Mock).mockImplementation(async () =>
      this.vault ? { username: 'session', password: this.vault } : false,
    );
    (Keychain.resetGenericPassword as jest.Mock).mockImplementation(
      async () => {
        this.vault = null;
        return true;
      },
    );
  }
}
