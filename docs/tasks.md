# Tasks

> REA / Architect agent: break the spec into ordered vertical slices.
> Task ID format: S<slice>-<B|M|Q>-<n>  (B = backend, M = mobile, Q = QA)
> Each task is small enough for one agent in one sitting and has a testable definition of done.

Within a slice, tasks run in table order unless they say otherwise. **Business-rule test tasks (Q) come before the backend task that implements the rule.** The Q agent writes the failing tests from `business_rules.md` test vectors; the B agent makes them pass without editing the tests. Endpoint and schema names refer to `openapi.yaml` (v0.1.1).

**Table ownership rule.** A migration is created in the slice where its first endpoint ships. Where an earlier table needs a foreign key to a later table (for example `expenses.recurring_rule_id`), the column is created early without the FK and the later migration adds the FK.

**Response fields before their data exists.** Until Slice 4 ships, every `balances`, `my_balances`, `breakdown` and `non_group_balances` field is returned as an empty array and `settled_up_since` as null (the fields are required by the schema, so they must be present).

## Test vector coverage map

| Vectors (business_rules.md) | Q task | B task |
|---|---|---|
| 1–16, 13b, 17, 18, 34 | S3-Q-1 | S3-B-1 |
| 39 (property) | S3-Q-2 | S3-B-1 |
| 19–24, 28, 33, 40 (property) | S4-Q-1, S4-Q-2 | S4-B-1 |
| 35 | S4-Q-1 (API-level) | S4-B-3 |
| 25, 26, 27, 32 | S5-Q-1 | S5-B-2 |
| 36, 37, 38 | S6-Q-1 | S6-B-1, S6-B-2 |
| 41 (expense) | S3-Q-4 | S3-B-4 |
| 41 (settlement) | S5-Q-1 | S5-B-2 |
| 42 | S3-Q-4 | S3-B-4 |
| 43, 44 | S2-Q-2 | S2-B-5 |
| 45 | S6-Q-4 | S6-B-3 |
| 29, 30, 31 (currency conversion) | none yet | deferred with F-44 |

## Slice 1: Foundation
**Goal:** a user can register, log in, and see an empty home screen.
**Depends on:** none

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S1-B-1 | Backend | Docker Compose with Postgres, FastAPI skeleton, health endpoint | `GET /health` returns 200 in compose |
| S1-B-2 | Backend | SQLAlchemy models + one Alembic migration for `currencies` (seed at least 30 ISO codes with exponents), `users` (all MVP columns in data_model.md, including `default_currency`, `time_zone`, `is_registered`, `friend_code`, `notification_prefs`) and `refresh_tokens` | migration applies and rolls back cleanly on an empty DB; the seed has 30+ rows with INR exponent 2 and JPY 0 |
| S1-B-3 | Backend | `/auth/register`, `/auth/login`, `/auth/refresh` (JWT, access 900 s, refresh 30 days, refresh rotates on use); responses match `AuthResponse` / `TokenPair` | pytest covers success, duplicate email (409 `EMAIL_TAKEN`), bad password (401 `INVALID_CREDENTIALS`), unknown currency (422 `CURRENCY_UNKNOWN`); `UserMe` has `plan=free`, a generated `friend_code` and all 10 `notification_prefs` keys true |
| S1-B-4 | Backend | `GET /currencies` | pytest: 30+ items, INR exponent 2, JPY exponent 0 |
| S1-M-1 | Mobile | React Native TS project, navigation shell | app boots on emulator |
| S1-M-2 | Mobile | Generate typed API client from openapi.yaml | client compiles, no hand-written endpoints |
| S1-M-3 | Mobile | Login and signup screens wired to the API (currency picker uses `GET /currencies`) | login persists across app restart |
| S1-Q-1 | QA | API tests and mobile smoke test | CI green |

