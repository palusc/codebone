"""Generates the benchmark project: a deliberately messy, undocumented mini shop backend.

Usage: python3 make_project.py <target_dir>

Names are unhelpful on purpose (calc2.py, h_cust.py, tok.py ...), there is dead legacy code and
30 distractor modules, so an agent without an architecture map has to grep and read around.
Pure stdlib, deterministic. Verification lives outside the project in check.py.
"""
import sys
from pathlib import Path

FILES = {
"app.py": '''
from web import h_cust, h_inv, h_misc

ROUTES = {
    "GET /c": h_cust.get_c,
    "POST /c": h_cust.new_c,
    "POST /i": h_inv.mk_inv,
    "GET /ping": h_misc.ping,
}


def dispatch(method, path, body=None):
    return ROUTES[f"{method} {path}"](body or {})
''',
"utils/__init__.py": "",
"utils/calc2.py": '''
"""money stuff"""
VAT = 0.19


def net(items):
    return sum(i["price"] * i["qty"] for i in items)


def tot(items):
    return round(net(items) * (1 + VAT), 2)
''',
"utils/helpers.py": '''
def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]
''',
"utils/helpers_old.py": '''
# TODO remove, replaced by helpers.py
def clamp(x, lo, hi):
    return x if lo <= x <= hi else (lo if x < lo else hi)
''',
"utils/strs.py": '''
def slug(s):
    return "-".join(s.lower().split())


def trunc(s, n=40):
    return s if len(s) <= n else s[: n - 1] + "~"
''',
"export/__init__.py": "",
"export/export_csv.py": '''
from utils import calc2


def row_for(inv):
    net = calc2.net(inv["items"])
    gross = net * 1.19
    return {"id": inv["id"], "net": round(net, 2), "gross": round(gross, 2)}


def to_csv(invs):
    lines = ["id,net,gross"]
    for inv in invs:
        r = row_for(inv)
        lines.append(f'{r["id"]},{r["net"]},{r["gross"]}')
    return "\\n".join(lines)
''',
"export/pdf_stub.py": '''
def render(inv):
    return f"PDF({inv['id']})"
''',
"db/__init__.py": "",
"db/store.py": '''
import json
import os

_PATH = os.environ.get("SHOP_DB", "shop_db.json")
_FIELDS = ("id", "name", "email")


def _load():
    if not os.path.exists(_PATH):
        return {"customers": {}, "invoices": {}}
    with open(_PATH) as f:
        return json.load(f)


def _save(db):
    with open(_PATH, "w") as f:
        json.dump(db, f)


def save_customer(c):
    db = _load()
    db["customers"][str(c["id"])] = {k: c.get(k) for k in _FIELDS}
    _save(db)


def get_customer(cid):
    return _load()["customers"].get(str(cid))


def save_invoice(inv):
    db = _load()
    db["invoices"][str(inv["id"])] = inv
    _save(db)
''',
"db/migrate_tmp.py": '''
# one-off from 2021, do not run
from db import store

def run():
    for cid in range(1, 5):
        store.save_customer({"id": cid, "name": f"legacy{cid}", "email": None})
''',
"web/__init__.py": "",
"web/h_cust.py": '''
from db import store


def new_c(body):
    c = {"id": body["id"], "name": body["name"], "email": body.get("email")}
    store.save_customer(c)
    return {"ok": True, "customer": c}


def get_c(body):
    c = store.get_customer(body["id"])
    if c is None:
        return {"ok": False}
    return {"ok": True, "customer": {"id": c["id"], "name": c["name"], "email": c["email"]}}
''',
"web/h_inv.py": '''
from db import store
from utils import calc2


def mk_inv(body):
    inv = {"id": body["id"], "items": body["items"], "total": calc2.tot(body["items"])}
    store.save_invoice(inv)
    return {"ok": True, "invoice": inv}
''',
"web/h_misc.py": '''
def ping(_body):
    return {"ok": True, "pong": True}
''',
"auth_stuff/__init__.py": "",
"auth_stuff/tok.py": '''
import secrets

TTL_MINUTES = 15


def make_reset_token(user, now):
    return {"user": user, "value": secrets.token_hex(8), "issued": now}


def is_valid(tok, now):
    return now - tok["issued"] < TTL_MINUTES
''',
"auth_stuff/pw.py": '''
import hashlib


def hash_pw(pw, salt="x"):
    return hashlib.sha256((salt + pw).encode()).hexdigest()
''',
"notif/__init__.py": "",
"notif/mailer.py": '''
def send(to, subject, body):
    print(f"MAIL to={to} subject={subject}")
    return True
''',
"old/inv_old.py": '''
# legacy invoice math, unused since 2020
def total_old(items):
    return sum(i["price"] * i["qty"] for i in items) * 1.16
''',
}

# 30 distractor modules; some mention tax/customer/token words on purpose.
DISTRACT_TOPICS = [
    "tax_report", "customer_stats", "token_debug", "cust_export_notes", "vat_notes", "reset_mail_tpl",
    "csv_utils", "date_fmt", "geo_lookup", "currency_fmt", "retry", "cache_lru", "pager", "sorter",
    "img_thumb", "audit_log", "feature_flags", "rate_limit", "cust_import", "inv_numbering",
    "locale", "unit_conv", "queue_stub", "health", "metrics_stub", "session_stub", "csv_diff",
    "text_wrap", "color_utils", "id_gen",
]


def distractor(i, name):
    return (
        f'"""{name.replace("_", " ")} helper #{i}"""\n\n\n'
        f"def {name}_a(x):\n    return [x, {i}, '{name}']\n\n\n"
        f"def {name}_b(items):\n    return sorted(items, key=lambda v: (len(str(v)), {i}))\n"
    )


def main(target):
    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.lstrip("\n"))
    folders = ["misc", "tools", "reports", "extras"]
    for i, name in enumerate(DISTRACT_TOPICS):
        d = root / folders[i % len(folders)]
        d.mkdir(exist_ok=True)
        (d / "__init__.py").touch()
        (d / f"{name}.py").write_text(distractor(i, name))


if __name__ == "__main__":
    main(sys.argv[1])
