"""CSV export layout, pure (F-45, business_rules 1). No database, no floats: amounts are integer minor units and are
rendered with the currency exponent using integer division (90000 INR -> `900.00`, dot separator, no thousands
separator). Columns: date, description, category, cost, currency, then one column per member holding that member's net
for the row (paid minus owed; for a payment the payer is positive and the receiver negative). After the data rows come
one total row per currency (description `Total`), in the order the currencies first appear."""
import csv
import io
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

FIXED_COLUMNS = ("date", "description", "category", "cost", "currency")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class ExportRow:
    day: date
    description: str
    category: str
    cost_minor: int
    currency: str
    nets: Mapping[Hashable, int] = field(default_factory=dict)  # member id -> net minor units in `currency`


def format_minor(amount: int, exponent: int) -> str:
    """12000, 2 -> '120.00'; -5, 2 -> '-0.05'; 500, 0 -> '500'. Integer arithmetic only."""
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if exponent == 0:
        return f"{sign}{amount}"
    whole, frac = divmod(amount, 10 ** exponent)
    return f"{sign}{whole}.{frac:0{exponent}d}"


def safe_text(value: str) -> str:
    """Stop spreadsheet formula injection: a cell that starts with = + - @ is prefixed with an apostrophe."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def member_headers(names: Sequence[str]) -> list[str]:
    """Header cells for the member columns; a repeated name gets ` (2)`, ` (3)`, ..."""
    seen: dict[str, int] = {}
    out = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return out


def build_csv(members: Sequence[tuple[Hashable, str]], rows: Sequence[ExportRow],
              exponents: Mapping[str, int]) -> str:
    """`members` are (id, display name) in column order; `exponents` maps currency -> minor-unit exponent."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([*FIXED_COLUMNS, *(safe_text(h) for h in member_headers([n for _, n in members]))])
    totals: dict[str, dict[Hashable, int]] = {}
    for r in rows:
        exp = exponents[r.currency]
        w.writerow([r.day.isoformat(), safe_text(r.description), safe_text(r.category),
                    format_minor(r.cost_minor, exp), r.currency,
                    *(format_minor(r.nets.get(m, 0), exp) for m, _ in members)])
        per = totals.setdefault(r.currency, {})
        for m, _ in members:
            per[m] = per.get(m, 0) + r.nets.get(m, 0)
    for currency, per in totals.items():
        exp = exponents[currency]
        w.writerow(["", "Total", "", "", currency, *(format_minor(per.get(m, 0), exp) for m, _ in members)])
    return out.getvalue()