## Slice 2: Groups
**Goal:** a user can add friends, create a group with members, change its settings, and leave or delete it, with the balance guard in place.
**Depends on:** Slice 1

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S2-B-1 | Backend | Migrations: `categories` (seed 7 parents / ~40 children, id 1 = General → Uncategorized), `friendships`, `groups`, `group_members`, `password_reset_tokens`, `notifications` (outbox only), `idempotency_keys`; `GET /categories` | `alembic upgrade head` then `downgrade base` both succeed on an empty DB; `GET /categories` returns 7 parents each with 2+ children and id 1 is a child |
| S2-B-2 | Backend | `/auth/logout`, `/auth/password-reset`, `/auth/password-reset/confirm`, refresh reuse detection. Emails are written to the `notifications` outbox and delivered by a console/log sender until the real sender ships in S6-B-3 | pytest: a revoked refresh → 401; reuse of a rotated token revokes all of that user's tokens; a reset token is single-use and expires at 60 min (time frozen) → 410; a reset request writes 1 outbox row of type `password_reset` |
| S2-B-3 | Backend | `GET/PATCH /users/me` | pytest: PATCH `default_currency=USD` persists; email clash → 409 `EMAIL_TAKEN` with `details.field=email`; invalid currency → 422 `CURRENCY_UNKNOWN`; PATCH of one `notification_prefs` key keeps the other 9 |
| S2-B-4 | Backend | `GET/POST /friends`, `GET/DELETE /friends/{user_id}` incl. placeholder creation, claim-on-register and `Idempotency-Key` | pytest: add registered → 201 `is_new_user=false`; add unknown email → placeholder + 1 outbox row of type `invite`; registering that email reuses the placeholder id; self → 422 `CANNOT_FRIEND_SELF`; repeat add → 200; same `Idempotency-Key` twice → identical response, 1 friendship; `GET /friends?filter=` honours all 4 values. Until S2-B-5 these endpoints see explicit friendships only; S2-B-5 adds the derived shared-group users (OQ-33) |
| S2-Q-2 | QA | Failing API tests for the derived friend list and friend removal: business_rules vectors 43 and 44 (OQ-33): no `friendships` rows are ever written for group co-members (assert the table row count), `GET /friends` returns explicit UNION shared-group users once each, an implicit friend disappears after the last shared group is deleted or left, `DELETE /friends/{id}` on an implicit-only friend → 409 `SHARED_GROUPS_EXIST`, and after the group is gone → 404 | tests exist and fail before S2-B-5 |
| S2-B-5 | Backend | `GET/POST /groups`, `GET/PATCH/DELETE /groups/{id}`, `POST /groups/{id}/members`, `DELETE /groups/{id}/members/{user_id}` (balance guard stubbed to read 0 until Slice 4), **derived** friendships (OQ-33: no rows written for members; `GET /friends` and `GET /friends/{id}` return explicit friends UNION users sharing a non-deleted group, using index `group_members(user_id, group_id) where left_at is null` added in this migration; `DELETE /friends/{id}` returns 409 `SHARED_GROUPS_EXIST` while a group is shared and 404 when there is neither a shared group nor an explicit row), `Idempotency-Key` on POST /groups | pytest: create with 2 member ids + 1 new member → 4 members, sort_index 0..3 (creator 0); name of 101 chars → 422; trip end < start → 422 `INVALID_DATE_RANGE`; more than 200 members → 422 `GROUP_TOO_LARGE`; non-member GET → 403; stale `version` PATCH → 409 `VERSION_CONFLICT`; delete twice → 409 `ALREADY_DELETED`; delete → hidden from all members' `GET /groups`; the other members of the new group appear in each other's `GET /friends` with 0 new `friendships` rows; S2-Q-2 (vectors 43, 44) passes; same `Idempotency-Key` twice → 1 group |
| S2-B-6 | Backend | Migration `activity_log` + `activity_recipients`; activity writes for group and friend events | pytest: creating a group with 3 members writes 1 `group.created` and 3 recipient rows |
| S2-M-1 | Mobile | Tab shell SCR-07 with Friends/Groups/Activity/Account tabs and the add-expense button placeholder | the 4 tabs render on the emulator; the last tab is restored after restart |
| S2-M-2 | Mobile | Friends tab SCR-08 (list, filters, empty state) and Add people wizard SCR-21 (email/phone entry, contacts with permission primer) | E2E (Detox or Maestro): add `ravi@example.com` → row appears; `abc` → error shown, no request sent (network mock asserts 0 calls) |
| S2-M-3 | Mobile | Groups tab SCR-09, Create group SCR-12, Group detail shell SCR-13 (empty states) | E2E: create "Goa Trip" (trip, 2 members) → SCR-13 shows 3 members and the empty state |
| S2-M-4 | Mobile | Group settings SCR-14 (rename, type, simplify toggle, add/remove member, leave, delete with 2-step confirm) | E2E: rename → visible on SCR-09; a 409 `OUTSTANDING_BALANCE` from a mock shows a dialog with the amount |
| S2-M-5 | Mobile | Account tab SCR-11 (profile fields, default currency via SCR-26, log out) and SCR-44 session expired | E2E: change currency to USD → persisted after restart; log out → SCR-02 and secure storage empty |
| S2-Q-1 | QA | API contract tests: every Slice 1 and Slice 2 endpoint response validates against `openapi.yaml` (schemathesis or similar) | CI job fails on any schema mismatch; green on main |

