"""Compact chart data for the front end, built from the report specs (report_specs/*.yaml).

The engine never decides how a report is presented: every series on the site is named in a spec. A selector that does not
resolve to exactly one series (or to the expected set) stops the build, so a layout change can never silently change a chart.
Output: web/data/home.json (cards) and web/data/reports/<id>.json (loaded when a card is opened).
"""
import collections, datetime as dt, json, pathlib, re, sys
import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from gastat import insights as I, scope, webdata            # noqa: E402

WEB = ROOT / "web" / "data"
SPECS = ROOT / "report_specs"
SOURCE_AR = "الهيئة العامة للإحصاء"
GROUPS = [("prices", "الأسعار والتضخم"), ("growth", "النمو والإنتاج"), ("trade", "التجارة والاستثمار الأجنبي"),
          ("labour", "سوق العمل"), ("confidence", "الثقة والتوقعات"), ("tourism", "السياحة")]
_cache = {}


def load(ds):
    if ds not in _cache:
        f = next(ROOT.glob(f"data/*/{ds}.parquet"))
        df = I.prepare(pd.read_parquet(f))
        for c in ("row_label_ar", "col_label_ar", "col_sub", "row_group"):
            df[c] = df[c].fillna("").astype(str)
        sub = df["col_sub"].where(df["col_sub"] == "", " | " + df["col_sub"])
        en_ = df["row_label_en"].fillna("").astype(str)
        row_lab = df["row_label_ar"].where((df["row_label_ar"] != "") | ~en_.str.contains("[\u0600-\u06ff]"), en_)   # a label written in one mixed-script cell lands in the English column
        parts = [row_lab, df["col_label_ar"] + sub]
        df["_name"] = (parts[0] + " | " + parts[1]).str.strip(" |").str.replace(r"\s*\|\s*\|\s*", " | ", regex=True)
        df["_ord"] = [I.ordinal(p)[0] for p in df["period"]]
        _cache[ds] = df
    return _cache[ds]


def sig(v):
    return None if v is None or pd.isna(v) else float(f"{v:.7g}")


def clean_label(s):
    s = webdata.ar_only(s)
    s = re.sub(r"^(\d{4}\s*=\s*100|100\s*=\s*\d{4})\s*/\s*", "", s)
    s = re.sub(r"^[أ-ي\-\d]{1,2}\s*[-/]\s*/?\s*", "", s).strip(" /|-")
    return s


def select(sel):
    df = load(sel["dataset"])
    m = pd.Series(True, index=df.index)
    if "block" in sel:
        m &= df["block"].astype(str) == str(sel["block"])
    if "measure" in sel:
        m &= df["measure_type"] == sel["measure"]
    if "period_type" in sel:
        m &= df["period_type"] == sel["period_type"]
    if "name" in sel:
        m &= df["_name"].str.contains(sel["name"], regex=True)
    if "row" in sel:
        m &= df["row_label_ar"].str.contains(sel["row"], regex=True)
    if sel.get("exclude"):
        m &= ~df["_name"].str.contains(sel["exclude"], regex=True)
    if sel.get("yoy_base"):
        m &= df["_off"] == 12 if (df["period_type"] == "month").any() else df["_off"] == 4
    if sel.get("prev_base"):
        m &= df["_off"] == 1
    return df[m]


def to_series(d, label=None, merge=False):
    """One series from rows that must belong to a single (block, name); later editions win when a period appears twice."""
    keys = set(zip(d["block"], d["_name"])) if not merge else {(0, 0)}
    if len(keys) != 1:
        raise ValueError(f"selector resolves to {len(keys)} series, expected 1: {sorted(map(str, keys))[:4]}")
    d = d.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last")
    last = d.iloc[-1]
    return dict(label=label or clean_label(last["_name"]), points=[[p, sig(v)] for p, v in zip(d["period"], d["value"])],
                cell=last["source_cell"], file=last["source_file_url"], release=str(last["release_date"]), unit=last["_unit"])


