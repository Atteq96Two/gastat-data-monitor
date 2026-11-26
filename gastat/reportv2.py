"""Report schema 2 (round 2): one chart at level 1, up to three at level 2, tabs at level 3, a "why this chart" caption on every chart,
sourced explanations, and weights next to items.

A spec with `schema: 2` is built here. Chart kinds:
  line         series: [selectors]                       fixed lines
               pick:   {dataset, name/names, ...}        many lines the reader picks from (at most 6 shown at once), optional weights
  bars         items:  {selector}                        latest value per item, optional weights
  bars_filter  a dropdown (e.g. a spending division) that changes which bars (e.g. regions) are shown
  cpi_tree     one tab per division with its groups and items (weight, index, annual and monthly change)
  avg_updown / avg_trend / avg_tables   Average Prices: how many items rose and fell, trend by division, items of each division
Every number comes from a stored table; a selector that does not resolve stops the build. Nothing is computed except where a chart says so
in its `why`/`note` (median change of a division's items; counts of items that rose or fell).
"""
import re, statistics
import pandas as pd
import yaml
from gastat import reportdata as R
from gastat.grid import norm

GLOSS = yaml.safe_load((R.SPECS / "_glossary.yaml").read_text(encoding="utf-8"))


def gloss(ids):
    return [dict(id=i, **GLOSS[i]) for i in ids or []]


def _key(s):
    return norm(R.clean_label(str(s)))


def label_of(name, c):
    for pat, lab in c.get("label_map") or []:
        if re.search(pat, name):
            return lab
    if c.get("label_re"):
        m = re.search(c["label_re"], name)
        if m:
            return m.group(1).strip()
    return R.clean_label(name)


def weight_map(w):
    """{normalised label: weight in percent} from a weights table; the newest release wins."""
    df = R.select(dict(w, measure="weight"))
    out = {}
    for (_, name), g in df.groupby(["block", "_name"], sort=False):
        m = re.search(w.get("key_re", r"^(.*?)\s*\|"), name)
        k = _key(m.group(1) if m else name)
        g = g.sort_values(["_ord", "release_date"])
        out[k] = float(g["value"].iloc[-1])
    for a, b in (w.get("alias") or {}).items():
        if _key(b) in out:
            out[_key(a)] = out[_key(b)]
    return out


def common(c, extra=None):
    d = dict(title=c["title_ar"], kind=c["kind"], unit=c.get("unit_ar", ""), why=c["why_ar"], explain=gloss(c.get("explain")), note=c.get("note_ar", ""))
    if c.get("tab"):
        d["tab"] = c["tab"]
    d.update(extra or {})
    return d


def line_chart(c):
    if "pick" in c:
        p = c["pick"]
        assert "period_type" in p, f"{c['title_ar']}: a pick needs a period_type (monthly lines never carry annual rows)"
        sel = {k: p[k] for k in ("dataset", "block", "measure", "period_type", "name", "exclude") if k in p}
        df = R.select(sel)
        if p.get("names"):
            df = df[df["_name"].isin(p["names"])]
        wm = weight_map(p["weights"]) if p.get("weights") else {}
        series = []
        for (_, name), g in df.groupby(["block", "_name"], sort=False):
            if g["period"].nunique() < p.get("min_points", 8):
                continue
            lab = label_of(name, p)
            s = R.to_series(g, lab)
            k = _key(lab)
            if p.get("mul") or p.get("div"):
                f = p.get("mul", 1) / p.get("div", 1)
                s["points"] = [[q, R.sig(v * f)] for q, v in s["points"]]
            if k in wm:
                s["weight"] = round(wm[k], 2)
            series.append(s)
        if not series:
            raise ValueError(f"{c['title_ar']}: the pick resolved to no series")
        if wm:
            series.sort(key=lambda s: -(s.get("weight") or 0))
        labels = [s["label"] for s in series]
        default = p.get("default") or labels[:3]
        for d_ in default:
            assert d_ in labels, f"{c['title_ar']}: default '{d_}' is not among {labels}"
        ds = p["dataset"]
        return common(c, dict(kind="line", series=series, selectable=True, default=default, period=series[0]["points"][-1][0], scale=1,
                              source=R.source_of(series[0], ds)))
    series = [R.ser(x) for x in c["series"]]
    for x, s in zip(c["series"], series):
        if x.get("weight_of"):
            s["weight"] = round(weight_map(x["weight_of"]).get(_key(x["weight_of"]["label"])), 2)
    return common(c, dict(kind="line", series=series, period=series[0]["points"][-1][0], scale=1, source=R.source_of(series[0], c["series"][0]["dataset"])))


