# Features

> REA: fill this in from UI observation. Describe behavior only. No copied text, assets, or branding.
> Every feature needs an ID, a priority, and testable acceptance criteria with concrete numbers.

## Conventions
- ID format: F-01, F-02, ...
- Priority: MVP / V2 / Later
- Acceptance criteria use Given / When / Then
- Money is in integer minor units (paise/cents), never floats

**How this was produced (applies to every "Evidence" line).** Static analysis only of the reference APK (version name 23.10.1, version code 724, minSdk 24, targetSdk 33). Sources: the decoded manifest, layout resource names, string resource keys (read for meaning, not copied) and DEX class/package names. The app was **not run**: no emulator or adb was available. Wherever a number comes from that inspection it says "observed (static)". Where I chose the number for our app it says "**decision**". Where I guessed what the reference app does it says "**inferred**" and points to an entry in `open_questions.md` (OQ-xx).

Abbreviations: "the reference app" = the analysed APK. "Pro" = its paid tier. Our own app may make different gating choices (see OQ-D1).

---

## F-01: Email + password sign up
- **Priority:** MVP
- **Summary:** A new user creates an account with name, email and password, then lands on the empty home screen.
- **Screens involved:** SCR-02, SCR-03, SCR-07
- **Free or premium:** free

**Acceptance criteria**
1. Given no account exists for `asha@example.com`, When the user submits name "Asha", that email and the 8-character password `abcd1234`, Then the API returns 201 and the app shows SCR-07 with 0 friends and 0 groups.
2. Given the password field holds 7 characters, When the user taps Sign up, Then no request is sent and an inline error says the minimum is 8 characters.
3. Given `asha@example.com` already exists, When the user signs up with it again, Then the API returns 409 and the app shows "email already registered" with no navigation.
4. Given the email field holds `asha@`, When the user taps Sign up, Then no request is sent and an invalid-email error is shown.
5. Given sign up succeeds, When the app is killed and relaunched, Then SCR-07 opens with no login prompt (refresh token stored in the device's secure storage).

**Evidence:** signup fragment and layout; a minimum-8-characters password rule and a 4-level password-strength meter (weak / fair / strong / very strong) observed (static). The strength meter is V2 (F-02).

---

## F-02: Password strength indicator
- **Priority:** V2
- **Summary:** While the password is typed, a 4-level meter shows its strength.
- **Screens involved:** SCR-03, SCR-06
- **Free or premium:** free

**Acceptance criteria**
1. Given the password has 1–7 characters, When it is typed, Then the meter shows level 1 ("too short").
2. Given a 12-character password with upper case, lower case, digits and a symbol, When it is typed, Then the meter shows level 4. (Level thresholds are a **decision**: level 2 = ≥8 characters with 1 character class; level 3 = ≥8 with 3 classes; level 4 = ≥12 with 4 classes.)

**Evidence:** strength-level string keys observed (static); thresholds not recoverable (OQ-05).

---

## F-03: Log in and log out
- **Priority:** MVP
- **Summary:** Email + password login that returns access and refresh tokens; log out clears them.
- **Screens involved:** SCR-04, SCR-11
- **Free or premium:** free

**Acceptance criteria**
1. Given a registered user, When the correct email and password are submitted, Then the API returns 200 with `access_token` (lifetime 900 s) and `refresh_token` (lifetime 30 days), and SCR-07 opens. (Lifetimes are a **decision**.)
2. Given a wrong password, When login is submitted, Then the API returns 401 with code `INVALID_CREDENTIALS` and the app shows one combined "email or password incorrect" error without saying which one was wrong.
3. Given an empty email or empty password, When Log in is tapped, Then no request is sent and the empty field is marked.
4. Given a logged-in user, When they tap Log out on SCR-11 and confirm, Then both tokens are deleted on the device, the refresh token is revoked on the server (a later refresh with it returns 401), and SCR-02 is shown.
5. Given 5 failed logins for one email within 15 minutes, When a 6th is attempted (even with the correct password), Then the API returns 429 with `retry_after_seconds` until the oldest failure leaves the window. (**owner decision 2026-11-09, OQ-38**; business_rules §11.2)
6. Given a refresh token revoked by logout, When it is presented to `/auth/refresh`, Then the API returns 401 `TOKEN_INVALID` and the user's other devices stay signed in (business_rules §11.1).

**Evidence:** login fragment, the combined incorrect-credentials error, and the empty-email / empty-password errors observed (static).

---

## F-04: Session refresh and expiry
- **Priority:** MVP
- **Summary:** An expired access token is refreshed without the user noticing. When the refresh also fails, a session-expired screen asks the user to log in again.
- **Screens involved:** SCR-44, SCR-04
- **Free or premium:** free

**Acceptance criteria**
1. Given the access token expired 1 s ago and the refresh token is valid, When any API call returns 401 `TOKEN_EXPIRED`, Then the client calls `/auth/refresh` once, retries the original call once, and the user sees no error.
2. Given the refresh token is revoked, When a refresh is attempted, Then SCR-44 is shown and local cached data is cleared.
3. Given 3 API calls fail with 401 at the same time, When the refresh runs, Then exactly 1 refresh request is sent (single-flight).

**Evidence:** expired-session screen activity and lifecycle listener observed (static).

---

## F-05: Password reset by email link
- **Priority:** MVP
- **Summary:** The user asks for a reset email, opens the link, and sets a new password of at least 8 characters.
- **Screens involved:** SCR-04, SCR-06
- **Free or premium:** free

**Acceptance criteria**
1. Given a registered email, When "forgot password" is submitted, Then the API returns 202 and sends 1 email whose token expires in 60 minutes. (**decision**)
2. Given an unregistered email, When "forgot password" is submitted, Then the API also returns 202, so the response doesn't reveal whether an account exists.
3. Given a valid token, When a new 8+ character password is set, Then all of the user's refresh tokens are revoked and the user is logged in on this device.
4. Given a token older than 60 minutes or already used, When it is submitted, Then the API returns 410 and the app shows "link expired".

**Evidence:** reset-link handling activities, a `/reset/` deep-link path prefix in the manifest, and a "create a new password" prompt observed (static).

---

## F-06: Third-party sign-in (Google)
- **Priority:** V2
- **Summary:** Sign in with a Google account. The account links to an existing user that has the same verified email.
- **Screens involved:** SCR-02, SCR-04
- **Free or premium:** free

**Acceptance criteria**
1. Given no user has `g@example.com`, When Google sign-in returns a verified token for that email, Then a user is created and the API returns 201 with tokens.
2. Given a user with `g@example.com` exists, When Google sign-in succeeds for that email, Then the API returns 200 for the existing user id (no duplicate account).

**Evidence:** Google sign-in helper fragment plus Google and Facebook SDKs observed (static). Facebook login: OQ-06.

---

## F-07: Login verification challenge (one-time code)
- **Priority:** Later
- **Summary:** For a risky login the server asks for a 6-digit code sent by email or SMS, with a "contact support" exit.
- **Screens involved:** SCR-05
- **Free or premium:** free

**Acceptance criteria**
1. Given the server answers a login with `challenge_required`, When the user picks "email" and enters the correct 6-digit code within 10 minutes, Then tokens are issued.
2. Given 5 wrong codes, When a 6th is entered, Then the challenge is locked and the user must request a new code.

**Evidence:** three login-challenge fragments (request code, enter code, contact support) observed (static). Code length and limits: OQ-07.

---

## F-08: Friends list with balances
- **Priority:** MVP
- **Summary:** A tab that lists every friend with the net balance with them (all groups plus non-group expenses), and an overall summary line.
- **Screens involved:** SCR-08, SCR-19
- **Free or premium:** free

**Acceptance criteria**
1. Given the user is owed 50000 paise by Ravi and owes 12000 paise to Meera (both INR), When SCR-08 opens, Then Ravi's row shows "owes you 500.00", Meera's row shows "you owe 120.00", and the header shows overall "you owe 120.00 and are owed 500.00".
2. Given a friend's balance has been 0 in every currency for more than 30 days, When SCR-08 opens, Then that friend is hidden behind a "show N settled-up friends" row, and tapping it reveals them.
3. Given the filter "friends who owe you" is chosen, When the list renders, Then only friends with a positive balance for the user are shown, and a "no friends owe you" empty state appears if there are none.
4. Given a friend has balances in 2 currencies (500 INR owed to the user, 10 USD owed by the user), When the row renders, Then both amounts are listed separately and never summed.
5. Given A and B were friends only through group G, When G ends for them (either leaves, one removes the other, or G is deleted) and they share no other group, Then B stays in A's list (and A in B's) with the same non-group balance, as an explicit friend (OQ-37a, business_rules §10.1a).

