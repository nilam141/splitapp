# Tasks

> REA / Architect agent: break the spec into ordered vertical slices.
> Task ID format: S<slice>-<B|M|Q>-<n>  (B = backend, M = mobile, Q = QA)
> Each task is small enough for one agent in one sitting and has a testable definition of done.

Within a slice, tasks run in table order unless they say otherwise. **Business-rule test tasks (Q) come before the backend task that implements the rule.** The Q agent writes the failing tests from `business_rules.md` test vectors; the B agent makes them pass without editing the tests. Endpoint and schema names refer to `openapi.yaml`.

## Slice 1: Foundation
**Goal:** a user can register, log in, and see an empty home screen.
**Depends on:** none

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S1-B-1 | Backend | Docker Compose with Postgres, FastAPI skeleton, health endpoint | `GET /health` returns 200 in compose |
| S1-B-2 | Backend | SQLAlchemy models + Alembic migration for `users` | migration applies and rolls back cleanly |
| S1-B-3 | Backend | `/auth/register`, `/auth/login`, `/auth/refresh` (JWT) | pytest covers success, duplicate email, bad password |
| S1-M-1 | Mobile | React Native TS project, navigation shell | app boots on emulator |
| S1-M-2 | Mobile | Generate typed API client from openapi.yaml | client compiles, no hand-written endpoints |
| S1-M-3 | Mobile | Login and signup screens wired to the API | login persists across app restart |
| S1-Q-1 | QA | API tests and mobile smoke test | CI green |

## Slice 2: Groups
**Goal:** a user can add friends, create a group with members, change its settings, and leave or delete it, with the balance guard in place.
**Depends on:** Slice 1

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S2-B-1 | Backend | Migrations: `currencies` (seed ≥ 30 ISO codes with exponents), `categories` (seed 7 parents / ~40 children), `friendships`, `groups`, `group_members`, `refresh_tokens`, `password_reset_tokens`; add `users.default_currency`, `time_zone`, `is_registered`, `friend_code` | `alembic upgrade head` then `downgrade base` both succeed on an empty DB; the seed gives `GET /currencies` 30+ rows with INR exponent 2 and JPY 0 |
| S2-B-2 | Backend | `/auth/logout`, `/auth/password-reset`, `/auth/password-reset/confirm`, refresh rotation with reuse detection | pytest: a revoked refresh → 401; reuse of a rotated token revokes all of that user's tokens; a reset token is single-use and expires at 60 min (time frozen) → 410 |
| S2-B-3 | Backend | `GET/PATCH /users/me` | pytest: PATCH `default_currency=USD` persists; email clash → 409; invalid currency → 422 |
| S2-B-4 | Backend | `GET/POST /friends`, `GET/DELETE /friends/{user_id}` incl. placeholder creation and claim-on-register | pytest: add registered → 201 `is_new_user=false`; add unknown email → placeholder + 1 outbox email; registering that email reuses the placeholder id; self → 422 `CANNOT_FRIEND_SELF`; repeat add → 200 |
| S2-B-5 | Backend | `GET/POST /groups`, `GET/PATCH/DELETE /groups/{id}`, `POST /groups/{id}/members`, `DELETE /groups/{id}/members/{user_id}` (balance guard stubbed to read 0 until Slice 4) | pytest: create with 2 member ids + 1 new member → 4 members, sort_index 0..3; name of 101 chars → 422; trip end < start → 422 `INVALID_DATE_RANGE`; non-member GET → 403; stale `version` PATCH → 409; delete → hidden from all members' `GET /groups` |
| S2-B-6 | Backend | Activity writes for group and friend events (`activity_log`, `activity_recipients`) | pytest: creating a group with 3 members writes 1 `group.created` and 3 recipient rows |
| S2-M-1 | Mobile | Tab shell SCR-07 with Friends/Groups/Activity/Account tabs and the add-expense button placeholder | the 4 tabs render on the emulator; the last tab is restored after restart |
| S2-M-2 | Mobile | Friends tab SCR-08 (list, filters, empty state) and Add people wizard SCR-21 (email/phone entry, contacts with permission primer) | E2E (Detox or Maestro): add `ravi@example.com` → row appears; `abc` → error shown, no request sent (network mock asserts 0 calls) |
| S2-M-3 | Mobile | Groups tab SCR-09, Create group SCR-12, Group detail shell SCR-13 (empty states) | E2E: create "Goa Trip" (trip, 2 members) → SCR-13 shows 3 members and the empty state |
| S2-M-4 | Mobile | Group settings SCR-14 (rename, type, simplify toggle, add/remove member, leave, delete with 2-step confirm) | E2E: rename → visible on SCR-09; a 409 `OUTSTANDING_BALANCE` from a mock shows a dialog with the amount |
| S2-M-5 | Mobile | Account tab SCR-11 (profile fields, default currency via SCR-26, log out) and SCR-44 session expired | E2E: change currency to USD → persisted after restart; log out → SCR-02 and secure storage empty |
| S2-Q-1 | QA | API contract tests: every Slice 2 endpoint response validates against `openapi.yaml` (schemathesis or similar) | CI job fails on any schema mismatch; green on main |

