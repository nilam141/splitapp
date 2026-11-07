# Open Questions

> REA: anything uncertain, inferred rather than observed, or contradictory. Do not guess silently.

**Context:** all evidence is static (manifest, resource names, string meanings, class/package names of the reference APK, v23.10.1). The app was **not run**: REA's adb, JADX and apktool providers aren't configured on this machine, and no emulator was available. "Confidence" is how sure I am that the **reference app** behaves as the spec assumes. Our spec stays deterministic regardless: each row says what we do if the answer differs.

| # | Question / uncertainty | What was observed | Confidence (high/med/low) | How to resolve |
|---|---|---|---|---|
| 1 | Remainder distribution order in equal splits (who gets the extra paise) | Equal-split screen shows "~X/person", so per-person amounts are approximate; no ordering rule visible | low | Manual test T1: add 100.00 split equally among 3 (you, B, C, in that order of joining) and record who owes 33.34. Repeat with a different payer. Our rule: first in group join order. |
| 2 | Percent precision and rounding: are 2 decimals allowed? Which person absorbs rounding? | Percent screen shows "X% left / over" and "X% of 100%"; the input filter class exists | med (2 dp) / low (rounding) | T2: 10.00 split 33.33/33.33/33.34; then try 33.333. Record the owed amounts and whether a 3rd decimal is accepted. |
| 3 | Shares: integers only, or decimals (e.g. 1.5)? | Share help text uses whole-number examples | med (integers) | T3: try entering 1.5 shares. |
| 4 | Adjustment: are negative adjustments allowed? | Help text says adjustments reflect "who owes extra"; an error exists for exceeding the total | med (non-negative) | T4: try −10.00 as an adjustment. |
| 5 | Password strength thresholds | 4 strength levels + "min 8 characters" | high (min 8) / low (thresholds) | Not needed: we define our own (F-02). |
| 6 | Is Facebook login offered, or is the SDK only for sharing? | Facebook SDK + the app queried in manifest `<queries>`; no Facebook login fragment found by name | low | Look at the login screen; screenshot it. |
| 7 | Phone-number login and the login-challenge code (length, channel, expiry) | Login challenge request/enter/contact-support fragments; phone verification modal; an SMS-retriever-style auth API library | med | T7: only if you hit a challenge; note the code length and channel. We default to 6 digits / 10 min. |
| 8 | "Settled up for over one month": is it exactly 30 days, a calendar month, or based on last activity? | Text says friends and groups settled up "over one month" are hidden | med | T8: hard to test quickly; accept 30 days. |
| 9 | Default of simplify debts for new groups | A toggle exists, plus a "turn on simplify debts" prompt (which suggests it can start off) | low | T9: create a group and open its settings; record the default. We default to **on**. |
| 10 | Is there any group admin/owner role? | No admin strings or layouts found; delete-group text addresses any user | med (no roles) | T10: as a non-creator, try rename / remove member / delete. |
| 11 | Does the app auto-suggest a category from the description? | Category chooser only; "auto" category ID strings not found | low | T11: type "Uber" as a description and see if the category icon changes. |
| 12 | Is the personal default split premium? | Default-split explanation texts; no Pro message for it | low | T12: open group settings → default split as a free user. |
| 13 | Who can edit/delete an expense or record a payment (any participant? any group member? creator only?) | Delete warning says it removes the expense for all people involved; no permission errors found | med (any involved person) | T13: as C, edit an expense created by A that doesn't involve C. |
| 14 | Exact debt-simplification algorithm | Only the explanation (3 people, chain → 1 payment) | low | T14: build vector 20 (4 people) and screenshot the balances. If the reference app gives a different set, we keep ours (it is still valid) but note it. |
| 15 | Can you record a payment larger than the debt (overpay)? | No error string for overpay found | low | T15: in a 30.00 debt, record 50.00. |
| 16 | Recurring expense when a member has left | No text found | low | Hard to test; our rule is in business_rules §8. |
| 17 | FX rate source and timing for "convert to currency" | Text says "current international exchange rate", irreversible | high (exists) / low (source) | Owner decision: choose a rate provider (OQ-D2). |
| 18 | Export column layout | Export produces a spreadsheet for a relationship | low | T18 (premium): export one group and send me the header row only, with no personal data. |
| 19 | Free-tier daily expense cap: N expenses/day and T-second wait? | A native-ad modal with a timer button and plan list; an add-expense key tagged "pro 2023-07"; server-configured | med (a cap exists in some form) / low (numbers) | T19: on a free account, add expenses until a modal appears; note the count and the timer length. |
| 20 | Passcode length (4 or 6) and timeout options | Passcode screen, change timeout, biometric prompt | med | T20: Account → passcode → screenshot the keypad and timeout options. |
| 21 | Dark mode: setting or system only? | Day/night resources only | med (system only) | Look in settings. |
| 22 | Reminder options for recurring expenses (which day counts) | Reminder-before-repeat and on-the-day texts | med | T22: set repeat monthly and screenshot the reminder picker. |
| 23 | Are charts native or a web view? | Charts title + a web-view screen exist | low | Not needed for our build. |
| 24 | Merge-accounts behaviour when an invite targets another email | Merge prompt: "this email will be added to your account, with relationships and expenses tied to it" | high (exists) / med (details) | Not needed; our design: data_model `user_emails`, business_rules §8. |
| 25 | Invites to phone-only contacts: SMS from the server, or the user's own SMS app? | `smsto` intent queries, a contact picker; no SMS provider SDK seen | med (user's SMS app via intent) | T25: add a phone contact and see what opens. Our default: share sheet (no SMS cost). |
| 26 | Can a PDF be attached as a receipt? | GET_CONTENT for `application/pdf` declared; a PDF viewer feature package exists | med | T26: try attaching a PDF. We accept JPEG/PNG only in V2. |
| 27 | Are payments stored as a special kind of expense? | A payment-flavoured expense list cell; payments listed among expenses | med | Not needed: our model uses a separate `settlements` table. |
| 28 | With simplify on, how is a simplified group debt shown on the friend screen (e.g. "you owe C" with no expense with C)? | Balance overlays "how was this balance calculated?" | low | T14 again: open each friend's screen and screenshot. |
| 29 | Is there an "approximate total in default currency" across currencies? | Per-currency total labels only | med (no) | T29: create USD + INR balances; screenshot the Friends header. |
| 30 | Behaviour of Undo after delete (snackbar) vs. Restore later | An undo string and undelete actions both exist | med | T30: delete an expense and watch for an undo snackbar. |
| 31 | Can PATCH change the currency of an existing expense or settlement (`total.currency`, `amount.currency`)? Nothing in business_rules covers it, and it would move balances between currencies. | Not observed | n/a (our design) | **DECIDED 2026-11-07 (owner):** PATCH cannot change currency; it is fixed at creation. To change it, delete and recreate. A `total.currency` / `amount.currency` that differs from the stored one is rejected with 422 `VALIDATION_ERROR` (`details.fields: ["total.currency"]` or `["amount.currency"]`); the same currency is accepted. Rationale: a currency change would silently move balances between currencies and break settled history. See business_rules §7, S3-B-4, S5-B-2. |
| 32 | Removing a friend who has a non-zero non-group balance: F-11 says their non-group expenses are soft-deleted, which silently erases the debt. Should removal be blocked like group leave (409 `OUTSTANDING_BALANCE`)? Are non-group settlements also deleted? | Remove text says non-group expenses are deleted; no balance guard text found | low | **DECIDED 2026-11-07 (owner):** removal is never blocked by a balance. The non-group expenses between the two are soft-deleted (the debt is erased) as F-11 and S3-B-4 specify; the shared-group block (409 `SHARED_GROUPS_EXIST`) is unchanged. Mobile must show a confirmation warning stating that non-group expenses and balances with this person will be deleted. Rationale: matches observed reference behaviour and keeps removal simple. Non-group settlements: see OQ-37. |
| 33 | Implicit friendships for every pair of group members is O(n²) rows (19,900 for 200 members). Store them, or derive "friends via shared group" at read time? | Observed behaviour: friends appear via shared groups | med | **DECIDED 2026-11-07 (owner):** derive. Store only explicit friendships (friend code, email, phone). Friend list = explicit active friends UNION users sharing at least one non-deleted group with the caller, computed at read time, backed by an index on `group_members (user_id, group_id)`. Implicit friends have no row, cannot be removed, and vanish when no shared group remains. Rationale: avoids O(n^2) rows (19,900 at 200 members) and stale-pair cleanup. See data_model `friendships`, business_rules §10, S2-B-5, S3-B-4. Follow-up: OQ-37. |
| 34 | `POST /reminders`: must the recipient actually owe the sender (in that scope)? The UI hides the button at balance 0, but the server rule is unspecified. | Not observed | low | **DECIDED 2026-11-07 (owner):** no server check that the recipient owes the sender. Any authorized sender may remind (subject to auth, recipient being a friend or co-member, premium gating and the 60 s rate limit). The UI still hides the button at balance 0. Rationale: balances can change between screens and the check adds a race for no safety gain. See business_rules §10.3, S6-B-3. |
| 37 | Follow-ups to OQ-32/33: (a) an implicit friend (shared group only) with whom the caller has non-group expenses vanishes from `GET /friends` once the last shared group goes, leaving non-group expenses and a possible non-zero balance with nobody in the friend list; (b) on friend removal, are non-group settlements between the two also soft-deleted? Today only expenses are (F-11), which would leave a settlement with no expense. | Not observed | n/a (our design) | Open. Proposal: (a) keep such users in the friend list while a non-deleted non-group expense or settlement exists between the two; (b) soft-delete the pair's non-group settlements too. (c) `POST /friends` on someone who is only an implicit friend: openapi says "idempotent if already friends (200)". The Architect interpretation in business_rules §10.1 creates the explicit row and returns 201 so the friendship survives leaving the group; owner to confirm or choose 200 with no row. Either changes S2-B-4/S3-B-4 behaviour only, not the API shape. Owner to rule. |
| 35 | Group detail (SCR-13) interleaves expenses and payments in one list, but `GET /groups/{id}/expenses` returns expenses only and `GET /settlements` pages separately with its own cursor. A merged timeline needs either client-side merging of two cursors or a new unified endpoint. | Reference list shows payments among expenses | n/a (our design) | Owner decision D-B (progress.md). |
| 36 | Activity badge: SCR-07 shows an unread count capped at "99+", but `ActivityPage` pages at 50 and has no total unread count. | Reference shows a badge | n/a (our design) | Owner decision D-A (progress.md). |

