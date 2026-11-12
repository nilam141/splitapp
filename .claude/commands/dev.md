---
description: Start, stop or check the local SplitApp dev environment (emulator, API, Metro, app)
argument-hint: up | down | status | up --build
allowed-tools: Bash(./scripts/dev.sh:*)
---

Run `./scripts/dev.sh $ARGUMENTS` from the repo root (default to `status` if no argument is given).

- `up` uses Postgres if it is running and starts it otherwise, then starts the API, boots the emulator, starts Metro and launches the app. `up --build` forces a rebuild and reinstall. Maestro is optional (E2E tests only): it is detected and reported, never required or installed.
- `down` stops Maestro leftovers, the app, Metro, the API, the emulator, the Gradle daemons and Postgres (data is kept). `down --keep-postgres` leaves Postgres running.

Report the result in a few lines. If the script fails or something needs intervention, stop, say what failed (include the relevant log path under `$TMPDIR/splitapp-dev`), and ask for permission before changing anything or retrying.
