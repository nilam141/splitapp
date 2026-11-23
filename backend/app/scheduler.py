"""Background jobs (S6-B-2, S6-B-3, S6-B-7). Run with `python -m app.scheduler` (a loop, every
`SCHEDULER_INTERVAL_SECONDS`, default 900 = 15 minutes) or call `run_once` from cron. One tick:
1. create due recurring occurrences and queue their reminders;
2. generate pending exports and purge expired ones;
3. deliver pending notifications.
Every step is idempotent and safe to run from several processes at once, and one failing step never blocks the next."""
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app import notify, services_exports, services_recurring

log = logging.getLogger("app.scheduler")


def run_once(db: Session, now: datetime | None = None) -> dict[str, int]:
    result: dict[str, int] = {}
    steps = (("occurrences", lambda: services_recurring.run_due(db, now)),
             ("exports_generated", lambda: services_exports.process_pending(db)),
             ("exports_purged", lambda: services_exports.purge_expired(db, now)),
             ("notifications_sent", lambda: notify.deliver_pending(db)["sent"]))
    for name, step in steps:
        try:
            result[name] = step()
        except Exception:  # noqa: BLE001 - keep the loop alive; the next tick retries
            log.exception("scheduler step %s failed", name)
            db.rollback()
            result[name] = -1
    return result


def main() -> None:
    from app.config import settings
    from app.db import SessionLocal
    logging.basicConfig(level=logging.INFO)
    while True:
        with SessionLocal() as db:
            log.info("scheduler tick: %s", run_once(db))
        time.sleep(settings.scheduler_interval_seconds)


if __name__ == "__main__":
    main()