## Decisions needed from the owner
- [ ] **D1. Premium features:** should our app have a paid tier at all? The proposal in business_rules §9 keeps everything core free and gates search, export, totals/charts, conversion, receipt images and scheduled reminders. Decide before Slice 6.
- [ ] **D2. Supported currencies at launch**, and an FX provider if conversion is wanted (Later). Proposal: about 30 major ISO currencies, INR default; no conversion until after MVP.
- [ ] **D3. Category list:** approve our own 7-parent / ~40-child list (not the reference list) and its icons.
- [ ] **D4. Domain and deep-link scheme** for invite, reset and add-friend links (e.g. `https://<yourdomain>/join/<token>`), plus Android App Links verification.
- [ ] **D5. Account deletion:** required by Play policy. Proposal: soft-delete the user, anonymise the name to "Deleted user", keep financial rows so others' balances stay correct.
- [ ] **D6. Group size limit:** proposal 200 members (no reference value found).
- [ ] **D7. Daily free-tier expense cap:** recommend **none** (OQ-19).
- [ ] **D8. Invite delivery for phone contacts:** share sheet (free) vs. SMS provider (cost). Recommend the share sheet.
- [ ] **D9. Google sign-in in V2 or Later?** It needs a Google Cloud project and an OAuth client.
- [ ] **D10. Email provider** for invites, resets and reminders (e.g. SES / Postmark), and the sender domain.
- [ ] **D-A. Unread activity count** (OQ-36): add an `unread_count` integer to `ActivityPage`, or add `GET /activity/unread-count`, or drop the "99+" cap. Blocks S5-M-2.
- [ ] **D-B. Group timeline with payments** (OQ-35): choose client merge of two paged lists, or a unified `GET /groups/{id}/timeline`. Blocks S3-M-3 / S5-M-1 list rendering of payments.
- [ ] **D-C. Missing endpoints**: approve adding each of the following to `openapi.yaml` (shapes proposed in progress.md, 2026-11-07): push-device registration, subscription verification, group invite preview, friend-code lookup, comment delete, avatar upload, account deletion. Blocks the tasks marked Blocked in Slice 6.

