"""Release insights (Phase 4). Every number is computed from the stored data and every sentence is a fixed template.
No language model is involved. Each insight carries the cells it was computed from (evidence) so it can be re-checked.

What is computed, per release, per dataset of that release:
  series_change   latest value of a series against the previous period and the same period a year earlier,
                  plus "highest/lowest in the available history" flags
  cross_section   highest and lowest member of a group published for the same period (for tables with no history)
  revisions       values that GASTAT changed in a file it had already published

A series is only compared with itself: same sheet, block, row, column, unit, scale and comparison base.
Periods are compared only when the previous / year-earlier period actually exists. Nothing is interpolated.
"""
import argparse, datetime as dt, json, math, pathlib, re, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gastat.grid import norm, MONTHS_AR  # noqa: E402

OUT = ROOT / "catalog" / "insights"
MONTH_NAMES = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
MONTH_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
QUARTER_AR = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع"}
MIN_HISTORY = 6          # observations needed before "highest since" style statements are made
MAX_HEADLINES = 10
MAX_PER_DATASET = 2
MOVERS_PER_DATASET = 2   # biggest rise and biggest fall among members of one group, each
CROSS_PER_DATASET = 3
TOTALS_PER_DATASET = 6
FLAGS_PER_DATASET = 3

# units that are safe to print; anything else came from a header we could not read as a unit and is left out of the sentence
UNIT_AR = {"percent": "%", "percent_or_fraction": "%", "index": "نقطة", "SAR": "ريال", "km": "كم", "count": "", "عدد": "", "طن": "طن"}
UNIT_EN = {"percent": "%", "percent_or_fraction": "%", "index": "points", "SAR": "SAR", "km": "km", "count": "", "عدد": "", "طن": "tons"}
PERCENT_TYPES = {"rate", "share", "weight", "distribution", "percentage"}
SCALE_AR = {1000.0: "ألف", 1e6: "مليون", 1e9: "مليار"}
SCALE_EN = {1000.0: "thousand", 1e6: "million", 1e9: "billion"}
MONTH_SET = {norm(m) for m in MONTH_NAMES + ["إبريل", "اغسطس", "اكتوبر"]}
YEAR_OR_MONTH = re.compile(r"(" + "|".join(MONTHS_AR + ["أبريل", "أغسطس", "أكتوبر", "إبريل", "اغسطس", "اكتوبر"]) + r")|(?<![\d=])(19|20)\d\d(?![\d=])|م\b", re.I)


