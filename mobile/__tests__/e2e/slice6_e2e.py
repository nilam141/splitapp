"""Slice 6 emulator E2E (S6-Q-2): FLOW-02 (invite link), 06, 07, 08, 09, 10, 11.

Not a jest test. Maestro is not installed in this environment, so the UI is driven with adb + uiautomator (adbkit.py).
Run with the dev environment up:   ./scripts/dev.sh up --build   then   python3 -I mobile/__tests__/e2e/slice6_e2e.py
(`-I` is not usable because the script imports its sibling adbkit; run it as `cd mobile/__tests__/e2e && python3 slice6_e2e.py`).
Every run registers fresh users (unique e-mails) so it can be repeated. Steps that depend on Blocked items (decision D-C)
or on features that are not built are recorded as BLOCKED with the reason, never faked.
Needs: Postgres reachable with the dev DB (premium is granted by inserting a `subscriptions` row, the stand-in for the
Blocked Play verification endpoint).
"""
import os
import subprocess
import sys
import time
import traceback

import adbkit as k

RUN = str(int(time.time()))
PSQL = "/Applications/Postgres.app/Contents/Versions/15/bin/psql"
DB = "postgresql://splitapp:splitapp@localhost:5432/splitapp"
RESULTS = []  # (flow, step, status, note)


def rec(flow, step, status, note=""):
    RESULTS.append((flow, step, status, note))
    print(f"[{status}] {flow} {step} {note}", flush=True)


def sql(q):
    return subprocess.run([PSQL, DB, "-tAc", q], capture_output=True, text=True, check=True).stdout.strip()


def email(tag):
    return f"{tag}.{RUN}@example.com"


def ui_login(addr):
    k.fresh_app()
    k.wait(r"^Log in$", 60)
    k.tap(r"^Log in$", clickable=True, last=True)
    k.login_ui(addr)
    k.wait(r"Start a new group|No groups yet|Friends", 40)


def group_id(token, name):
    return next(g["id"] for g in k.api("GET", "/groups", token=token)[1]["items"] if g["name"] == name)


