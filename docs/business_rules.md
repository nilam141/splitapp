# Business Rules

> REA: describe the logic in plain language AND pseudocode, with worked numeric examples.
> These examples become the QA agent's tests, so be precise. Verify against the real app by hand.

**Status of these rules.** The reference APK shows *which* rules exist: the split types, the validation messages ("over/under by X", "X% left", "at least 1 share", "adjustments cannot exceed the total"), the simplify-debts description and example, "one person cannot pay multiple shares", the max amount, and leave/remove blocked by debts. These were observed (static). The **exact arithmetic** (remainder order, rounding, the simplification algorithm) could **not** be recovered: the app wasn't run and no code was decompiled. So every algorithm below is **our own decision**, chosen to be deterministic and testable. Where the reference app may differ, an OQ number says so. Every expected number in the test vectors was computed by a reference implementation, not by hand.

## 1. Money representation
- Integer minor units. Currency has its own exponent (INR/USD = 2, JPY = 0).
- KWD/BHD/OMR have exponent 3. Supported in the data model; shown to 3 decimals.
- The API never accepts or returns decimal money, only `amount_minor` (integer) + `currency`.
- Formatting for display = `amount_minor / 10^exponent` with exactly `exponent` decimals, done in the client with integer maths (string padding), never with float division.
- Limits: `1 ≤ amount_minor ≤ 9,999,999,999` for any single expense or settlement (that is 99,999,999.99 in a 2-decimal currency; matches the maximum observed (static)). In a 0-decimal currency the same integer cap applies.
- All intermediate products (`T × weight`) fit in a signed 64-bit integer: 9,999,999,999 × 10,000 (basis points) ≈ 1e14 < 9.2e18. Python ints are unbounded anyway. The TypeScript client must use integer-safe maths: values stay < 2^53 ≈ 9.0e15, so `number` is safe for the products used here; property tests assert this.

**Canonical order.** Wherever leftover units are handed out, participants are ordered by:
1. Group expense: `group_members.sort_index` (join order) ascending.
2. Non-group expense: the expense creator first, then the others by ascending `user_id` (uuid string compare).

The server computes the order; client order is ignored. The client mirrors the same rule only for previews. (Reference order unknown: OQ-01.)

## 2. Split types
For each type: inputs, validation, algorithm, rounding rule, worked example.

All types produce `owed[u]` for each participant with `Σ owed = T` exactly. The participant set `P` must have ≥ 1 member. Every participant must be a current group member (group expense) or the creator or a friend (non-group).

### 2.1 Equal
- **Inputs:** `T`, a participant set `P` (n ≥ 1).
- **Validation:** n ≥ 1, otherwise `422 SPLIT_NO_PARTICIPANTS` ("select at least 1 person").
- **Rule:** `base = T div n`, `r = T mod n`. The first `r` participants in canonical order get `base + 1`; the rest get `base`.
- **Example:** 10000 paise among 3 -> 3334, 3333, 3333, sum = 10000

```
def split_equal(T, P_canonical):
    base, r = divmod(T, len(P_canonical))
    return {u: base + (1 if i < r else 0) for i, u in enumerate(P_canonical)}
```

### 2.2 Exact amounts
- **Inputs:** `amount[u] ≥ 0` for each participant (integer minor units).
- **Validation:** sum of entries must equal total, otherwise reject with `422 SPLIT_SUM_MISMATCH` and `details: {expected: T, actual: S, difference: S − T}`. The UI shows "over by X" if `S > T` and "under by X" if `S < T`. At least one entry must be > 0.
- **Rounding:** none (inputs are already integers).
- **Example:** T = 10000, entries 5000 / 3000 / 2000 → accepted. 5000 / 3000 / 1000 → rejected, difference −1000 ("under by 10.00").

