"""Run one cross-engine case through the backend engine (used by test_cross_engine.py and the case generator)."""
from app.splits import SplitError, compute_split


def run_case(c):
    try:
        out = compute_split(c["split_type"], c["total"], [(u, v) for u, v in c["entries"]])
    except SplitError as e:
        return {"error": {"code": e.code, "details": e.details}}
    return {"owed": [[u, v] for u, v in out.items()]}