def many(sel, min_points=1):
    df = select(sel)
    out = []
    for (blk, name), g in df.groupby(["block", "_name"], sort=False):
        if g["period"].nunique() >= min_points:
            out.append((name, g))
    return out


def ser(x, label=None):
    """One series for a selector; optional mul / div convert units (fraction -> percent, million -> billion)."""
    s_ = to_series(select(x), label or x.get("label_ar"))
    k = x.get("mul", 1) / x.get("div", 1)
    if k != 1:
        s_["points"] = [[p, sig(v * k)] for p, v in s_["points"]]
    return s_


def change_pp(points, lag=1):
    a, b = points[-1][1], points[-1 - lag][1]
    return dict(value=sig(a - b), unit="نقطة مئوية", kind="pp", ref=points[-1 - lag][0])


def direction(v):
    return "flat" if v is None or abs(v) < 0.005 else ("up" if v > 0 else "down")


def source_of(s, ds):
    df = load(ds)
    sheet = str(df["sheet"].iloc[0])
    return dict(file=s["file"], sheet=sheet, release=s["release"])


def fill_headline(spec, rep):
    """Headline value, change and its press-release assertions; returns the headline series."""
    rid = spec["id"]
    h = spec["headline"]
    if "derived_yoy_of" in h:
        base = to_series(select(h["derived_yoy_of"]))
        v = {p: x for p, x in base["points"]}
        pts = []
        for p, x in base["points"]:
            q = f"{int(p[:4]) - 1}-{p[5:]}"
            if q in v and v[q]:
                pts.append([p, sig((x / v[q] - 1) * 100)])
        hs = dict(label=h["label_ar"], points=pts, cell=base["cell"], file=base["file"], release=base["release"])
        hs["unit"] = "%"
    else:
        hs = ser(h["series"], h["label_ar"])
    last_p, last_v = hs["points"][-1]
    ch = h["change"]
    if ch["mode"] == "pp":
        change = change_pp(hs["points"], ch.get("lag", 1))
    elif ch["mode"] == "derived_pct":      # percent change against the point `lag` periods back (1 = previous period, 4 = same quarter last year, 12 = same month last year)
        a, b = hs["points"][-1], hs["points"][-1 - ch["lag"]]
        change = dict(value=sig((a[1] / b[1] - 1) * 100), unit="%", kind="pct", ref=b[0])
    else:
        cs = to_series(select(ch["series"]))
        assert cs["points"][-1][0] == last_p, "published change is for another period"
        cv = cs["points"][-1][1]
        change = dict(value=cv, unit="%", kind="pct", ref=None)
    pr = h.get("press_release_value")
    if pr is not None and abs(round(last_v, 1) - pr) > 0.051:
        raise AssertionError(f"{rid}: headline {last_v:.3f} does not match the GASTAT press release ({pr})")
    prc = h.get("press_release_change")
    if prc is not None and abs(round(change["value"], 1) - prc) > 0.051:
        raise AssertionError(f"{rid}: change {change['value']:.3f} does not match the GASTAT press release ({prc})")
    rep["headline"] = dict(label=h["label_ar"], value=last_v, unit=h["unit_ar"], period=last_p, change=change, direction=direction(change["value"]), press_release_value=pr)
    ds_main = (h.get("series") or h["derived_yoy_of"])["dataset"]
    rep["period"] = last_p
    rep["release_date"] = hs["release"]
    rep["source"] = source_of(hs, ds_main)
    return hs


