"""One-off: rebuild data/ as Parquet (+ small CSV mirrors) from the validated Phase 2 rows."""
import sys, json, pickle, shutil, pathlib, collections, datetime as dt
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from gastat.store import merge_dataset
reg = {p["publication_id"]: p for p in json.load(open(ROOT / "registry/publications.json"))["publications"]}
R = pickle.load(open(ROOT / "cache/phase2_rows.pkl", "rb"))
shutil.rmtree(ROOT / "data", ignore_errors=True)
ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def col_letter(n):
    s = ""
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s
by = collections.defaultdict(list)
for pid, rows in R.items():
    url = next(f["url"] for f in reg[pid]["files"] if f["type"] == "xlsx")
    for r in rows:
        if r["table_status"] != "pass": continue
        r.update(source_file_url=url, source_cell=f"{r['sheet']}!{col_letter(r['source_col'])}{r['source_row']}", ingested_at=ts, unit=r["unit"] or "")
        by[(r["domain"], r["dataset_id"])].append(r)
tot = 0
for (dom, ds), rows in by.items():
    a, rv, u, _ = merge_dataset(dom, ds, rows, ts); tot += a
print("datasets", len(by), "rows", tot)
