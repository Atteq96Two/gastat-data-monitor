"""Write tidy CSVs for validated tables, the coverage report, and the automated cell-equality integrity test."""
import sys, json, pickle, csv, pathlib, collections, datetime as dt, warnings, openpyxl
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
reg = {p["publication_id"]: p for p in json.load(open(ROOT / "registry/publications.json"))["publications"]}
T = json.load(open(ROOT / "cache/phase2_tables.json")); R = pickle.load(open(ROOT / "cache/phase2_rows.pkl", "rb"))
COLS = ["dataset_id", "publication_id", "domain", "sheet", "block", "row_code", "row_level", "row_label_ar", "row_label_en", "row_unit", "row_group",
        "is_total_row", "row_parent", "col_code", "col_sub", "measure_inferred", "unit_inferred", "col_label_ar", "col_label_en", "period", "period_type", "base_period", "measure_type", "unit", "scale", "value",
        "source_file_url", "source_cell", "release_date", "ingested_at", "period_source", "fingerprint"]
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def col_letter(n):
    s = ""
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s
files = collections.defaultdict(list); bad = collections.Counter(); checked = collections.Counter()
for pid, rows in R.items():
    p = reg[pid]; url = next(f["url"] for f in p["files"] if f["type"] == "xlsx")
    wb = openpyxl.load_workbook(ROOT / f"cache/files/{pid}/source.xlsx", data_only=True)
    for r in rows:
        if r["table_status"] != "pass": continue
        r["source_file_url"] = url; r["source_cell"] = f"{r['sheet']}!{col_letter(r['source_col'])}{r['source_row']}"
        r["ingested_at"] = now; r["unit"] = r["unit"] or ""
        v = wb[r["sheet"]].cell(row=r["source_row"], column=r["source_col"]).value
        checked[pid] += 1
        try:
            if abs(float(str(v).replace(",", "")) - r["value"]) > 1e-9: bad[pid] += 1
        except Exception: bad[pid] += 1
        files[(r["domain"], r["dataset_id"])].append(r)
for (dom, ds), rows in files.items():
    d = ROOT / "data" / str(dom); d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{ds}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
# coverage report
L = ["# Phase 2 coverage report (November 2026 pilot)", "", f"Generated {now}. Only tables that pass every gate are written to /data. Others are quarantined and not published.", ""]
L += ["| Publication | Data tables | Validated | Quarantined | Rows published |", "|---|---|---|---|---|"]
tot = collections.Counter()
for pid in sorted(R, key=lambda x: reg[x]["release_date"]):
    ts = [t for t in T if t["pub"] == pid and t["status"] not in ("skipped_navigation", "skipped_decoration")]
    ok = sum(t["status"] == "pass" for t in ts); n = sum(t["rows"] for t in ts if t["status"] == "pass")
    L.append(f"| {reg[pid]['title_en']} | {len(ts)} | {ok} | {len(ts)-ok} | {n} |"); tot["t"] += len(ts); tot["ok"] += ok; tot["n"] += n
L += ["", f"**Total: {tot['ok']} of {tot['t']} data tables validated ({100*tot['ok']/tot['t']:.0f}%), {tot['n']} numbers published.**", ""]
L += ["## Integrity test: every published number equals the original Excel cell", "", "| Publication | Values checked | Mismatches |", "|---|---|---|"]
L += [f"| {reg[p]['title_en']} | {checked[p]} | {bad[p]} |" for p in checked]
L += ["", "## Quarantined tables", "", "| Publication | Sheet | Status | Reason |", "|---|---|---|---|"]
for t in T:
    if t["status"] in ("review", "fail"):
        why = "; ".join(c["detail"][:110] for c in t["checks"] if not c["ok"])
        L.append(f"| {reg[t['pub']]['title_en'][:40]} | {t['sheet']} (block {t['block']}) | {t['status']} | {why.replace('|','/')} |")
(ROOT / "docs").mkdir(exist_ok=True); (ROOT / "docs/coverage_phase2.md").write_text("\n".join(L) + "\n")
print("\n".join(L[:20])); print("datasets written:", len(files))
