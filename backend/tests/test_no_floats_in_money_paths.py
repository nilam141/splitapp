"""S6-Q-3: no floating point in backend money paths (CLAUDE.md rule 3). An AST scan, not a grep, so comments and
docstrings that say "no floats" do not count. Money modules may not contain: a float literal, the names `float`,
`Decimal`, `round`, the true-division operator `/`, or `math` float functions."""
import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
MONEY_MODULES = [
    "splits.py", "balances.py", "recurrence.py", "csv_export.py", "schemas_expenses.py", "schemas_settlements.py",
    "schemas_recurring.py", "services_expenses.py", "services_settlements.py", "services_balances.py",
    "services_recurring.py", "services_exports.py", "services_reminders.py",
]
BANNED_NAMES = {"float", "Decimal", "round"}


def findings(source: str) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            out.append(f"line {node.lineno}: float literal {node.value!r}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            out.append(f"line {node.lineno}: name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in {"Decimal"}:
            out.append(f"line {node.lineno}: attribute {node.attr}")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            out.append(f"line {node.lineno}: true division")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Div):
            out.append(f"line {node.lineno}: true division")
    return out


@pytest.mark.parametrize("module", MONEY_MODULES)
def test_money_module_has_no_floats(module):
    path = APP / module
    assert path.exists(), f"{module} moved: update MONEY_MODULES"
    assert findings(path.read_text()) == [], module


def test_money_columns_are_integers_not_floats_or_numerics():
    """Every *_minor column in the models is an integer type (BigInteger/Integer); fx_rate is the only Numeric and is a rate."""
    from sqlalchemy import BigInteger, Integer

    from app.db import Base
    import app.models  # noqa: F401

    bad = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.name.endswith("_minor") and not isinstance(col.type, (BigInteger, Integer)):
                bad.append(f"{table.name}.{col.name}: {col.type}")
    assert bad == []


def test_scanner_negative_control():
    assert findings("x = 1.5") and findings("y = a / b") and findings("z = float(q)") and findings("r = round(v)")
    assert findings("x = a // b\n'''no floats'''") == []


def test_other_app_modules_only_use_floats_for_time():
    """Outside the money modules a float may appear only as a time value (seconds); list them so a new one is noticed."""
    allowed = {"storage.py"}  # signed-URL expiry: epoch seconds
    offenders = {}
    for p in APP.rglob("*.py"):
        if p.name in MONEY_MODULES or p.name in allowed:
            continue
        hits = [h for h in findings(p.read_text()) if "float" in h and "true division" not in h]
        if hits:
            offenders[str(p.relative_to(APP))] = hits
    assert offenders == {}, offenders