## Slice 3: Expenses and split types
**Goal:** a user can add, view, edit, delete and restore expenses with all 5 split types and multiple payers, in any currency, in a group or with friends only.
**Depends on:** Slice 2

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S3-Q-1 | QA | Write failing pytest unit tests for the pure split engine and amount validation from business_rules vectors 1–18, 13b and 34 (equal, exact, percent, shares, adjustment, multiple payers, bounds, validation errors with exact `details` values) | tests exist under `backend/tests/rules/test_splits.py`, are parametrised one row per vector, and fail with `NotImplementedError` |
| S3-Q-2 | QA | Property tests (hypothesis) for vector 39: Σ owed = T, all owed ≥ 0, deterministic for the same input, for T in [1, 9,999,999,999] and 1–50 participants | 10,000 examples per split type; tests fail before S3-B-1 |
| S3-B-1 | Backend | Implement the split engine and amount validation (pure functions, no DB) per business_rules §1–3 incl. canonical ordering | S3-Q-1 and S3-Q-2 pass unchanged; 100% branch coverage of the engine module |
| S3-B-2 | Backend | Migrations for `expenses` (incl. `recurring_rule_id` and `occurrence_date` columns without the FK, `idempotency_key`, `fx_*` columns), `expense_payers`, `expense_splits`, `comments`, the deferred sum-check trigger, and the indexes in data_model.md for the tables created here | a direct SQL insert with Σ splits ≠ total fails at commit; migration round-trips |
| S3-B-3 | Backend | `POST /groups/{id}/expenses`, `POST /expenses`, `GET /groups/{id}/expenses`, `GET /expenses` (filters `friend_user_id`, `non_group`; no `q` yet), `GET /expenses/{id}`, Idempotency-Key handling | pytest: FLOW-03 a–h each return 201 with the expected splits; `group_id` in the body of a group-path POST is ignored; non-group without the creator → 422 `CURRENT_USER_NOT_INVOLVED`; payer or participant outside the group → 422 `PARTICIPANT_NOT_MEMBER`; same Idempotency-Key twice → 1 row; list is ordered by `expense_date` desc and pages with `next_cursor`; `recurrence` in the body → 501 `NOT_IMPLEMENTED` until S6-B-1 |
| S3-Q-4 | QA | Failing API tests for business_rules vectors 41 (expense) and 42: PATCH with a different `total.currency` → 422 `VALIDATION_ERROR` with `details.fields[0].field = total.currency`, expense and version unchanged; PATCH with the same currency succeeds; friend removal with a non-zero non-group balance → 204 and the expense soft-deleted (OQ-31, OQ-32) | tests exist and fail before S3-B-4 |
| S3-B-4 | Backend | `PATCH/DELETE /expenses/{id}`, `POST /expenses/{id}/restore`, departed-member edit guard, system comments on edit, currency-immutable PATCH (OQ-31), and the explicit-friend branch of `DELETE /friends/{user_id}` (OQ-32/33): soft-deleting non-group expenses between only the two users, never blocked by balance; implicit-only friends are handled by the S2-B-5 409/404 logic | pytest: stale version → 409 `VERSION_CONFLICT`; delete twice → 409 `ALREADY_DELETED`; restore a non-deleted one → 409 `NOT_DELETED`; editing an expense whose participant has `left_at` set → 409 `EXPENSE_HAS_DEPARTED_MEMBER` (delete still works); editing the total writes 1 system comment; removing a friend soft-deletes the pair's non-group expenses and leaves group expenses alone, even with a non-zero balance; PATCH changing the currency → 422 `VALIDATION_ERROR`; S3-Q-4 (vectors 41, 42) passes |
| S3-B-5 | Backend | `GET/POST /expenses/{id}/comments` | pytest: post and list oldest first with cursor; commenting on a deleted expense → 409 `ALREADY_DELETED`; empty body → 422; non-participant → 403 |
| S3-M-1 | Mobile | Client money utilities: parse a user string into minor units per currency exponent, format minor → display, all integer-only | Jest: "12.34" INR → 1234; "12.345" rejected; "1500" JPY → 1500; "1500.5" JPY rejected; 9,999,999,999 round-trips; no `parseFloat` in the module (lint rule) |
| S3-M-2 | Mobile | Port the split engine to TypeScript for live previews; run the same vector table (exported JSON from S3-Q-1) | Jest runs all business_rules vectors 1–18 and 13b with identical outputs to the backend |
| S3-M-3 | Mobile | Add/edit expense SCR-22 with category SCR-25, currency SCR-26, date SCR-27, note SCR-28 (text only) | E2E: FLOW-03a saves and SCR-13 shows "you lent 66.66"; empty description → error, no request |
| S3-M-4 | Mobile | Adjust split SCR-23 (5 tabs, two-person shortcuts, live over/under footers) and payers SCR-24 | E2E: percent 50/30/19 shows "1% left" and Done is disabled; shares 1/2/3 on 600.00 shows 100.00/200.00/300.00 |
| S3-M-5 | Mobile | Expense detail SCR-29 with comments, delete/restore, and the edit entry point | E2E: delete → banner "deleted by…"; restore → banner gone; post a comment → appears at the bottom |
| S3-M-6 | Mobile | Friend settings SCR-20 remove flow (SCR-19/20 had no owning task): Remove friend shows a confirmation dialog warning that non-group expenses and any balance with this person will be deleted (OQ-32); a 409 `SHARED_GROUPS_EXIST` lists the groups; implicit-only friends (no explicit row) show the same 409 dialog | E2E: with a mocked 3000 balance, tapping Remove shows the warning with the amount; Cancel sends 0 requests; Confirm sends 1 `DELETE /friends/{id}` and the row disappears; mocked 409 shows the group list |
| S3-Q-3 | QA | E2E suite for FLOW-03 (all sub-flows) and FLOW-04 | CI green on the emulator; each sub-flow asserts the stored splits via the API |