def bars_chart(c):
    it = c["items"]
    wm = weight_map(c["weights"]) if c.get("weights") else {}
    pairs = R.many(it, it.get("min_points", 1))
    bars, lastp = [], max(g["_ord"].max() for _, g in pairs)
    for name, g in pairs:
        g = g.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last")
        r = g.iloc[-1]
        if r["_ord"] != lastp:
            continue
        lab = label_of(name, it)
        b = dict(label=lab, value=R.sig(r["value"] * it.get("mul", 1) / it.get("div", 1)), cell=r["source_cell"])
        if _key(lab) in wm:
            b["weight"] = round(wm[_key(lab)], 2)
        bars.append(b)
    bars.sort(key=lambda b: -b["value"])
    lp = g.iloc[-1]
    return common(c, dict(kind="bars", bars=bars, period=lp["period"], scale=1,
                          source=dict(file=lp["source_file_url"], sheet=str(R.load(it["dataset"])["sheet"].iloc[0]), release=str(lp["release_date"]))))


def bars_filter(c):
    p = c["filter_bars"]
    df = R.select({k: p[k] for k in ("dataset", "block", "measure", "period_type", "name", "exclude") if k in p})
    groups, order = {}, []
    for (_, name), g in df.groupby(["block", "_name"], sort=False):
        fm, lm = re.search(p["filter_re"], name), re.search(p["label_re"], name)
        if not (fm and lm):
            continue
        f = R.clean_label(fm.group(1).strip())
        if p.get("filters") and f not in p["filters"]:
            continue
        g = g.sort_values(["_ord", "release_date"])
        r = g.iloc[-1]
        if f not in groups:
            groups[f] = []; order.append(f)
        groups[f].append(dict(label=lm.group(1).strip(), value=R.sig(r["value"]), cell=r["source_cell"]))
    for f in groups:
        groups[f].sort(key=lambda b: -b["value"])
    if p.get("filters"):
        order = [x for x in p["filters"] if x in groups]
    default = p.get("default") if p.get("default") in groups else order[0]
    r = g.iloc[-1]
    return common(c, dict(kind="bars_filter", filters=order, groups=groups, default=default, period=r["period"], scale=1,
                          source=dict(file=r["source_file_url"], sheet=str(R.load(p["dataset"])["sheet"].iloc[0]), release=str(r["release_date"]))))


# ---------------------------------------------------------------- CPI: division -> groups -> items
def cpi_tree(c):
    """One tab per division: the division, then its groups and items in the order of GASTAT's table, with weight, index and changes."""
    ds = c["dataset"]
    df = R.load(ds)
    latest = df.loc[df["_ord"] == df["_ord"].max()]
    rn = lambda cell: int(re.search(r"R(\d+)C", cell).group(1))     # noqa: E731
    nodes = {}
    for r in latest.itertuples():
        k = rn(r.source_cell)
        n = nodes.setdefault(k, dict(label=R.clean_label(r.row_label_ar), level=int(r.row_level or 0), weight=None, index=None, yoy=None, mom=None, cell=None))
        if r.measure_type == "weight":
            n["weight"] = R.sig(r.value)
        elif r.measure_type == "index":
            n["index"] = R.sig(r.value); n["cell"] = r.source_cell
    # itertuples hides underscore columns: read the offsets explicitly
    for k, off, mt, v in zip(latest["source_cell"].map(rn), latest["_off"], latest["measure_type"], latest["value"]):
        if mt == "rate" and off == 12:
            nodes[k]["yoy"] = R.sig(v)
        elif mt == "rate" and off == 1:
            nodes[k]["mom"] = R.sig(v)
    period = latest["period"].iloc[0]
    tabs, cur, divisions = [], None, []
    for k in sorted(nodes):
        n = nodes[k]
        if n["level"] == 0:
            continue
        if n["level"] == 1:
            cur = dict(division=n, rows=[])
            divisions.append(cur)
        if cur is not None:
            cur["rows"].append(n)
    ref = latest.iloc[0]
    for d in divisions:
        div = d["division"]
        rows = [dict(label=n["label"], level=n["level"], weight=n["weight"], value=n["index"], change=n["yoy"], change2=n["mom"]) for n in d["rows"]]
        tabs.append(common(c, dict(kind="table", tab=div["label"], title=div["label"], period=period, scale=1,
                                    columns=dict(weight="الوزن %", value="الرقم القياسي", change="التغير السنوي %", change2="التغير الشهري %"),
                                    rows=rows, source=dict(file=ref["source_file_url"], sheet=str(ref["sheet"]), release=str(ref["release_date"])))))
    return tabs