**Evidence:** friends-list layout, balance-filter options layout (all / outstanding / owe you / you owe), the "hiding friends settled up over one month" text and "show N settled-up friends" row observed (static). Exact 1-month rule: OQ-08.

---

## F-09: Add a friend by email or phone
- **Priority:** MVP
- **Summary:** Add someone by email, or by picking a phone contact. If they have no account, a placeholder ("invited") user is created and an invitation is sent.
- **Screens involved:** SCR-21, SCR-08
- **Free or premium:** free

**Acceptance criteria**
1. Given `ravi@example.com` is registered, When the user adds him, Then a friendship exists in both directions and Ravi appears on SCR-08 with balance 0.
2. Given `new@example.com` is not registered, When the user adds "New Person" with that email, Then a placeholder user is created with `is_registered=false`, 1 invitation email is queued, and the person appears on SCR-08 with an "invited" badge.
3. Given the placeholder later signs up with `new@example.com`, When registration completes, Then the placeholder becomes that real account (same user id) and its existing expenses and balances are kept.
4. Given the user enters `abc`, When they tap Add, Then the error "not a valid email or phone number" appears and nothing is created.
5. Given the user tries to add themselves, When they submit their own email, Then the API returns 422 `CANNOT_FRIEND_SELF`.

**Evidence:** the select-people wizard (choose / add new contact / verify / edit), READ_CONTACTS permission, the "not on the app, send an invite?" prompt and the merge-accounts-on-invite flow observed (static).

---

## F-10: Add a friend by link or QR code
- **Priority:** V2
- **Summary:** Each user has a personal add-friend link and QR code. Opening or scanning it makes the two users friends.
- **Screens involved:** SCR-42
- **Free or premium:** free

**Acceptance criteria**
1. Given user A shares their link, When logged-in user B opens it, Then B sees A's name and a confirm button, and confirming creates the friendship.
2. Given B is already A's friend, When B opens the link, Then B is taken to A's friend screen and no duplicate is created.
3. Given A resets the link, When B opens the old link, Then the API returns 410.

**Evidence:** scan-code activity with "my code" and "scan" pages, an `/l/add_friend/` deep-link path, CAMERA permission and a share-code message key observed (static).

---

## F-11: Remove or block a friend
- **Priority:** MVP (remove), V2 (block)
- **Summary:** Remove a friend only when no shared group links you. Removing deletes your non-group expenses with them. Blocking also hides shared groups and mutes them.
- **Screens involved:** SCR-20
- **Free or premium:** free

**Acceptance criteria**
1. Given A and B share 0 groups, When A removes B, Then the friendship is soft-deleted, every non-group expense and every non-group settlement between only A and B is soft-deleted (OQ-37b), and B gets no email or push but sees an activity entry.
2. Given A and B share 1 group, When A tries to remove B, Then the API returns 409 `SHARED_GROUPS_EXIST` and the app lists the shared group. This also applies when B is a friend only because of the shared group (no stored friendship, OQ-33).
2a. Given A and B share 0 groups and have a non-zero non-group balance, When A confirms the removal after the warning dialog, Then the API returns 204 and the non-group expenses and settlements are deleted; a balance never blocks removal (OQ-32).
2b. Given A and B were friends only through group G and G has ended for them (OQ-37a), When A opens B, Then B is an explicit friend and A can remove B (204, subject to AC1 and AC2a); if they share another group, 409 `SHARED_GROUPS_EXIST` applies first, even if an explicit friendship exists.
2c. Given A and B share group G with no explicit friendship, When A adds B with `POST /friends`, Then the API returns 201 and creates the explicit friendship; a repeat returns 200 (OQ-37c).
3. (V2) Given A blocks B, When B later adds a non-group expense with A, Then A gets no notification and the expense is hidden from A's feeds.

**Evidence:** friendship-settings layout with a shared-groups list, "cannot delete friend while in shared groups" text, the remove explanation (non-group expenses deleted, they see it in activity, no email or push) and the block explanation observed (static).

---

## F-12: Create a group
- **Priority:** MVP
- **Summary:** Create a group with a name, a type (home / trip / couple / other) and initial members picked from friends or new contacts.
- **Screens involved:** SCR-12, SCR-21, SCR-13
- **Free or premium:** free

