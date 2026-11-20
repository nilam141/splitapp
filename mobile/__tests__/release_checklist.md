# Release checklist (S6-Q-3)

Location note: tasks.md does not name a path, `docs/` belongs to the Architect, so this file lives in the QA-owned test
tree. Ticked means verified in the session of 2026-11-20 on the evidence shown; unticked means not done, with the reason.
tasks.md asks for "all items ticked": that is NOT met, see the unticked items.

## 1. Accessibility (TalkBack labels on every money value)
- [x] Money texts on the Groups tab, Friends tab, Friend detail, Group detail and Balances screens carry an unsigned
      accessibility label wherever the visible text has a sign (37 money texts, 0 without), checked on an API 36 emulator
      with `mobile/__tests__/e2e/a11y_money_labels.py` (reads the uiautomator hierarchy).
- [ ] Same audit on the remaining screens (activity feed, expense detail, settle up, record payment, remind, paywall,
      export, search, recurring label). Not run: only five screens were audited.
- [ ] Spoken pass with TalkBack switched on (reading order, focus, "minus" read as "owes"). Not run: needs a person or
      a TalkBack-enabled run; the hierarchy check only proves a label exists.
- [ ] Touch targets 48dp and font scale 130% on money rows. Not run on a device (jest covers the component sizes).

## 2. No floats in money paths
- [x] Backend: `backend/tests/test_no_floats_in_money_paths.py` (AST scan of 13 money modules: no float literal, `float`,
      `Decimal`, `round`, true division; every `*_minor` column is an integer type). 16 passed.
- [x] Mobile: `mobile/__tests__/noFloatMoney.test.ts` (no parseFloat, toFixed, Math rounding, Number(), or fractional
      literal in non-UI code under src/, with a negative control). 3 passed. The ESLint money rules in `.eslintrc.js` pass
      (`eslint .` clean) and `tsc --noEmit` is clean.
- [x] Grep over both trees. The only float uses outside UI layout values are `storage.py` (epoch seconds for the signed
      URL), `models/expense.py` `fx_rate` Numeric(18,8) (an exchange rate, not an amount; the conversion feature is Later),
      `api/helpers.ts` (random UUID nibble) and `useOsPermission.ts` (Android API level). None holds money.
- [x] API refuses JSON floats and strings for amounts (StrictInt; existing tests in test_expenses_api / test_settlements).

## 3. Crash-free smoke on devices
- [ ] Android 7 (API 24): not run. The only system image installed is `android-36` (google_apis_playstore, arm64-v8a);
      no API 24 image or device exists here. Install the image, then run `slice6_e2e.py`.
- [ ] Android 14 (API 34): not run, same reason (no API 34 image).
- [ ] Android 16 (API 36) crash-free: the seven E2E flows ran on this emulator and no crash dialog or process death was
      noticed, but `adb logcat` was not scanned for FATAL EXCEPTION, so this is not ticked.

## 4. Slice 6 end-to-end (emulator, API 36, `mobile/__tests__/e2e/slice6_e2e.py`)
- [x] FLOW-10, FLOW-02 (link part), FLOW-06 (e-mail), FLOW-07 (steps 1-3 and stop), FLOW-08, FLOW-09, FLOW-11: see the
      run results in docs/progress.md (QA Slice 6 handoff). Blocked and skipped steps are listed there.
- [ ] Open defect: cold start with the persisted cache breaks every infinite list (timeline, friend, comments, search):
      `GET ...?cursor=null` returns 422. Failing test `__tests__/slice6/persistedInfinite.test.ts`. Release blocker.
- [ ] Open defect: export `download_url` points to `http://localhost:8000` (unreachable from a phone) and the app shares
      it as text rather than a CSV file. Needs a public base URL setting and a download step, or an Architect ruling.

## 5. Suites (2026-11-20)
- [x] Backend pytest (SQLite): 956 passed, 20 skipped, 0 failed.
- [x] Mobile `tsc --noEmit` and `eslint .` clean.
- [ ] Mobile jest: 855 passed, 31 failed. 30 are the existing SUI-M-04..06 failures in `__tests__/ui/components.test.tsx`;
      1 is the new deliberate failing test for the cursor defect above.
- [ ] Backend on PostgreSQL 16 for this QA session: not run (Postgres was started only for the emulator run).

## 6. Blocked by decision D-C (cannot be ticked until approved and built)
- [ ] Push registration, subscription verification (Play Billing), invite preview and placeholder claim UI, friend-code
      lookup and QR scan, receipt upload/remove UI (no image-picker), Copy button (no clipboard module), NetInfo.
