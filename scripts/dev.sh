#!/usr/bin/env bash
# SplitApp local dev environment (macOS, Android emulator).
#
#   ./scripts/dev.sh up [--build]   start everything and launch the app
#   ./scripts/dev.sh down [--keep-postgres]   stop everything, including Postgres
#   ./scripts/dev.sh status         show what is running
#
# up:   uses Postgres if it is running, otherwise starts it (Postgres.app's pg_ctl);
#       checks the splitapp DB, runs migrations, starts the API (:8000), boots the
#       emulator, starts Metro (:8081), sets adb reverse, installs the app if missing
#       (or always with --build), then launches it. Maestro is OPTIONAL (E2E tests
#       only, the app does not need it): it is detected and reported, never installed.
# down: stops leftover Maestro processes, force-stops the app, stops Metro, the API,
#       the emulator, the Gradle daemons and Postgres (fast shutdown, data is kept).
#       Pass --keep-postgres to leave Postgres running (e.g. other DBs such as TextSQL
#       live on the same server).
#
# Dev-only credentials below match backend/.env.example. Logs and pids live in
# $TMPDIR/splitapp-dev, nothing is written into the repo.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="${TMPDIR:-/tmp}/splitapp-dev"
mkdir -p "$STATE"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

AVD="${SPLITAPP_AVD:-Medium_Phone_API_36}"
PG_BIN="${PG_BIN:-/Applications/Postgres.app/Contents/Versions/15/bin}"
PG_DATA="${PG_DATA:-$HOME/Library/Application Support/Postgres/var-15}"
MAESTRO_DRIVER_PKG="dev.mobile.maestro"
APP_ID="com.splitapp"
API_PORT=8000
METRO_PORT=8081
PG_PORT=5432

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://splitapp:splitapp@localhost:5432/splitapp}"
export JWT_SECRET="${JWT_SECRET:-dev-only-change-me-dev-only-change-me}"
export ENV="${ENV:-development}"

say()  { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

listener_pids() { lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null; }

emulator_serial() { adb devices 2>/dev/null | awk '/^emulator-[0-9]+[[:space:]]+device/ {print $1; exit}'; }

stop_port() {
  local port="$1" name="$2" pids
  pids="$(listener_pids "$port")"
  if [ -z "$pids" ]; then say "$name: not running (port $port)"; return; fi
  say "$name: stopping (port $port, pid $(echo "$pids" | tr '\n' ' '))"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -z "$(listener_pids "$port")" ] && return; sleep 1; done
  # shellcheck disable=SC2086
  kill -9 $(listener_pids "$port") 2>/dev/null
}

pg_ready() { "$PG_BIN/pg_isready" -q -h localhost -p "$PG_PORT"; }

start_postgres() {
  if pg_ready; then say "Postgres: already running, using it"; return; fi
  [ -x "$PG_BIN/pg_ctl" ] || fail "pg_ctl not found in $PG_BIN (set PG_BIN)."
  [ -d "$PG_DATA" ] || fail "Postgres data directory not found: $PG_DATA (set PG_DATA)."
  say "Postgres: not running, starting it ($PG_DATA)"
  "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$STATE/postgres.log" -w -t 60 start >/dev/null 2>&1 \
    || fail "Postgres failed to start, see $STATE/postgres.log"
  pg_ready || fail "Postgres started but is not accepting connections on :$PG_PORT, see $STATE/postgres.log"
}

stop_postgres() {
  if ! pg_ready; then say "Postgres: not running"; return; fi
  say "Postgres: stopping (fast shutdown, data is kept)"
  "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast -w -t 60 stop >/dev/null 2>&1 \
    || say "Postgres: pg_ctl stop failed; quit it from the Postgres.app menu"
}

# Maestro is optional (E2E test runner only, no daemon). Detect it; never required to run the app.
maestro_note() {
  if command -v maestro >/dev/null 2>&1; then
    say "Maestro: installed ($(maestro --version 2>/dev/null | tail -1)), available for E2E flows"
  else
    say "Maestro: not installed (optional, only needed for E2E tests; the app does not need it)"
  fi
}

stop_maestro() {
  # No Maestro daemon exists; clean up anything it left behind (studio / CLI processes, device driver app).
  local found=0
  if pgrep -f "maestro studio|maestro-cli|maestro/lib" >/dev/null 2>&1; then
    found=1; pkill -f "maestro studio|maestro-cli|maestro/lib" 2>/dev/null
  fi
  if [ -n "$(emulator_serial)" ] && adb shell pm list packages 2>/dev/null | grep -q "package:$MAESTRO_DRIVER_PKG"; then
    found=1; adb shell am force-stop "$MAESTRO_DRIVER_PKG" 2>/dev/null
    adb shell am force-stop "$MAESTRO_DRIVER_PKG.test" 2>/dev/null
  fi
  [ "$found" = 1 ] && say "Maestro: stopped leftover processes" || say "Maestro: nothing running"
}

wait_http() { # url, seconds
  local i
  for ((i = 0; i < $2; i++)); do
    curl -s -m 2 -o /dev/null "$1" && return 0
    sleep 1
  done
  return 1
}

