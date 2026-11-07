# SplitApp: shared rules for all agents

## Stack
- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, pytest
- Mobile: React Native + TypeScript (Android first), React Query, typed client generated from docs/openapi.yaml
- Dev: Docker Compose for Postgres; Android emulator reaches host at http://10.0.2.2:8000

## Ground rules
1. Read `docs/` before writing any code. `docs/openapi.yaml` is the single source of truth for the API.
2. Never change the contract silently. If it needs to change, log it in `docs/progress.md` and stop for review.
3. Money is stored and computed as integer minor units. No floats anywhere in money paths.
4. Original code only. Nothing copied from any other app, decompiled source, assets, strings, or branding.
5. Work only on the task you were given (task IDs live in `docs/tasks.md`). Stay inside the files you own.
6. Write tests with the code. Business-rule tests come from `docs/business_rules.md` test vectors.
7. Append a short handoff note to `docs/progress.md` when you finish.

## File ownership
- Architect: `docs/`
- Backend agent: `backend/`
- Mobile agent: `mobile/`
- QA agent: tests in both trees
- Reviewer agent: read-only; reviews diffs against the contract, money handling, and auth

## Conventions
- Backend: snake_case, routers per resource, Pydantic schemas mirror openapi.yaml, Alembic for every schema change
- Mobile: feature folders, no hand-written API calls (use the generated client), TypeScript strict mode