**Acceptance criteria**
1. Given the user enters the name "Goa Trip", picks type `trip` and adds 2 friends, When they tap Done, Then a group exists with 3 members (creator included), `simplify_debts=true` and `default_currency` = the creator's default currency, and SCR-13 opens.
2. Given the name is empty or only spaces, When Done is tapped, Then no request is sent and the name field shows an error.
3. Given the name has 101 characters, When it is submitted, Then the API returns 422 (max 100 characters; **decision**).
4. Given type `trip`, When the user sets the start date 2026-12-20 and end date 2026-12-27, Then both dates are saved. An end date before the start date returns 422.

**Evidence:** group setup fragment, group-type strings (home/apartment, trip with trip dates, couple, other), the trip-dates reminder text and the group first-launch screen observed (static). Default for simplify debts: OQ-09.

---

## F-13: Group invite link
- **Priority:** V2
- **Summary:** Any member can share a join link. Opening it lets a person join, or claim a placeholder member already added under their name.
- **Screens involved:** SCR-17, SCR-18
- **Free or premium:** free

**Acceptance criteria**
1. Given group G has invite token T, When a logged-in non-member opens the link, Then SCR-18 lists G's placeholder members plus "I'm not on this list", and choosing "not on list" adds them as a new member.
2. Given the person picks placeholder "Kiran", When they confirm, Then the placeholder's history is merged into their account and the placeholder disappears.
3. Given a member regenerates the link, When the old token T is used, Then the API returns 410 "invite no longer valid".

**Evidence:** group invite-link and invite-acceptance activities, the "select your name to join / not seeing your name?" prompts, the "anyone with this link can join" warning and a `/join/` deep-link path observed (static).

---

## F-14: Group settings
- **Priority:** MVP
- **Summary:** Rename the group, change type or avatar, manage members, toggle simplify debts, set a personal default split, and leave or delete the group.
- **Screens involved:** SCR-14
- **Free or premium:** free, except the Pro settings section (F-41, F-42)

**Acceptance criteria**
1. Given a member renames the group to "Flat 4B", When they save, Then every member sees the new name and 1 activity entry "renamed group" is created.
2. Given any member (not only the creator), When they open SCR-14, Then every setting is editable. (**inferred**: the reference app shows no admin role; OQ-10.)
3. See F-15 for leave/remove and F-16 for delete.

**Evidence:** group settings fragment and dialog with cells for name, icon buttons, simplify debts, a Pro settings header and Pro button observed (static).

---

## F-15: Leave a group / remove a member
- **Priority:** MVP
- **Summary:** A member can leave, or be removed, only when their balance in that group is 0 in every currency.
- **Screens involved:** SCR-14
- **Free or premium:** free

**Acceptance criteria**
1. Given Ravi's balance in G is 0 INR and 0 USD, When a member removes Ravi, Then `group_members.left_at` is set, Ravi no longer sees G, and his past expenses remain.
2. Given Ravi's balance in G is -1 paise (owes 1 paise), When anyone tries to remove him, Then the API returns 409 `OUTSTANDING_BALANCE` and the app explains the debts must be settled first.
3. Given the user's own balance is +2500 paise, When they tap Leave group, Then the API returns 409 `OUTSTANDING_BALANCE`.
4. Given an expense includes a member who has left, When anyone tries to edit it, Then the API returns 409 `EXPENSE_HAS_DEPARTED_MEMBER`. Deleting it is still allowed.
5. Given Ravi leaves G (or is removed) and he and member Meera share no other group, When the call succeeds, Then in the same transaction they become explicit friends (one `active` friendship, no activity entry, no notification) and each stays in the other's friend list; a pair that still shares another group is unchanged. A refused call (409) changes nothing (OQ-37a, business_rules §10.1a).

**Evidence:** "can't leave/remove with outstanding debts" alerts and the "expense involves someone who left, can no longer be edited" error observed (static).

---

## F-16: Delete and restore a group
- **Priority:** MVP (delete), V2 (restore)
- **Summary:** Deleting a group removes it for all members after a strong confirmation. A deleted group can be restored.
- **Screens involved:** SCR-14
- **Free or premium:** free

**Acceptance criteria**
1. Given group G with 3 members, When a member deletes G and confirms twice, Then `groups.deleted_at` is set, G disappears for all 3 members, and its expenses no longer count in any balance.
1a. Given G is deleted, When the call succeeds, Then every pair of its members that shares no other non-deleted group becomes explicit friends in the same transaction (no activity entry, no notification), so nobody vanishes from anyone's friend list (OQ-37a, business_rules §10.1a).
2. (V2) Given G was deleted, When a former member restores it from the activity entry, Then `deleted_at` is cleared and every balance is exactly what it was before the delete.

**Evidence:** "absolutely sure, removes for ALL users" confirmation and an undelete-group action observed (static).

---

## F-17: Simplify debts toggle
- **Priority:** MVP
- **Summary:** A per-group switch. When on, group balances are shown as the reduced set of payments from F-33 instead of pairwise debts.
- **Screens involved:** SCR-14, SCR-15, SCR-40
- **Free or premium:** free

**Acceptance criteria**
1. Given G has A owes B 1000 and B owes C 1000 with simplify on, When SCR-15 opens, Then exactly 1 suggested payment is shown: A pays C 1000.
2. Given the same data with simplify off, When SCR-15 opens, Then 2 payments are shown: A pays B 1000 and B pays C 1000.
3. Given a member toggles the switch, When it saves, Then 1 activity entry is created, every member sees the same mode, and no stored expense or net balance changes.
4. Given the info link is tapped, When SCR-40 opens, Then a 3-person worked example is shown.

**Evidence:** simplify-debts setting cell, on/off confirmation toasts, the explanation activity (3 flatmates, $10 example) and the "how was this balance calculated?" overlay observed (static).

---

## F-18: Add an expense (core fields)
- **Priority:** MVP
- **Summary:** Record an expense: with whom (friends and/or one group), description, amount, currency, date, payer(s) and split. Defaults to "paid by you, split equally".
- **Screens involved:** SCR-22, SCR-23, SCR-24, SCR-27
- **Free or premium:** free (see F-46 for a possible daily cap)