cmd_up() {
  local build=0
  [ "${1:-}" = "--build" ] && build=1

  # 1. Postgres (use it if running, otherwise start it) + DB
  start_postgres
  PGPASSWORD=splitapp "$PG_BIN/psql" -h localhost -p "$PG_PORT" -U splitapp -d splitapp -Atc 'select 1' >/dev/null 2>&1 \
    || fail "Cannot log in as role splitapp to database splitapp. Create them first (see docs/progress.md / .env.example)."
  say "Postgres: ok"

  # 2. Migrations (idempotent)
  say "Migrations: alembic upgrade head"
  (cd "$ROOT/backend" && . .venv/bin/activate && alembic upgrade head >"$STATE/alembic.log" 2>&1) \
    || fail "alembic failed, see $STATE/alembic.log"

  # 3. API
  if [ -n "$(listener_pids "$API_PORT")" ]; then
    say "API: already running on :$API_PORT"
  else
    say "API: starting on :$API_PORT"
    (cd "$ROOT/backend" && . .venv/bin/activate \
      && nohup uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" >"$STATE/api.log" 2>&1 </dev/null & echo $! >"$STATE/api.pid")
    wait_http "http://127.0.0.1:$API_PORT/docs" 40 || fail "API did not come up, see $STATE/api.log"
  fi

  # 4. Emulator
  if [ -n "$(emulator_serial)" ]; then
    say "Emulator: already running ($(emulator_serial))"
  else
    say "Emulator: booting $AVD"
    nohup emulator -avd "$AVD" -no-snapshot-save >"$STATE/emulator.log" 2>&1 </dev/null &
    echo $! >"$STATE/emulator.pid"
    adb wait-for-device
    local i
    for ((i = 0; i < 60; i++)); do
      [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
      sleep 3
    done
    [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] \
      || fail "Emulator did not finish booting, see $STATE/emulator.log"
  fi

  # 5. Metro
  if [ -n "$(listener_pids "$METRO_PORT")" ]; then
    say "Metro: already running on :$METRO_PORT"
  else
    say "Metro: starting on :$METRO_PORT"
    (cd "$ROOT/mobile" && nohup npx react-native start >"$STATE/metro.log" 2>&1 </dev/null & echo $! >"$STATE/metro.pid")
    wait_http "http://localhost:$METRO_PORT/status" 60 || fail "Metro did not come up, see $STATE/metro.log"
  fi
  adb reverse "tcp:$METRO_PORT" "tcp:$METRO_PORT" >/dev/null

  # 6. Install (if needed) and launch
  if [ "$build" = 1 ] || ! adb shell pm list packages 2>/dev/null | grep -q "package:$APP_ID\$"; then
    say "App: building and installing (first run takes several minutes)"
    (cd "$ROOT/mobile" && npx react-native run-android --no-packager >"$STATE/build.log" 2>&1) \
      || fail "Build failed, see $STATE/build.log"
  else
    say "App: already installed, launching"
    adb shell am force-stop "$APP_ID"
    adb shell am start -n "$APP_ID/.MainActivity" >/dev/null
  fi

  maestro_note
  say "Up. Logs: $STATE   (API http://localhost:$API_PORT/docs)"
}

cmd_down() {
  local keep_pg=0
  [ "${1:-}" = "--keep-postgres" ] && keep_pg=1
  stop_maestro
  if [ -n "$(emulator_serial)" ]; then
    say "App: force-stop"
    adb shell am force-stop "$APP_ID" 2>/dev/null
  fi
  stop_port "$METRO_PORT" "Metro"
  stop_port "$API_PORT" "API"

  if [ -n "$(emulator_serial)" ]; then
    say "Emulator: shutting down"
    adb emu kill >/dev/null 2>&1
    local i
    for ((i = 0; i < 20; i++)); do [ -z "$(emulator_serial)" ] && break; sleep 1; done
  else
    say "Emulator: not running"
  fi
  pkill -f "qemu-system-aarch64.*$AVD" 2>/dev/null

  if [ -x "$ROOT/mobile/android/gradlew" ]; then
    say "Gradle daemons: stopping"
    (cd "$ROOT/mobile/android" && ./gradlew --stop >/dev/null 2>&1)
  fi
  adb kill-server >/dev/null 2>&1
  rm -f "$STATE"/*.pid
  if [ "$keep_pg" = 1 ]; then
    say "Postgres: left running (--keep-postgres)"
  else
    stop_postgres
  fi
  say "Down."
}

cmd_status() {
  printf 'Postgres : %s\n' "$(pg_ready && echo "running :$PG_PORT" || echo stopped)"
  printf 'Maestro  : %s\n' "$(command -v maestro >/dev/null 2>&1 && echo "installed (optional)" || echo "not installed (optional)")"
  printf 'API      : %s\n' "$([ -n "$(listener_pids "$API_PORT")" ] && echo "running :$API_PORT" || echo stopped)"
  printf 'Metro    : %s\n' "$([ -n "$(listener_pids "$METRO_PORT")" ] && echo "running :$METRO_PORT" || echo stopped)"
  printf 'Emulator : %s\n' "$([ -n "$(emulator_serial)" ] && echo "running $(emulator_serial)" || echo stopped)"
  if [ -n "$(emulator_serial)" ]; then
    printf 'App      : %s\n' "$(adb shell pm list packages 2>/dev/null | grep -q "package:$APP_ID\$" && echo installed || echo "not installed")"
  fi
  printf 'Gradle   : %s\n' "$(pgrep -f GradleDaemon >/dev/null && echo "daemon running" || echo "no daemon")"
}

case "${1:-}" in
  up)     shift; cmd_up "$@" ;;
  down)   shift; cmd_down "$@" ;;
  status) cmd_status ;;
  *)      echo "usage: $0 up [--build] | down [--keep-postgres] | status" >&2; exit 2 ;;
esac