### 2.3 Percentages
- **Inputs:** `bp[u]` = percentage in **basis points** (integer 0–10000; 33.33% → 3333). The UI accepts at most 2 decimals (OQ-02).
- **Validation:** percentages must sum to 100, i.e. `Σ bp = 10000`, otherwise `422 SPLIT_PERCENT_MISMATCH` with `difference_bp = Σbp − 10000`. The UI shows "X% over" / "X% left".
- **Rounding:** largest remainder (Hamilton). `raw[u] = T × bp[u] / 10000`. Each participant first gets `floor(raw)`. The leftover `R = T − Σ floor` units (0 ≤ R < n) go one each to the participants with the largest fractional part `(T × bp[u]) mod 10000`. Ties are broken by canonical order.
- **Example:** T = 1000 with 3333 / 3333 / 3334 bp → raw 333.3 / 333.3 / 333.4 → floors 333 / 333 / 333 (sum 999) → 1 unit to the largest fraction (0.4, the third person) → **333, 333, 334**.

```
def split_weighted(T, weights_canonical):          # used by percent and shares
    W = sum(w for _, w in weights_canonical)
    floors, fracs = {}, []
    for i, (u, w) in enumerate(weights_canonical):
        floors[u] = (T * w) // W
        fracs.append(((T * w) % W, i, u))
    R = T - sum(floors.values())
    for _, _, u in sorted(fracs, key=lambda f: (-f[0], f[1]))[:R]:
        floors[u] += 1
    return floors
```

### 2.4 Shares
- **Inputs:** `shares[u]`, an integer 0–999 (OQ-03: fractional shares in the reference app?).
- **Validation:** `Σ shares ≥ 1`, otherwise `422 SPLIT_NO_SHARES` ("assign at least 1 share"). Negative → 422.
- **Algorithm:** `split_weighted(T, shares)`, the same largest-remainder rule as percentages.
- **Example:** T = 10000 with shares 2 / 1 → raw 6666.67 / 3333.33 → floors 6666 / 3333 → 1 leftover to the larger fraction → **6667, 3333**.
- A participant with 0 shares owes 0 but stays "involved" (a split row with 0).

### 2.5 Adjustment
- **Inputs:** `adj[u] ≥ 0` minor units for each participant (the extra amount that person owes). Negative adjustments are **not** allowed in our MVP (OQ-04).
- **Validation:** `Σ adj ≤ T`, otherwise `422 SPLIT_ADJUSTMENT_EXCEEDS_TOTAL` with `difference = Σadj − T` ("over by X").
- **Algorithm:** `rest = T − Σ adj`. `eq = split_equal(rest, P)` over **all** participants. `owed[u] = adj[u] + eq[u]`.
- **Example:** T = 10000, 3 people, adj A = 1000 → rest 9000 → 3000 each → **A 4000, B 3000, C 3000**.

```
def split_adjustment(T, adj_canonical):
    A = sum(adj_canonical.values())
    if A > T: raise SplitAdjustmentExceedsTotal(A - T)
    eq = split_equal(T - A, list(adj_canonical))
    return {u: adj_canonical[u] + eq[u] for u in adj_canonical}
```

### 2.6 Two-person shortcuts (UI only)
These four choices compile to the types above. Nothing new is stored.
| Choice | payers | split |
|---|---|---|
| You paid, split equally | you: T | equal over {you, them} |
| They paid, split equally | them: T | equal over {you, them} |
| You are owed the full amount | you: T | exact {you: 0, them: T} |
| They are owed the full amount | them: T | exact {you: T, them: 0} |

## 3. Multiple payers
- `payers` is a list of `{user_id, paid_amount_minor > 0}`. A `user_id` appears at most once, otherwise `422 DUPLICATE_PAYER`. Observed (static): "one person cannot pay multiple shares".
- `Σ paid = T`, otherwise `422 PAYER_SUM_MISMATCH` with a difference (UI: "over/under by X").
- A payer doesn't need to be a split participant. They then have `owed = 0` and no split row.
- How paid and owed combine: for each user on an expense, `net = paid − owed`. Positive = the others owe this person; negative = this person owes.
- Example: T 9000; A paid 6000, B paid 3000; equal over A, B, C (3000 each) → nets A +3000, B 0, C −3000.

