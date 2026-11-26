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
    v2 = r.get("schema") == 2
    l2 = r.get("level2") or []
    l2 = l2 if isinstance(l2, list) else [l2]
    blocks = [r["level1"]] + l2 + r.get("level3", [])
    if v2:
        check(len(l2) <= 3, f"{rid}: level 2 has at most 3 charts")
        check(all(b.get("tab") for b in r.get("level3", [])), f"{rid}: every level-3 chart is a tab")
    for b in blocks:
        check(b.get("source", {}).get("file", "").startswith("http"), f"{rid}: '{b['title']}' has a source link")
        check((bool(b.get("unit")) or b["kind"] == "table") and b.get("period"), f"{rid}: '{b['title']}' shows unit and period")
        if v2:
            check(bool(b.get("why")), f"{rid}: '{b['title']}' has its why-this-chart caption")
            check(all(x.get("url", "").startswith("http") and x.get("quote") for x in b.get("explain", [])), f"{rid}: '{b['title']}' explanations quote and link GASTAT")
        if b["kind"] in ("line", "small_multiples"):
            shown = len(b.get("default") or b["series"]) if b.get("selectable") else len(b["series"])
            check(shown <= 6, f"{rid}: '{b['title']}' shows at most 6 series")
            for s in b["series"]:
                check(len(s["points"]) >= 8 or b["kind"] == "small_multiples" or (v2 and len(s["points"]) >= 3), f"{rid}: '{s['label']}' has enough periods")
                kinds = {("Q" if "Q" in p else "M" if len(p) == 7 else "Y") for p, _ in s["points"]}
                check(len(kinds) == 1, f"{rid}: '{s['label']}' does not mix annual and monthly periods")
                check("=100" not in s["label"] and "=" not in s["label"][:6], f"{rid}: '{s['label']}' has no base-year text in its name")
        if b["kind"] == "bars":
            check(all("=100" not in x["label"] for x in b["bars"]), f"{rid}: no base-year text in bar labels")
        if b["kind"] == "bars_filter":
            check(all("=100" not in x["label"] for g in b["groups"].values() for x in g), f"{rid}: no base-year text in bar labels")
    pr = r["headline"].get("press_release_value")
    if pr is not None:
        check(abs(round(r["headline"]["value"], 1) - pr) <= 0.051, f"{rid}: headline equals the GASTAT press release")
    print("ok  ", rid, "levels", r["levels"], "headline", round(r["headline"]["value"], 2), r["headline"]["unit"])
print("failures:", len(fails))
sys.exit(1 if fails else 0)