## Slice 4: Balances and debt simplification
**Goal:** every screen shows correct per-currency balances: group, friend and overall. Simplify debts on/off produces the documented transfers, and the leave/remove guard is live.
**Depends on:** Slice 3

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S4-Q-1 | QA | Failing tests for net balances, pairwise debts and simplification: business_rules vectors 17, 19–24, 28, 33 (ordered transfer lists), plus vector 35 as an API-level test against the S2 stubbed guard | tests exist, parametrised by vector, fail before S4-B-1 (vector 35: before S4-B-3) |
| S4-Q-2 | QA | Property tests (vector 40): random group histories → Σ nets = 0 per currency; applying `simplify()` zeroes every net; transfers ≤ N−1; pairwise edges net to the same per-user nets | 2,000 random histories per run; failing before S4-B-1 |
| S4-B-1 | Backend | Implement `net_balances` (accepting expenses and settlement records as plain inputs, no DB), `pairwise_edges`, `simplify` (pure) per business_rules §4–5 | S4-Q-1 (except vector 35) and S4-Q-2 pass unchanged |
| S4-B-2 | Backend | `GET /groups/{id}/balances`, `GET /balances`, real values for the balance fields in `GET /groups`, `GET /groups/{id}`, `GET /friends`, `GET /friends/{id}` (incl. `breakdown`, `settled_up_since` per data_model "Derived data") | pytest: fixture "Flat 4B" after 03a returns nets +6666/−3333/−3333 and transfers [B→A 3333, C→A 3333]; toggling simplify changes `transfers` but not `members`; members are in canonical order; p95 < 200 ms with 5,000 expenses (pytest-benchmark) |
| S4-B-3 | Backend | Turn on the real `OUTSTANDING_BALANCE` guard for leave/remove (from the S2-B-5 stub) | S4-Q-1 vector 35 passes; pytest: member at −1 paise → 409 with `details.balances`; at 0 in all currencies → 204 |
| S4-M-1 | Mobile | Balance rendering everywhere (SCR-08, 09, 13, 19): per currency, never summed, owes/owed colouring, settled-up collapse after 30 days | Jest snapshot for 1-, 2- and 3-currency cases; E2E: a friend at 0 since 31 days ago is hidden behind "show 1 settled-up friend" |
| S4-M-2 | Mobile | Group balances SCR-15 and simplify explainer SCR-40 | E2E: vector 20 fixture shows 3 transfers in the documented order; simplify off shows the pairwise list |
| S4-Q-3 | QA | Cross-check: for 1,000 random seeded expenses the mobile split engine (S3-M-2) and the API return identical splits, and for 50 random seeded groups `GET /groups/{id}/balances` equals the pure functions from S4-B-1 run in the test harness | CI job diffs JSON outputs; 0 differences |

