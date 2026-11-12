"""Import shim for the balance functions under test (S4-Q-1 / S4-Q-2). Contains NO application logic.

Expected application module (S4-B-1, not created by QA): `app.balances`, pure functions, no DB.
Proposed signatures (also in docs/progress.md, QA handoff Slice 4):

    net_balances(expenses, settlements=()) -> {currency: {user: int}}
    pairwise_edges(expenses, settlements=(), canonical=()) -> {currency: [(from_user, to_user, amount_minor), ...]}
    simplify(nets, canonical) -> [(from_user, to_user, amount_minor), ...]       # one currency

Record shapes (plain dicts, integer minor units, only LIVE (non-deleted) records are passed in):
    expense    = {"currency": "INR", "payers": [(user, paid_minor), ...], "splits": [(user, owed_minor), ...]}
    settlement = {"currency": "INR", "from_user_id": user, "to_user_id": user, "amount_minor": 3000}
`user` is any hashable id (tests use "A".."L"; the DB layer passes uuid.UUID). `canonical` is the list of users in
group order (group_members.sort_index); it decides tie-breaks and the order of the returned lists.
Zero balances may be present or absent in the nets dict; tests read them with `.get(user, 0)`.
Pairwise list order: debtor in canonical order, then creditor in canonical order. Only edges with amount >= 1.
Empty currencies may be absent.

Until the module exists every use raises NotImplementedError (the agreed "fails for the right reason" mode).
QA_BALANCES_REFERENCE=<path to a .py file> loads a scratch reference implementation instead; it exists only so QA can
prove the tests themselves are correct, and is never set in CI.
"""
import importlib
import importlib.util
import os


def balances():
    ref = os.environ.get("QA_BALANCES_REFERENCE")
    if ref:
        spec = importlib.util.spec_from_file_location("qa_balances_reference", ref)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    try:
        return importlib.import_module("app.balances")
    except ModuleNotFoundError as exc:
        if exc.name != "app.balances":
            raise
        raise NotImplementedError("module app.balances does not exist yet (S4-B-1)") from exc


def expense(currency, payers, splits):
    return {"currency": currency, "payers": list(payers), "splits": list(splits)}


def settlement(currency, from_user, to_user, amount):
    return {"currency": currency, "from_user_id": from_user, "to_user_id": to_user, "amount_minor": amount}
