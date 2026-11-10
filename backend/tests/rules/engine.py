"""Import shim for the split engine under test (S3-Q-1 / S3-Q-2). Contains NO application logic.

Expected application module (to be created by S3-B-1, not by QA): `app.splits`, pure functions, no DB. Signatures are
listed in docs/progress.md (QA handoff, Slice 3 step 1). Until the module exists every use of `engine()` raises
NotImplementedError, which is the agreed failure mode of these tests ("fail with NotImplementedError").
"""
import importlib


def engine():
    try:
        return importlib.import_module("app.splits")
    except ModuleNotFoundError as exc:
        if exc.name != "app.splits":  # a real import problem inside the module must stay visible
            raise
        raise NotImplementedError("split engine module app.splits does not exist yet (S3-B-1)") from exc