def build_report(spec, fresh):
    rid = spec["id"]
    rep = dict(id=rid, name_ar=spec["name_ar"], group=spec["group"], frequency=spec["frequency"], description_ar=spec["description_ar"], source_ar=SOURCE_AR)
    if spec.get("schema") == 2:
        from gastat import reportv2
        return reportv2.build(spec, rep, fresh)
    if rid == "avgprices":
        return build_avg(spec, rep, fresh)
    fill_headline(spec, rep)

    def chart(title, kind, unit, series, ds):
        return dict(title=title, kind=kind, unit=unit, scale=1, period=series[0]["points"][-1][0], series=series, source=source_of(series[0], ds))

    l1 = spec["level1"]
    s1 = [ser(x) for x in l1["series"]]
    rep["level1"] = chart(l1["title_ar"], "line", l1["unit_ar"], s1, l1["series"][0]["dataset"])
    rep["levels"] = 1
    l2 = spec.get("level2")
    if l2:
        if "top_by_weight" in l2:
            t = l2["top_by_weight"]
            w = select(dict(t["weights"], dataset=t["weights"]["dataset"]))
            wmap = {}
            for name in t["divisions"]:
                g = w[w["_name"].str.startswith(name)]
                if g.empty:
                    raise ValueError(f"no weight for division {name}")
                wmap[name] = float(g.sort_values("release_date")["value"].iloc[-1])
            top = sorted(wmap, key=lambda n: -wmap[n])[: t["top"]]
            sers = [to_series(select(dict(t["series"], name="^" + re.escape(n) + "$")), n) for n in top]
            ds2 = t["series"]["dataset"]
            rep["weights"] = {n: round(wmap[n], 2) for n in t["divisions"]}
        else:
            sers = [ser(x) for x in l2["series"]]
            ds2 = l2["series"][0]["dataset"]
        rep["level2"] = chart(l2["title_ar"], l2["kind"], l2["unit_ar"], sers, ds2)
        rep["levels"] = 2
    l3 = []
    for sec in spec.get("level3") or []:
        if sec["kind"] == "line":
            sers = [ser(x) for x in sec["series"]]
            c = chart(sec["title_ar"], "line", sec["unit_ar"], sers, sec["series"][0]["dataset"])
        else:
            it = sec["items"]
            if it.get("names_from") == "divisions":
                names = spec["level2"]["top_by_weight"]["divisions"]
                found = [(n, select(dict(it, name="^" + re.escape(n) + "$"))) for n in names]
                pairs = [(n, g) for n, g in found if not g.empty]
            else:
                pairs = many(it, it.get("min_points", 1))
            bars = []
            lastp = max(g["_ord"].max() for _, g in pairs)
            for name, g in pairs:
                g = g.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last")
                r = g.iloc[-1]
                if r["_ord"] != lastp:
                    continue
                lab = clean_label(r["row_label_ar"] or name)
                bars.append(dict(label=lab, value=sig(r["value"] * it.get("mul", 1) / it.get("div", 1)), cell=r["source_cell"]))
            if not bars:
                raise ValueError(f"{rid}: level 3 '{sec['title_ar']}' is empty")
            bars.sort(key=lambda b: -b["value"])
            lp = g.iloc[-1]
            c = dict(title=sec["title_ar"], kind="bars", unit=sec["unit_ar"], scale=1, period=lp["period"], bars=bars,
                     source=dict(file=lp["source_file_url"], sheet=str(load(it["dataset"])["sheet"].iloc[0]), release=str(lp["release_date"])))
        c["detail"] = bool(sec.get("detail"))
        l3.append(c)
    if l3:
        rep["level3"] = l3
        rep["levels"] = 3
    rep["freshness"] = fresh
    return rep