**Acceptance criteria**
1. Given group G with A, B, C and the user A, When A enters "Dinner", 900.00 INR and saves without opening the split screen, Then 1 expense is stored with `total_amount_minor=90000`, payer A 90000, splits A 30000, B 30000, C 30000, and A's group balance becomes +60000.
2. Given the description is empty, When Save is tapped, Then the error "description required" appears and nothing is saved.
3. Given the amount is empty or 0, When Save is tapped, Then the error "amount required" appears. Negative amounts can't be typed (minus key ignored).
4. Given the amount 99,999,999.99 (9,999,999,999 minor units), When saved, Then it is accepted. Given 100,000,000.00, Then the input is refused with a maximum-amount error.
5. Given the amount 12.345 in a 2-decimal currency, When typed, Then the 3rd decimal is rejected at input. In a 0-decimal currency (JPY), the decimal separator is rejected.
6. Given the user adds 2 groups to "with", When the 2nd group is added, Then it is refused with "only one group per expense".
7. Given a non-group expense that doesn't include the current user as payer or participant, When saved, Then the API returns 422 `CURRENT_USER_NOT_INVOLVED`. Inside a group this is allowed.
8. Given the date is left unchanged, When saved, Then the expense date = today in the device's time zone.

**Evidence:** add-expense screen and add-detail fragments (date, group picker, note, image), the currency-amount input filter, a "cannot be above 99,999,999.99" error, "one group per expense", "must involve yourself unless in a group", "must enter an amount" and "must enter a description" observed (static).

---

## F-19: Categories
- **Priority:** MVP
- **Summary:** Each expense has one category from a fixed two-level list (parent → child). Default is "uncategorized". The picker is searchable.
- **Screens involved:** SCR-25
- **Free or premium:** free

**Acceptance criteria**
1. Given no category is chosen, When the expense saves, Then `category_id` = the seeded "uncategorized" category.
2. Given the user types "taxi" in the picker, When results show, Then only matching child categories (case-insensitive substring) are listed under their parent heading.
3. Given seed data, When `/categories` is called, Then 7 parents are returned, each with ≥2 children. (**decision**: our own list, 7 parents and about 40 children. The reference app ships 48 entries under 7 parents, observed (static).)

**Evidence:** category chooser fragment, a "search or select a category" hint, 48 numbered category resources grouped under 7 parents observed (static). Automatic category suggestion from the description: OQ-11.

---

## F-20: Split equally
- **Priority:** MVP
- **Summary:** Choose which participants share the cost. The amount divides equally, and any leftover minor units go out deterministically (business_rules §2.1).
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given total 10000 and 3 selected people, When saved, Then the splits are 3334, 3333, 3333 (the first person in canonical order gets the extra unit) and they sum to 10000.
2. Given total 10000 and 2 of 3 people selected, When the screen renders, Then it shows about 50.00 per person, and the unselected person's split = 0.
3. Given 0 people selected, When Done is tapped, Then the error "select at least 1 person" appears.

**Evidence:** equal-split fragment and cell, "select at least 1 person", "~X/person" and "(N people)" labels observed (static). Remainder rule: OQ-01.

---

## F-21: Split by exact amounts
- **Priority:** MVP
- **Summary:** Enter each person's owed amount. They must add up to the total exactly, and a live counter shows the amount over or under.
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given total 10000 and entries 5000, 3000, 2000, When Done is tapped, Then it saves.
2. Given entries 5000, 3000, 1000, When the screen updates, Then it shows "1000 left" and Done is refused with "under by 10.00".
3. Given entries 5000, 3000, 3000, Then it shows "over by 10.00" and Done is refused.

**Evidence:** exact-amounts fragment, the "per-person amounts don't add up to the total, over/under by X" errors and an "X of Y" counter observed (static).

---

## F-22: Split by percentages
- **Priority:** MVP
- **Summary:** Enter a percentage per person (up to 2 decimals). They must add up to exactly 100%.
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given total 1000 and 33.33% / 33.33% / 33.34%, When saved, Then the splits are 333, 333, 334 (business_rules vector 9).
2. Given 50% / 49%, When the screen updates, Then it shows "1% left" and Done is refused with "under by 1%".
3. Given 60% / 50%, Then it shows "10% over" and Done is refused.

**Evidence:** percentage-split fragment, "X% left", "X% over", "X% of 100%" and the over/under-100% errors observed (static). Decimal precision: OQ-02.

---

## F-23: Split by shares
- **Priority:** MVP
- **Summary:** Give each person a number of shares; the cost is divided in proportion to the shares.
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given total 10000 and shares 1, 2, 2, When saved, Then the splits are 2000, 4000, 4000.
2. Given total 10000 and shares 2, 1, Then the splits are 6667, 3333.
3. Given every share is 0, When Done is tapped, Then the error "assign at least 1 share" appears.
4. Given shares 1, 2, 2, When the screen renders, Then the footer shows "5 total shares".

**Evidence:** shares-split fragment, "at least 1 share", "N total shares" and the nights/families explanation observed (static). Fractional shares: OQ-03.

---

## F-24: Split by adjustment
- **Priority:** MVP
- **Summary:** Enter the extra amount each person owes. The rest is split equally among all selected participants.
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given total 10000 with 3 people and adjustment +1000 for A, When saved, Then the splits are A 4000, B 3000, C 3000.
2. Given adjustments A 6000 and B 5000 on a 10000 total, When Done is tapped, Then it is refused with "adjustments exceed the total by 10.00".
3. Given adjustments that add up to exactly the total (10000), When saved, Then each person owes exactly their adjustment and the equal part is 0.

**Evidence:** adjustment-split fragment and cell, the "enter adjustments, remainder distributed equally" detail and the "cannot exceed the total, over by X" error observed (static). Negative adjustments: OQ-04.

---

## F-25: Two-person quick split choices
- **Priority:** MVP
- **Summary:** When an expense involves exactly 2 people, offer 4 one-tap options: you paid, split equally / they paid, split equally / you are owed the full amount / they are owed the full amount.
- **Screens involved:** SCR-23
- **Free or premium:** free

**Acceptance criteria**
1. Given you (A) and B on a total of 5000, When "you are owed the full amount" is chosen, Then payer A 5000, splits A 0 and B 5000, and B's balance with A = -5000.
2. Given the same, When "they paid, split equally" is chosen, Then payer B 5000, splits 2500 / 2500.
3. Given 3 participants, When the split screen opens, Then the 4 quick options are not shown.

**Evidence:** two-person split-choices fragment with you-paid / you-owe cells and the four option labels observed (static).

---