## 4. Net balance computation
```
# Per scope (a group, or the non-group pair space) and per currency.
def net_balances(scope, currency):
    bal = defaultdict(int)
    for e in expenses(scope, currency, deleted_at=None):
        for p in e.payers: bal[p.user_id] += p.paid_amount_minor
        for s in e.splits: bal[s.user_id] -= s.owed_amount_minor
    for st in settlements(scope, currency, deleted_at=None):
        bal[st.from_user_id] += st.amount_minor      # paying reduces what you owe
        bal[st.to_user_id]   -= st.amount_minor      # receiving reduces what you're owed
    return bal
```
- **Invariant:** the sum of all net balances in a group = 0, per currency. Property test: for 1000 random groups (2–12 members, 1–50 expenses of random types and currencies, random settlements), Σ = 0 for every currency.
- **Overall balance (Friends/Groups tab header):** for each currency, `you_are_owed = Σ max(0, b)` and `you_owe = Σ max(0, −b)` over the user's pairwise balances with each friend (§4.2). These are never summed across currencies.

### 4.2 Pairwise debts (who owes whom)
Used when simplify is **off**, and for friend-level balances.
- For each expense: let creditors `C` = users with net > 0 and debtors `D` = users with net < 0. Each debtor `d` owes `|net_d|`. That debt is spread over the creditors in proportion to their credit with `split_weighted(|net_d|, [(c, net_c) for c in C])`, in canonical order. Each piece is an edge `d → c`.
- For each settlement `X → Y` with amount `a`: add the edge `Y → X` of `a` (it cancels X's debt to Y; an overpayment makes Y owe X).
- Sum the edges per ordered pair, then net each unordered pair: `owe(i→j) = max(0, E[i→j] − E[j→i])`.
- Single-payer expenses reduce to the obvious rule: every split participant owes the payer their owed amount.
- **Example:** T 10000; A paid 7000, B paid 3000; equal among A, B, C, D (2500 each). Nets A +4500, B +500, C −2500, D −2500. C's 2500 spread 4500:500 → C→A 2250, C→B 250. Same for D → D→A 2250, D→B 250.

### 4.3 Friend balance
`friend_balance(me, f, currency)` = `Σ over shared groups g` of the amount on the suggested-payment edge between me and f in g (simplified edges if `g.simplify_debts`, pairwise edges otherwise) **+** the pairwise non-group balance between me and f. Positive = f owes me. (**decision**; OQ-28 for how the reference app attributes simplified group debts to friends.)

## 5. Debt simplification
- **Plain language:** within one group and one currency, ignore who owes whom on each expense. Look only at each member's net balance. Then repeatedly match the member who is owed the most with the member who owes the most; the debtor pays the smaller of the two amounts. Repeat until everyone is at zero. This uses at most N−1 payments for N non-zero members. Nobody pays or receives more in total than their net balance says, so no one ends up worse off. A member may be told to pay someone they never shared an expense with (this is what the reference app's explanation describes, observed (static)).

```
def simplify(nets, canonical):                         # nets: {user: int}, Σ = 0
    b = dict(nets); transfers = []
    while any(v > 0 for v in b.values()):
        c = max((u for u in canonical if b[u] > 0), key=lambda u: (b[u], -canonical.index(u)))
        d = max((u for u in canonical if b[u] < 0), key=lambda u: (-b[u], -canonical.index(u)))
        x = min(b[c], -b[d])
        transfers.append((d, c, x))                    # d pays c x
        b[c] -= x; b[d] += x
    return transfers                                   # order = output order shown to users
```
- Ties on amount: the earlier member in canonical order wins.
- The greedy method is not guaranteed to give the absolute minimum number of payments (that problem is NP-hard). It does guarantee ≤ N−1. The reference app's exact algorithm is unknown (OQ-14).
- **Example:** A owes B 10, B owes C 10 -> A pays C 10 (1 transaction instead of 2). In minor units: nets A −1000, B 0, C +1000 → [A→C 1000].
- **When the toggle is off:** show the pairwise edges from §4.2 (A→B 1000, B→C 1000). Toggling changes only how payments are *presented and suggested*. It never changes stored expenses, settlements or net balances. A settlement recorded under either mode is just a settlement; nets are recomputed from scratch.
- Simplification is computed per currency, never across currencies.

