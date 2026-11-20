"""Minimal adb UI driver for the Slice 6 emulator E2E (Maestro is not installed in this environment).
Not a jest test: run with `python3 -I mobile/__tests__/e2e/slice6_e2e.py` while `./scripts/dev.sh up` is running."""
import json
import os
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
API = "http://localhost:8000"
APP = "com.splitapp"


def sh(*a, check=True):
    return subprocess.run([ADB, *a], capture_output=True, text=True, check=check).stdout


def api(method, path, body=None, token=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def register(name, email, password="Passw0rd!x1"):
    s, b = api("POST", "/auth/register", {"name": name, "email": email, "password": password})
    assert s == 201, (s, b)
    return b


def nodes():
    sh("shell", "uiautomator", "dump", "/sdcard/u.xml", check=False)
    xml = sh("exec-out", "cat", "/sdcard/u.xml", check=False)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            out.append({"text": n.get("text", ""), "desc": n.get("content-desc", ""), "click": n.get("clickable") == "true",
                        "c": ((x1 + x2) // 2, (y1 + y2) // 2), "b": (x1, y1, x2, y2), "edit": n.get("class", "").endswith("EditText")})
    return out


def texts():
    return [t for n in nodes() for t in (n["text"], n["desc"]) if t]


def find(pattern, nds=None):
    rx = re.compile(pattern)
    for n in (nds if nds is not None else nodes()):
        if rx.search(n["text"]) or rx.search(n["desc"]):
            return n
    return None


def wait(pattern, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        n = find(pattern)
        if n:
            return n
        time.sleep(0.8)
    raise AssertionError(f"timed out waiting for /{pattern}/; screen has: {texts()[:30]}")


def gone(pattern, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if not find(pattern):
            return True
        time.sleep(0.8)
    return False


def tap(pattern, timeout=25, clickable=False, last=False):
    wait(pattern, timeout)
    ms = [n for n in nodes() if (re.search(pattern, n["text"]) or re.search(pattern, n["desc"])) and (n["click"] or not clickable)]
    assert ms, f"no match for /{pattern}/ (clickable={clickable})"
    n = ms[-1] if last else ms[0]
    sh("shell", "input", "tap", str(n["c"][0]), str(n["c"][1]))
    time.sleep(0.8)
    return n


def type_into(pattern_or_index, text):
    """Tap the n-th EditText (int) or the field whose text/desc matches, then type."""
    if isinstance(pattern_or_index, int):
        eds = [n for n in nodes() if n["edit"]]
        n = eds[pattern_or_index]
    else:
        n = wait(pattern_or_index)
    sh("shell", "input", "tap", str(n["c"][0]), str(n["c"][1]))
    time.sleep(0.5)
    sh("shell", "input", "text", "".join("\\" + ch if ch in "&()<>|;$'\"`!*?[]{}~#\\" else ("%s" if ch == " " else ch) for ch in text))
    time.sleep(0.4)


def back():
    sh("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.8)


def hide_keyboard():
    sh("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.5)


def fresh_app():
    sh("shell", "pm", "clear", APP)
    launch()


def launch():
    sh("shell", "am", "start", "-n", f"{APP}/.MainActivity")
    time.sleep(3)


def deeplink(url):
    sh("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", url, "-p", APP)
    time.sleep(2)


def screenshot(path):
    with open(path, "wb") as f:
        f.write(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)


def login_ui(email, password="Passw0rd!x1"):
    wait(r"(?i)log in|sign in|email", 60)
    eds = [n for n in nodes() if n["edit"]]
    assert len(eds) >= 2, texts()
    type_into(0, email)
    type_into(1, password)
    hide_keyboard()
    tap(r"^(Log in|Sign in)$", clickable=True, last=True)


import uuid  # noqa: E402

PW = "Passw0rd!x1"


def login_api(email, password=PW):
    s, b = api("POST", "/auth/login", {"email": email, "password": password})
    assert s == 200, (s, b)
    return b["access_token"], b["user"]["id"]


def add_expense(token, group_id, payer, people, total, currency="INR", desc="Dinner", date="2026-11-05", extra=None):
    body = {"description": desc, "total": {"amount_minor": total, "currency": currency}, "expense_date": date,
            "payers": [{"user_id": payer, "paid_amount_minor": total}],
            "split": {"type": "equal", "entries": [{"user_id": p} for p in people]}, **(extra or {})}
    s, b = api("POST", f"/groups/{group_id}/expenses", body, token=token, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert s == 201, (s, b)
    return b


def clear_and_type(index, text):
    eds = [n for n in nodes() if n["edit"]]
    n = eds[index]
    sh("shell", "input", "tap", str(n["c"][0]), str(n["c"][1]))
    time.sleep(0.4)
    sh("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    sh("shell", "input", "keyevent", *(["KEYCODE_DEL"] * 40))
    type_into(index, text) if False else sh("shell", "input", "text", text)
    time.sleep(0.4)