# ---------------------------------------------------------------- Average Prices
def _avg_frame(c):
    d = R.load(c["dataset"])
    rules = [(re.compile(m["groups"]), m["division"]) for m in c["division_map"]]
    def division(g):
        for rx, dv in rules:
            if rx.search(g):
                return dv
        raise ValueError(f"average prices: the group '{g[:60]}' has no division in the spec (division_map)")
    d = d.copy()
    d["_div"] = d["row_group"].map(division)
    return d


def _avg_changes(d, period):
    """Published annual change of every item in `period` (the column compares with the same month a year earlier)."""
    r = d[(d["measure_type"] == "rate") & (d["period"] == period) & (d["_off"] == 12)]
    return r.sort_values("release_date").drop_duplicates("row_label_ar", keep="last")


def avg_updown(c, d):
    last = d[d["measure_type"] == "level"]["period"].max()
    r = _avg_changes(d, last)
    rows = []
    for dv, g in sorted(r.groupby("_div"), key=lambda kv: -len(kv[1])):
        v = g["value"]
        rows.append(dict(label=dv, up=int((v > 0.005).sum()), down=int((v < -0.005).sum()), flat=int((v.abs() <= 0.005).sum()), total=int(len(v))))
    tot = dict(label="كل البنود", up=sum(x["up"] for x in rows), down=sum(x["down"] for x in rows), flat=sum(x["flat"] for x in rows), total=sum(x["total"] for x in rows))
    ref = r.iloc[0]
    return common(c, dict(kind="updown", rows=[tot] + rows, period=last, scale=1, source=dict(file=ref["source_file_url"], sheet=str(ref["sheet"]), release=str(ref["release_date"]))))


def avg_trend(c, d):
    per = sorted(d[d["measure_type"] == "level"]["period"].unique())
    per26 = [p for p in per if p.startswith("2026")]
    series = []
    for dv in sorted(d["_div"].unique()):
        pts = []
        for p in per26:
            g = _avg_changes(d, p)
            v = g[g["_div"] == dv]["value"].tolist()
            if v:
                pts.append([p, R.sig(statistics.median(v))])
        if len(pts) >= 3:
            series.append(dict(label=dv, points=pts, unit="%", cell=None, release=None, file=None))
    ref = d[d["measure_type"] == "rate"].sort_values("release_date").iloc[-1]
    cnt = d[(d["measure_type"] == "level") & (d["period"] == per[-1])].groupby("_div").size()
    default = sorted((s["label"] for s in series), key=lambda x: -cnt.get(x, 0))[:3]      # the divisions with the most items
    return common(c, dict(kind="line", series=series, selectable=True, default=default, period=per26[-1], scale=1, computed=True,
                          source=dict(file=ref["source_file_url"], sheet=str(ref["sheet"]), release=str(ref["release_date"]))))


