"""Series files for programs (News Tracker, verdict checker): one compressed Parquet file per dataset, long format.

catalog/series/<dataset_id>.parquet  - one row per (series, period) with a value. Columns:
  s (series number in the table), label, label_en, measure, unit, unit_ok, unit_text, base, total, cell (first cell, with sheet),
  period, value, cellref (R<row>C<col> of this value), sheet, title_ar.
`read()` rebuilds the dict the old JSON files held (periods sorted, series with values/cells aligned to periods)."""
import pandas as pd

META = ("label", "label_en", "measure", "unit", "unit_ok", "unit_text", "base", "total", "cell")


def write(path, dataset_id, title_ar, sheet, periods, series):
    rows = []
    for i, s in enumerate(series):
        for p, v, c in zip(periods, s["values"], s["cells"]):
            if v is not None:
                rows.append((i, *(s[k] for k in META), p, v, c))
    df = pd.DataFrame(rows, columns=["s", *META, "period", "value", "cellref"])
    for c in ("label", "label_en", "measure", "unit", "unit_text", "base", "cell", "period", "cellref"):
        df[c] = df[c].fillna("").astype(str).astype("category")
    df["unit_ok"] = df["unit_ok"].astype(bool); df["total"] = df["total"].astype(bool)
    df["sheet"] = str(sheet); df["title_ar"] = title_ar or ""
    df["sheet"] = df["sheet"].astype("category"); df["title_ar"] = df["title_ar"].astype("category")
    df.to_parquet(path, compression="zstd", compression_level=19, index=False)


def read(path):
    df = pd.read_parquet(path)
    if df.empty:
        return dict(dataset_id=path.stem, title_ar="", sheet="", periods=[], series=[])
    from gastat.insights import ordinal
    periods = sorted(df["period"].astype(str).unique(), key=lambda p: ordinal(p)[0])
    pidx = {p: i for i, p in enumerate(periods)}
    series = []
    for _, g in df.groupby("s", sort=True):
        r = g.iloc[0]
        vals, cells = [None] * len(periods), [None] * len(periods)
        for p, v, c in zip(g["period"].astype(str), g["value"], g["cellref"].astype(str)):
            vals[pidx[p]] = float(v); cells[pidx[p]] = c
        series.append({**{k: (r[k] if k in ("unit_ok", "total") else str(r[k])) for k in META}, "unit_ok": bool(r["unit_ok"]), "total": bool(r["total"]), "cells": cells, "values": vals})
    return dict(dataset_id=path.stem, title_ar=str(df["title_ar"].iloc[0]), sheet=str(df["sheet"].iloc[0]), periods=periods, series=series)
