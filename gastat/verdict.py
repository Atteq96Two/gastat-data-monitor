"""Reference implementation of the News Tracker contract: check ONE factual claim against the stored GASTAT data.

It reads only the public JSON files (catalog/catalog.json, catalog/search_index.json, web/data/series/<dataset>.json), the same files the
News Tracker reads over HTTP. It never guesses: anything it cannot pin down gives "insufficient_data" with the reason and the candidates.

Verdicts: supports | contradicts | insufficient_data | data_too_old   (see INTEGRATION.md)

Claim (a dict, all keys optional except one of query / dataset_id):
  query        words that identify the indicator, e.g. "الرقم القياسي لأسعار المستهلك" or "business confidence"
  series       the item name inside the table, e.g. "الرقم القياسي العام"; an exact match of the item name wins over partial matches
  column       words that identify the column of that item, e.g. "معدل مقارنة مع أكتوبر 2025" or "الأرقام القياسية"
  dataset_id   exact table (skips the search)
  period       "2026-10", "2026-Q3" or "2025"; omitted = the latest period the data has
  metric       "value" (default) | "change_prev" (vs previous period) | "change_yoy" (vs same period a year earlier)
  claimed      the number the claim states (in the unit of the series: percent for rates, index points for indices)
  direction    "up" | "down" | "flat" (instead of, or together with, claimed)
  decimals     decimals the claim was stated with (default: as written in claimed); tolerance = half of the last stated digit
  tolerance    explicit absolute tolerance, overrides decimals
  as_of        date of the claim, "YYYY-MM-DD" (default today); used for "data too old"
"""
import datetime as dt, json, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gastat.grid import norm            # noqa: E402
from gastat.insights import ordinal, period_label   # noqa: E402

SOURCE = "الهيئة العامة للإحصاء / General Authority for Statistics (stats.gov.sa)"
CYCLE = {"monthly": 31, "quarterly": 92, "annual": 366, "biennial": 731}
GRACE = 10
FLAT = 1e-9


