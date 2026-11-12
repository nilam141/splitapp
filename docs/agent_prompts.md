# Agent Prompt Playbook (VS Code, Claude Code chat)

Your main chat window is the **orchestrator**. It plans and delegates to the subagents defined in `.claude/agents/`: architect, backend, mobile, qa, reviewer. Subagents do not talk to each other; they communicate through the files in `docs/` and report back to the orchestrator.

## Step 0: Setup (once)

1. Unzip this pack into the repo root so you have `.claude/agents/` and `docs/agent_prompts.md`.
2. Run `git add -A && git commit -m "REA spec + agents"`.
3. In the Claude Code chat, run `/agents` and confirm architect, backend, mobile, qa and reviewer are listed. Restart the chat panel if they are not.
4. Create a branch per slice: `git switch -c slice-1`.

## Step 1: Finalize the contract (Architect)

Paste into the chat:

```
Use the architect subagent. Read CLAUDE.md and all of docs/. Make
docs/openapi.yaml, docs/data_model.md, docs/business_rules.md and
docs/tasks.md fully consistent with each other. List every contradiction you
found and how you resolved it. Do not write application code. Report back
the list of changed files and any decision I need to make.
```

Review the result and `git diff docs/`. Commit it. Do not start building until you are happy with this step.

## Step 2: Slice 1 (Foundation)

Backend and mobile touch different folders, so they can run in parallel.

```
Implement Slice 1 from docs/tasks.md.
1. Run the backend subagent for S1-B-1, S1-B-2, S1-B-3, S1-B-4, S1-B-5, S1-B-6 and the mobile subagent
   for S1-M-1, S1-M-2, S1-M-3 in parallel. Each works only in its own folder.
2. When both finish, run the qa subagent for S1-Q-1.
   Contract 0.2.0 follow-ups (after the above): qa subagent S1-Q-2 (failing tests for vectors 46 and 47), then
   backend subagent S1-B-7 (Alembic migration 0002, `revoked_reason`), and mobile subagent S1-M-4 (rename the
   generated client calls to the new operationIds using the table in docs/progress.md).
3. Then run the reviewer subagent on the full slice diff.
4. If the reviewer says REQUEST CHANGES, send the findings to the right
   subagent, then re-review. Repeat until APPROVE.
5. Tell me the final test results and what to verify by hand. Do not merge or
   commit; I will do that.
```

If the two agents ever need the same file (for example `docker-compose.yml`), run them one after the other instead.

## Step 3: Each later slice

Replace `N` with the slice number. For slices with money logic (3, 4, 5), keep QA first.

Slice 2 note: run qa S2-Q-2 and S2-Q-3 (failing tests) before backend S2-B-5 and S2-B-7; run qa S2-Q-4 before backend S2-B-8 (keep friends when a shared group ends, after S2-B-5). Slice 3: qa S3-Q-5 before backend S3-B-6 (group timeline). Slice 5: qa S5-Q-3 before backend S5-B-3 (unread count) and S5-B-4 (timeline settlements, friend-removal settlements).

**Slices 2 and 6 (CRUD style):**

```
Implement Slice N from docs/tasks.md. Run backend and mobile subagents in
parallel on their tasks, then qa for the Q tasks, then reviewer on the whole
diff. Loop on reviewer findings until APPROVE. Stop and report if any
subagent logs a contract conflict in docs/progress.md.
```

**Slices 3, 4, 5 (money logic):**

```
Implement Slice N from docs/tasks.md in this order:
1. qa subagent writes the tests for the business rules (test vectors and
   property tests). They should fail because nothing is implemented yet; confirm that.
2. backend subagent implements the B tasks until those tests pass.
3. mobile subagent implements the M tasks against the generated client.
4. qa subagent runs the full suite for the slice.
5. reviewer subagent reviews the diff, with extra attention to money and auth.
Loop on findings. Do not merge or commit; report results and what I should check by hand.
```

## Step 4: After every slice (you)

1. Read the reviewer verdict and `docs/progress.md`.
2. Run the app yourself: `docker compose up`, then `npx react-native run-android` in `mobile/`.
3. For money slices, compare 3 to 5 cases against the original app by hand.
4. `git add -A && git commit -m "slice N"`, merge to main, then `git switch -c slice-N+1`.

## When something goes wrong

- **Contract conflict**: `Use the architect subagent to resolve the conflict logged in docs/progress.md, update the docs, and tell me what changed.` Then re-run the blocked task.
- **Test fails repeatedly**: do not let an agent edit the test to pass. Ask: `Use the reviewer subagent to say whether the test or the code is wrong, and why.`
- **An agent went outside its folder**: `git diff --stat`, revert those files, and re-run with: `Only change files in <folder>.`
- **Context gets long**: start a fresh chat. All state is in the repo; begin with `Read CLAUDE.md and docs/progress.md, then continue with the next unfinished task in docs/tasks.md.`

## Single-task prompt (if you prefer to drive one agent at a time)

```
Use the <backend|mobile|qa> subagent. Read CLAUDE.md and docs/ first.
Implement only task <ID> from docs/tasks.md. Do not change docs/openapi.yaml;
log any conflict in docs/progress.md. Run the tests and report the real result.
```
