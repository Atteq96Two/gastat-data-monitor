"""Apply a (draft or reviewed) recipe to a detected block and emit tidy long rows: one row per single number."""
import re, datetime as dt
from .grid import kind, clean, norm, script, to_num, MONTHS_AR
from .detect import TOTAL

DIST = re.compile(r"التوزيع النسبي|التوزيع النسبى|relative distribution|percentage distribution|distribution")
RATE = re.compile(r"معدل|نسبه التغير|نسبه النمو|التغير|التغيير|change|rate|growth|نمو")
PCT = re.compile(r"النسبه المئويه|percentage|percent|%|نسبه")
INDEX = re.compile(r"الرقم القياسي|الارقام القياسيه|index|indices|مؤشر")
WEIGHT = re.compile(r"الاوزان|الوزن النسبي|الوزن \(|^الوزن$|weight")
LEVEL = re.compile(r"كيلومتر|km|كميه|كمية|عدد|number|count|الف |thousand|مليون|million|مليار|billion|ريال|sar|الكميه|quantity|اسعار|price|سعر|متوسطات|متوسط (سعر|اسعار|الاسعار)|average (price|prices)")
SCALES = [(r"بالمليار|billion", 1e9), (r"بالمليون|million", 1e6), (r"بالالف|thousand|\(الف\)|الاف", 1e3)]
M_AR = {m: i + 1 for i, m in enumerate("يناير فبراير مارس ابريل مايو يونيو يوليو اغسطس سبتمبر اكتوبر نوفمبر ديسمبر".split())}
M_EN = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
Q_AR = {"الاول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4}


def period_from_text(t):
    n = norm(t)
    m = re.search(r"ربع (\S+)\D*(20\d\d)", n)
    if m and m.group(1) in Q_AR:
        return f"{m.group(2)}-Q{Q_AR[m.group(1)]}", "quarter"
    m = re.search(r"q([1-4])\D{0,3}(20\d\d)", n)
    if m:
        return f"{m.group(2)}-Q{m.group(1)}", "quarter"
    for name, i in M_AR.items():
        m = re.search(name + r"\D{0,3}(20\d\d)", n)
        if m:
            return f"{m.group(1)}-{i:02d}", "month"
    for name, i in M_EN.items():
        m = re.search(name + r"[a-z]*[\s,\-/]*(20\d\d)", n)
        if m:
            return f"{m.group(1)}-{i:02d}", "month"
    return None, None


def measure_type(col_text, title_text):
    for t in (norm(col_text), norm(title_text)):
        if not t:
            continue
        if WEIGHT.search(t):
            return "weight"
        if DIST.search(t):
            return "distribution"
        if RATE.search(t):
            return "rate"
        if INDEX.search(t):
            return "index"
        if LEVEL.search(t):
            return "level"
        if PCT.search(t):
            return "percentage"
    return "unknown"


def unit_scale(*texts):
    t = norm(" ".join(x for x in texts if x))
    scale = 1
    for pat, f in SCALES:
        if re.search(pat, t):
            scale = f
            break
    unit = None
    m = re.search(r"(20\d\d)\s*=\s*100", t)
    if m:
        unit = f"index_base_{m.group(1)}"
    elif re.search(r"كيلومتر|\bkm\b", t):
        unit = "km"
    elif re.search(r"ريال|sar|riyal", t):
        unit = "SAR"
    elif re.search(r"%|نسبه مئويه|percent", t):
        unit = "percent"
    return unit, scale


def parse_unit_text(text):
    """'ألف خلية' -> ('خلية', 1000); 'مليون' -> ('count', 1e6); 'عدد' -> ('count', 1); 'طن' -> ('طن', 1)."""
    t = clean(text); nb = norm(t); scale = 1
    for pat, f in ((r"^(ب)?(مليار|billion)", 1e9), (r"^(ب)?(مليون|million)", 1e6), (r"^(ب)?(الف|thousand)", 1e3)):
        if re.search(pat, nb):
            scale = f; break
    rest = re.sub(r"^(ب)?(الف|مليون|مليار|thousand|million|billion)\s*", "", nb).strip()
    if scale != 1 and not rest:
        return "count", scale
    if nb in ("عدد", "count", "number"):
        return "count", 1
    if scale != 1:
        return t.split(None, 1)[-1], scale
    return t, 1


def infer_percent_types(rows):
    """Classify percentage-like tables from the data: distribution (components sum to 100), multi_response (sum above 100), else share."""
    for r in rows:   # flattened "a_b" headers whose measure words are absent: percent-style table (rule c)
        if r["measure_type"] == "unknown" and r["col_sub"] and 0 <= r["value"] <= 100.5:
            r["measure_type"] = "percentage"
    cand = [r for r in rows if r["measure_type"] in ("percentage", "distribution") and 0 <= r["value"] <= 100.5]
    if not cand or any(r["measure_type"] not in ("percentage", "distribution", "rate") for r in rows if r["measure_type"] != "level" and False):
        return
    import collections
    def groups(by_sub):
        gp = collections.defaultdict(list)
        for r in cand:
            if r["is_total_row"]:
                continue
            key = ((r["row_label_ar"], r["row_group"], r["col_sub"], r["period"]) if by_sub else (r["col_label_ar"], r["col_sub"], r["period"], r["block"]))
            gp[key].append(r["value"])
        return [sum(v) for v in gp.values() if len(v) >= 2]
    flat = any(r["col_sub"] for r in cand)
    sums = groups(True) if flat else groups(False)
    if sums and all(abs(x - 100) <= 1.5 for x in sums):
        t = "distribution"
    elif sums and any(x > 101.5 for x in sums):
        t = "multi_response"
    else:
        t = "share"
    for r in cand:
        if r["measure_type"] == "percentage" or r["measure_type"] == "distribution":
            r["measure_type"] = t; r["measure_inferred"] = True


def extract_block(g, infos, c0, b, d, pub, sheet, block_idx, recipe):
    rows, notes = [], []
    title_txt = " ".join(clean(g.cells[r][c]) for r in b["title"] for c in range(g.ncols)
                         if g.anchor[r][c] and kind(g.cells[r][c]) == "text")
    # header rows carrying only a few anchored texts are really table titles (e.g. "annual rate of change series")
    for hr in b["header"]:
        anc = [clean(g.cells[hr][c]) for c in range(g.ncols) if g.anchor[hr][c] and kind(g.cells[hr][c]) == "text"]
        if 0 < len(anc) <= 3:
            title_txt += " " + " ".join(anc)
    ref_p, ref_pt = period_from_text(title_txt)
    foot_txt = " ".join(clean(g.cells[r][c]) for r in range(b["end"] + 1, min(g.nrows, b["end"] + 7)) for c in range(g.ncols)
                        if g.anchor[r][c] and kind(g.cells[r][c]) == "text")
    labs = (recipe or {}).get("label_roles") or [x["role"] for x in d["label_cols"]]
    # sparse leading label columns are group headers: forward fill
    fill = {}
    for x in d["label_cols"][:-1]:
        c = x["col"]
        vals = [g.cells[r][c] for r in range(b["start"], b["end"] + 1)]
        ne = sum(kind(v) != "empty" for v in vals)
        fill[c] = ne < 0.7 * len(vals) and x["role"] not in ("code", "unit", "level")
    last = {}
    group = ""
    col_info = {}
    # a header row made only of the word "الوحدة" (unit) marks the next header row as the per-column units
    unit_row = None
    for i, hr in enumerate(b["header"][:-1]):
        cells = [clean(g.cells[hr][c]) for c in d["val_cols"] if kind(g.cells[hr][c]) == "text"]
        if cells and all(norm(t) in ("الوحده", "unit", "units") for t in cells):
            unit_row = b["header"][i + 1]
            break
    for c in d["val_cols"]:
        toks = d["col_tokens"][c]
        texts = [t for k, t in toks if k == "text"]
        dates = [t for k, t in toks if k == "date"]
        years = [t for k, t in toks if k == "year"]
        quarters = [t for k, t in toks if k == "quarter"]
        codes = [t for t in texts if script(t) == "none" and re.fullmatch(r"[\d.\-]+", t)]
        texts = [t for t in texts if t not in codes]
        row_unit_txt = ""
        if unit_row is not None:
            row_unit_txt = clean(g.cells[unit_row][c]) if kind(g.cells[unit_row][c]) == "text" else ""
            texts = [t for t in texts if t != row_unit_txt and norm(t) not in ("الوحده", "unit", "units")]
        sub = ""
        if len(texts) == 1 and re.fullmatch(r"[^_]+_[^_]+", texts[0]):
            texts[0], sub = [x.strip() for x in texts[0].split("_", 1)]   # two dimensions flattened into one header
        bracket = " ".join(re.findall(r"[(（]([^()（）]{1,30})[)）]", " ".join(texts)))
        col_ar = " / ".join(t for t in texts if script(t) in ("ar", "none"))
        col_en = " / ".join(t for t in texts if script(t) == "en")
        is_ts = any(x["role"] in ("year", "month") for x in d["label_cols"])  # time series: columns are items, the title names the measure
        ov = next((o for o in (recipe or {}).get("measure_overrides", []) if o.get("sheet") == sheet), {})
        mt = ov.get("measure_type") or (recipe or {}).get("measure_type") or (measure_type("", title_txt) if is_ts else measure_type(" ".join(texts), title_txt))
        p = pt = base = None
        if dates and mt != "rate":
            dd = dates[-1]; p, pt = f"{dd.year}-{dd.month:02d}", "month"
        elif dates:
            dd = dates[0]; base = f"{dd.year}-{dd.month:02d}"
        if years and quarters:
            qn = re.search(r"[1-4]|الاول|الثاني|الثالث|الرابع", norm(quarters[0]))
            q = int(qn.group()) if qn and qn.group().isdigit() else Q_AR.get(qn.group() if qn else "", None)
            if q:
                p, pt = f"{years[0]}-Q{q}", "quarter"
        elif quarters:
            qn = re.search(r"[1-4]|الاول|الثاني|الثالث|الرابع", norm(quarters[0]))
            q = int(qn.group()) if qn and qn.group().isdigit() else Q_AR.get(qn.group() if qn else "", None)
            yr = (ref_p or pub["reference_period"] or "")[:4]
            if q and yr:
                p, pt = f"{yr}-Q{q}", "quarter"
        elif years:
            p, pt = str(years[0]), "year"
        psrc = "header"
        if p is None:
            tp, tpt = period_from_text(" ".join(texts))
            if tp:
                p, pt = tp, tpt
            elif ref_p:
                p, pt, psrc = ref_p, ref_pt, "sheet_title"
            else:
                p, pt, psrc = pub["reference_period"], pub["period_type"], "publication"
        u, sc = unit_scale(title_txt, " ".join(texts))
        if row_unit_txt:
            u2, sc2 = parse_unit_text(row_unit_txt)
            u, sc = u2, (sc2 if sc2 != 1 else sc)
            if mt in ("unknown", "level") or True:
                mt = "level" if mt in ("unknown", "level") else mt
        elif bracket:
            bu, bsc = unit_scale(bracket)
            nb = norm(bracket)
            for pat, f in ((r"^(ب)?(مليار|billion)", 1e9), (r"^(ب)?(مليون|million)", 1e6), (r"^(ب)?(الف|thousand)", 1e3)):
                if re.search(pat, nb):
                    bsc = f; break
            if bsc != 1: sc = bsc
            rest = re.sub(r"^(ب)?(الف|مليون|مليار|thousand|million|billion)\s*", "", nb).strip()
            u = bu or (rest and bracket.split(None, 1)[-1] if rest and " " in bracket.strip() else None) or ("count" if bsc != 1 else bracket)
        if u is None and mt in ("unknown", "level"):
            fu, fsc = unit_scale(foot_txt)
            u = fu; sc = fsc if sc == 1 else sc
        if ov.get("unit") or (recipe or {}).get("unit"): u = ov.get("unit") or recipe["unit"]
        if (recipe or {}).get("scale"): sc = recipe["scale"]
        if mt in ("unknown", "level") and bracket:
            mt = "ratio" if re.search(r"/|لكل|per", bracket) else "level"   # bracketed unit: a quantity, or a ratio (not additive)
        if mt == "rate" and not u: u = "percent_or_fraction"
        if mt == "index" and not u: u = "index"
        col_info[c] = dict(col_sub=sub, col_code="|".join(codes), col_ar=col_ar, col_en=col_en, measure_type=mt, period=p, period_type=pt, period_source=psrc,
                           base_period=base, unit=u, scale=sc, col_text=" | ".join(texts))
    # flattened headers where a repeated triple lost its "_gender" suffix: assign male/female/total by position
    # (the same reading used in the user's reference CSV; recorded as an inferred value)
    cols = list(col_info)
    gender_vals = {"ذكر", "انثى", "أنثى", "اجمالي", "إجمالي", "الاجمالي", "الإجمالي"}
    if any(col_info[c]["col_sub"] and norm(col_info[c]["col_sub"]) in {norm(x) for x in gender_vals} for c in cols):
        i = 0
        while i + 2 < len(cols):
            a, bb, cc = (col_info[cols[i]], col_info[cols[i + 1]], col_info[cols[i + 2]])
            if not a["col_sub"] and not bb["col_sub"] and not cc["col_sub"] and a["col_ar"] and a["col_ar"] == bb["col_ar"] == cc["col_ar"]:
                a["col_sub"], bb["col_sub"], cc["col_sub"] = "ذكر", "انثى", "اجمالي"
                a["sub_inferred"] = bb["sub_inferred"] = cc["sub_inferred"] = True
                i += 3
            else:
                i += 1
    for r in range(b["start"], b["end"] + 1):
        inf = infos[r]
        is_dat = any(c in col_info for c in inf["nums"]) and not inf["yearish"]
        if not is_dat:
            lab = " ".join(clean(g.cells[r][x["col"]]) for x in d["label_cols"] if kind(g.cells[r][x["col"]]) == "text")
            if lab:
                group = lab
            continue
        parent = " / ".join(clean(last[x["col"]]) for x in d["label_cols"] if fill.get(x["col"]) and last.get(x["col"]) is not None)
        lv = {"code": [], "level": "", "label_ar": [], "label_en": [], "unit": "", "year": "", "month": ""}
        for x in d["label_cols"]:
            c = x["col"]; v = g.cells[r][c]
            if kind(v) == "empty" and fill.get(c):
                v = last.get(c)
            elif kind(v) != "empty":
                last[c] = v
                for cc in [y["col"] for y in d["label_cols"] if y["col"] > c and fill.get(y["col"])]:
                    last.pop(cc, None)
            if kind(v) == "empty":
                continue
            s = clean(v)
            if x["role"] == "code": lv["code"].append(s)
            elif x["role"] == "level": lv["level"] = s
            elif x["role"] in ("year", "month"): lv[x["role"]] = s
            elif x["role"] == "unit": lv["unit"] = s
            elif x["role"] == "label_en": lv["label_en"].append(s)
            else: lv["label_ar"].append(s)
        if not parent and len(lv["label_ar"]) >= 2:
            parent = lv["label_ar"][0]
        lab_ar, lab_en = " / ".join(lv["label_ar"]), " / ".join(lv["label_en"])
        if (recipe or {}).get("region_city_level") and len(lv["label_ar"]) >= 2:
            lv["level"] = "region" if norm(lv["label_ar"][0]) == norm(lv["label_ar"][1]) else "city"
        is_total = bool(TOTAL.search(norm(lab_ar))) or bool(TOTAL.search(norm(lab_en)))
        for c in d["val_cols"]:
            k = g.k(r, c)
            if k not in ("num", "numtext"):
                continue
            ci = col_info[c]
            per, pty, psrc = ci["period"], ci["period_type"], ci["period_source"]
            if lv["year"] and lv["month"]:
                per, pty, psrc = f"{lv['year']}-{int(lv['month']):02d}", "month", "row"
            elif lv["year"]:
                per, pty, psrc = lv["year"], "year", "row"
            rows.append(dict(sheet=sheet, block=block_idx, source_row=r + 1, source_col=c + 1, row_code="|".join(lv["code"]), row_level=lv["level"],
                             row_label_ar=lab_ar, row_label_en=lab_en, row_unit=lv["unit"], row_group=group, row_parent=parent,
                             is_total_row=is_total, col_label_ar=ci["col_ar"], col_label_en=ci["col_en"], col_sub=ci["col_sub"],
                             period=per, period_type=pty, period_source=psrc, col_code=ci["col_code"],
                             base_period=ci["base_period"], measure_type=ci["measure_type"], unit=ci["unit"],
                             scale=ci["scale"], value=to_num(g.cells[r][c])))
    # a filled unit column (tonnes, count, head ...) means the numbers are quantities
    for r in rows:
        if r["measure_type"] == "unknown" and r["row_unit"]:
            r["measure_type"] = "level"; r["unit"] = r["unit"] or r["row_unit"]; r["measure_inferred"] = True
    # no unit/measure words anywhere: whole-number values are counts (flagged as inferred, to be confirmed by the user)
    unk = [r for r in rows if r["measure_type"] == "unknown"]
    if unk and all(float(r["value"]).is_integer() and r["value"] >= 0 for r in unk):
        for r in unk:
            r["measure_type"] = "level"; r["measure_inferred"] = True
    for r in rows:
        if not r["unit"] and r["row_unit"]:
            r["unit"] = r["row_unit"]
    # whole-number quantities with no stated unit are counts (flagged as inferred); fractional ones stay unresolved and are asked about
    nu = [r for r in rows if r["measure_type"] == "level" and not r["unit"]]
    if nu and all(float(r["value"]).is_integer() for r in nu):
        for r in nu:
            r["unit"] = "count"; r["unit_inferred"] = True
    infer_percent_types(rows)
    return rows, dict(title=title_txt[:200], col_info={str(k): v for k, v in col_info.items()})
