"""Dataset storage: one Parquet file per dataset (plus a CSV mirror for small ones). Revisions are logged, never silent."""
import json, pathlib, datetime as dt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = ["dataset_id", "sheet", "block", "row_code", "row_level", "row_label_ar", "row_label_en", "row_unit", "row_group", "row_parent",
       "col_code", "col_label_ar", "col_label_en", "col_sub", "period", "base_period"]
COLS = KEY + ["period_type", "period_source", "is_total_row", "measure_type", "measure_inferred", "unit", "unit_inferred", "scale", "multi_response",
              "value", "publication_id", "domain", "source_file_url", "source_cell", "release_date", "ingested_at", "fingerprint"]
CSV_MAX_BYTES = 1_500_000


def _frame(rows):
    df = pd.DataFrame(rows)
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    df = df[COLS].copy()
    for c in KEY + ["period_type", "period_source", "measure_type", "unit", "source_file_url", "source_cell", "release_date", "ingested_at", "fingerprint"]:
        df[c] = df[c].fillna("").astype(str)
    for c in ("is_total_row", "measure_inferred", "unit_inferred", "multi_response"):
        df[c] = df[c].map(lambda v: bool(v) if v is not None and v == v else False).astype(bool)
    df["block"] = df["block"].astype(str)
    df["domain"] = df["domain"].astype(str); df["publication_id"] = df["publication_id"].astype(str)
    df["scale"] = df["scale"].astype(float); df["value"] = df["value"].astype(float)
    return df


def merge_dataset(domain, dataset_id, rows, run_ts):
    """Merge new rows into data/<domain>/<dataset_id>.parquet. Returns (added, revised, unchanged, revision_rows)."""
    new = _frame(rows).drop_duplicates(KEY, keep="last")
    d = ROOT / "data" / str(domain); d.mkdir(parents=True, exist_ok=True)
    path = d / f"{dataset_id}.parquet"
    revisions = []
    if path.exists():
        old = pd.read_parquet(path)
        m = new.merge(old[KEY + ["value", "release_date", "publication_id"]], on=KEY, how="left", suffixes=("", "_old"))
        has_old = m["value_old"].notna()
        changed = has_old & ((m["value"] - m["value_old"]).abs() > 1e-9)
        for _, r in m[changed].iterrows():
            revisions.append(dict(dataset_id=dataset_id, period=r["period"], row=r["row_label_ar"] or r["row_label_en"] or r["row_code"],
                                  col=(r["col_label_ar"] or r["col_label_en"]), old_value=float(r["value_old"]), new_value=float(r["value"]),
                                  old_release=r["release_date_old"], new_release=r["release_date"], recorded_at=run_ts))
        added = int((~has_old).sum()); unchanged = int((has_old & ~changed).sum())
        keep = old.merge(new[KEY], on=KEY, how="left", indicator=True)
        keep = keep[keep["_merge"] == "left_only"].drop(columns="_merge")
        out = pd.concat([keep[COLS], new[COLS]], ignore_index=True)
    else:
        out, added, unchanged = new, len(new), 0
    out = out.sort_values(["sheet", "block", "period", "row_code", "row_label_ar", "col_code", "col_label_ar"], kind="stable")
    out.to_parquet(path, compression="zstd", index=False)
    csv = path.with_suffix(".csv")
    if path.stat().st_size * 6 < CSV_MAX_BYTES:   # small dataset: keep a CSV mirror for easy reading
        out.to_csv(csv, index=False, encoding="utf-8-sig")
    elif csv.exists():
        csv.unlink()
    return added, len(revisions), unchanged, revisions


def append_revisions(revs):
    if not revs:
        return
    p = ROOT / "registry" / "revisions.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        for r in revs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