## Slice 3: Expenses and split types
**Goal:** a user can add, view, edit, delete and restore expenses with all 5 split types and multiple payers, in any currency, in a group or with friends only.
**Depends on:** Slice 2

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S3-Q-1 | QA | Write failing pytest unit tests for the pure split engine from business_rules vectors 1–18 and 13b (equal, exact, percent, shares, adjustment, multiple payers, validation errors with exact `difference` values) | tests exist under `backend/tests/rules/test_splits.py`, are parametrised one row per vector, and fail with `NotImplementedError` |
| S3-Q-2 | QA | Property tests (hypothesis) for vector 39: Σ owed = T, all owed ≥ 0, deterministic for the same input, for T in [1, 9,999,999,999] and 1–50 participants | 10,000 examples per split type; tests fail before S3-B-1 |
| S3-B-1 | Backend | Implement the split engine (pure functions, no DB) per business_rules §2–3 incl. canonical ordering | S3-Q-1 and S3-Q-2 pass unchanged; 100% branch coverage of the engine module |
| S3-B-2 | Backend | Migrations for `expenses`, `expense_payers`, `expense_splits`, `comments`, the deferred sum-check trigger, and the indexes listed in data_model.md | a direct SQL insert with Σ splits ≠ total fails at commit; migration round-trips |
| S3-B-3 | Backend | `POST/GET /groups/{id}/expenses`, `POST/GET /expenses`, `GET/PATCH/DELETE /expenses/{id}`, `POST /expenses/{id}/restore`, Idempotency-Key handling | pytest: FLOW-03 a–h each return 201 with the expected splits; 2nd group in body → 422; non-group without the creator → 422 `CURRENT_USER_NOT_INVOLVED`; same Idempotency-Key twice → 1 row; stale version → 409; delete twice → 409 `ALREADY_DELETED`; restore a non-deleted one → 409 `NOT_DELETED` |
| S3-B-4 | Backend | Departed-member edit guard, system comments on edit, `GET/POST /expenses/{id}/comments` | pytest: editing an expense whose participant has `left_at` set → 409 `EXPENSE_HAS_DEPARTED_MEMBER`; editing the total writes 1 system comment; commenting on a deleted expense → 409 |
| S3-M-1 | Mobile | Client money utilities: parse a user string into minor units per currency exponent, format minor → display, all integer-only | Jest: "12.34" INR → 1234; "12.345" rejected; "1500" JPY → 1500; "1500.5" JPY rejected; 9,999,999,999 round-trips; no `parseFloat` in the module (lint rule) |
| S3-M-2 | Mobile | Port the split engine to TypeScript for live previews; run the same vector table (exported JSON from S3-Q-1) | Jest runs all business_rules vectors 1–18 and 13b with identical outputs to the backend |
| S3-M-3 | Mobile | Add/edit expense SCR-22 with category SCR-25, currency SCR-26, date SCR-27, note SCR-28 (text only) | E2E: FLOW-03a saves and SCR-13 shows "you lent 66.66"; empty description → error, no request |
| S3-M-4 | Mobile | Adjust split SCR-23 (5 tabs, two-person shortcuts, live over/under footers) and payers SCR-24 | E2E: percent 50/30/19 shows "1% left" and Done is disabled; shares 1/2/3 on 600.00 shows 100.00/200.00/300.00 |
| S3-M-5 | Mobile | Expense detail SCR-29 with comments, delete/restore, and the edit entry point | E2E: delete → banner "deleted by…"; restore → banner gone; post a comment → appears at the bottom |
| S3-Q-3 | QA | E2E suite for FLOW-03 (all sub-flows) and FLOW-04 | CI green on the emulator; each sub-flow asserts the stored splits via the API |

