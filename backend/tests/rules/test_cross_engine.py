"""Cross-engine check, backend half: random_cases.json (240 seeded cases, valid and invalid) must still equal what
app.splits computes. The mobile half (mobile/__tests__/crossEngine.test.ts) runs the TS engine on the same file."""
import json
from pathlib import Path

import pytest

from tests.rules.cross import run_case

CASES = json.loads((Path(__file__).parent / "random_cases.json").read_text())["cases"]


def test_case_count():
    assert len(CASES) == 240


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_backend_matches_recorded(case):
    assert run_case(case) == case["expected"]
    if "owed" in case["expected"]:
        assert sum(v for _, v in case["expected"]["owed"]) == case["total"]
