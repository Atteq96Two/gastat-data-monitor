"""Re-run the extraction engine on already downloaded files (cache/files/<id>/source.xlsx) after an engine fix.

  python3 -I gastat/reingest.py            dry run: list which datasets would change, change nothing
  python3 -I gastat/reingest.py --apply    replace those datasets' rows for that publication, log value changes as revisions

Only rows of the publication being re-run are replaced, so history from other releases is never touched.
"""
import argparse, datetime as dt, hashlib, json, pathlib, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
from gastat import collect                                  # noqa: E402
from gastat.run import process                              # noqa: E402
from gastat.store import merge_dataset, append_revisions, KEY  # noqa: E402


def fresh_rows(p):
    xlsx = ROOT / "cache" / "files" / str(p["publication_id"]) / "source.xlsx"
    xl = next(f for f in p["files"] if f["type"] == "xlsx")
    tables, rows = process(p, xlsx, strict=True)
    rows = [r for r in rows if r["table_status"] == "pass"]
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    by = {}
    for r in rows:
        r.update(publication_id=p["publication_id"], release_date=p["release_date"], domain=p["domain_id"], source_file_url=xl["url"], ingested_at=ts,
                 unit=r["unit"] or "", source_cell=f"{r['sheet']}!R{r['source_row']}C{r['source_col']}")
        by.setdefault((p["domain_id"], r["dataset_id"]), []).append(r)
    return by


def signature(df):
    d = df.copy()
    if "table_title" not in d.columns:
        d["table_title"] = ""
    return set(zip(*(d[c].astype(str) for c in KEY + ["unit", "scale", "measure_type", "period_type", "table_title"]), d["value"].round(9).astype(str)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--pid", type=int)
    a = ap.parse_args()
    reg = json.loads((ROOT / "registry" / "publications.json").read_text(encoding="utf-8"))["publications"]
    from gastat.store import _frame
    changed_total = 0
    for p in sorted(reg, key=lambda x: x["release_date"]):
        if not str(p.get("status", "")).startswith("processed") or (a.pid and p["publication_id"] != a.pid):
            continue
        if not (ROOT / "cache" / "files" / str(p["publication_id"]) / "source.xlsx").exists():
            print("skip (no cached file):", p["publication_id"], p["title_en"]); continue
        xl = next(f for f in p["files"] if f["type"] == "xlsx")
        cached = ROOT / "cache" / "files" / str(p["publication_id"]) / "source.xlsx"
        if xl.get("sha256") and hashlib.sha256(cached.read_bytes()).hexdigest() != xl["sha256"]:
            data = collect.http_get(xl["url"].replace(" ", "%20"), binary=True)   # cached copy is an older version: fetch the published one
            if hashlib.sha256(data).hexdigest() != xl["sha256"]:
                print("skip (published file differs from the registered version):", p["publication_id"], p["title_en"]); continue
            cached.write_bytes(data)
        by = fresh_rows(p)
        pid = str(p["publication_id"])
        stored = {}
        for f in (ROOT / "data").glob("*/*.parquet"):
            df = pd.read_parquet(f)
            df = df[df["publication_id"] == pid]
            if len(df):
                stored[(f.parent.name, f.stem)] = (f, df)
        changed = []
        for k, (f, df) in stored.items():
            new = signature(_frame(by.get(k, [])).drop_duplicates(KEY, keep="last")) if k in by else set()
            if new != signature(df):
                changed.append(k)
        for k in by:
            if k not in stored:
                changed.append(k)
        print(f"{p['publication_id']} {p['title_en'][:55]}: {len(changed)} dataset(s) would change", [c[1] for c in changed][:6])
        changed_total += len(changed)
        if a.apply and changed:
            run_ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            for k in changed:
                if k in stored:   # drop this publication's rows first so wrong keys do not survive next to the corrected ones
                    f, _ = stored[k]
                    allrows = pd.read_parquet(f)
                    rest = allrows[allrows["publication_id"] != pid]
                    if len(rest):
                        rest.to_parquet(f, compression="zstd", index=False)
                    else:
                        f.unlink(missing_ok=True); f.with_suffix(".csv").unlink(missing_ok=True)
                if k in by:
                    _, _, _, revs = merge_dataset(k[0], k[1], by[k], run_ts)[0:4]
                    append_revisions(revs)
    print("total datasets changed:", changed_total, "(applied)" if a.apply else "(dry run)")


if __name__ == "__main__":
    main()