## Slice 4: Balances and debt simplification
**Goal:** every screen shows correct per-currency balances: group, friend and overall. Simplify debts on/off produces the documented transfers, and the leave/remove guard is live.
**Depends on:** Slice 3

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S4-Q-1 | QA | Failing unit tests for net balances, pairwise debts and simplification: business_rules vectors 17, 19–24, 28, 32, 33 (ordered transfer lists) | tests exist, parametrised by vector, fail before S4-B-1 |
| S4-Q-2 | QA | Property tests (vector 40): random group histories → Σ nets = 0 per currency; applying `simplify()` zeroes every net; transfers ≤ N−1; pairwise edges net to the same per-user nets | 2,000 random histories per run; failing before S4-B-1 |
| S4-B-1 | Backend | Implement `net_balances`, `pairwise_edges`, `simplify` (pure) per business_rules §4–5 | S4-Q-1 and S4-Q-2 pass unchanged |
| S4-B-2 | Backend | `GET /groups/{id}/balances`, `GET /balances`, balances inside `GET /groups`, `GET /groups/{id}`, `GET /friends`, `GET /friends/{id}` (incl. `breakdown`, `settled_up_since`) | pytest: fixture "Flat 4B" after 03a returns nets +6666/−3333/−3333 and transfers [B→A 3333, C→A 3333]; toggling simplify changes `transfers` but not `members`; p95 < 200 ms with 5,000 expenses (pytest-benchmark) |
| S4-B-3 | Backend | Turn on the real `OUTSTANDING_BALANCE` guard for leave/remove (from the S2-B-5 stub) | pytest: member at −1 paise → 409 with balances in details; at 0 in all currencies → 204 |
| S4-M-1 | Mobile | Balance rendering everywhere (SCR-08, 09, 13, 19): per currency, never summed, owes/owed colouring, settled-up collapse after 30 days | Jest snapshot for 1-, 2- and 3-currency cases; E2E: a friend at 0 since 31 days ago is hidden behind "show 1 settled-up friend" |
| S4-M-2 | Mobile | Group balances SCR-15 and simplify explainer SCR-40 | E2E: vector 20 fixture shows 3 transfers in the documented order; simplify off shows the pairwise list |
| S4-Q-3 | QA | Cross-check: for 50 random seeded groups, the mobile engine (S3-M-2 + a balance port) and the API return identical balances | CI job diffs JSON outputs; 0 differences |

## Slice 5: Settle up and activity feed
**Goal:** users can record full, partial and "settle all" payments, edit/delete/restore them, and see a paginated activity feed with each event's effect on them.
**Depends on:** Slice 4

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S5-Q-1 | QA | Failing tests for settlement rules: vectors 25, 26, 27, settle-all (one settlement per scope and currency, shared `batch_id`), SAME_PARTY, currency isolation (USD payment leaves the INR debt) | tests fail before S5-B-2 |
| S5-B-1 | Backend | Migration `settlements`; include settlements in `net_balances` (+from / −to) | S4-Q-2 property tests still pass with random settlements added to the generator |
| S5-B-2 | Backend | `POST/GET /settlements`, `POST /settlements/settle-all`, `GET/PATCH/DELETE /settlements/{id}`, `POST /settlements/{id}/restore` | S5-Q-1 passes; FLOW-05 steps 1–7 pass as an API test |
| S5-B-3 | Backend | Activity feed: `GET /activity` (cursor, 50/page, `my_effect`), `POST /activity/read`; activity rows for every expense/settlement/comment action | pytest: 120 events → 3 pages (50, 50, 20) with no duplicates; `my_effect` for 03a from B's view is −3333 INR |
| S5-M-1 | Mobile | Settle up SCR-30, Record payment SCR-31, Payment detail SCR-32 incl. overpay confirmation | E2E: FLOW-05 partial then full → C sees "settled up"; amount 0 → error; overpay → confirmation dialog shown |
| S5-M-2 | Mobile | Activity tab SCR-10 with infinite scroll, unread badge, tap-through to SCR-29/32/13 | E2E: after B adds an expense, A's badge shows 1; opening the tab clears it |
| S5-Q-2 | QA | E2E for FLOW-05 and an activity pagination test on a seeded account with 120 events | CI green |

## Slice 6: Friends, multi-currency, notifications, recurring, export, polish
**Goal:** the V2 feature set: invite links and QR, push notifications and reminders, recurring expenses, receipt images, premium gating with search and export, offline queue.
**Depends on:** Slice 5