## 6. Settlements
- **Full settle:** the UI pre-fills `amount = |suggested edge|` in its currency. After saving, that edge becomes 0 and, when it was the only one, both members' nets are 0.
- **Partial settle:** any `1 ≤ amount < edge` is allowed. The remainder stays owed (5000 owed, 2000 paid → 3000 owed).
- **Overpayment:** `amount > edge` is allowed after a client-side confirmation. The direction flips (3000 owed, 5000 paid → the receiver now owes 2000). The API doesn't block it (OQ-15).
- **Who can record:** either party, or any group member for a group settlement (**decision**, OQ-13).
- **Currency:** a settlement has its own currency and only affects that currency's balances. Paying USD against an INR debt leaves the INR debt and creates a USD balance.
- **Settling across groups vs. overall friend balance:** "settle all with friend f" creates one settlement per (scope, currency) with a non-zero edge between the two, all sharing a `batch_id`, each for the exact edge amount. It does not create a single cross-group payment. The friend total becomes 0 in each currency.
- **Edit/delete/restore:** soft delete; balances are recomputed; restore re-applies the settlement.

## 7. Multi-currency
- **Conversion timing:** none by default. Each expense and settlement stays in its own currency forever. Balances are computed and shown **per currency** (e.g. "owes you ₹500.00 and $10.00").
- **Optional conversion (Later, premium in the reference app):** a user-triggered, irreversible "convert all of this group (or this friend's non-group items) to currency Q" at the rate on the day of the action. For each expense or settlement in a currency B ≠ Q:
  - `new_total = round_half_up(old_total × rate(B→Q) × 10^(exp_Q − exp_B))`, done in `Decimal`.
  - Payer and split amounts are re-allocated over `new_total` with `split_weighted`, using the old amounts as weights. Sums stay exact.
  - The original amount, currency and rate go into `fx_*` columns; activity `group.currency_converted` is written.
- **Rate source and rounding:** one provider, daily rates stored in `exchange_rates` (OQ-17). Rounding is ROUND_HALF_UP to the target's minor unit, applied once per total (never per split).
- **Balances displayed per currency or converted:** per currency. No "approximate total in default currency" in MVP (OQ-29).

## 8. Edge cases
- **Deleted or removed user with a non-zero balance:** a member can't leave or be removed while their group balance ≠ 0 in any currency → `409 OUTSTANDING_BALANCE` (observed (static)). A deleted *account* keeps its rows. The name becomes "Deleted user" and balances stay visible to the others, who can still record settlements against it (OQ-D5).
- **Departed member on an old expense:** the expense can't be edited (`409 EXPENSE_HAS_DEPARTED_MEMBER`, observed (static)) but can be deleted or restored.
- **Editing/deleting an expense after a settlement:** allowed. Settlements are never modified automatically. Nets are recomputed, so the pair may become unsettled again (an edit from 9000 to 12000 re-opens 1000 per participant). The activity feed shows the change.
- **Payer not in the split:** allowed. The payer has `owed = 0` and no split row; their net = paid.
- **Zero or negative amounts:** `T ≤ 0` → `422 AMOUNT_OUT_OF_RANGE`. Negative per-person inputs (exact, shares, adjustment, percentage) → 422. An exact split may give some people 0, but at least one must be > 0. Refunds are modelled as an expense whose payer is the person receiving the refund (no negative expenses).
- **Recurring expense when a member has left:** the next occurrence drops departed members. Equal splits run over the remaining participants. Percent and shares splits re-normalise the remaining weights (e.g. 50/30/20 with the 20% member gone → weights 50:30 → 62.5/37.5). An exact split that no longer sums gets converted to shares using the old amounts as weights. Adjustment keeps the remaining adjustments, and if their total now exceeds T, it falls back to equal. If no participant remains, the rule deactivates. (**decision**, OQ-16)
- **Expense with only the creator involved** (group expense, A pays, split only A): allowed but pointless; the net is 0. The UI warns.
- **Non-group expense not involving the creator** → `422 CURRENT_USER_NOT_INVOLVED` (observed (static)).
- **More than one group on an expense** → rejected (observed (static)).
- **Same user twice in splits** → `422 DUPLICATE_PARTICIPANT`.
- **Concurrent edits** → optimistic locking on `version` → `409 VERSION_CONFLICT`.
- **Placeholder merge:** when a placeholder is claimed, every row referencing the placeholder id is re-pointed to the real user in one transaction. If both appear on the same expense, their payer and split rows are summed into one row.