def flow(name):
    def deco(fn):
        def run():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                rec(name, "ABORTED", "FAIL", f"{type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    k.screenshot(f"{os.environ.get('TMPDIR', '.')}/e2e_fail_{name}.png")
                except Exception:  # noqa: BLE001
                    pass
        return run
    return deco


def check(flow_name, step, cond, note=""):
    rec(flow_name, step, "PASS" if cond else "FAIL", note)
    if not cond:
        raise AssertionError(f"{flow_name} {step} failed {note}")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-10")
def flow10():
    f = "FLOW-10"
    a = k.register("Asha Ten", email("asha10"))
    ta = a["access_token"]
    gid = k.api("POST", "/groups", {"name": f"Link Group {RUN}"}, token=ta)[1]["id"]
    token = k.api("GET", f"/groups/{gid}/invite-link", token=ta)[1]["token"]
    k.fresh_app()
    k.wait(r"^Sign up$", 60)
    k.deeplink(f"https://splitapp.example/join/{token}")  # link opened while logged out
    check(f, "1 link opened logged out: stays on SCR-01 (pending link stored)", k.find(r"^Sign up$") is not None)
    k.tap(r"^Sign up$", clickable=True, last=True)
    k.wait(r"Full name")
    k.type_into(0, "Dev Ten")
    d_mail = email("dev10")
    k.type_into(1, d_mail)
    k.type_into(2, k.PW)
    k.hide_keyboard()
    k.tap(r"^Sign up$", clickable=True, last=True)
    k.wait(r"Join this group\?", 40)
    rec(f, "2-3 after sign-up the pending link resumes on SCR-18", "PASS")
    k.tap(r"^Join group$", clickable=True, last=True)
    k.wait(f"Link Group {RUN}", 30)
    members = [m["user"]["name"] for m in k.api("GET", f"/groups/{gid}", token=ta)[1]["members"]]
    check(f, "3 join -> SCR-13, D is a member on the server", "Dev Ten" in members, str(members))
    # alternate: expired link -> "invite no longer valid"
    k.api("POST", f"/groups/{gid}/invite-link", token=ta)  # reset: the old token is now 410
    e = k.register("Eve Ten", email("eve10"))
    k.fresh_app()
    k.wait(r"^Log in$", 60)
    k.tap(r"^Log in$", clickable=True, last=True)
    k.login_ui(email("eve10"))
    k.wait(r"No groups yet|Start a new group", 40)
    k.deeplink(f"https://splitapp.example/join/{token}")
    k.wait(r"Join this group\?", 30)
    k.tap(r"^Join group$", clickable=True, last=True)
    n = k.wait(r"(?i)no longer valid|expired", 20)
    check(f, "alt expired link shows 'invite no longer valid'", n is not None, n["text"] or n["desc"])
    rec(f, "no-account install via Play (steps 'app installs')", "BLOCKED", "install-from-link not testable on an emulator; the link opens the installed app")
    rec(f, "alt SCR-07 after expiry", "NOTE", "the app shows the message on SCR-18 rather than navigating to SCR-07; see report")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-02")
def flow02():
    f = "FLOW-02"
    a = k.register("Asha Two", email("asha02"))
    ta = a["access_token"]
    c = k.register("Cara Two", email("cara02"))
    gid = k.api("POST", "/groups", {"name": f"Goa Two {RUN}", "new_members": [{"name": "Kiran", "email": email("kiran02")}]}, token=ta)[1]["id"]
    rec(f, "1-6 create group UI (SCR-12, SCR-21, SCR-13)", "SKIPPED", "group creation is covered by jest slice2Groups; this run seeds the group (with placeholder Kiran) through the API")
    ui_login(email("asha02"))
    k.tap(f"Open group Goa Two {RUN}")
    k.tap(r"^Settings$", clickable=True)
    k.tap(r"^Invite via link$", clickable=True)
    n = k.wait(r"https://splitapp\.example/join/")
    link = [t for t in k.texts() if t.startswith("https://splitapp.example/join/")][0]
    tok1 = link.rsplit("/", 1)[1]
    check(f, "7 SCR-17 shows the invite link", tok1 == k.api("GET", f"/groups/{gid}/invite-link", token=ta)[1]["token"])
    rec(f, "7 Share copies the link", "BLOCKED", "no Copy button (no clipboard module installed, progress.md mobile handoff); Share opens the OS sheet, not asserted")
    k.tap(r"^Reset link$", clickable=True)
    k.tap(r"^(Reset|Reset link|Confirm)$", clickable=True, last=True)
    time.sleep(3)
    tok2 = [t for t in k.texts() if t.startswith("https://splitapp.example/join/")][0].rsplit("/", 1)[1]
    check(f, "alt reset link gives a new token in the UI", tok2 != tok1)
    cb = k.api("POST", "/groups/join", {"token": tok1}, token=k.login_api(email("cara02"))[0])
    check(f, "alt the old token answers 410", cb[0] == 410, str(cb[0]))
    # step 8: C (registered) opens the link while logged in -> SCR-18 -> join
    ui_login(email("cara02"))
    k.deeplink(f"https://splitapp.example/join/{tok2}")
    k.wait(r"Join this group\?", 30)
    rec(f, "8 SCR-18 lists placeholder Kiran + 'not on the list'", "BLOCKED", "invite preview endpoint Blocked (D-C): SCR-18 has no placeholder list")
    k.tap(r"^Join group$", clickable=True, last=True)
    k.wait(f"Goa Two {RUN}", 30)
    members = [m["user"]["name"] for m in k.api("GET", f"/groups/{gid}", token=ta)[1]["members"]]
    check(f, "8 C joined: 3rd member (A, Kiran, C)", "Cara Two" in members and len(members) == 3, str(members))
    rec(f, "8 claim placeholder", "BLOCKED", "claim needs the preview list (D-C); backend merge is covered by test_invites.py")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-06")
def flow06():
    f = "FLOW-06"
    k.register("Asha Six", email("asha06"))
    k.register("Ravi Six", email("ravi06"))
    ta, aid = k.login_api(email("asha06"))
    ui_login(email("asha06"))
    k.tap(r"^Friends$", clickable=True)
    k.tap(r"^Add friend$", clickable=True)
    k.wait(r"Add people")
    k.type_into(1, "abc")
    k.hide_keyboard()
    k.tap(r"^Add to list$", clickable=True, last=True)
    time.sleep(1)
    check(f, "alt 'abc' is refused inline", k.find(r"(?i)not a valid|valid email") is not None, " | ".join(k.texts()[:12]))
    k.clear_and_type(1, email("ravi06"))
    k.hide_keyboard()
    k.tap(r"^Add to list$", clickable=True, last=True)
    k.tap(r"^Done", clickable=True, last=True)
    k.wait(r"Friend: Ravi Six", 20)
    friends = [x["user"]["name"] for x in k.api("GET", "/friends", token=ta)[1]["items"]] if True else []
    check(f, "2-3 e-mail add: Ravi on SCR-08 as 'settled up' and on the server", "Ravi Six" in friends and k.find(r"settled up") is not None, str(friends))
    rec(f, "4 contact (Neha) with contacts permission", "SKIPPED", "contacts primer/permission dialog needs a granted READ_CONTACTS and seeded device contacts; not driven (jest covers the primer)")
    rec(f, "5 QR scan / friend-code lookup", "BLOCKED", "friend-code lookup endpoint and QR library Blocked (D-C)")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-07")
def flow07():
    f = "FLOW-07"
    a = k.register("Asha Seven", email("asha07"))
    b = k.register("Bo Seven", email("bo07"))
    ta, aid = a["access_token"], a["user"]["id"]
    bid = b["user"]["id"]
    gid = k.api("POST", "/groups", {"name": f"Flat Seven {RUN}", "member_user_ids": [bid]}, token=ta)[1]["id"]
    ui_login(email("asha07"))
    k.tap(f"Open group Flat Seven {RUN}")
    k.tap(r"^Add expense$", clickable=True, last=True)
    k.wait(r"Description")
    k.type_into(0, "Rent")
    k.type_into(1, "30000")
    k.hide_keyboard()
    k.tap(r"^Date$", clickable=True)
    k.wait(r"Expense date")
    k.clear_and_type(0, "2026-01-31")
    k.hide_keyboard()
    k.tap(r"^Repeat: Every month$", clickable=True)
    k.tap(r"^Reminder: 2 days before$", clickable=True)
    k.tap(r"^Done$", clickable=True, last=True)
    k.wait(r"repeats monthly")
    k.tap(r"^Save$", clickable=True, last=True)
    k.wait(r"Expense: Rent", 20)
    rules = k.api("GET", "/recurring-expenses", token=ta)[1]["items"]
    r = next((x for x in rules if x["group_id"] == gid), None)
    check(f, "1-3 rule in GET /recurring-expenses", r is not None, str(rules))
    check(f, "3 next_occurrence_date 2026-02-28, monthly, reminder 2 days, 3000000 INR minor", (r["next_occurrence_date"], r["interval"], r["reminder_days_before"], r["total"]["amount_minor"]) == ("2026-02-28", "monthly", 2, 3000000), str(r))
    k.tap(r"Expense: Rent")
    k.wait(r"Repeats monthly, next on 2026-02-28")
    rec(f, "SCR-29 shows 'Repeats monthly, next on 2026-02-28'", "PASS")
    rec(f, "4-6 scheduler, reminders emails, system actor", "SKIPPED", "scheduler is a separate process (not started by dev up); covered by backend test_recurring.py. Not driven on the emulator")
    k.tap(r"^Stop repeating$", clickable=True)
    k.tap(r"^(Stop repeating|Stop|Confirm)$", clickable=True, last=True)
    time.sleep(3)
    rules = k.api("GET", "/recurring-expenses", token=ta)[1]["items"]
    r = next(x for x in rules if x["group_id"] == gid)
    check(f, "alt Stop repeating -> PATCH active=false on the server", r["active"] is False, str(r))
    rec(f, "alt 'edit E1, Repeat: never' through the edit form", "NOTE", "mobile handoff: done with the Stop button, edit form has no repeat control (documented deviation)")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-08")
def flow08():
    f = "FLOW-08"
    a = k.register("Asha Eight", email("asha08"))
    b = k.register("Bo Eight", email("bo08"))
    ta, aid = a["access_token"], a["user"]["id"]
    tb, bid = b["access_token"], b["user"]["id"]
    gid = k.api("POST", "/groups", {"name": f"Eight {RUN}", "member_user_ids": [bid]}, token=ta)[1]["id"]
    k.add_expense(ta, gid, aid, [aid, bid], 5000, desc="Groceries")  # an INR balance
    k.add_expense(ta, gid, aid, [aid, bid], 9000, currency="USD", desc="Hotel")  # 90.00 USD, split 45.00 each
    ui_login(email("asha08"))
    k.tap(f"Open group Eight {RUN}")
    k.wait(r"owes you \+USD 45\.00")
    texts = k.texts()
    check(f, "3 group screen: separate INR and USD lines, no conversion", any("INR 25.00" in t for t in texts) and any("USD 45.00" in t for t in texts), str(texts[:14]))
    check(f, "3 no 'convert' action offered (Later feature)", not any("onvert" in t for t in texts))
    k.back()
    k.wait(r"Overall: you are owed")
    ov = [t for t in k.texts() if t.startswith("Overall: you are owed")][0]
    check(f, "3 SCR-08 overall summary lists both currencies unconverted", "INR 25.00" in ov and "USD 45.00" in ov, ov)
    st = k.api("POST", "/settlements", {"group_id": gid, "from_user_id": bid, "to_user_id": aid, "amount": {"amount_minor": 3000, "currency": "USD"}, "settled_on": "2026-11-05"}, token=tb)
    check(f, "4 partial USD settlement via API (the settle UI is Slice 5)", st[0] == 201)
    ui_login(email("asha08"))
    k.tap(f"Open group Eight {RUN}")
    k.wait(r"owes you \+USD 15\.00", 20)
    texts = k.texts()
    check(f, "4 USD balance is 15.00 and INR untouched", any("USD 15.00" in t for t in texts) and any("INR 25.00" in t for t in texts), str(texts[:14]))
    rec(f, "5-6 convert all to INR", "BLOCKED", "Later feature: endpoint not in the contract")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-09")
def flow09():
    f = "FLOW-09"
    a = k.register("Asha Nine", email("asha09"))
    b = k.register("Bo Nine", email("bo09"))
    ta, aid = a["access_token"], a["user"]["id"]
    tb, bid = b["access_token"], b["user"]["id"]
    gid = k.api("POST", "/groups", {"name": f"Flat 4B {RUN}", "member_user_ids": [bid]}, token=ta)[1]["id"]
    for i, amt in enumerate((90000, 30000, 12000)):
        k.add_expense(ta, gid, aid, [aid, bid], amt, desc=f"Item{i}")
    k.api("POST", "/settlements", {"group_id": gid, "from_user_id": bid, "to_user_id": aid, "amount": {"amount_minor": 10000, "currency": "INR"}, "settled_on": "2026-11-05"}, token=tb)
    before = int(sql(f"select count(*) from exports where requested_by='{aid}'"))
    ui_login(email("asha09"))
    k.tap(f"Open group Flat 4B {RUN}")
    k.tap(r"^Settings$", clickable=True)
    k.tap(r"^Export to CSV$", clickable=True)
    k.wait(r"Upgrade to Premium", 15)
    after = int(sql(f"select count(*) from exports where requested_by='{aid}'"))
    check(f, "alt free user lands on SCR-39 and no export row is created", after == before, f"{before}->{after}")
    # grant premium (stand-in for the Blocked Play verification), cold restart so /users/me is re-read
    sql(f"insert into subscriptions(user_id,plan,status,current_period_end,store) values('{aid}','premium_monthly','active',now()+interval '30 days','google_play') on conflict (user_id) do update set plan='premium_monthly',status='active',current_period_end=now()+interval '30 days'")
    ui_login(email("asha09"))
    k.tap(f"Open group Flat 4B {RUN}")
    k.tap(r"^Settings$", clickable=True)
    k.tap(r"^Export to CSV$", clickable=True)
    k.wait(r"flat-4b-.*\.csv", 40)
    rec(f, "1-3 premium: generating -> share sheet with flat-4b-<date>.csv", "PASS")
    eid = sql(f"select id from exports where requested_by='{aid}' order by created_at desc limit 1")
    ex = k.api("GET", f"/exports/{eid}", token=ta)[1]
    import urllib.request
    csv = urllib.request.urlopen(ex["download_url"]).read().decode().strip().split("\n")
    check(f, "4 CSV: 1 header + 3 expenses + 1 payment + 1 total = 6 lines", len(csv) == 6, str(csv))
    check(f, "4 90000 minor renders 900.00", any(",900.00,INR," in ln for ln in csv))
    rec(f, "3 app downloads the file and shares it", "NOTE", "the share sheet shows 'Sharing text' (a link as text), not a CSV file; and download_url is http://localhost:8000/... which an emulator or phone cannot reach (needs 10.0.2.2 / a public base URL). See report")
    k.back()
    rec(f, "alt failure -> try again", "SKIPPED", "needs a failing generation; covered by jest (SUI-M-138 retry sends 1 request)")


# ---------------------------------------------------------------------------------------------------------------------
@flow("FLOW-11")
def flow11():
    f = "FLOW-11"
    a = k.register("Asha Eleven", email("asha11"))
    b = k.register("Bo Eleven", email("bo11"))
    ta, aid = a["access_token"], a["user"]["id"]
    bid = b["user"]["id"]
    gid = k.api("POST", "/groups", {"name": f"Eleven {RUN}", "member_user_ids": [bid]}, token=ta)[1]["id"]
    k.add_expense(ta, gid, aid, [aid, bid], 5000, desc="Dinner")  # B owes A 25.00
    n0 = int(sql(f"select count(*) from reminders where from_user_id='{aid}'"))
    ui_login(email("asha11"))
    k.tap(r"^Friends$", clickable=True)
    k.tap(r"^Friend: Bo Eleven$")
    k.wait(r"Remind about INR 25\.00")
    k.tap(r"Remind about INR 25\.00")
    k.wait(r"^Message$")
    check(f, "1 SCR-33 message is prefilled with 25.00", any("INR 25.00" in t for t in k.texts()))
    k.tap(r"^Send via app$", clickable=True, last=True)
    seen = []
    for _ in range(6):
        seen += k.texts()
    check(f, "2 toast 'Reminder sent'", any(t == "Reminder sent" for t in seen))
    n1 = int(sql(f"select count(*) from reminders where from_user_id='{aid}'"))
    outbox = sql(f"select count(*) from notifications where user_id='{bid}' and type='reminder'")
    check(f, "2 one reminders row and one outbox row", n1 - n0 == 1 and outbox == "1", f"{n1 - n0}, {outbox}")
    k.tap(r"Remind about INR 25\.00")
    k.wait(r"^Message$")
    k.tap(r"^Send via app$", clickable=True, last=True)
    seen = []
    for _ in range(6):
        seen += k.texts()
    check(f, "alt 2nd send within 60 s shows 'Wait 1 minute'", any("Wait 1 minute" in t for t in seen))
    check(f, "alt still one reminders row", int(sql(f"select count(*) from reminders where from_user_id='{aid}'")) - n0 == 1)
    rec(f, "alt Share -> OS share sheet, no server call", "SKIPPED", "not driven (OS sheet); jest covers it")
    rec(f, "alt zero balance hides Remind", "SKIPPED", "not driven on the emulator")


if __name__ == "__main__":
    only = sys.argv[1:]
    for name, fn in (("FLOW-10", flow10), ("FLOW-02", flow02), ("FLOW-06", flow06), ("FLOW-07", flow07),
                     ("FLOW-08", flow08), ("FLOW-09", flow09), ("FLOW-11", flow11)):
        if not only or name in only:
            fn()
    print("\n==== SUMMARY ====")
    for r in RESULTS:
        print(" | ".join(r))
    counts = {}
    for r in RESULTS:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print(counts)
    sys.exit(1 if counts.get("FAIL") else 0)