# ------------------------------------------------------------------ periods
def ordinal(p):
    """(ordinal, lag_for_one_year, kind) or None when the period format is not understood."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m and 1 <= int(m[2]) <= 12:
        return int(m[1]) * 12 + int(m[2]) - 1, 12, "month"
    m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
    if m:
        return int(m[1]) * 4 + int(m[2]) - 1, 4, "quarter"
    m = re.fullmatch(r"(\d{4})", p)
    if m:
        return int(m[1]), 1, "year"
    return None


def period_label(p, lang):
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m:
        return f"{(MONTH_NAMES if lang == 'ar' else MONTH_EN)[int(m[2]) - 1]} {m[1]}"
    m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
    if m:
        return f"الربع {QUARTER_AR[int(m[2])]} {m[1]}" if lang == "ar" else f"Q{m[2]} {m[1]}"
    return p


def offset_of(period, base):
    a, b = ordinal(period), ordinal(base or "")
    return "" if not (a and b) else a[0] - b[0]


# ------------------------------------------------------------------ formatting
def bunud(n):
    return f"{n} بنود" if 3 <= n <= 10 else f"{n} بنداً"


def short_title(t, lang, n=90):
    """Arabic or English half of a bilingual table title, cut at a word boundary."""
    m = re.search(r"\s[A-Za-z]{3,}", t)
    half = (t[:m.start()] if m else t) if lang == "ar" else (t[m.start():] if m else t)
    half = half.strip(" -,،")
    return half if len(half) <= n else half[:n].rsplit(" ", 1)[0] + "..."


def fmt(v):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    a = abs(v)
    s = f"{v:,.0f}" if a >= 1000 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def resolve_units(df):
    """Display unit per row. 'fraction' (confirmed in a reviewed recipe) is shown as percent (x100). 'percent_or_fraction' and unreadable units on
    percentage-type measures are shown as percent only when the dataset itself proves it (some |value| above 1.5); otherwise they stay unresolved
    and the sentence prints the number without a unit."""
    df = df.copy()
    df["value_raw"] = df["value"]
    frac = df["unit"] == "fraction"
    df.loc[frac, "value"] = df.loc[frac, "value"] * 100
    unit = df["unit"].where(~frac, "percent")
    pct_rows = df["measure_type"].isin(PERCENT_TYPES) & ~unit.isin(["percent"])
    proven = pct_rows & (df["value"].abs() > 1.5)
    ds_proven = proven.any()
    unit = unit.where(~pct_rows, "percent" if ds_proven else "unresolved_percent")
    df["_unit"] = unit
    return df


def unit_text(r, lang):
    """Unit words for a sentence, or '' when the unit is unknown or not printable."""
    if r["_unit"] == "percent":
        return "%"          # a scale such as "thousand" never applies to a percentage
    u = (UNIT_AR if lang == "ar" else UNIT_EN).get(r["_unit"], "") if not r["_unit"].startswith("index_base") else (UNIT_AR if lang == "ar" else UNIT_EN)["index"]
    sc = (SCALE_AR if lang == "ar" else SCALE_EN).get(float(r["scale"]), "")
    return " ".join(x for x in (sc, u) if x)


def unit_ok(r):
    return r["_unit"] == "percent" or (r["measure_type"] not in PERCENT_TYPES and (r["_unit"] in UNIT_AR or r["_unit"].startswith("index_base")))


def num_with_unit(v, r, lang):
    u = unit_text(r, lang)
    return f"{fmt(v)}{u}" if u == "%" else (f"{fmt(v)} {u}".strip())


def diff_unit(r, lang):
    if r["_unit"] == "percent":
        return "نقطة مئوية" if lang == "ar" else "percentage points"
    return {"ar": "نقطة", "en": "points"}[lang] if (r["_unit"] == "index" or r["_unit"].startswith("index_base")) else ""


# ------------------------------------------------------------------ series
def series_key(r):
    col = r["col_label_ar"]
    if r["measure_type"] == "rate":          # descriptions of the change period ("... لشهر أكتوبر 2026م مقارنة مع") move every release
        col = norm(YEAR_OR_MONTH.sub("", col))
    month_row = r["period"][4:5] == "-" and norm(r["row_label_ar"]) in MONTH_SET     # matrix of months x items: the month row is the period, not an item
    return (r["sheet"], r["block"], "" if month_row else r["row_code"], "" if month_row else norm(r["row_label_ar"]), "" if month_row else norm(r["row_label_en"]),
            r["row_group"], r["row_parent"],
            r["col_code"], col, norm(r["col_label_en"]), r["col_sub"], r["measure_type"], r["unit"], float(r["scale"]), r["_off"])


def dedupe(parts):
    out = []
    for x in parts:
        segs = []
        for sg in (x or "").split(" / "):      # "A / A" -> "A"
            if sg.strip() and norm(sg) not in [norm(t) for t in segs]:
                segs.append(sg.strip())
        x = " / ".join(segs)
        if x and not any(norm(x) == norm(o) for o in out):
            out.append(x)
    return out


BASE_PREFIX = re.compile(r"^\s*\d{4}\s*=\s*100\s*/\s*")   # "2023=100 / الجوف": the base year belongs to the unit, not the name


def label(r, lang="ar"):
    row = r["row_label_ar"] if lang == "ar" else (r["row_label_en"] or r["row_label_ar"])
    if norm(row) in MONTH_SET and r["period"][4:5] == "-":
        row = ""            # the row is just the month of the period, which the sentence already states
    parts = [r["row_group"], row]
    col = r["col_label_ar"] if lang == "ar" else (r["col_label_en"] or r["col_label_ar"])
    col = BASE_PREFIX.sub("", col or "")
    if col:
        parts.append(YEAR_OR_MONTH.sub("", col).strip(" -/") if r["measure_type"] == "rate" else col)
    if r["col_sub"]:
        parts.append(r["col_sub"])
    return " | ".join(dedupe(parts))


def prepare(df):
    df = resolve_units(df[df["period"].map(lambda p: ordinal(p) is not None)])
    df["_off"] = [offset_of(p, b) for p, b in zip(df["period"], df["base_period"])]
    df["_key"] = [series_key(r) for r in df.to_dict("records")]
    return df


def series_insight(rows, focus_period, pid, dataset_id):
    """rows: all observations of one series (sorted by period). Returns an insight dict or None."""
    byp = {r["period"]: r for r in rows}
    cur = byp.get(focus_period)
    if cur is None:
        return None
    o, lag, kind = ordinal(focus_period)
    inv = {ordinal(p)[0]: p for p in byp}
    prev = byp.get(inv.get(o - 1)) if (o - 1) in inv else None
    yoy = byp.get(inv.get(o - lag)) if lag != 1 and (o - lag) in inv else (byp.get(inv.get(o - 1)) if lag == 1 and (o - 1) in inv else None)
    if lag == 1:
        yoy = None   # for yearly data the previous period already is the year-earlier period
    hist = [(ordinal(p)[0], p, byp[p]["value"]) for p in byp if ordinal(p)[0] <= o]
    hist.sort()
    n = len(hist)
    v = cur["value"]
    mt = cur["measure_type"]
    pct_type = mt in PERCENT_TYPES
    nums, ev = {"value": v, "period": focus_period}, [dict(period=focus_period, value=cur["value_raw"], cell=cur["source_cell"])]
    parts_ar, parts_en = [], []
    ok_unit = unit_ok(cur)
    base_ar = f" مقارنة مع {period_label(cur['base_period'], 'ar')}" if cur["base_period"] else ""
    base_en = f" compared with {period_label(cur['base_period'], 'en')}" if cur["base_period"] else ""
    head_ar = f"{label(cur)}: {num_with_unit(v, cur, 'ar') if ok_unit else fmt(v)} في {period_label(focus_period, 'ar')}{base_ar}"
    head_en = f"{label(cur, 'en')}: {num_with_unit(v, cur, 'en') if ok_unit else fmt(v)} in {period_label(focus_period, 'en')}{base_en}"
    if mt in ("weight", "distribution"):
        return None        # weights and distributions are structure, not news
    comparable = mt in ("index", "level", "ratio", "rate", "share", "percentage") and ok_unit

    def compare(other, word_ar, word_en, key):
        if other is None or not comparable:
            return
        d = v - other["value"]
        nums[key + "_value"] = other["value"]; nums[key + "_period"] = other["period"]
        ev.append(dict(period=other["period"], value=other["value_raw"], cell=other["source_cell"]))
        if pct_type or mt == "ratio":
            nums[key + "_diff"] = d
            du_ar, du_en = diff_unit(cur, "ar"), diff_unit(cur, "en")
            parts_ar.append(f"{word_ar} {fmt(other['value'])}{'%' if pct_type else ''} ({'+' if d > 0 else ''}{fmt(d)} {du_ar})".replace(" )", ")"))
            parts_en.append(f"{word_en} {fmt(other['value'])}{'%' if pct_type else ''} ({'+' if d > 0 else ''}{fmt(d)} {du_en})".replace(" )", ")"))
        else:
            pc = d / other["value"] * 100 if other["value"] else None
            nums[key + "_diff"] = d
            if pc is not None:
                nums[key + "_pct"] = pc
            tail_ar = f"{'+' if pc > 0 else ''}{fmt(pc)}%" if pc is not None else f"{'+' if d > 0 else ''}{fmt(d)}"
            parts_ar.append(f"{word_ar} {fmt(other['value'])} ({tail_ar})")
            parts_en.append(f"{word_en} {fmt(other['value'])} ({tail_ar})")
    compare(prev, "مقابل", "versus", "prev")
    if prev is not None and parts_ar:
        parts_ar[-1] += " في " + period_label(prev["period"], "ar"); parts_en[-1] += " in " + period_label(prev["period"], "en")
    compare(yoy, "ومقابل", "and versus", "yoy")
    if yoy is not None and len(parts_ar) and "yoy_value" in nums:
        parts_ar[-1] += " في " + period_label(yoy["period"], "ar"); parts_en[-1] += " in " + period_label(yoy["period"], "en")
    flag = ""
    if comparable and n >= MIN_HISTORY:
        earlier = [(p, val) for _, p, val in hist[:-1]]
        first_p = hist[0][1]
        hi = [p for p, val in earlier if val >= v]
        lo = [p for p, val in earlier if val <= v]
        if not hi:
            flag = "high"
            parts_ar.append(f"وهي الأعلى في البيانات المتاحة (منذ {period_label(first_p, 'ar')})"); parts_en.append(f"the highest in the available data (since {period_label(first_p, 'en')})")
        elif not lo:
            flag = "low"
            parts_ar.append(f"وهي الأدنى في البيانات المتاحة (منذ {period_label(first_p, 'ar')})"); parts_en.append(f"the lowest in the available data (since {period_label(first_p, 'en')})")
        else:
            nums["history_observations"] = n
        nums["history_start"] = first_p; nums["history_observations"] = n
    if not parts_ar and not flag:
        return None        # no previous or year-earlier period to compare with and no record: nothing to say
    if all(nums.get(k + "_diff", 1) == 0 for k in ("prev", "yoy") if k + "_diff" in nums) and not flag:
        return None        # unchanged
    text_ar = head_ar + (("، " + "، ".join(parts_ar)) if parts_ar else "") + "."
    text_en = head_en + ((", " + ", ".join(parts_en)) if parts_en else "") + "."
    # importance score: totals first, then series with history and a comparison, then notable movement
    score = (6 if cur["is_total_row"] else 0) + (1 if prev is not None else 0) + (1 if yoy is not None else 0) + (1 if n >= 12 else 0) + (2 if flag else 0) + (1 if mt == "rate" else 0)
    mv = abs(nums.get("prev_pct", nums.get("prev_diff", 0)) or 0)
    return dict(kind="series_change", score=score, movement=mv, flag=flag, dataset_id=dataset_id, sheet=cur["sheet"], period=focus_period,
                measure_type=mt, unit=cur["unit"], unit_ok=ok_unit, text_ar=text_ar, text_en=text_en, numbers=nums, evidence=ev,
                is_total=bool(cur["is_total_row"]), group_key=(cur["sheet"], cur["block"], cur["col_label_ar"] if mt != "rate" else "", cur["col_sub"], mt, cur["unit"], cur["_off"], focus_period),
                source_file_url=cur["source_file_url"], series_label=label(cur), table_title=cur.get("table_title", ""))


def cross_section(members, dataset_id):
    """members: one observation per series, same group and period. Highest and lowest member (no history needed)."""
    ms = [m for m in members if not m["is_total_row"]]
    if len(ms) < 3 or not unit_ok(ms[0]) or ms[0]["measure_type"] in ("unknown",):
        return None
    ms.sort(key=lambda r: r["value"])
    lo, hi = ms[0], ms[-1]
    if hi["value"] == lo["value"]:
        return None
    r0 = ms[0]
    same = norm(hi["row_label_ar"]) == norm(lo["row_label_ar"]) and norm(hi["row_label_en"]) == norm(lo["row_label_en"])
    lab_ar = lambda r: (r["row_label_ar"] or r["row_label_en"] or r["row_code"]).lstrip("*") + (f" [{r['row_code']}]" if same and r["row_code"] else "")  # noqa: E731
    lab_en = lambda r: (r["row_label_en"] or r["row_label_ar"] or r["row_code"]).lstrip("*") + (f" [{r['row_code']}]" if same and r["row_code"] else "")  # noqa: E731
    ctx_ar = " | ".join(x for x in (r0["row_group"], r0["col_label_ar"] if r0["measure_type"] != "rate" else "", r0["col_sub"]) if x)
    ctx_en = " | ".join(x for x in (r0["row_group"], (r0["col_label_en"] or r0["col_label_ar"]) if r0["measure_type"] != "rate" else "", r0["col_sub"]) if x)
    pre_ar = (ctx_ar + ": ") if ctx_ar else ""
    pre_en = (ctx_en + ": ") if ctx_en else ""
    t_ar = (f"{pre_ar}الأعلى بين {bunud(len(ms))} هو {lab_ar(hi)} ({num_with_unit(hi['value'], hi, 'ar')}) والأدنى هو {lab_ar(lo)} ({num_with_unit(lo['value'], lo, 'ar')}) "
            f"في {period_label(hi['period'], 'ar')}.")
    t_en = (f"{pre_en}Highest of {len(ms)} items is {lab_en(hi)} ({num_with_unit(hi['value'], hi, 'en')}), lowest is {lab_en(lo)} ({num_with_unit(lo['value'], lo, 'en')}) "
            f"in {period_label(hi['period'], 'en')}.")
    return dict(kind="cross_section", score=1, movement=0, dataset_id=dataset_id, sheet=hi["sheet"], period=hi["period"], measure_type=hi["measure_type"], unit=hi["unit"],
                unit_ok=True, text_ar=t_ar, text_en=t_en, numbers=dict(items=len(ms), highest=hi["value"], lowest=lo["value"], period=hi["period"]),
                evidence=[dict(period=hi["period"], value=hi["value_raw"], cell=hi["source_cell"]), dict(period=lo["period"], value=lo["value_raw"], cell=lo["source_cell"])],
                is_total=False, source_file_url=hi["source_file_url"], series_label=ctx_ar, table_title=hi.get("table_title", ""))


# ------------------------------------------------------------------ build
def build_for_publication(pid, pub=None):
    pid = str(pid)
    insights, datasets, ds_ids = [], 0, set()
    for f in sorted((ROOT / "data").glob("*/*.parquet")):
        head = pd.read_parquet(f, columns=["publication_id"])
        if pid not in set(head["publication_id"]):
            continue
        datasets += 1
        df = prepare(pd.read_parquet(f))
        dsid = df["dataset_id"].iloc[0]; ds_ids.add(dsid)
        this = df[df["publication_id"] == pid]
        keys = set(this["_key"])
        per_series = {}
        for r in df[df["_key"].isin(keys)].sort_values("period").to_dict("records"):
            per_series.setdefault(r["_key"], []).append(r)
        singles, multis = [], []
        fps = {k: max((r["period"] for r in rows if r["publication_id"] == pid), key=lambda p: ordinal(p)[0]) for k, rows in per_series.items()}
        latest = max(ordinal(p)[0] for p in fps.values())
        for k, rows in per_series.items():
            fp = fps[k]
            if ordinal(fp)[0] != latest:
                continue      # a series that stops earlier than the rest of the table is history, not news for this release
            if len({r["period"] for r in rows}) >= 2:
                ins = series_insight(rows, fp, pid, dsid)
                if ins:
                    multis.append(ins)
            else:
                cur = [r for r in rows if r["period"] == fp][0]
                singles.append(cur)
        # movers: largest rise / fall inside each group of series that share a table, column and period
        groups = {}
        for i in multis:
            if "prev_diff" in i["numbers"] and not i["is_total"]:
                groups.setdefault(i["group_key"], []).append(i)
        # per dataset: all totals (capped), the strongest record highs/lows, the biggest movers, then cross sections
        ds_ins = []
        ordr = lambda i: (-i["score"], -i["movement"], i["series_label"])  # noqa: E731
        ds_ins += sorted([i for i in multis if i["is_total"]], key=ordr)[:TOTALS_PER_DATASET]
        ds_ins += sorted([i for i in multis if i["flag"] and not i["is_total"]], key=lambda i: (-i["movement"], i["series_label"]))[:FLAGS_PER_DATASET]
        movers = []
        for g, items in groups.items():
            if len(items) < 3:
                continue
            key = "prev_pct" if all("prev_pct" in i["numbers"] for i in items) else "prev_diff"
            items.sort(key=lambda i: i["numbers"][key])
            for i, role in ((items[-1], "mover_up"), (items[0], "mover_down")):
                val = i["numbers"][key]
                if (role == "mover_up" and val > 0) or (role == "mover_down" and val < 0):
                    movers.append(dict(i, kind=role, score=min(i["score"], 4) + 0.5, movement=abs(val)))
        ds_ins += sorted(movers, key=lambda i: (-len(groups[i["group_key"]]), -i["movement"]))[:MOVERS_PER_DATASET * 2]
        sg = {}
        for r in singles:
            sg.setdefault((r["sheet"], r["block"], r["col_label_ar"] if r["measure_type"] != "rate" else "", r["col_sub"], r["measure_type"], r["unit"], r["_off"], r["period"], r["row_group"]), []).append(r)
        cs = [c for c in (cross_section(m, dsid) for m in sg.values()) if c]
        cs.sort(key=lambda c: -c["numbers"]["items"])
        ds_ins += cs[:CROSS_PER_DATASET]
        insights += ds_ins
    # revisions of already published values
    revs = []
    rp = ROOT / "registry" / "revisions.jsonl"
    if rp.exists() and pub:
        for line in rp.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("new_release") == pub["release_date"] and r["dataset_id"] in ds_ids:
                revs.append(r)
    if revs:
        by = {}
        for r in revs:
            by.setdefault(r["dataset_id"], []).append(r)
        n_ds = len(by)
        big = max(revs, key=lambda r: abs(r["new_value"] - r["old_value"]) / (abs(r["old_value"]) or 1))
        ratio = big["new_value"] / big["old_value"] if big["old_value"] else None
        k = next((e for e in (3, 6, 2, 1) if ratio and (abs(ratio / 10 ** e - 1) < 0.005 or abs(ratio * 10 ** e - 1) < 0.005)), None)
        note_ar = f" التغيّر يعادل قسمة أو ضرب القيمة في 10^{k} تقريباً، أي أنه يبدو تصحيح وحدة وليس تغيّراً في الواقع." if k else ""
        note_en = f" The change equals a factor of 10^{k}, which looks like a unit correction rather than a real change." if k else ""
        tbl_ar = "جدول واحد" if n_ds == 1 else ("جدولين" if n_ds == 2 else (f"{n_ds} جداول" if n_ds <= 10 else f"{n_ds} جدولاً"))
        insights.append(dict(kind="revision", score=4, movement=0, dataset_id=big["dataset_id"], sheet="", period=big["period"], measure_type="", unit="", unit_ok=True, is_total=False,
                             text_ar=f"عُدّلت {len(revs)} قيمة منشورة سابقاً في {tbl_ar}. أكبر تعديل نسبي: {big['row']} ({big['period']}) من {fmt(big['old_value'])} إلى {fmt(big['new_value'])}." + note_ar,
                             text_en=f"{len(revs)} previously published values were revised across {n_ds} tables. Largest relative change: {big['row']} ({big['period']}) from {fmt(big['old_value'])} to {fmt(big['new_value'])}." + note_en,
                             numbers=dict(revised_values=len(revs), tables=n_ds, old=big["old_value"], new=big["new_value"]), evidence=[], series_label=big["row"], table_title=""))

    nd, kept = {}, []
    for i in insights:      # the same figure published in several summary tables is one insight
        n = i["numbers"]
        sig = (i["dataset_id"].rsplit("_", 1)[0], i["kind"], i.get("series_label", ""), i["period"], round(n.get("value", n.get("highest", 0)), 6), n.get("prev_value"), n.get("yoy_value"),
               n.get("lowest"), n.get("items"))
        if sig in nd:
            nd[sig].setdefault("also_in_tables", []).append(i["dataset_id"])
            continue
        nd[sig] = i; kept.append(i)
    insights = kept
    dup = {}
    for i in insights:
        dup.setdefault((i["dataset_id"], i["kind"], i.get("series_label", ""), i["period"]), []).append(i)
    for grp in dup.values():
        if len(grp) > 1:
            for i in grp:
                t = (i.get("table_title") or "").strip()
                if t:
                    i["text_ar"] = i["text_ar"].rstrip(".") + f" (الجدول: {short_title(t, 'ar')})."
                    i["text_en"] = i["text_en"].rstrip(".") + f" (table: {short_title(t, 'en') or short_title(t, 'ar')})."
    seen, uniq = set(), []
    for i in sorted(insights, key=lambda i: (-i["score"], -i["movement"], i["dataset_id"])):
        if i["text_ar"] in seen:
            continue
        seen.add(i["text_ar"]); uniq.append(i)
    insights = uniq
    out = []
    for n, i in enumerate(sorted(insights, key=lambda i: (-i["score"], -i["movement"], i["dataset_id"], i.get("series_label", ""))), 1):
        i = {k: v for k, v in i.items() if k not in ("group_key", "score", "movement")}
        i["id"] = f"{pid}-{n:03d}"
        out.append(i)
    # headline selection: best score first, at most MAX_PER_DATASET per dataset
    top, cnt = [], {}
    for i in out:
        if len(top) < MAX_HEADLINES and cnt.get(i["dataset_id"], 0) < MAX_PER_DATASET:
            cnt[i["dataset_id"]] = cnt.get(i["dataset_id"], 0) + 1
            i["headline"] = True; top.append(i["id"])
        else:
            i["headline"] = False
    return dict(publication_id=pid, datasets=datasets, insight_count=len(out), headline_ids=top, insights=out)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 10)
    if hasattr(o, "item"):
        return clean(o.item())
    return o


def write_for_publication(pub, run_ts=None):
    res = build_for_publication(pub["publication_id"], pub)
    res.update(title_ar=pub["title_ar"], title_en=pub["title_en"], release_date=pub["release_date"], source="الهيئة العامة للإحصاء / General Authority for Statistics",
               method="Computed from stored data with fixed templates. No language model. Each insight lists the source cells.",
               generated_at=run_ts or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{pub['publication_id']}.json"
    p.write_text(json.dumps(clean(res), ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def write_latest(limit=10):
    """catalog/latest_insights.json: headline insights of the most recent processed releases (feeds the web page)."""
    reg = json.loads((ROOT / "registry" / "publications.json").read_text(encoding="utf-8"))["publications"]
    out = []
    for p in sorted(reg, key=lambda x: (x["release_date"], x["publication_id"]), reverse=True):
        f = OUT / f"{p['publication_id']}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d["insights"]:
            continue
        byid = {i["id"]: i for i in d["insights"]}
        out.append(dict(publication_id=d["publication_id"], title_ar=d["title_ar"], title_en=d["title_en"], release_date=d["release_date"],
                        insight_count=d["insight_count"], headlines=[{k: byid[h][k] for k in ("id", "kind", "text_ar", "text_en", "period", "dataset_id")} for h in d["headline_ids"]]))
        if len(out) >= limit:
            break
    (ROOT / "catalog" / "latest_insights.json").write_text(json.dumps(clean(dict(source="الهيئة العامة للإحصاء / General Authority for Statistics", releases=out)), ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild insights for every processed publication")
    ap.add_argument("--pid", type=int)
    a = ap.parse_args()
    reg = json.loads((ROOT / "registry" / "publications.json").read_text(encoding="utf-8"))["publications"]
    for p in reg:
        if (a.pid and p["publication_id"] == a.pid) or (a.all and str(p.get("status", "")).startswith("processed")):
            r = write_for_publication(p)
            print(p["publication_id"], p["title_en"][:50], "datasets", r["datasets"], "insights", r["insight_count"], "headlines", len(r["headline_ids"]))
    write_latest()


if __name__ == "__main__":
    main()
