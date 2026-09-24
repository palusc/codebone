"""Verifies the three benchmark tasks. Usage: python3 check.py <project_dir>  -> prints JSON, exit 0 if all pass."""
import json
import os
import sys
import tempfile

proj = os.path.abspath(sys.argv[1])
sys.path.insert(0, proj)
os.chdir(proj)
os.environ["SHOP_DB"] = os.path.join(tempfile.mkdtemp(), "db.json")
res = {}

try:
    from utils import calc2
    from export import export_csv
    inv = {"id": 1, "items": [{"price": 100, "qty": 1}]}
    res["vat"] = calc2.tot(inv["items"]) == 120.0 and export_csv.row_for(inv)["gross"] == 120.0
except Exception:
    res["vat"] = False

try:
    from web import h_cust
    r = h_cust.new_c({"id": 7, "name": "Ann", "email": "a@x.io", "phone": "+49 123"})
    g = h_cust.get_c({"id": 7})["customer"]
    res["phone"] = r["customer"].get("phone") == "+49 123" and g.get("phone") == "+49 123"
    h_cust.new_c({"id": 8, "name": "Bob"})  # phone stays optional
    res["phone"] = res["phone"] and h_cust.get_c({"id": 8})["ok"]
except Exception:
    res["phone"] = False

try:
    from auth_stuff import tok
    t = tok.make_reset_token("u", now=1000)
    res["token"] = tok.is_valid(t, now=1000 + 600) and not tok.is_valid(t, now=1000 + 1000)
except Exception:
    res["token"] = False

print(json.dumps(res))
sys.exit(0 if all(res.values()) else 1)