## F-26: Multiple payers
- **Priority:** MVP
- **Summary:** More than one person can pay for an expense. Paid amounts must add up to the total. One person appears at most once among payers.
- **Screens involved:** SCR-24
- **Free or premium:** free

**Acceptance criteria**
1. Given total 9000 with payers A 6000 and B 3000, split equally among A, B, C, When saved, Then the nets are A +3000, B 0, C -3000.
2. Given payers A 6000 and B 2000 for 9000, When Done is tapped, Then it is refused with "under by 10.00".
3. Given A is listed twice as payer, When the request reaches the API, Then it returns 422 `DUPLICATE_PAYER`.

**Evidence:** multiple-payers fragment, "enter paid amounts", "paid by N people" and "one person cannot pay multiple shares" observed (static).

---

## F-27: Personal default split per group
- **Priority:** V2
- **Summary:** Each user can set their own default split for a group (for example 60/40). It only affects new expenses that user adds there.
- **Screens involved:** SCR-14, SCR-22
- **Free or premium:** unknown (OQ-12)

**Acceptance criteria**
1. Given A set a default of percentages A 60% / B 40% in G, When A adds a 10000 expense in G, Then the split pre-fills as 6000 / 4000.
2. Given the same group, When B adds an expense, Then B's default (equal unless B set one) is used, not A's.

**Evidence:** "default split" settings text saying the setting is personal, not group-wide, and that unequal default splits with friends are "coming soon" observed (static).

---

## F-28: Notes and receipt image on an expense
- **Priority:** MVP (notes), V2 (image)
- **Summary:** Free-text notes up to 2000 characters (**decision**) and one image (JPEG/PNG up to 10 MB; **decision**) attached to an expense.
- **Screens involved:** SCR-28, SCR-29
- **Free or premium:** notes free; image upload premium in the reference app (observed (static); our choice is OQ-D1)

**Acceptance criteria**
1. Given a note of 2000 characters, When saved, Then it is stored and shown on SCR-29. 2001 characters returns 422.
2. Given a 4 MB JPEG, When attached and saved, Then `receipts` has 1 row linked to the expense and SCR-29 shows a thumbnail.
3. Given an 11 MB image, When attached, Then the API returns 413 and the expense still saves without it.

**Evidence:** note-entry and edit-image fragments, crop library, the "receipt uploading is a Pro feature" text and CAMERA and READ_MEDIA_IMAGES permissions observed (static).

---

## F-29: Edit an expense
- **Priority:** MVP
- **Summary:** Any participant can edit any field. Balances recalculate, and an activity entry records the change.
- **Screens involved:** SCR-29, SCR-22
- **Free or premium:** free

**Acceptance criteria**
1. Given expense E (9000, equal among A, B, C) and A's group balance +6000, When B edits E to 12000, Then splits become 4000 × 3, A's balance becomes +8000, and 1 `expense.updated` activity entry is created with the before and after totals.
2. Given two clients edit E, When the second sends a stale `version`, Then the API returns 409 `VERSION_CONFLICT`.
3. Given E includes a departed member, Then editing is refused (F-15 AC4).

**Evidence:** edit-expense key, "expense updated/deleted" notification channel and the departed-member edit block observed (static). Who may edit: OQ-13.

---

## F-30: Delete and restore an expense
- **Priority:** MVP
- **Summary:** Delete is a soft delete for everyone involved, with a confirmation. Any participant can restore it later.
- **Screens involved:** SCR-29
- **Free or premium:** free

**Acceptance criteria**
1. Given E with A +6000, When B deletes E and confirms, Then `deleted_at` is set, A's balance returns to 0, and SCR-29 shows "deleted by B on <date>" with a Restore button.
2. Given E was deleted, When A taps Restore, Then the balances are exactly as before the delete and 1 `expense.restored` activity entry is created.
3. Given E is already deleted, When another client deletes it, Then the API returns 409 `ALREADY_DELETED`. Restoring an expense that isn't deleted returns 409 `NOT_DELETED`.
4. Given a deleted expense, When a comment is attempted, Then it is refused until the expense is restored.

**Evidence:** "delete for ALL people involved" confirmation, undelete actions, "already deleted / already restored" errors, "deleted by X on DATE" labels and "restore to add a comment" observed (static).

---

## F-31: Non-group expenses
- **Priority:** MVP
- **Summary:** An expense with friends but no group. It counts in the friend balance under "non-group expenses".
- **Screens involved:** SCR-22, SCR-19
- **Free or premium:** free

**Acceptance criteria**
1. Given A and B share no group, When A adds a 2000 expense with B split equally, Then the expense has `group_id = null` and the A–B balance = +1000 for A.
2. Given A and B also share group G with B owing A 500, When A opens B's friend screen, Then the total shows B owes A 1500, broken down as "non-group: 1000" and "G: 500".

**Evidence:** explanatory text about expenses that belong to no group, and balance cells labelled for in-group and non-group observed (static).

---

## F-32: Group balances screen
- **Priority:** MVP
- **Summary:** Shows each member's net balance per currency, and the suggested payments (simplified or pairwise, F-17).
- **Screens involved:** SCR-15
- **Free or premium:** free

**Acceptance criteria**
1. Given nets A +4500, B +500, C -2500, D -2500 (INR), When SCR-15 opens, Then 4 rows show those nets, they sum to 0, and each row expands to list its payments.
2. Given every net is 0, When SCR-15 opens, Then an "all settled up in this group" state is shown.

**Evidence:** group-balances screen, list and cells, the group-repayments cell and settled-up states observed (static).

---

## F-33: Debt simplification (computation)
- **Priority:** MVP
- **Summary:** Compute a list of payments that settles every member's net balance using at most N−1 payments for N non-zero members (business_rules §5).
- **Screens involved:** SCR-15, SCR-30
- **Free or premium:** free

**Acceptance criteria**
1. Given nets A -3000, B -1000, C +2500, D +1500, When simplified, Then the payments are A→C 2500, B→D 1000, A→D 500 (3 payments, exact order per business_rules vector 20).
2. Given any group, When simplified, Then the number of payments ≤ (number of non-zero members − 1) and applying them makes every net 0.

**Evidence:** simplify-debts explanation text observed (static). The reference algorithm is not recoverable (OQ-14).

---

## F-34: Settle up (record a payment)
- **Priority:** MVP
- **Summary:** Record a cash payment from one person to another, in full or in part, inside a group or across all shared balances.
- **Screens involved:** SCR-30, SCR-31
- **Free or premium:** free

