"""Net balances, pairwise debts and debt simplification (business_rules 4, 4.2, 5). Pure functions: no database,
no I/O, no floats. All amounts are integer minor units; users are opaque hashable ids.

Records are plain dicts of LIVE (non-deleted) rows only:
    expense    = {"currency": "INR", "payers": [(user, paid_minor)], "splits": [(user, owed_minor)]}
    settlement = {"currency": "INR", "from_user_id": user, "to_user_id": user, "amount_minor": 3000}
`canonical` is the member order (group_members.sort_index). It decides tie-breaks and the order of every returned
list. Users missing from it are placed after it in order of first appearance.
"""
from collections import defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any

Transfer = tuple[Hashable, Hashable, int]


def net_balances(expenses: Iterable[Mapping[str, Any]],
                 settlements: Iterable[Mapping[str, Any]] = ()) -> dict[str, dict[Hashable, int]]:
    """{currency: {user: net}}; positive = is owed. Sum per currency is 0 (business_rules 4)."""
    out: dict[str, dict[Hashable, int]] = {}
    for e in expenses:
        bal = out.setdefault(e["currency"], defaultdict(int))
        for user, paid in e["payers"]:
            bal[user] += paid
        for user, owed in e["splits"]:
            bal[user] -= owed
    for s in settlements:
        bal = out.setdefault(s["currency"], defaultdict(int))
        bal[s["from_user_id"]] += s["amount_minor"]
        bal[s["to_user_id"]] -= s["amount_minor"]
    return {cur: dict(bal) for cur, bal in out.items()}


def _order(canonical: Sequence[Hashable]) -> dict[Hashable, int]:
    return {u: i for i, u in enumerate(canonical)}


def _index(order: dict[Hashable, int], user: Hashable) -> int:
    if user not in order:
        order[user] = len(order)
    return order[user]


def _controlled_rounding(debtors: list[tuple[Hashable, int]],
                         creditors: list[tuple[Hashable, int]]) -> list[Transfer]:
    """business_rules 4.2 steps 1-4. `debtors`/`creditors` are (user, positive amount) in canonical order.
    Integer-only; returns [(debtor, creditor, amount >= 1)] in debtor, creditor canonical order."""
    if not debtors or not creditors:
        return []
    s_total = sum(a for _, a in debtors)
    floors: dict[tuple[int, int], int] = {}
    cands: list[tuple[int, int, int]] = []  # (r, di, ci)
    row = [0] * len(debtors)
    col = [0] * len(creditors)
    for di, (_, dn) in enumerate(debtors):
        for ci, (_, cn) in enumerate(creditors):
            f, r = divmod(dn * cn, s_total)
            floors[(di, ci)] = f
            row[di] += f
            col[ci] += f
            if r > 0:
                cands.append((r, di, ci))
    rd = [dn - row[i] for i, (_, dn) in enumerate(debtors)]
    kc = [cn - col[i] for i, (_, cn) in enumerate(creditors)]
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))
    accepted: set[tuple[int, int]] = set()

    def feasible(rem_r: list[int], rem_k: list[int], cells: list[tuple[int, int, int]]) -> bool:
        """Can rem_r/rem_k be met by choosing each cell at most once? (bipartite max-flow, unit cell capacities)"""
        need = sum(rem_r)
        if need != sum(rem_k):
            return False
        if need == 0:
            return True
        nd, nk = len(rem_r), len(rem_k)
        src, snk = nd + nk, nd + nk + 1
        cap: dict[tuple[int, int], int] = {}
        nbr: dict[int, set[int]] = {}

        def edge(u: int, v: int, c: int) -> None:
            cap[(u, v)] = cap.get((u, v), 0) + c
            cap.setdefault((v, u), 0)
            nbr.setdefault(u, set()).add(v)
            nbr.setdefault(v, set()).add(u)

        for d in range(nd):
            edge(src, d, rem_r[d])
        for k in range(nk):
            edge(nd + k, snk, rem_k[k])
        for _, di, ci in cells:
            edge(di, nd + ci, 1)
        flow = 0
        while True:  # Ford-Fulkerson, BFS augmenting paths (unit-ish, tiny graphs)
            prev: dict[int, int] = {src: src}
            queue = [src]
            for u in queue:
                for v in sorted(nbr.get(u, ())):
                    if v not in prev and cap[(u, v)] > 0:
                        prev[v] = u
                        queue.append(v)
            if snk not in prev:
                break
            v = snk
            while v != src:
                cap[(prev[v], v)] -= 1
                cap[(v, prev[v])] += 1
                v = prev[v]
            flow += 1
        return flow == need

    for idx, (_, di, ci) in enumerate(cands):
        if sum(rd) == 0:
            break
        if rd[di] > 0 and kc[ci] > 0:
            rd[di] -= 1
            kc[ci] -= 1
            if feasible(rd, kc, cands[idx + 1:]):
                accepted.add((di, ci))
            else:
                rd[di] += 1
                kc[ci] += 1
    out: list[Transfer] = []
    for di, (d, _) in enumerate(debtors):
        for ci, (c, _) in enumerate(creditors):
            x = floors[(di, ci)] + ((di, ci) in accepted)
            if x > 0:
                out.append((d, c, x))
    return out


