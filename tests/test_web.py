"""Checks on the exported web data and the page files. Run: python3 -I tests/test_web.py (exit 1 on failure)"""
import glob, json, pathlib, re, sys
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parent.parent
W = ROOT / "web"
fails = []
cat = json.loads((W / "data" / "catalog.json").read_text(encoding="utf-8"))["datasets"]
stored = {pathlib.Path(f).stem: len(pd.read_parquet(f, columns=["value"])) for f in glob.glob(str(ROOT / "data" / "*" / "*.parquet"))}
if {d["dataset_id"] for d in cat} != set(stored):
    fails.append(f"catalog has {len(cat)} datasets, data folder has {len(stored)}")
for d in cat:
    s = json.loads((W / "data" / "series" / f"{d['dataset_id']}.json").read_text(encoding="utf-8"))
    n = sum(1 for x in s["series"] for v in x["values"] if v is not None)
    if n != d["values"] or d["values"] != stored[d["dataset_id"]]:
        fails.append(f"{d['dataset_id']}: series has {n} values, catalog {d['values']}, parquet {stored[d['dataset_id']]}")
    if any(len(x["values"]) != len(s["periods"]) for x in s["series"]):
        fails.append(f"{d['dataset_id']}: misaligned series")
    if not d["freshness"]["status"]:
        fails.append(f"{d['dataset_id']}: no freshness")
html = (W / "index.html").read_text(encoding="utf-8")
if html.count("الهيئة العامة للإحصاء") < 4 or "<footer" not in html or 'class="credit"' not in html:
    fails.append("GASTAT credit missing from the page shell")
for f in list(W.glob("*.html")) + list(W.glob("*.js")) + list(W.glob("*.css")):
    t = f.read_text(encoding="utf-8")
    if "—" in t or "–" in t:
        fails.append(f"long dash in {f.name}")
for f in ("latest", "freshness", "quality"):
    json.loads((W / "data" / f"{f}.json").read_text(encoding="utf-8"))
print("datasets", len(cat), "failures", len(fails))
for x in fails[:15]:
    print("  FAIL", x)
sys.exit(1 if fails else 0)