**Acceptance criteria**
1. Given B owes A 5000 in G, When B records a payment of 5000 to A in G, Then their G balance becomes 0 and SCR-13 shows "settled up".
2. Given the same debt, When B records 2000, Then B still owes A 3000.
3. Given the payment amount is 0, Then Save is refused with "enter an amount greater than 0".
4. Given B owes A 3000, When B records 5000, Then the app warns the amount is larger than the balance, and on confirm A owes B 2000. (**decision**; OQ-15)
5. Given B owes A 1000 in G1 and 2000 non-group, When B chooses "settle all balances" with A, Then 2 settlements are created (1000 in G1, 2000 non-group) and the friend balance becomes 0.
6. Given a balance in INR, When the payment screen opens, Then the currency pre-fills as INR and the amount as the full balance.

**Evidence:** add-payment activity, balance chooser, person chooser, record-payment fragment, a "settle all balances" option, a "total in currency" label and a "greater than 0" amount error observed (static).

---

## F-35: Edit, delete and restore a payment
- **Priority:** MVP
- **Summary:** A recorded payment can be edited or deleted (soft) and restored, just like an expense.
- **Screens involved:** SCR-32
- **Free or premium:** free

**Acceptance criteria**
1. Given payment P of 2000 from B to A, When A deletes P, Then the B→A balance grows back by 2000 and P can be restored.
2. Given P is edited to 2500, When saved, Then the balance moves by a further 500.

**Evidence:** payment details fragment, edit-payment layout, delete-payment and restore-payment confirmations observed (static). Rules for third-party payment services are out of scope.

---

## F-36: Activity feed
- **Priority:** MVP
- **Summary:** Reverse-chronological feed of events that involve the user: expenses added, edited, deleted or restored; payments; comments; group changes; friendships. Each item shows its effect on the user ("you owe 100.00" or "you get back 50.00").
- **Screens involved:** SCR-10
- **Free or premium:** free

**Acceptance criteria**
1. Given B adds a 9000 expense equal among A, B, C, When A opens SCR-10, Then the top item names B, the expense, and "you owe 30.00".
2. Given 120 activity items, When SCR-10 loads, Then the first page has 50 items and scrolling loads the next 50 with cursor pagination. (**decision**)
3. Given no activity, Then an empty state is shown.
4. Given an item is tapped, When it refers to an expense, Then SCR-29 opens. A deleted expense shows with a restore option.

**Evidence:** recent-activity screen with header, empty view and an ad slot layout observed (static).

---

## F-37: Comments on an expense
- **Priority:** MVP
- **Summary:** Participants can comment on an expense. System comments record edits.
- **Screens involved:** SCR-29
- **Free or premium:** free

**Acceptance criteria**
1. Given expense E, When A posts "paid in cash" (≤ 1000 characters; **decision**), Then it appears under E for all participants and 1 notification goes to each other participant.
2. Given an empty or whitespace-only comment, When Send is tapped, Then nothing is sent.
3. Given B edits E's amount, When A opens E, Then a system comment describes the change (old total → new total).
4. Given A deletes their own comment, Then it is removed. Deleting someone else's comment returns 403. (No delete-comment endpoint exists in the contract yet; progress.md, decision D-C. Not in any slice until decided.)

**Evidence:** expense-details cells for the current user's comment, another user's comment and a system comment, the comment bar fragment, "N new comments" and the comments notification channel observed (static).

---

## F-38: Push notifications
- **Priority:** V2
- **Summary:** Push notifications by event type, each type with its own toggle.
- **Screens involved:** SCR-34
- **Free or premium:** free

**Acceptance criteria**
1. Given A has "expense added" on, When B adds an expense with A, Then A receives exactly 1 push within 60 s.
2. Given A turns "comments" off, When B comments, Then A gets no push but the activity entry still appears.
3. Given B adds an expense, When B's own device registers, Then B does not receive a push for their own action.
4. The types are: expense added, expense updated/deleted, comment added, added to group, removed from group, group updated/deleted, added as friend, friend removed, payment recorded, reminder. That is 10 types, each a boolean preference defaulting to on.

**Evidence:** a messaging service, POST_NOTIFICATIONS permission and notification-channel description strings for each listed type observed (static).

---

## F-39: Manual reminder to settle up
- **Priority:** V2
- **Summary:** From a friend or a group balance, send a reminder by in-app email or through the device share sheet. The message includes a link to settle up.
- **Screens involved:** SCR-33
- **Free or premium:** free

**Acceptance criteria**
1. Given B owes A 2500, When A taps Remind → "send via app", Then 1 reminder email to B is queued and a "reminder sent" toast is shown.
2. Given A sent a reminder to B less than 60 s ago, When A sends another, Then the API returns 429 with "wait 1 minute".
3. Given A chooses "share", When the share sheet opens, Then the prefilled text holds the amount (25.00 INR) and a settle-up link, and no server email is sent.

**Evidence:** remind screen, send-reminder dialog, "send limit exceeded, wait 1 minute" and the reminder message templates observed (static).

---

## F-40: Recurring expenses
- **Priority:** V2
- **Summary:** An expense can repeat weekly, fortnightly, monthly or yearly. Each occurrence creates a new expense on its date. An optional email reminder goes out N days before.
- **Screens involved:** SCR-27, SCR-22
- **Free or premium:** free

