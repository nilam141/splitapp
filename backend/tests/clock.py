"""Minimal clock freezing for rate-limit tests (no freezegun in the environment).

Implementation-agnostic as far as possible: replaces the `datetime` class bound in every loaded `app.*` module, and
`time.time` / `time.monotonic`, with versions driven by a controllable offset. Time starts at the real current
instant and only moves when the test calls set(seconds)/advance(seconds).
"""
import sys
import time as _time
from datetime import datetime as _real_datetime, timedelta, timezone


class FakeClock:
    def __init__(self):
        self.base = _real_datetime.now(timezone.utc)
        self.offset = 0.0

    def now(self, tz=None):
        t = self.base + timedelta(seconds=self.offset)
        return t.astimezone(tz) if tz else t.replace(tzinfo=None)

    def set(self, seconds):
        self.offset = float(seconds)


def install(monkeypatch):
    clock = FakeClock()

    class FrozenDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now(tz)

        @classmethod
        def utcnow(cls):
            return clock.now(None)

    real_time, real_mono = _time.time, _time.monotonic
    t0, m0 = real_time(), real_mono()
    monkeypatch.setattr(_time, "time", lambda: t0 + clock.offset)
    monkeypatch.setattr(_time, "monotonic", lambda: m0 + clock.offset)
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.") or name == "app":
            if getattr(mod, "datetime", None) is _real_datetime:
                monkeypatch.setattr(mod, "datetime", FrozenDatetime)
    return clock
