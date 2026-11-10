# User Flows

> REA: step-by-step flows as observed. Include the failure paths too.

**Important:** none of these flows was run in the reference app (no emulator or adb was available; see `open_questions.md` §"Manual test script"). Every flow below is **specified for our app**. It is assembled from the screens, validation messages and constraints found statically in the APK. Steps that depend on runtime behaviour I couldn't see are tagged **(inferred, OQ-xx)**. Numbers follow `business_rules.md`.

Shared test fixture (used by every flow unless stated):
- Users: **A** (Asha, the actor, default INR), **B** (Ravi), **C** (Meera), all registered and friends with each other.
- Group **G** "Flat 4B", type home, members A, B, C, `simplify_debts=true`, default currency INR.

## FLOW-01: Sign up and log in
- **Actor:** new user Asha
- **Preconditions:** app freshly installed, no account for `asha@example.com`
- **Related features / screens:** F-01, F-03, F-04, F-05 / SCR-01 to SCR-04, SCR-06, SCR-07, SCR-44

**Happy path**
1. Open the app → SCR-01 finds no token → SCR-02.
2. Tap Sign up → SCR-03. Enter "Asha", `asha@example.com`, `abcd1234`; INR is the default currency.
3. Tap Sign up → `POST /auth/register` → 201 with `access_token`, `refresh_token` and `user`.
4. The app stores the tokens in secure storage → SCR-07 Friends tab: 0 friends, summary "settled up".
5. Kill and relaunch → SCR-01 → `POST /auth/refresh` → 200 → SCR-07 with no prompt.
6. Account tab → Log out → confirm → `POST /auth/logout` → 204 → tokens erased → SCR-02.
7. Log in with the same credentials → `POST /auth/login` → 200 → SCR-07.

**Alternate / error paths**
- Password `abc1234` (7 chars) → inline error, no request.
- Email already registered → 409 → "email already registered" under the email field; the user stays on SCR-03.
- Wrong password → 401 `INVALID_CREDENTIALS` → combined error; the counter goes up. After 5 failures for the email within 15 min the 6th attempt → 429 `RATE_LIMITED` with `retry_after_seconds` (OQ-38, business_rules §11.2).
- Offline when tapping Log in → "can't reach server", no retry loop.
- Forgot password: `POST /auth/password-reset` → always 202 → email → link → SCR-06 → new password `newpass99` → `POST /auth/password-reset/confirm` → 200 + tokens; all other refresh tokens are revoked. A link used twice → 410.
- Refresh token revoked on another device → the next 401 triggers 1 refresh → 401 → SCR-44 → SCR-04 with the email prefilled. A token revoked by logout answers 401 without revoking the user's other tokens; only a token revoked by rotation triggers revoke-all (business_rules §11.1).

