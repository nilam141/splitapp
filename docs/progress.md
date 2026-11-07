# Progress and Handoff Notes

> Every agent appends a short entry when it finishes or hits a blocker. Newest first.

## Template
**<date> | <agent> | <task ID>** | status: done / blocked / partial
- What changed: <files, endpoints>
- Contract conflicts or questions: <or "none">
- Next agent should: <...>

## Log

**2026-11-05 | REA | spec extraction (pre-Slice 2)** | status: partial (spec complete; reference-app runtime behaviour not verified)
- What changed: filled in every file in `docs/` except `CLAUDE.md`:
  - `features.md`: F-01 to F-54 with priority, free/premium and Given/When/Then criteria; the checklist marked present/absent; an out-of-scope list (fintech, wallet, cards, ads).
  - `screens.md`: SCR-01 to SCR-44 plus the navigation graph (Mermaid, validated by rendering it).
  - `user_flows.md`: FLOW-01 to FLOW-11 covering every checklist flow, with error paths and postconditions.
  - `data_model.md`: 27 tables, constraints, indexes, ER diagram (validated by rendering it).
  - `business_rules.md`: algorithms in prose and pseudocode for all 5 split types, multiple payers, nets, pairwise debts, simplification, settlements, multi-currency, edge cases, a free/premium proposal, and 41 test vectors. Every expected number was produced by a reference script, not by hand.
  - `openapi.yaml`: v0.1.0, 38 paths / 56 operations covering every endpoint in the original comment list, plus the extras the specs need (`/health`, logout, password reset, `/friends/{user_id}`, `POST/GET /expenses`, restore endpoints, settlement item endpoints, settle-all, receipt upload, invite link/join, reminders, `/activity/read`, `/categories`, `/currencies`). The Money schema and bearer auth are unchanged; Error gained an optional `details` object and a list of codes. Checked: YAML parses, all 78 `$ref`s resolve, every path parameter is declared, every `*_minor` field is an integer. No full OpenAPI validator was available offline. **Run one in S1-M-2 (client generation will also catch errors).**
  - `tasks.md`: Slice 1 kept as-is; Slices 2–6 have 54 tasks, with Q tasks ahead of the B tasks they gate.
  - `open_questions.md`: 30 questions with evidence and confidence, 10 owner decisions, and a manual test script (T1–T30).
- How: static analysis only. REA opened the APK and inventoried it (2,686 entries), but its JADX, apktool and adb providers aren't configured on this Mac. I decoded the binary manifest, resource table and DEX class/string tables with my own small parsers in the cloud workspace. **No code was decompiled, nothing was copied** (no strings, assets, layouts, code or branding). Evidence is cited by component/screen name only.
- Not done / incomplete:
  - The app was **not run**, so no flow was traced and no network was observed. Remainder order, percent rounding, the simplification output, overpay handling, roles and the free-tier cap are **our decisions**, flagged in open_questions.md (OQ-01, 02, 10, 13, 14, 15, 19).
  - The category list, currency list, FX provider, domain/deep links and premium scope wait on the owner (D1–D10).
- Housekeeping: the APK copy is at `.rea-input/target.apk` (42 MB). It is excluded via `.git/info/exclude`, so it can't be committed. Delete it when done. A 3-byte probe file `docs/test_w` was created while diagnosing write permissions. Delete it if it is still there.
- To enable dynamic analysis next time: set `REA_ADB_PATH` (e.g. `~/Library/Android/sdk/platform-tools/adb`), `REA_APKTOOL_COMMAND` and `REA_JADX_MCP_JAR` (jadx-headless-mcp 0.7.1) in REA's launch environment, restart REA, and start an emulator with a test account.
- Contract conflicts or questions: none against an earlier contract (this is v0.1.0). Deviation from the comment list: member removal is `DELETE /groups/{id}/members/{user_id}` (with `me` for leave), not `DELETE /groups/{id}/members`.
- Next agent should: the owner answers D1, D2, D4 and runs manual tests T1, T2, T9, T14a/b and T19 (the top 5 below). Backend starts S2-B-1. QA can start S3-Q-1 / S3-Q-2 now, because the vectors are final for our own rules.
- **Verify by hand first (top 5):** (1) T1 equal-split remainder order; (2) T2 percent rounding and decimals; (3) T14a/b simplification output, and how friend screens show simplified debts; (4) T9/T10/T13 the simplify default and who may edit/delete/remove; (5) T19 whether the free tier caps expenses per day, and the timer length.