def pairwise_edges(expenses: Iterable[Mapping[str, Any]], settlements: Iterable[Mapping[str, Any]] = (),
                   canonical: Sequence[Hashable] = ()) -> dict[str, list[Transfer]]:
    """{currency: [(debtor, creditor, amount), ...]} per business_rules 4.2, implemented literally.

    Per expense each debtor's debt is spread over the creditors with split_weighted in canonical order; a settlement
    X -> Y adds the edge Y -> X; edges are summed per ordered pair and each unordered pair is netted. Order: debtor
    in canonical order, then creditor in canonical order. Only amounts >= 1 are listed."""
    order = _order(canonical)
    totals: dict[str, dict[tuple[Hashable, Hashable], int]] = {}

    def add(currency: str, frm: Hashable, to: Hashable, amount: int) -> None:
        edges = totals.setdefault(currency, {})
        edges[(frm, to)] = edges.get((frm, to), 0) + amount

    for e in expenses:
        net: dict[Hashable, int] = {}
        for user, paid in e["payers"]:
            net[user] = net.get(user, 0) + paid
        for user, owed in e["splits"]:
            net[user] = net.get(user, 0) - owed
        ranked = sorted(net, key=lambda u: _index(order, u))
        totals.setdefault(e["currency"], {})
        for d, c, amount in _controlled_rounding([(u, -net[u]) for u in ranked if net[u] < 0],
                                                 [(u, net[u]) for u in ranked if net[u] > 0]):
            add(e["currency"], d, c, amount)
    for s in settlements:
        add(s["currency"], s["to_user_id"], s["from_user_id"], s["amount_minor"])

    result: dict[str, list[Transfer]] = {}
    for currency, edges in totals.items():
        rows: list[Transfer] = []
        for (i, j), amount in edges.items():
            owe = amount - edges.get((j, i), 0)
            if owe > 0:
                rows.append((i, j, owe))
        rows.sort(key=lambda t: (_index(order, t[0]), _index(order, t[1])))
        result[currency] = rows
    return result


def simplify(nets: Mapping[Hashable, int], canonical: Sequence[Hashable]) -> list[Transfer]:
    """Greedy simplification of ONE currency (business_rules 5): the member owed most is matched with the member who
    owes most, the debtor pays the smaller amount; ties go to the earlier canonical member. At most N-1 transfers.
    Does not modify `nets`."""
    order = _order(canonical)
    users = list(canonical) + [u for u in nets if u not in order]
    for u in users:
        _index(order, u)
    b = {u: nets.get(u, 0) for u in users}
    transfers: list[Transfer] = []
    while True:
        creditors = [u for u in users if b[u] > 0]
        debtors = [u for u in users if b[u] < 0]
        if not creditors or not debtors:
            return transfers
        c = max(creditors, key=lambda u: (b[u], -order[u]))
        d = max(debtors, key=lambda u: (-b[u], -order[u]))
        x = min(b[c], -b[d])
        transfers.append((d, c, x))
        b[c] -= x
        b[d] += x


def suggested_transfers(expenses: Sequence[Mapping[str, Any]], settlements: Sequence[Mapping[str, Any]],
                        canonical: Sequence[Hashable], simplified: bool) -> dict[str, list[Transfer]]:
    """Per currency, the suggested payments of a group: simplify() when `simplified`, else pairwise_edges()."""
    if not simplified:
        return {c: t for c, t in pairwise_edges(expenses, settlements, canonical).items() if t}
    return {c: t for c, nets in net_balances(expenses, settlements).items()
            if (t := simplify(nets, canonical))}