## Slice 5: Settle up and activity feed
**Goal:** users can record full, partial and "settle all" payments, edit/delete/restore them, and see a paginated activity feed with each event's effect on them.
**Depends on:** Slice 4

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S5-Q-1 | QA | Failing tests for settlement rules: vectors 25, 26, 27 and 32, settle-all (one settlement per scope and currency, shared `batch_id`), SAME_PARTY, currency isolation (USD payment leaves the INR debt), who-can-record (non-group third party → 403), vector 41 for settlements (PATCH with a different `amount.currency` → 422 `VALIDATION_ERROR`, `details.fields[0].field = amount.currency`; OQ-31) | tests fail before S5-B-2 |
| S5-B-1 | Backend | Migration `settlements` (incl. `idempotency_key`); feed settlement rows into the S4 balance queries | S4-Q-2 property tests still pass with random settlements added to the generator |
| S5-B-2 | Backend | `POST/GET /settlements`, `POST /settlements/settle-all`, `GET/PATCH/DELETE /settlements/{id}`, `POST /settlements/{id}/restore` | S5-Q-1 passes; FLOW-05 steps 1–7 pass as an API test; delete twice → 409 `ALREADY_DELETED`; restore a live one → 409 `NOT_DELETED` |
| S5-B-3 | Backend | Activity feed: `GET /activity` (cursor, 50/page, `my_effect`), `POST /activity/read`; activity rows for every expense/settlement/comment action (the S3 endpoints gain their writes here) | pytest: 120 events → 3 pages (50, 50, 20) with no duplicates; `my_effect` for 03a from B's view is −3333 INR |
| S5-M-1 | Mobile | Settle up SCR-30, Record payment SCR-31, Payment detail SCR-32 incl. overpay confirmation | E2E: FLOW-05 partial then full → C sees "settled up"; amount 0 → error; overpay → confirmation dialog shown |
| S5-M-2 | Mobile | Activity tab SCR-10 with infinite scroll, unread badge, tap-through to SCR-29/32/13 | E2E: after B adds an expense, A's badge shows 1; opening the tab clears it. **Blocked on owner decision D-A (unread count source), see progress.md** |
| S5-Q-2 | QA | E2E for FLOW-05 and an activity pagination test on a seeded account with 120 events | CI green |

## Slice 6: Friends, multi-currency, notifications, recurring, export, polish
**Goal:** the V2 feature set: invite links and QR, push notifications and reminders, recurring expenses, receipt images, premium gating with search and export, offline queue.
**Depends on:** Slice 5

