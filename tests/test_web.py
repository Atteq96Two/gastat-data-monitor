"""Checks the website data: every card and report obeys the redesign rules. Run: python3 -I tests/test_web.py"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
W = ROOT / "web" / "data"
fails = []
def check(c, m):
    if not c:
        fails.append(m); print("FAIL", m)
home = json.loads((W / "home.json").read_text(encoding="utf-8"))
ids = [c["id"] for g in home["groups"] for c in g["cards"]]
check(len(ids) == len(set(ids)) and ids, "cards are unique")
size = sum(p.stat().st_size for p in (ROOT / "web").rglob("*") if p.is_file())
print("web bundle:", round(size / 1e6, 2), "MB")
check(size < 2_000_000, "web bundle under 2 MB")
for rid in ids:
    r = json.loads((W / "reports" / f"{rid}.json").read_text(encoding="utf-8"))
    check(1 <= r["levels"] <= 3, f"{rid}: at most 3 levels")
    check(len(r["description_ar"].split()) <= 10, f"{rid}: description of 10 words or fewer")
    blocks = [r["level1"]] + ([r["level2"]] if r.get("level2") else []) + r.get("level3", [])
    for b in blocks:
        check(b.get("source", {}).get("file", "").startswith("http"), f"{rid}: '{b['title']}' has a source link")
        check(bool(b.get("unit")) and b.get("period"), f"{rid}: '{b['title']}' shows unit and period")
        if b["kind"] in ("line", "small_multiples"):
            check(len(b["series"]) <= 6, f"{rid}: '{b['title']}' has at most 6 series")
            for s in b["series"]:
                check(len(s["points"]) >= 8 or b["kind"] == "small_multiples", f"{rid}: '{s['label']}' has 8 or more periods")
    pr = r["headline"].get("press_release_value")
    if pr is not None:
        check(abs(round(r["headline"]["value"], 1) - pr) <= 0.051, f"{rid}: headline equals the GASTAT press release")
    print("ok  ", rid, "levels", r["levels"], "headline", round(r["headline"]["value"], 2), r["headline"]["unit"])
print("failures:", len(fails))
sys.exit(1 if fails else 0)
