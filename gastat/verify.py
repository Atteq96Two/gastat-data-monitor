"""Compare every stored value with its original Excel cell. Writes registry/verification.json.
Run: python3 -I gastat/verify.py   (uses cache/files/<id>/source.xlsx; collect.py keeps the file of each new release there)"""
import datetime as dt, glob, json, pathlib, re, sys, warnings
import openpyxl, pandas as pd
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent


def verify(only=None):
    """only: iterable of publication ids to (re)check; the rest of registry/verification.json is kept."""
    old = {}
    vp = ROOT / "registry" / "verification.json"
    if only and vp.exists():
        old = json.loads(vp.read_text(encoding="utf-8")).get("publications", {})
    only = {str(x) for x in only} if only else None
    res, wbs = dict(old), {}
    for k in (only or ()):
        res.pop(k, None)
    for f in glob.glob(str(ROOT / "data" / "*" / "*.parquet")):
        df = pd.read_parquet(f, columns=["publication_id", "source_cell", "value"])
        for pid, g in df.groupby("publication_id"):
            if only and pid not in only:
                continue
            src = next((x for x in (ROOT / "cache" / "files" / pid / "source.xlsx", ROOT / "cache" / "incoming" / pid / "source.xlsx") if x.exists()), None)
            if src is None:
                continue
            wb = wbs.setdefault(pid, openpyxl.load_workbook(src, data_only=True))
            r = res.setdefault(pid, dict(checked=0, different=0))
            for ref, v in zip(g.source_cell, g.value):
                sh, rc = ref.rsplit("!", 1)
                row, col = map(int, re.fullmatch(r"R(\d+)C(\d+)", rc).groups())
                x = wb[sh].cell(row=row, column=col).value
                r["checked"] += 1
                try:
                    if abs(float(str(x).replace(",", "")) - v) > 1e-9:
                        r["different"] += 1
                except Exception:
                    r["different"] += 1
    out = dict(verified_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), publications=res,
               total_checked=sum(v["checked"] for v in res.values()), total_different=sum(v["different"] for v in res.values()))
    vp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("verified", out["total_checked"], "values; different:", out["total_different"])
    return out


if __name__ == "__main__":
    verify()