def build_avg(spec, rep, fresh):
    ds = spec["dataset"]
    items = spec["items"]
    d_all = load(ds)
    lv = d_all[d_all["measure_type"] == "level"]
    series = {}
    for it in items:
        g = lv[lv["row_label_ar"].str.contains(it["row"], regex=True)]
        if g.empty:
            raise ValueError(f"avgprices: item not found {it['label_ar']}")
        s = to_series(g, it["label_ar"], merge=True)
        s["unit"] = it["unit_ar"]; s["group"] = g["row_group"].iloc[0]
        series[it["key"]] = s
    h = spec["headline"]
    s0 = series[h["item"]]
    g = d_all[(d_all["measure_type"] == "rate") & (d_all["_off"] == 1) & d_all["row_label_ar"].str.contains(items[0]["row"], regex=True)]
    g = g.sort_values(["_ord", "release_date"]).drop_duplicates("period", keep="last")
    chg = g.iloc[-1]
    assert chg["period"] == s0["points"][-1][0], "published monthly change is for another period"
    cv = sig(chg["value"])
    rep["headline"] = dict(label=h["label_ar"], value=s0["points"][-1][1], unit=items[0]["unit_ar"], period=s0["points"][-1][0],
                           change=dict(value=cv, unit="%", kind="pct", ref=None), direction=direction(cv), press_release_value=None)
    rep["period"] = s0["points"][-1][0]; rep["release_date"] = s0["release"]
    rep["source"] = source_of(s0, ds)
    rep["level1"] = dict(title=spec["level1"]["title_ar"] + "، " + items[0]["label_ar"], kind="line", unit=items[0]["unit_ar"], scale=1, period=rep["period"],
                         series=[dict(s0, label=items[0]["label_ar"])], source=rep["source"])
    rep["level2"] = dict(title=spec["level2"]["title_ar"], kind="small_multiples", unit="ريال", scale=1, period=rep["period"],
                         series=[dict(series[it["key"]], unit=it["unit_ar"]) for it in items], source=rep["source"])
    # level 3: all items of the groups the six items belong to, annual change in the newest edition
    yoy = d_all[(d_all["measure_type"] == "rate") & (d_all["_off"] == 12)]
    secs = []
    for grp in dict.fromkeys(s["group"] for s in series.values()):
        gg = yoy[yoy["row_group"] == grp]
        lastp = gg["_ord"].max()
        gg = gg[gg["_ord"] == lastp].sort_values("release_date").drop_duplicates("row_label_ar", keep="last")
        bars = [dict(label=clean_label(r.row_label_ar), value=sig(r.value), cell=r.source_cell) for r in gg.itertuples()]
        bars.sort(key=lambda b: -b["value"])
        secs.append(dict(title=clean_label(grp), kind="bars", unit="%", scale=1, period=gg["period"].iloc[0], bars=bars, detail=False, source=rep["source"]))
    rep["level3"] = secs
    rep["levels"] = 3
    rep["freshness"] = fresh
    return rep


def main():
    reg = json.loads((ROOT / "registry" / "publications.json").read_text(encoding="utf-8"))
    pubs = reg["publications"]
    cal = json.loads((ROOT / "registry" / "calendar.json").read_text(encoding="utf-8"))
    processed = {webdata.family(p) for p in pubs if (p.get("status") or "").startswith("processed")}
    fresh_all = {f["family"]: f for f in webdata.build_freshness([p for p in pubs if scope.family(p)], cal, processed)}
    today = webdata.today()
    out_dir = WEB / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for f in sorted(SPECS.glob("[!_]*.yaml")):
        spec = yaml.safe_load(f.read_text(encoding="utf-8"))
        core = next(c for c in scope.CORE if c["id"] == spec["id"])
        fr = fresh_all.get(core["prefix"], {})
        fresh = dict(last_release=fr.get("last_release"), next_release=fr.get("calendar_next"), status=fr.get("status", "current"))
        rep = build_report(spec, fresh)
        rel = dt.date.fromisoformat(rep["release_date"])
        rep["new"] = (today - rel).days <= 7
        webdata.jdump(out_dir / f"{rep['id']}.json", rep)
        hl = rep["headline"]
        cards.append(dict(id=rep["id"], name_ar=rep["name_ar"], group=rep["group"], description_ar=rep["description_ar"], frequency=rep["frequency"],
                          headline=hl, period=rep["period"], release_date=rep["release_date"], next_release=fresh["next_release"], new=rep["new"],
                          stale=fresh["status"] == "overdue", levels=rep["levels"]))
    home = dict(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), source_ar=SOURCE_AR,
                groups=[dict(id=g, name_ar=n, cards=[c for c in cards if c["group"] == g]) for g, n in GROUPS if any(c["group"] == g for c in cards)])
    webdata.jdump(WEB / "home.json", home)
    print("reports:", len(cards))
    return home


if __name__ == "__main__":
    main()