def avg_tables(c, d):
    lv = d[d["measure_type"] == "level"]
    last = lv["period"].max()
    yoy = _avg_changes(d, last).set_index("row_label_ar")["value"].to_dict()
    mm = d[(d["measure_type"] == "rate") & (d["period"] == last) & (d["_off"] == 1)].sort_values("release_date").drop_duplicates("row_label_ar", keep="last").set_index("row_label_ar")["value"].to_dict()
    tabs = []
    ref = lv.sort_values("release_date").iloc[-1]
    for dv, g in lv.groupby("_div"):
        rows = []
        for item, gi in g.groupby("row_label_ar"):
            gi = gi.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last")
            if gi["period"].iloc[-1] != last:
                continue
            rows.append(dict(label=R.clean_label(item), level=2, value=R.sig(gi["value"].iloc[-1]), pack=str(gi["row_unit"].iloc[-1] or ""), change=yoy.get(item), change2=mm.get(item),
                             spark=[[p, R.sig(x)] for p, x in zip(gi["period"], gi["value"])], cell=gi["source_cell"].iloc[-1]))
        rows.sort(key=lambda x: -(x["change"] if x["change"] is not None else -999))
        if rows:
            tabs.append(common(c, dict(kind="table", tab=dv, title=dv, period=last, scale=1,
                                        columns=dict(value="السعر (ريال)", change="التغير السنوي %", change2="التغير الشهري %"),
                                        rows=rows, source=dict(file=ref["source_file_url"], sheet=str(ref["sheet"]), release=str(ref["release_date"])))))
    order = {}
    for i, m in enumerate(c["division_map"]):
        order.setdefault(m["division"], i)
    tabs.sort(key=lambda t: order.get(t["tab"], 99))
    return tabs


def build_avg_headline(spec, rep):
    d = R.load(spec["dataset"])
    items = spec["items"]
    h = spec["headline"]
    it = next(x for x in items if x["key"] == h["item"])
    g = d[(d["measure_type"] == "level") & d["row_label_ar"].str.contains(it["row"], regex=True)]
    s = R.to_series(g, it["label_ar"], merge=True)
    ch = d[(d["measure_type"] == "rate") & (d["_off"] == 1) & d["row_label_ar"].str.contains(it["row"], regex=True)]
    ch = ch.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last").iloc[-1]
    assert ch["period"] == s["points"][-1][0], "published monthly change is for another period"
    cv = R.sig(ch["value"])
    rep["headline"] = dict(label=h["label_ar"], value=s["points"][-1][1], unit=it["unit_ar"], period=s["points"][-1][0],
                           change=dict(value=cv, unit="%", kind="pct", ref=None), direction=R.direction(cv), press_release_value=None)
    rep["period"] = s["points"][-1][0]; rep["release_date"] = s["release"]
    rep["source"] = R.source_of(s, spec["dataset"])
    return s


# ---------------------------------------------------------------- assembly
def make(c, spec):
    k = c["kind"]
    if k == "line":
        return [line_chart(c)]
    if k == "bars":
        return [bars_chart(c)]
    if k == "bars_filter":
        return [bars_filter(c)]
    if k == "cpi_tree":
        return cpi_tree(c)
    d = _avg_frame(spec["avg"]) if k.startswith("avg_") else None
    if k == "avg_updown":
        return [avg_updown(dict(c, **spec["avg"]), d)]
    if k == "avg_trend":
        return [avg_trend(dict(c, **spec["avg"]), d)]
    if k == "avg_tables":
        return avg_tables(dict(c, **spec["avg"]), d)
    raise ValueError(f"unknown chart kind {k}")


def build(spec, rep, fresh):
    if spec["id"] == "avgprices":
        build_avg_headline(dict(spec, dataset=spec["avg"]["dataset"], items=spec["avg"]["items"]), rep)
    else:
        R.fill_headline(spec, rep)
    rep["schema"] = 2
    l1 = make(spec["level1"], spec)
    assert len(l1) == 1, "level 1 is exactly one chart"
    rep["level1"] = l1[0]
    l2 = [x for c in spec.get("level2", []) for x in make(c, spec)]
    assert len(l2) <= 3, f"{spec['id']}: level 2 has {len(l2)} charts (at most 3)"
    rep["level2"] = l2
    rep["level3"] = [x for c in spec.get("level3", []) for x in make(c, spec)]
    rep["levels"] = 3 if rep["level3"] else (2 if l2 else 1)
    if spec.get("differs"):
        dd = yaml.safe_load((R.SPECS / "_differs.yaml").read_text(encoding="utf-8"))[spec["differs"]]
        rep["differs"] = dict(title_ar=dd["title_ar"], items=[
            dict(name_ar=it["name_ar"], self=it["id"] == spec["id"], text_ar=" ".join(GLOSS[g]["text_ar"] for g in it["gloss"]),
                 source_ar=GLOSS[it["gloss"][0]]["source_ar"], url=GLOSS[it["gloss"][0]]["url"]) for it in dd["items"]])
    rep["freshness"] = fresh
    return rep