## Manual test script (for the owner, in the reference app)
I couldn't run the app. To close the most important questions, please do the following on a phone or emulator with **test accounts and fake names only**. Send me **numbers and screenshots of the split/balance screens only**: no emails, phone numbers, real names or anything that identifies the other app's servers. Use 3 test accounts (A, B, C) in one new group, joined in the order A, B, C.

| Test | Steps | Send me |
|---|---|---|
| T1 Equal remainder | A adds 100.00, paid by A, split equally A/B/C | who owes 33.34 vs 33.33 (3 numbers + names A/B/C) |
| T2 Percent rounding | A adds 10.00, percentages 33.33/33.33/33.34; then try 33.333 | the 3 owed amounts; whether a 3rd decimal is accepted |
| T3 Fractional shares | Shares split, try 1.5 | accepted or refused |
| T4 Negative adjustment | Adjustment split, try −10.00 for B | accepted or refused, and the resulting amounts |
| T9 Simplify default | Create a new group, open settings | on or off |
| T10 Roles | As B (non-creator): rename the group, remove C, open delete | which actions are allowed |
| T13 Edit rights | As C, edit an expense A created between A and B only | allowed / refused / not visible |
| T14a Simplification, chain | New group A, B, C, simplify on. A pays 10.00, split exact: B owes 10.00. B pays 10.00, split exact: C owes 10.00 | group balances screen (expected for us: C pays A 10.00, one payment); then turn simplify off and screenshot again |
| T14b Simplification, 4 people | New group A, B, C, D, simplify on. C pays 25.00, exact: A owes 25.00. D pays 15.00, exact: A owes 5.00, B owes 10.00. Nets: A −30.00, B −10.00, C +25.00, D +15.00 | screenshot of the suggested payments (ours: A→C 25.00, B→D 10.00, A→D 5.00), and each friend screen for A (OQ-28) |
| T15 Overpay | B owes A 30.00; B records a 50.00 payment | accepted? the resulting balance |
| T19 Free cap | Free account: add expenses one after another | the count at which a modal appears, and the timer seconds |
| T20 Passcode | Account → passcode | number of digits; timeout options |
| T22 Recurring reminder | Add an expense, set repeat monthly | the reminder options listed |
| T29 Multi-currency header | Make B owe A in INR and USD | screenshot of the Friends tab header |
| T30 Undo | Delete an expense | whether an undo snackbar appears, and for how long |

To let me run these flows myself next time, either attach an emulator/phone with USB debugging and set REA's `REA_ADB_PATH`, or configure `REA_JADX_MCP_JAR` and `REA_APKTOOL_COMMAND`, then restart REA (see progress.md).