**Acceptance criteria**
1. Given "Rent" 2,000,000 paise monthly starting 2026-01-31, When the scheduler runs, Then occurrences are created on 2026-01-31, 2026-02-28, 2026-03-31 and 2026-04-30 (the day is clamped to the month's last day).
2. Given interval `fortnightly` starting 2026-01-01, When occurrences are created, Then they fall on 01-01, 01-15 and 01-29.
3. Given a reminder 2 days before, When the 2026-02-28 occurrence is due, Then reminders are queued on 2026-02-26.
4. Given a member has left the group, When the next occurrence is created, Then that member is dropped from the split and the cost is re-split among the remaining participants with the same split type. (**decision**; OQ-16)
5. Given the user sets repeat to "never" on the latest occurrence, Then no future occurrences are created and past ones are unchanged.
6. Given the scheduler was down for 3 days, When it restarts, Then each missed occurrence is created exactly once (idempotent on `(rule_id, occurrence_date)`).

**Evidence:** repeat setting with the values never / weekly / fortnightly / monthly / yearly, "repeats X" label, the reminder-before-repeat and day-of-repeat reminder texts and a background job manager observed (static).

---

## F-41: Settle-up reminders on a schedule (group)
- **Priority:** Later
- **Summary:** A group setting that reminds members to settle up weekly on a weekday or monthly on a day (or the last day).
- **Screens involved:** SCR-14
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given monthly on day 31, When the month is February 2027, Then the reminder goes out on 2027-02-28.
2. Given the setting is turned on without a day chosen, When saved, Then it is refused with "select a day".

**Evidence:** reminder cadence picker modal with weekly, fixed-dates and frequency layouts, "settles on day N every month / last day / weekday every week" and "settle up reminders are a Pro feature" observed (static).

---

## F-42: Balance alerts
- **Priority:** Later
- **Summary:** Notify the user when what they are owed in a group crosses a threshold they set.
- **Screens involved:** SCR-14
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given a threshold of 500000 paise, When the user's group balance goes from 480000 to 510000, Then exactly 1 alert is sent. It is not sent again until the balance falls below 500000 and crosses it again.

**Evidence:** balance-threshold reminder settings layout, the balance-alert texts and "balance alerts are a Pro feature" observed (static).

---

## F-43: Multi-currency expenses
- **Priority:** MVP
- **Summary:** Each expense has its own ISO 4217 currency, defaulting to the group's or the user's default. Balances are kept and shown per currency and never summed across currencies.
- **Screens involved:** SCR-22, SCR-26, SCR-15, SCR-08
- **Free or premium:** free

**Acceptance criteria**
1. Given G default INR, When A adds an expense without changing the currency, Then its currency = INR.
2. Given B owes A 1000 INR and 500 USD, When balances are read, Then 2 entries are returned (INR 1000, USD 500) and no combined total.
3. Given JPY (exponent 0), When 1000 is entered, Then `amount_minor=1000`. For INR, 10.00 → 1000.
4. Given the user searches "rupee" in the currency picker, Then INR appears.

**Evidence:** currency chooser fragment with search, the currency-code field on the expense, "unsynced because no currency" and per-currency "total X balance" labels observed (static).

---

## F-44: Convert balances to one currency
- **Priority:** Later
- **Summary:** A one-off action that converts all of a group's (or a friend's non-group) transactions to the user's default currency at the current rate. It can't be undone.
- **Screens involved:** SCR-14, SCR-20
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given a 1000 USD-cent expense and rate 83.2156 INR per USD, When converted, Then the expense becomes 83216 paise (round half up) and the original currency, amount and rate are kept in `fx_conversion` fields.
2. Given the confirmation dialog, When the user cancels, Then nothing changes.

**Evidence:** "convert to X", the group and non-group conversion confirmations (current international rate, cannot be undone) and "conversion is a Pro feature" observed (static). Rate source: OQ-17.

---

## F-45: Export
- **Priority:** V2
- **Summary:** Export one group's or one friend's expenses and payments as a CSV file the user can share.
- **Screens involved:** SCR-14, SCR-20
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given G with 3 expenses and 1 payment, When export is requested, Then a CSV with 1 header row + 4 data rows is produced. Columns: date, description, category, cost, currency, then one column per member with that member's net for the row. A final balance row totals each member's column.
2. Given amounts in minor units, When written to CSV, Then they are formatted with the currency exponent (90000 INR → `900.00`) using a dot decimal separator and no thousands separator.
3. Given export takes more than 2 s, When it runs, Then the app shows "generating" and then the share sheet.

**Evidence:** export action, "generating spreadsheet", "export for <relationship>" file title, and "export is a Pro feature" observed (static). Exact column layout: OQ-18.

---

## F-46: Free vs premium gating and the daily add-expense limit
- **Priority:** V2
- **Summary:** A subscription tier unlocks the gated features. The reference app also has a server-driven upsell modal on add-expense, with a countdown timer button.
- **Screens involved:** SCR-39
- **Free or premium:** n/a

**Acceptance criteria**
1. Given a free user, When they tap a premium feature (search, charts, export, conversion, group totals, receipt image, reminders, balance alerts), Then SCR-39 opens and the feature does not run.
2. Given a premium user, When they tap the same feature, Then it runs and SCR-39 is not shown.
3. Given the server reports the user's entitlement expired, When the app refreshes `/users/me`, Then the gated features re-lock within one app session.
4. (Conditional on OQ-19) Given a free user has added N expenses today, When they add the (N+1)th, Then they must wait T seconds or upgrade. N and T are server-configured.

**Evidence:** Pro offline messages for 9 features, an in-app billing client fragment, a native-ad modal with an offered-plan list and a timer button, and an add-expense key with a "pro 2023-07" suffix observed (static). Values of N and T are not in the APK (OQ-19).

---

## F-47: Search expenses
- **Priority:** V2
- **Summary:** Search across all of the user's expenses by description, notes or amount, or within one friend.
- **Screens involved:** SCR-36
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given expenses "Dinner Goa" and "Groceries", When the user searches "goa", Then exactly 1 result is returned (case-insensitive substring on description and notes).
2. Given search "450", When run, Then expenses whose total is 450.00 in their currency are returned.

**Evidence:** all-expenses screen, search menu, "search expenses with friend" and "search is a Pro feature" observed (static).

---

## F-48: Charts and group spending totals
- **Priority:** Later
- **Summary:** Spending by category and by month for a group. A group totals screen shows total group spend and the user's share for a chosen period.
- **Screens involved:** SCR-16, SCR-37
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given G with expenses 9000 (Food) and 3000 (Taxi) in November 2026, of which the user's share is 4000, When group totals for "this month" are opened, Then total spending = 12000 and the user's share = 4000.
2. Given period "all time", Then payments are excluded from both totals.

**Evidence:** group totals screen and layout ("spending summary"), a date-range picker modal, charts screen title and the Pro messages for charts and group totals observed (static).

---

## F-49: Receipt scanning and itemization
- **Priority:** Later
- **Summary:** Scan a paper receipt with the camera, detect the merchant, date, total and line items, then assign each item to people.
- **Screens involved:** SCR-43
- **Free or premium:** premium in the reference app

**Acceptance criteria**
1. Given a scan detects items 300, 200 and 500 (total 1000) assigned A: item 1, B: item 2, A+B: item 3, When confirmed, Then the expense splits are A 550 and B 450.
2. Given any item is left unassigned, When Next is tapped, Then it is refused with "every item must be assigned".

**Evidence:** a third-party receipt OCR SDK with native libraries, camera-scan activity, itemization wizard (review items, confirmation), "assign all items" error and "receipt scanning is a Pro feature" observed (static).