## 9. Free vs premium limits
Observed (static) as premium-only in the reference app: currency conversion, charts, search, receipt image upload, receipt scanning/itemization, export, group totals, settle-up reminders, balance alerts. A server-driven upsell with a countdown button is attached to add-expense (a daily free-tier cap is likely, but its numbers aren't in the APK: OQ-19).

**Proposal for our app (owner decision OQ-D1):**
| Capability | Free | Premium |
|---|---|---|
| Groups, friends, expenses, all 5 split types, multiple payers, settle up, simplify debts, activity, comments, multi-currency (no conversion), recurring | unlimited | unlimited |
| Receipt image on expense | 0 | 1 per expense |
| Search | – | yes |
| Export CSV | – | yes |
| Group totals and charts | – | yes |
| Currency conversion | – | yes |
| Scheduled settle-up reminders, balance alerts | – | yes |
| Daily add-expense cap | none (recommended) | none |

**When a limit is hit:** the API returns `402 PREMIUM_REQUIRED` with `{feature: "<key>"}`. The client opens SCR-39 and does not retry. Gating is enforced server-side; the client gate is cosmetic.

## Test vectors (REA: provide at least 15)
Participants are listed in canonical order. "→" means "pays". Amounts are minor units.

| # | Scenario | Input | Expected output |
|---|---|---|---|
| 1 | Equal split, remainder | 10000 / 3 | 3334, 3333, 3333 |
| 2 | Equal, small remainder | 100 / 3 | 34, 33, 33 |
| 3 | Equal, odd over 2 | 10001 / 2 | 5001, 5000 |
| 4 | Equal, JPY (exp 0) | 1000 JPY / 3 | 334, 333, 333 |
| 5 | Payer not in split | T 9000, A paid 9000, equal over B, C | splits B 4500, C 4500; nets A +9000, B −4500, C −4500 |
| 6 | Exact, valid | T 10000; 5000, 3000, 2000 | accepted; owed 5000, 3000, 2000 |
| 7 | Exact, under | T 10000; 5000, 3000, 1000 | 422 SPLIT_SUM_MISMATCH, difference −1000 |
| 8 | Percent, exact divide | T 10000; 3333, 3333, 3334 bp | 3333, 3333, 3334 |
| 9 | Percent, remainder | T 1000; 3333, 3333, 3334 bp | 333, 333, 334 |
| 10 | Percent, not 100 | 5000, 4900 bp | 422 SPLIT_PERCENT_MISMATCH, difference_bp −100 |
| 11 | Shares | T 10000; 1, 2, 2 | 2000, 4000, 4000 |
| 12 | Shares, all equal, remainder | T 1000; 1, 1, 1 | 334, 333, 333 |
| 13 | Shares, fractional remainder | T 10000; 2, 1 | 6667, 3333 |
| 13b | Shares, 7-way tie | T 100; seven people with 1 share each | 15, 15, 14, 14, 14, 14, 14 |
| 14 | Adjustment | T 10000; adj 1000, 0, 0 | 4000, 3000, 3000 |
| 15 | Adjustment exceeds | T 10000; adj 6000, 5000, 0 | 422 SPLIT_ADJUSTMENT_EXCEEDS_TOTAL, difference 1000 |
| 16 | Adjustment, remainder | T 10001; adj 1000, 0, 0 | 4001, 3000, 3000 |
| 17 | Multiple payers | T 9000; A 6000, B 3000; equal A, B, C | nets A +3000, B 0, C −3000 |
| 18 | Payers mismatch | T 9000; A 6000, B 2000 | 422 PAYER_SUM_MISMATCH, difference −1000 |
| 19 | Simplify chain | A owes B 1000, B owes C 1000 (nets A −1000, B 0, C +1000) | [A→C 1000] |
| 20 | Simplify, 4 people | nets A −3000, B −1000, C +2500, D +1500 | [A→C 2500, B→D 1000, A→D 500] |
| 21 | Simplify off (same data as 19) | pairwise edges | [A→B 1000, B→C 1000] |
| 22 | Simplify, 2 creditors | nets A +4500, B +500, C −2500, D −2500 | [C→A 2500, D→A 2000, D→B 500] |
| 23 | Pairwise, multiple payers | T 10000; A paid 7000, B 3000; equal A, B, C, D | C→A 2250, C→B 250, D→A 2250, D→B 250 |
| 24 | Pairwise, uneven credit | nets A +3334, B +3333, C −3333, D −3334 | C→A 1667, C→B 1666, D→A 1667, D→B 1667 |
| 25 | Partial settlement | B owes A 5000; B pays A 2000 | B owes A 3000 |
| 26 | Full settlement | B owes A 3000; B pays A 3000 | balance 0 |
| 27 | Overpayment | B owes A 3000; B pays A 5000 | A owes B 2000 |
| 28 | Multi-currency kept apart | B owes A 1000 INR; then a 1000-cent USD expense, A paid, equal A, B | B owes A 1000 INR and 500 USD (two balances, no total) |
| 29 | Conversion rounding | 1000 USD cents @ 83.2156 INR/USD | 83216 INR paise (83215.6 → half-up) |
| 30 | Conversion re-allocates splits | T 10000 USD cents split 3334/3333/3333, rate 83.2156 → INR | total 832156; splits 277441, 277358, 277357 |
| 31 | Conversion to 0-exponent currency | 12345 USD cents @ 149.875 JPY/USD | 18502 JPY |
| 32 | Edit after settle | E 9000 equal A, B, C (A paid); C settles 3000; E edited to 12000 | C owes A 1000 again |
| 33 | Delete restores state | E deleted, then restored | balances identical to before the delete (snapshot compare) |
| 34 | Amount bounds | T = 0; T = 9,999,999,999; T = 10,000,000,000 | 422; accepted; 422 |
| 35 | Leave with debt | member net −1 in INR | 409 OUTSTANDING_BALANCE |
| 36 | Recurring month-end clamp | monthly from 2026-01-31 | 2026-01-31, 2026-02-28, 2026-03-31, 2026-04-30 |
| 37 | Recurring leap year | yearly from 2028-02-29 | 2028-02-29, 2029-02-28, 2030-02-28, 2031-02-28, 2032-02-29 |
| 38 | Recurring after member left | Rent 3,000,000 equal A, B, C; B leaves | next occurrence: A 1,500,000, C 1,500,000 |
| 39 | Property: sums | random T in [1, 9,999,999,999], random type, 1–50 participants | Σ owed = T; every owed ≥ 0 |
| 40 | Property: zero-sum | random group history | Σ nets = 0 per currency; applying simplify() output → all nets 0; transfers ≤ N−1 |

Notes for QA:
- Yearly recurrence anchors on the anchor date: Feb 29 falls back to Feb 28 in non-leap years and returns to Feb 29 in the next leap year (vector 37).
- Vectors 19–24 compare **ordered** lists. Order is part of the contract, so the UI is stable.
