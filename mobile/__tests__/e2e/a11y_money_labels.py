"""S6-Q-3 helper: on the emulator, every visible money value must be readable by TalkBack. A signed amount (+/-/U+2212)
is read badly, so its text node must be covered by an accessibility label (content-desc) without the sign.
Checks a few screens of a logged-in user. Run: cd mobile/__tests__/e2e && python3 a11y_money_labels.py <email>"""
import re
import sys
import time

import adbkit as k

MONEY = re.compile(r"[+−-]\s?(?:[A-Z]{3}\s)?\d[\d,]*(?:\.\d+)?")
ANY_MONEY = re.compile(r"\b[A-Z]{3}\s[\d,]+(?:\.\d+)?|\d[\d,]*\.\d\d")


def audit(label):
    bad, seen = [], 0
    nds = k.nodes()
    descs = [n["desc"] for n in nds if n["desc"]]
    for n in nds:
        t = n["text"]
        if not t or not ANY_MONEY.search(t):
            continue
        seen += 1
        amount = re.sub(r"^[+−-]\s?", "", MONEY.search(t).group(0)) if MONEY.search(t) else None
        if MONEY.search(t):  # signed: needs a desc that carries the same amount without a sign
            stem = re.sub(r"[+−]", "", t).strip()
            if not any(amount in d and not re.search(r"[+−]", d) for d in descs):
                bad.append(t)
    print(f"{label}: {seen} money texts, {len(bad)} without an unsigned accessibility label {bad}")
    return seen, bad


if __name__ == "__main__":
    k.fresh_app()
    k.wait(r"^Log in$", 60)
    k.tap(r"^Log in$", clickable=True, last=True)
    k.login_ui(sys.argv[1])
    k.wait(r"Open group|Friends", 40)
    total, allbad = 0, []
    s, b = audit("Groups tab"); total += s; allbad += b
    k.tap(r"^Friends$", clickable=True); time.sleep(2)
    s, b = audit("Friends tab"); total += s; allbad += b
    k.tap(r"^Friend: ", clickable=True); time.sleep(3)
    s, b = audit("Friend detail"); total += s; allbad += b
    k.back(); k.tap(r"^Groups$", clickable=True); k.tap(r"^Open group "); time.sleep(3)
    s, b = audit("Group detail"); total += s; allbad += b
    k.tap(r"^Balances$", clickable=True); time.sleep(3)
    s, b = audit("Balances"); total += s; allbad += b
    print("TOTAL", total, "UNLABELLED", len(allbad))
    sys.exit(1 if allbad or total == 0 else 0)