---

## F-50: App lock (passcode and biometrics)
- **Priority:** V2
- **Summary:** An optional 4-digit passcode, with biometric unlock, required after the app has been in the background longer than a timeout.
- **Screens involved:** SCR-35, SCR-11
- **Free or premium:** free

**Acceptance criteria**
1. Given the passcode is on with a 5-minute timeout, When the app returns from 4 min 59 s in the background, Then no lock is shown. After 5 min 01 s, SCR-35 is shown.
2. Given 5 wrong passcodes, When a 6th is tried, Then input is disabled for 30 s. (**decision**)
3. Given biometrics are enrolled, When SCR-35 opens, Then the biometric prompt appears first, with the passcode as fallback.

**Evidence:** passcode activity, biometrics helper, lock lifecycle listener, change-passcode / change-timeout / turn-off actions and fingerprint error strings observed (static). Passcode length: OQ-20.

---

## F-51: Account settings
- **Priority:** MVP
- **Summary:** Edit name, email, phone, default currency, time zone and avatar, and manage notification preferences.
- **Screens involved:** SCR-11, SCR-34
- **Free or premium:** free

**Acceptance criteria**
1. Given the default currency is INR, When the user picks USD, Then `PATCH /users/me` saves `default_currency=USD` and new non-group expenses default to USD. Existing expenses keep their currency.
2. Given a new email already used by another account, When saved, Then the API returns 409.
3. Given an avatar over 5 MB, When uploaded, Then the API returns 413. (No avatar upload endpoint exists in the contract yet; progress.md, decision D-C. Not in any slice until decided.)

**Evidence:** account tab layout, avatar helper, country picker, "I use X as my currency" and device-settings activity observed (static).

---

## F-52: Group whiteboard
- **Priority:** Later
- **Summary:** A shared free-text note on the group (for example, the landlord's contact details). Every member can edit it.
- **Screens involved:** SCR-41
- **Free or premium:** free

**Acceptance criteria**
1. Given a member saves 500 characters of text, When another member opens the whiteboard, Then they see the same text and the last-edited-by name.
2. Given 10001 characters, When saved, Then the API returns 422. (max 10000; **decision**)

**Evidence:** whiteboard screen and layout, with a footer warning not to store sensitive information, observed (static).

---

## F-53: Offline cache and background sync
- **Priority:** V2
- **Summary:** The app shows cached data offline and queues new expenses until it reconnects.
- **Screens involved:** all list screens
- **Free or premium:** free

**Acceptance criteria**
1. Given airplane mode, When the user opens SCR-08, Then the last cached balances are shown with an "offline" banner.
2. Given an expense was added offline, When connectivity returns, Then it is sent exactly once (client-generated `idempotency_key`) and the "unsynced" marker disappears.
3. Given a queued expense is rejected by the server (422), When sync runs, Then the item shows "tap for error details" and is not retried automatically.

**Evidence:** a local database with 36 schema migrations and DAOs for expenses, groups, friends, balances and notifications; background refresh and expense workers; ACCESS_NETWORK_STATE; "sync in progress"; and the "tap for error details" expense-cell subtitle observed (static).

---

## F-54: Deep links
- **Priority:** V2
- **Summary:** App links open the right screen: group join, add friend, password reset, magic login, specific expense.
- **Screens involved:** SCR-01
- **Free or premium:** free

**Acceptance criteria**
1. Given a logged-out user opens a group-join link, When they log in, Then they continue to SCR-18 for that group (the link survives login).
2. Given an unknown link path, When opened, Then SCR-07 opens with no error.

**Evidence:** manifest intent filters for several path prefixes (join, reset, add friend, and others) on the launch activity, plus magic-login and share-sheet link-handling activities, observed (static). Our own domain and paths are a **decision** (OQ-D4).

---

## Out of scope (observed but not to build)
- In-app money transfer, bank linking, debit cards, wallet and KYC flows (large `p2p`, `cards`, `paybybank`, Plaid packages): regulated fintech, US-specific. **Later / not planned.**
- Hand-offs to third-party payment apps (the manifest queries packages for two payment apps). **Later**, optional.
- Ads, promotion modules, "we're hiring" banners, debug panel, screenshot detector, rate-the-app prompt.

---

## Feature checklist (REA: keep, expand, or mark "not present")
- [x] Sign up / login (email, phone, social): **present**. Email+password F-01/F-03; Google F-06; Facebook SDK present, use unclear (OQ-06); phone used for invites and verification codes, not as a login identifier (OQ-07).
- [x] Friends and contacts: **present**. F-08, F-09, F-10, F-11 (contacts permission observed).
- [x] Groups: create, members, settings, simplify-debts toggle: **present**. F-12 to F-17.
- [x] Add expense: fields, categories, notes, receipts, currency: **present**. F-18, F-19, F-28, F-43.
- [x] Split types: equal, exact, percent, shares, adjustment: **present** (all 5). F-20 to F-24, plus two-person shortcuts F-25.
- [x] Multiple payers: **present**. F-26.
- [x] Balances (per group, per friend, overall): **present**. F-08, F-31, F-32.
- [x] Settle up and partial settlements: **present**. F-34, F-35.
- [x] Debt simplification: **present**. F-17, F-33.
- [x] Activity feed and comments: **present**. F-36, F-37.
- [x] Notifications and reminders: **present**. F-38, F-39, F-41, F-42.
- [x] Recurring expenses: **present**. F-40.
- [x] Multi-currency and conversion: **present**. F-43 (free), F-44 (Pro).
- [x] Export: **present** (Pro). F-45.
- [x] Settings: **present**. F-14, F-50, F-51.
- [x] Free vs premium gating: **present**. F-46.
- [x] Search: **present** (Pro). F-47.
- [x] Charts / group totals: **present** (Pro). F-48.
- [x] Receipt scanning / itemization: **present** (Pro). F-49.
- [x] App lock: **present**. F-50.
- [x] Group whiteboard: **present**. F-52.
- [x] Offline cache and sync: **present**. F-53.
- [x] In-app payments / wallet / cards: **present but out of scope**.
- [ ] Budgets or spending limits per category: **not present** (no evidence found).
- [ ] Dark-mode toggle in settings: **not present** as a setting (only the platform theme was seen; OQ-21).
- [ ] Account deletion: **not observed** in the APK. Required by store policy, so add it to our app (OQ-D5).