Several tasks below depend on endpoints that are not yet in `openapi.yaml` (push-device registration, subscription verification, invite preview, friend-code lookup). Those tasks are marked **Blocked** until the owner decides (progress.md, 2026-11-07).

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S6-Q-1 | QA | Failing tests for recurrence date generation (pure function): vectors 36, 37 plus fortnightly from 2026-01-01 (01-01, 01-15, 01-29); idempotent catch-up after a 3-day outage; vector 38 (member left) | tests fail before S6-B-1 |
| S6-B-1 | Backend | Migration `recurring_rules` (adds the FK from `expenses.recurring_rule_id`); the pure next-occurrence function; `recurrence` on expense create (replaces the 501); `GET/POST /recurring-expenses`, `PATCH/DELETE /recurring-expenses/{id}` | S6-Q-1 date tests pass; creating Rent with `recurrence` returns 201, 1 rule with `next_occurrence_date=2026-02-28`, and the template expense carries the rule id and `occurrence_date=2026-01-31` |
| S6-B-2 | Backend | Scheduler job (every 15 min) that creates due occurrences and queues reminders | S6-Q-1 catch-up and vector 38 tests pass; running the job twice for the same date creates exactly 1 expense |
| S6-Q-4 | QA | Failing test for vector 45 (OQ-34): a reminder to a recipient who owes nothing is accepted (202, 1 outbox/push row), with no balance check; second call within 60 s → 429 `RATE_LIMITED`; reminder to a non-friend, non-co-member → 422 `VALIDATION_ERROR` | tests fail before S6-B-3 |
| S6-B-3 | Backend | Notifications: `push_devices`, FCM sender, real email sender behind the S2 outbox, per-type prefs, no self-notify; `reminders` migration and `POST /reminders` with a 60 s rate limit and no check that the recipient owes the sender (OQ-34, business_rules §10.3). **Device registration endpoint Blocked (decision D-C)** | pytest: B adds an expense → 1 push row for A and C, 0 for B; A disables comments → 0 rows; 2nd reminder within 60 s → 429 `RATE_LIMITED`; S6-Q-4 passes |
| S6-B-4 | Backend | Invite links: `group_invites` migration, `GET/POST /groups/{id}/invite-link`, `POST /groups/join` incl. claim placeholder; friend code via `POST /friends` with `friend_code`. **Invite preview and friend-code lookup endpoints Blocked (decision D-C)** | pytest: a reset link → the old token gives 410; claiming placeholder Kiran moves all of Kiran's split rows to the joining user; a reset friend code → 410 |
| S6-B-5 | Backend | Receipts: migration `receipts`; `POST/DELETE /expenses/{id}/receipt` (multipart, ≤ 10 MB, JPEG/PNG), object storage, `receipt_url` on Expense | pytest: 4 MB JPEG → 201; 11 MB → 413; wrong MIME → 422 `VALIDATION_ERROR` |
| S6-B-6 | Backend | Premium gating: `subscriptions` migration, `plan` on `/users/me`, a 402 guard on search (`GET /expenses?q=`), `POST /exports` and receipt upload. **Play purchase verification endpoint Blocked (decision D-C)** | pytest: free user `?q=goa` → 402 `PREMIUM_REQUIRED`; free user receipt upload → 402; premium → 200 with 1 result |
| S6-B-7 | Backend | Export job: `exports` migration, `POST /exports`, `GET /exports/{id}`, CSV per F-45 (header, rows, per-member columns, total row per currency), signed URL valid 15 min refreshed on each poll, purge after 24 h | pytest: the G fixture with 3 expenses + 1 settlement → CSV with 6 lines; 90000 INR renders `900.00`; the file is gone after 24 h (time frozen) and the export then returns 404 |
| S6-M-1 | Mobile | Push registration (**Blocked**, D-C), notification settings SCR-34, deep links (join, add friend, reset) incl. resume-after-login | E2E: opening a join link while logged out → after login lands on SCR-18 |
| S6-M-2 | Mobile | Recurring UI in SCR-27, the "repeats monthly" label on SCR-29, stop-repeat action | E2E: FLOW-07 steps 1–3 create a rule visible in `GET /recurring-expenses` |
| S6-M-3 | Mobile | Remind SCR-33 (send via app + share sheet), invite link SCR-17, join SCR-18 (**preview Blocked**, D-C), My code / scan SCR-42 (**lookup Blocked**, D-C) | E2E: FLOW-11 shows the "reminder sent" toast; a 2nd send shows "wait 1 minute" |
| S6-M-4 | Mobile | Paywall SCR-39 with Play Billing (**Blocked**, D-C), gated entry points (search SCR-36, export SCR-38), receipt image in SCR-28 | E2E with billing test cards: purchase → search opens; a free user tapping Export opens SCR-39 |
| S6-M-5 | Mobile | Offline cache (React Query persistence) + a write queue with Idempotency-Key for expenses and settlements | E2E: airplane mode → add expense → "unsynced" badge; reconnect → exactly 1 expense on the server |
| S6-Q-2 | QA | E2E for FLOW-02 (invite link), FLOW-06, FLOW-07, FLOW-08 (no conversion), FLOW-09, FLOW-10, FLOW-11 | CI green on the emulator |
| S6-Q-3 | QA | Release checklist: accessibility (TalkBack labels on every money value), 0 floats in money paths (grep + lint across both trees), crash-free smoke on Android 7 (API 24) and Android 14 | checklist file committed; all items ticked |

Deferred (no slice yet; see features.md "Later"): F-07 login challenge, F-41/F-42 scheduled reminders and balance alerts (`group_reminder_settings`), F-44 currency conversion (`exchange_rates`, business_rules vectors 29–31, `POST /groups/{id}/convert-currency`), F-48 charts/totals (`GET /groups/{id}/totals`), F-49 receipt scanning, F-52 whiteboard, F-06 Google sign-in (`/auth/google`; can join Slice 6 if wanted), F-27 personal default splits (`user_group_default_splits`), merge accounts (`user_emails`), account deletion (OQ-D5), avatar upload, comment delete, SCR-34 email-digest switch. None of these has an endpoint in `openapi.yaml` yet, apart from the group whiteboard field.

## Global rules
- A slice is merged only when QA tests pass and the Reviewer agent approves.
- Money handling and auth are reviewed on every slice.
