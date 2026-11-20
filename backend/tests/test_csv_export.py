"""S6-B-7: the pure CSV layout (F-45). No database."""
from datetime import date

from app.csv_export import ExportRow, build_csv, format_minor, member_headers, safe_text

EXP = {"INR": 2, "USD": 2, "JPY": 0, "KWD": 3}


def test_format_minor_uses_integer_division_and_the_currency_exponent():
    assert format_minor(90000, 2) == "900.00"
    assert format_minor(5, 2) == "0.05" and format_minor(0, 2) == "0.00" and format_minor(100, 2) == "1.00"
    assert format_minor(-5, 2) == "-0.05" and format_minor(-123456, 2) == "-1234.56"
    assert format_minor(900, 0) == "900" and format_minor(-900, 0) == "-900"
    assert format_minor(1234, 3) == "1.234" and format_minor(9_999_999_999, 2) == "99999999.99"


def test_layout_rows_member_columns_and_a_total_row():
    members = [("a", "Asha"), ("b", "Ravi")]
    rows = [ExportRow(date(2026, 11, 1), "Dinner", "Dining out", 90000, "INR", {"a": 45000, "b": -45000}),
            ExportRow(date(2026, 11, 2), "Payment: Ravi paid Asha", "Payment", 10000, "INR", {"b": 10000, "a": -10000})]
    lines = build_csv(members, rows, EXP).splitlines()
    assert lines == ["date,description,category,cost,currency,Asha,Ravi",
                     "2026-11-01,Dinner,Dining out,900.00,INR,450.00,-450.00",
                     "2026-11-02,Payment: Ravi paid Asha,Payment,100.00,INR,-100.00,100.00",
                     ",Total,,,INR,350.00,-350.00"]


def test_one_total_row_per_currency_in_first_seen_order():
    members = [("a", "A"), ("b", "B")]
    rows = [ExportRow(date(2026, 1, 1), "x", "c", 1000, "USD", {"a": 500, "b": -500}),
            ExportRow(date(2026, 1, 2), "y", "c", 700, "JPY", {"a": 700}),
            ExportRow(date(2026, 1, 3), "z", "c", 2000, "USD", {"b": 1000, "a": -1000})]
    lines = build_csv(members, rows, EXP).splitlines()
    assert len(lines) == 1 + 3 + 2
    assert lines[-2] == ",Total,,,USD,-5.00,5.00" and lines[-1] == ",Total,,,JPY,700,0"


def test_no_rows_still_has_the_header_only():
    assert build_csv([("a", "A")], [], EXP) == "date,description,category,cost,currency,A\n"


def test_quotes_commas_and_formula_injection():
    members = [("a", "=Evil")]
    rows = [ExportRow(date(2026, 1, 1), '=HYPERLINK("x")', "a,b", 100, "INR", {"a": 100})]
    out = build_csv(members, rows, EXP)
    assert "'=Evil" in out.splitlines()[0]
    assert out.splitlines()[1].startswith("2026-01-01,\"'=HYPERLINK(\"\"x\"\")\",\"a,b\",1.00,INR,1.00")
    assert safe_text("plain") == "plain" and safe_text("@x") == "'@x" and safe_text("-1") == "'-1"


def test_duplicate_member_names_get_a_suffix():
    assert member_headers(["Sam", "Lee", "Sam", "Sam"]) == ["Sam", "Lee", "Sam (2)", "Sam (3)"]