| ID | Owner | Task | Definition of done |
|---|---|---|---|
| S6-Q-1 | QA | Failing tests for recurrence date generation: vectors 36, 37 plus fortnightly from 2026-01-01 (01-01, 01-15, 01-29); idempotent catch-up after a 3-day outage; vector 38 (member left) | tests fail before S6-B-2 |
| S6-B-1 | Backend | Migration `recurring_rules`; `recurrence` on expense create; `GET/POST /recurring-expenses`, `PATCH/DELETE /recurring-expenses/{id}` | pytest: creating Rent with `recurrence` returns 201 and 1 rule with `next_occurrence_date=2026-02-28` |
| S6-B-2 | Backend | Scheduler job (every 15 min) that creates due occurrences and queues reminders | S6-Q-1 passes; running the job twice for the same date creates exactly 1 expense |
| S6-B-3 | Backend | Notifications: `push_devices`, `notifications` outbox, FCM sender, email sender, per-type prefs, no self-notify; `POST /reminders` with a 60 s rate limit | pytest: B adds an expense → 1 push row for A and C, 0 for B; A disables comments → 0 rows; 2nd reminder within 60 s → 429 |
| S6-B-4 | Backend | Invite links: `GET/POST /groups/{id}/invite-link`, `POST /groups/join` incl. claim placeholder; friend code `POST /friends` with `friend_code` | pytest: a reset link → the old token gives 410; claiming placeholder Kiran moves all of Kiran's split rows to the joining user |
| S6-B-5 | Backend | Receipts: migration `receipts`; `POST/DELETE /expenses/{id}/receipt` (multipart, ≤ 10 MB, JPEG/PNG), object storage, `receipt_url` on Expense | pytest: 4 MB JPEG → 201; 11 MB → 413; wrong MIME → 422 |
| S6-B-6 | Backend | Premium gating: `subscriptions`, Play purchase verification, `plan` on `/users/me`, a 402 guard on search (`GET /expenses?q=`) and `POST /exports` | pytest: free user `?q=goa` → 402 `PREMIUM_REQUIRED`; premium → 200 with 1 result |
| S6-B-7 | Backend | Export job: CSV per F-45 (header, rows, per-member columns, total row per currency), signed URL valid 15 min, purge after 24 h | pytest: the G fixture with 3 expenses + 1 settlement → CSV with 6 lines; 90000 INR renders `900.00`; the file is gone after 24 h (time frozen) |
| S6-M-1 | Mobile | Push registration, notification settings SCR-34, deep links (join, add friend, reset) incl. resume-after-login | E2E: opening a join link while logged out → after login lands on SCR-18 |
| S6-M-2 | Mobile | Recurring UI in SCR-27, the "repeats monthly" label on SCR-29, stop-repeat action | E2E: FLOW-07 steps 1–3 create a rule visible in `GET /recurring-expenses` |
| S6-M-3 | Mobile | Remind SCR-33 (send via app + share sheet), invite link SCR-17, join SCR-18, My code / scan SCR-42 | E2E: FLOW-11 shows the "reminder sent" toast; a 2nd send shows "wait 1 minute" |
| S6-M-4 | Mobile | Paywall SCR-39 with Play Billing, gated entry points (search SCR-36, export SCR-38), receipt image in SCR-28 | E2E with billing test cards: purchase → search opens; a free user tapping Export opens SCR-39 |
| S6-M-5 | Mobile | Offline cache (React Query persistence) + a write queue with Idempotency-Key for expenses and settlements | E2E: airplane mode → add expense → "unsynced" badge; reconnect → exactly 1 expense on the server |
| S6-Q-1b | QA | E2E for FLOW-02 (invite link), FLOW-06, FLOW-07, FLOW-08 (no conversion), FLOW-09, FLOW-10, FLOW-11 | CI green on the emulator |
| S6-Q-2 | QA | Release checklist: accessibility (TalkBack labels on every money value), 0 floats in money paths (grep + lint across both trees), crash-free smoke on Android 7 (API 24) and Android 14 | checklist file committed; all items ticked |

Deferred (no slice yet; see features.md "Later"): F-07 login challenge, F-41/F-42 scheduled reminders and balance alerts, F-44 currency conversion, F-48 charts/totals, F-49 receipt scanning, F-52 whiteboard, F-06 Google sign-in (can join Slice 6 if wanted).

## Global rules
- A slice is merged only when QA tests pass and the Reviewer agent approves.
- Money handling and auth are reviewed on every slice.