**Postconditions:** 1 `users` row (`is_registered=true`); 1 active `refresh_tokens` row per logged-in device. No activity entry is written (the contract's activity actions have no sign-up event).

---

## FLOW-02: Create a group and invite members
- **Actor:** A
- **Preconditions:** logged in; B is a friend; `kiran@example.com` has no account
- **Related features / screens:** F-12, F-13, F-09 / SCR-09, SCR-12, SCR-21, SCR-13, SCR-14, SCR-17, SCR-18

**Happy path**
1. Groups tab → "Start a new group" → SCR-12.
2. Name "Goa Trip", type trip, dates 2026-12-20 → 2026-12-27.
3. Add members → SCR-21 → select B; type "Kiran" + `kiran@example.com` → verify screen → Done.
4. Tap Done → `POST /groups` with `member_user_ids=[B]` and `new_members=[{name:"Kiran", email:"kiran@example.com"}]` → 201.
5. The server creates placeholder user Kiran (`is_registered=false`), 3 `group_members` rows (A, B, Kiran), and queues 1 invite email to Kiran.
6. SCR-13 opens for "Goa Trip": empty state "no expenses yet", 3 members.
7. Settings → Invite via link → SCR-17 → Share → the link is copied.
8. C (registered, not a member) opens the link → SCR-18 lists placeholder "Kiran" + "not on the list" → C picks "not on the list" → `POST /groups/join` → 200 → C becomes the 4th member → SCR-13.

**Alternate / error paths**
- Empty name → inline error, no request.
- End date before start date → 422 `INVALID_DATE_RANGE`.
- Kiran signs up later with `kiran@example.com` → the placeholder is claimed (same `user_id`), membership kept.
- Someone opens the link as placeholder "Kiran" while logged in as `k2@example.com` → "merge accounts?" → on confirm, `kiran@example.com` is added as a secondary email of `k2`'s account, and Kiran's group membership and history move to `k2` **(inferred, OQ-24)**.
- Link reset by a member → the old link returns 410 → "invite no longer valid".
- A tries to add more than 200 members → 422 `GROUP_TOO_LARGE` (**decision**).

**Postconditions:** 1 `groups` row; 4 `group_members`; 1 `group_invites` token; activity entries `group.created` (1) and `group.member_added` (one per added member); a push "added to group" to each registered added member (V2).

---

## FLOW-03: Add an expense (each split type)
- **Actor:** A
- **Preconditions:** shared fixture; G has no expenses
- **Related features / screens:** F-18 to F-26, F-43 / SCR-22, SCR-23, SCR-24, SCR-25, SCR-26, SCR-27

Common steps for each sub-flow: from SCR-13 tap Add expense → SCR-22 opens with "with you and: Flat 4B", INR, today's date, "paid by you and split equally".

### 03a: Equal (default)
1. Description "Groceries", amount `100.00` → Save.
2. `POST /groups/G/expenses` with `{total: {amount_minor: 10000, currency: INR}, payers: [{user_id: A, paid_amount_minor: 10000}], split: {type: equal, entries: [{user_id: A}, {user_id: B}, {user_id: C}]}}` → 201.
3. Stored splits: A 3334, B 3333, C 3333 (business_rules vector 1; canonical order A, B, C).
4. Nets: A +6666, B −3333, C −3333. Sum = 0.

### 03b: Exact amounts
1. "Electricity", `2450.00` → Split → Exact tab → A 1000.00, B 800.00, C 650.00 → footer "2450.00 of 2450.00" → Done → Save.
2. Splits 100000 / 80000 / 65000; nets A +145000, B −80000, C −65000.
- Error: C 600.00 → footer "50.00 left" → Done → "under by 50.00", stays on SCR-23.

### 03c: Percentages
1. "Internet", `10.00` → Percent → A 33.33, B 33.33, C 33.34 → footer "100% of 100%" → Save.
2. Splits 333 / 333 / 334 (vector 9).
- Error: 50 / 30 / 19 → "1% left" → Done refused.

### 03d: Shares
1. "Cottage 3 nights", `600.00` → Shares → A 1, B 2, C 3 → footer "6 total shares" → Save.
2. Splits 10000 / 20000 / 30000.
- Error: all 0 → "assign at least 1 share".

### 03e: Adjustment
1. "Pizza", `100.00` → Adjustment → A +10.00, B 0, C 0 → each row shows A 40.00, B 30.00, C 30.00 → Save.
2. Splits 4000 / 3000 / 3000 (vector 14).
- Error: A +60.00 and B +50.00 → "adjustments exceed total by 10.00".

### 03f: Two-person shortcut (non-group)
1. From B's friend screen → Add expense → with B only → "Cab", `300.00` → split sentence → choose "you are owed the full amount" → Save.
2. `group_id=null`; payer A 30000; splits A 0, B 30000; A–B balance +30000 for A.

### 03g: Multiple payers
1. "Dinner", `900.00` → Paid by → Multiple people → A 600.00, B 300.00 → Done → split equal A, B, C → Save.
2. Nets A +30000, B 0, C −30000 (vector 17).
- Error: A 600.00 + B 200.00 → "under by 100.00".

### 03h: Another currency
1. "Museum", currency → SCR-26 → search "USD" → `45.00` → Save.
2. Stored as 4500 USD; G now shows separate INR and USD balance lines.

**Alternate / error paths (all sub-flows)**
- Description empty → "description required"; amount 0 or empty → "amount required".
- Amount over 9,999,999,999 minor units (99,999,999.99 in a 2-decimal currency) → refused at input; the API returns 422 `AMOUNT_OUT_OF_RANGE`.
- 3 decimals typed → the 3rd digit is ignored. JPY → no decimal point allowed.
- A second group added to "with" → "only one group per expense".
- A non-group expense that doesn't include A → 422 `CURRENT_USER_NOT_INVOLVED`.
- Offline (V2) → saved locally with an `idempotency_key`; "unsynced" badge; sent once on reconnect.
- Free user over the daily limit (if adopted, OQ-19) → SCR-39 with a wait timer.

**Postconditions:** 1 `expenses` row; `expense_payers` sum = `expense_splits` sum = total; activity `expense.created`; push "expense added" to the other participants (V2); group and friend balances updated in the same transaction.

---

## FLOW-04: Edit and delete an expense
- **Actor:** B (not the creator)
- **Preconditions:** expense E "Groceries" 10000 equal A/B/C from 03a, `version=1`
- **Related features / screens:** F-29, F-30, F-37 / SCR-29, SCR-22

**Happy path (edit)**
1. B opens E from Activity → SCR-29 → Edit → SCR-22 prefilled.
2. Change the amount to `120.00` → Save → `PATCH /expenses/E` with `version=1` → 200, `version=2`.
3. Splits recomputed: 4000 × 3. Nets A +8000, B −4000, C −4000.
4. A system comment records "total 100.00 → 120.00"; activity `expense.updated`; push "expense updated" to A and C (V2).

**Happy path (delete and restore)**
5. B → SCR-29 → Delete → confirm dialog ("removes for everyone") → `DELETE /expenses/E` → 200.
6. E shows "deleted by Ravi on 5 Nov 2026"; every balance returns to the state without E (all 0 if E was the only expense).
7. A opens E from Activity → Restore → `POST /expenses/E/restore` → 200 → balances return to +8000 / −4000 / −4000.

**Alternate / error paths**
- Concurrent edit: C saved first (`version=2`) → B's `PATCH` with `version=1` → 409 `VERSION_CONFLICT` → the app reloads E and shows "this expense changed, review and save again".
- E involves a member who left G → Edit → 409 `EXPENSE_HAS_DEPARTED_MEMBER`; Delete still allowed.
- E already deleted by someone else → Delete → 409 `ALREADY_DELETED`; the app refreshes the view.
- Commenting on a deleted expense → refused: "restore to add a comment".
- Non-participant D (not in G) tries `PATCH` → 403.
- Edit after settlement: E edited after A and B settled → the balances re-open by the difference. Settlements are never changed automatically (business_rules §8).

**Postconditions:** `expenses.version` incremented; `deleted_at` / `deleted_by` set or cleared; activity entries `expense.updated`, `expense.deleted`, `expense.restored`; net-balance invariant holds after each step.

---

## FLOW-05: Settle up (full and partial)
- **Actor:** C
- **Preconditions:** G nets A +6666, B −3333, C −3333 (from 03a); simplify on
- **Related features / screens:** F-34, F-35, F-33 / SCR-13, SCR-30, SCR-31, SCR-32, SCR-15

**Happy path (partial)**
1. C opens G → Settle up → SCR-30 shows "you owe Asha 33.33" (simplified suggestion C→A 3333).
2. Tap the row → SCR-31 prefilled: from C to A, 33.33 INR, today, group G.
3. Change the amount to `20.00` → Save → `POST /settlements` `{from_user_id: C, to_user_id: A, amount: {amount_minor: 2000, currency: INR}, group_id: G}` → 201.
4. Nets: A +4666, B −3333, C −1333.

**Happy path (full)**
5. C → Settle up → row shows 13.33 → Save the prefilled 1333 → nets A +3333, C 0.
6. C's G header shows "you are settled up"; the group list shows C settled for G.

**Happy path (settle all across scopes, from the friend screen)**
7. B owes A 3333 in G and 500 non-group. B → A's friend screen → Settle up → "settle all balances" → confirm → 2 settlements created (3333 in G, 500 non-group) → A–B total = 0.

**Alternate / error paths**
- Amount 0 → "enter an amount greater than 0".
- Amount 50.00 when 13.33 is owed → "more than owed" confirmation → on confirm, A owes C 36.67 (direction flips; business_rules §6). (**decision**, OQ-15)
- Currency differs from the balance (C pays 5 USD against an INR debt) → allowed. It creates a USD balance line; it does not reduce the INR debt.
- Delete the settlement → SCR-32 → Delete → balances revert; Restore re-applies it.
- from == to → 422 `SAME_PARTY`.

**Postconditions:** `settlements` rows; activity `settlement.created`; push "payment recorded" to the receiver (V2); group and friend balances updated.

---

## FLOW-06: Add a friend
- **Actor:** A
- **Preconditions:** logged in; contacts permission not yet asked
- **Related features / screens:** F-09, F-10, F-11 / SCR-08, SCR-21, SCR-19, SCR-42

**Happy path (registered by email)**
1. Friends tab → Add friend → SCR-21.
2. Type `ravi@example.com` → row "add ravi@example.com" → tap → Done → `POST /friends {email}` → 201 `{user, is_new_user:false}`.
3. Ravi appears on SCR-08 with "settled up".

**Happy path (contact, not registered)**
4. SCR-21 → contacts primer → allow → choose "Neha" (phone +91 98xxxxxxx) → verify screen shows the number → Done → `POST /friends {name, phone_e164}` → 201 `{friend, is_new_user:true}` → placeholder created; 1 SMS/email invite queued (channel: OQ-25).

**Happy path (QR, V2)**
5. B opens Account → My code. A → SCR-42 → Scan → reads B's code → "Add Ravi?" (the name lookup needs an endpoint that is not yet in the contract, decision D-C) → confirm → `POST /friends {friend_code}` → 201.

**Alternate / error paths**
- `abc` → "not a valid email or phone number".
- Own email → 422 `CANNOT_FRIEND_SELF`.
- Already friends → 200 with the existing friendship (idempotent), toast "already friends".
- Contacts permission denied → the list hides contacts; manual entry still works.
- Remove a friend with shared groups → 409 `SHARED_GROUPS_EXIST` with the group list.

**Postconditions:** `friendships` row(s); placeholder `users` row if new; activity `friend.added` for both sides; push "added as friend" to the registered friend (V2).

---

## FLOW-07: Recurring expense setup
- **Actor:** A
- **Preconditions:** shared fixture; the server's scheduler job runs every 15 min (**decision**)
- **Related features / screens:** F-40 / SCR-22, SCR-27

**Happy path**
1. Add expense in G: "Rent", `30000.00`, date 2026-01-31, equal A/B/C.
2. Date chip → SCR-27 → Repeat: monthly; Reminder: 2 days before → Done → Save.
3. `POST /groups/G/expenses` with `recurrence:{interval:monthly, reminder_days_before:2}` → 201. This creates expense E1 (2026-01-31) and `recurring_rules` R with `next_occurrence_date=2026-02-28`.
4. On 2026-02-26 (time zone of the rule's creator): reminder emails to A, B and C.
5. On 2026-02-28 the job creates E2 (a copy of E1's description, amount, category and split; date 2026-02-28; `recurring_rule_id=R`). Then 2026-03-31, 2026-04-30, …
6. Each generated expense posts activity `expense.created` with actor "system (recurring)".

**Alternate / error paths**
- B leaves G before 2026-03-31 (balance 0) → E3 is created with participants A, C only, equal: 1500000 each (**decision**, OQ-16).
- A edits only E2 → just E2 changes; the rule is unchanged.
- A edits the rule via E1 → Repeat: never → `PATCH /recurring-expenses/R {active:false}` → no further occurrences.
- Scheduler outage from 2026-02-27 to 2026-03-02 → on restart E2 is created once (unique `(rule_id, occurrence_date)`).
- The group is deleted → the rule is deactivated.
- Exact or shares split on the template with a departed member → percentages / shares re-normalised over the remaining people (business_rules §8).

**Postconditions:** 1 `recurring_rules` row; one `expenses` row per occurrence; `reminders` jobs; no duplicate occurrence for the same date.

---

## FLOW-08: Multi-currency expense
- **Actor:** A
- **Preconditions:** G default INR; no USD activity yet
- **Related features / screens:** F-43, F-44 / SCR-22, SCR-26, SCR-15, SCR-08

**Happy path**
1. Add expense in G: currency USD, `90.00`, equal A/B/C, A paid.
2. Stored as `total_amount_minor=9000`, `currency=USD`; splits 3000 each.
3. SCR-15 shows A "+60.00 USD" and any INR balance on separate lines; the overall summary on SCR-08 shows "owed $60.00 and ₹X" with no conversion.
4. C settles 30.00 USD to A → C's USD balance = 0; the INR balance is untouched.

**Conversion (Later, premium)**
5. A → SCR-14 → "convert all to INR" → confirm dialog (cannot be undone) → `POST /groups/G/convert-currency {target:INR}` (Later; this endpoint is **not yet in the contract**).
6. The server fetches today's rate (for example 1 USD = 83.2156 INR) and rewrites every USD expense and settlement in G. A 9000 USD expense becomes 748940 INR minor units (9000 × 83.2156 = 748940.4 → 748940). The splits are re-allocated with the largest-remainder rule (business_rules §7); the original amounts are stored in `fx_*` fields.

**Alternate / error paths**
- A currency without a rate available → 503 `FX_UNAVAILABLE`; nothing changes.
- JPY expense `1500` → stored as 1500 (exponent 0); typing `1500.5` is refused at input.
- An unknown currency code over the API → 422.

**Postconditions:** per-currency balances; conversion writes an activity entry `group.currency_converted` with the rate used.

---

## FLOW-09: Export data
- **Actor:** A (premium)
- **Preconditions:** G has 3 expenses and 1 settlement
- **Related features / screens:** F-45, F-46 / SCR-13, SCR-38, SCR-39

**Happy path**
1. SCR-13 → Export → `POST /exports {scope:group, group_id:G, format:csv}` → 202 `{id, status:pending}`.
2. The app shows "generating" and polls `GET /exports/{id}` every 1 s, at most 30 times.
3. Status `ready` with a `download_url` (signed, expires in 15 min) → the app downloads it and opens the share sheet with `flat-4b-2026-11-05.csv`.
4. The file has 1 header + 4 rows + 1 total row; amounts formatted to the currency exponent (F-45).

**Alternate / error paths**
- Free user → SCR-39; no export is created (the API returns 402 `PREMIUM_REQUIRED` if called directly).
- Generation fails → status `failed` → "try again".
- 30 polls without `ready` → "this is taking longer; we'll notify you" (V2).
- Mixed currencies → a `currency` column per row; one total row per currency.

**Postconditions:** an `exports` row; file kept for 24 h then purged (**decision**).

---

## FLOW-10: Join a group from a link while logged out
- **Actor:** new user D
- **Preconditions:** D has no account; G's invite link
- **Related features / screens:** F-13, F-54 / SCR-01, SCR-02, SCR-03, SCR-18

**Happy path**
1. D taps the link → the app installs/opens → SCR-01 stores the pending link → SCR-02.
2. D signs up (FLOW-01 steps 2–4).
3. The app resumes the pending link → SCR-18 → join → SCR-13.

**Alternate / error paths**
- Link expired → SCR-07 with the toast "invite no longer valid".

**Postconditions:** D is a member of G; activity `group.member_joined`.

---

## FLOW-11: Send a settle-up reminder
- **Actor:** A
- **Preconditions:** B owes A 2500 INR
- **Related features / screens:** F-39 / SCR-19, SCR-33

**Happy path**
1. A → B's friend screen → Remind → SCR-33 with a prefilled message containing "25.00".
2. "Send via app" → `POST /reminders {to_user_id:B}` → 202 → toast "reminder sent".

**Alternate / error paths**
- A second send within 60 s → 429 → "wait 1 minute".
- "Share" → OS share sheet; no server call.
- B's balance with A is 0 → the Remind button is hidden.

**Postconditions:** 1 email queued to B; `reminders` row with `sent_at`.

---

## Flows to cover
- [x] Sign up and log in: FLOW-01
- [x] Create a group and invite members: FLOW-02 (+ FLOW-10)
- [x] Add expense (each split type): FLOW-03 a–h
- [x] Edit and delete an expense: FLOW-04
- [x] Settle up (full and partial): FLOW-05
- [x] Add a friend: FLOW-06
- [x] Recurring expense setup: FLOW-07
- [x] Multi-currency expense: FLOW-08
- [x] Export data: FLOW-09
- [x] (extra) Send reminder: FLOW-11