def _load(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _words(s):
    return [w for w in norm(s).replace("|", " ").replace("/", " ").split() if w]


def _decimals(claimed):
    s = str(claimed)
    return len(s.split(".")[1]) if "." in s else 0


def _out(verdict, reason, **kw):
    return dict(verdict=verdict, reason=reason, source=SOURCE, **kw)


def find(claim, root=ROOT):
    """All (dataset, series) pairs that match the claim words."""
    cat = _load(root / "catalog" / "catalog.json")["datasets"]
    idx = _load(root / "catalog" / "search_index.json")["labels"]
    qw, sw, cw = _words(claim.get("query", "")), _words(claim.get("series", "")), _words(claim.get("column", ""))
    out = []
    for d in cat:
        if claim.get("dataset_id") and d["dataset_id"] != claim["dataset_id"]:
            continue
        hay = norm(" ".join([d["title_ar"], d["title_en"], d["publication_title_ar"], d["publication_title_en"]] + idx.get(d["dataset_id"], [])))
        if not all(w in hay for w in qw):
            continue
        s = _load(root / "web" / "data" / "series" / f"{d['dataset_id']}.json")
        head = norm(" ".join([d["title_ar"], d["title_en"], d["publication_title_ar"], d["publication_title_en"]]))
        for x in s["series"]:
            lab = norm(x["label"] + " " + x["label_en"])
            parts = [norm(p) for p in x["label"].split(" | ")]
            rest = " ".join(parts[1:]) + " " + norm(x["label_en"])
            # every query word must be in the table or series text, every series word in the series text, every column word in the column part
            if all(w in lab or w in head for w in qw) and all(w in lab for w in sw) and all(w in rest for w in cw):
                out.append((d, s, x, bool(sw) and parts[0] == " ".join(sw)))
    exact = [o[:3] for o in out if o[3]]
    return exact or [o[:3] for o in out]


def evaluate(d, s, x, claim, as_of):
    P = s["periods"]
    have = [p for p, v in zip(P, x["values"]) if v is not None]
    if not have:
        return None, _out("insufficient_data", "the series has no values")
    last = max(have, key=lambda p: ordinal(p)[0])
    metric = claim.get("metric", "value")
    want = claim.get("period") or last
    o, lag, _ = ordinal(want) if ordinal(want) else (None, None, None)
    if o is None:
        return None, _out("insufficient_data", f"period '{want}' is not understood (use YYYY-MM, YYYY-Qn or YYYY)")
    # data too old: the claim is about a period after the newest one we hold, or we have not seen a release for more than a cycle
    if ordinal(want)[0] > ordinal(last)[0]:
        return None, _out("data_too_old", f"the claim is about {period_label(want, 'en')}, the newest data available is {period_label(last, 'en')} (published {d['release_date']})",
                          data_as_of=d["release_date"], latest_period=last)
    if not claim.get("period"):
        rel = dt.date.fromisoformat(d["release_date"])
        if (as_of - rel).days > CYCLE.get(d["frequency"], 31) + GRACE:
            return None, _out("data_too_old", f"latest data is {period_label(last, 'en')}, released {d['release_date']}, more than one {d['frequency']} cycle before {as_of}",
                              data_as_of=d["release_date"], latest_period=last)
    pos = {p: v for p, v in zip(P, x["values"]) if v is not None}
    inv = {ordinal(p)[0]: p for p in pos}
    if want not in pos:
        return None, _out("insufficient_data", f"no value for {period_label(want, 'en')} in this series (available {have[0]} to {last})", data_as_of=d["release_date"])
    cur = pos[want]
    cellof = lambda p: f"{s.get('sheet', '')}!{x['cells'][P.index(p)]}"   # noqa: E731
    ev = [dict(period=want, value=cur, cell=cellof(want))]
    if metric == "value":
        val = cur
    else:
        ref_o = o - (1 if metric == "change_prev" else lag)
        ref_p = inv.get(ref_o)
        if ref_p is None:
            return None, _out("insufficient_data", f"no value for the comparison period of {metric} ({'previous period' if metric == 'change_prev' else 'a year earlier'})", data_as_of=d["release_date"])
        ref = pos[ref_p]; ev.append(dict(period=ref_p, value=ref, cell=cellof(ref_p)))
        if x["measure"] in ("rate", "share", "weight", "distribution", "percentage"):
            val = cur - ref                     # percentage points
        else:
            if not ref:
                return None, _out("insufficient_data", "comparison value is zero")
            val = (cur - ref) / ref * 100       # percent change
    if (claim.get("claimed") is not None) and not x["unit_ok"] and metric == "value":
        return None, _out("insufficient_data", "the unit of this series is not settled in the source, so a number cannot be compared", data_as_of=d["release_date"])
    tol = claim.get("tolerance")
    if tol is None:
        dec = claim.get("decimals", _decimals(claim["claimed"]) if claim.get("claimed") is not None else 0)
        tol = 0.5 * 10 ** (-dec)
    checks = []
    if claim.get("claimed") is not None:
        checks.append(abs(val - claim["claimed"]) <= tol + FLAT)
    if claim.get("direction"):
        dr = claim["direction"]
        checks.append((val > tol) if dr == "up" else (val < -tol) if dr == "down" else abs(val) <= tol)
    if not checks:
        return None, _out("insufficient_data", "the claim has neither a number nor a direction to check")
    ok = all(checks)
    return (val, ev, last), _out("supports" if ok else "contradicts",
                                 f"{period_label(want, 'en')} {metric}: data says {round(val, 4)}" + (f", claim says {claim['claimed']}" if claim.get("claimed") is not None else "") + (f", direction {claim['direction']}" if claim.get("direction") else ""),
                                 computed=round(val, 6), tolerance=tol, data_as_of=d["release_date"], latest_period=last, period=want, metric=metric,
                                 evidence=ev, dataset_id=d["dataset_id"], series=x["label"], unit=x["unit_text"] or x["unit"],
                                 table_url_csv=d.get("csv_url"), table_url_parquet=d.get("parquet_url"))


def check_claim(claim, root=ROOT):
    as_of = dt.date.fromisoformat(claim["as_of"]) if claim.get("as_of") else dt.date.today()
    if not (claim.get("query") or claim.get("dataset_id")):
        return _out("insufficient_data", "no indicator given (query or dataset_id)")
    cands = find(claim, root)
    if not cands:
        return _out("insufficient_data", "no stored indicator matches these words (the data covers releases from November 2026 only)", candidates=[])
    res = [(c, *evaluate(*c, claim, as_of)) for c in cands]
    # several tables can publish the same figure (the headline index appears in a summary and in a detail table). They count as one when they agree.
    kinds = {(r[2]["verdict"], round(r[2].get("computed", 0), 4), r[2].get("period"), r[2].get("latest_period")) for r in res}
    if len(kinds) == 1:
        out = res[0][2]
        out["agreeing_series"] = len(res)
        return out
    cand = [dict(dataset_id=c[0]["dataset_id"], title=c[0]["title_ar"], series=c[2]["label"], verdict=o["verdict"], computed=o.get("computed")) for c, _, o in res][:8]
    return _out("insufficient_data", f"{len(res)} different series match and they do not agree; narrow the claim (series words or dataset_id)", candidates=cand)


if __name__ == "__main__":
    print(json.dumps(check_claim(json.loads(sys.argv[1])), ensure_ascii=False, indent=1))
