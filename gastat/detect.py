"""Detect table blocks inside a sheet and describe their structure (positions are discovered, never hardcoded)."""
import re, hashlib, json, datetime as dt
from .grid import Grid, kind, norm, clean, script, is_year, MONTHS_AR, MONTHS_EN

FOOT = re.compile(r"^(المصدر|source|ملاحظه|ملاحظات|note|notes|\*|\(\*\))", re.I)
TOTAL = re.compile(r"(^|\s)(اجمالي|المجموع|مجموع|total|overall|الرقم القياسي العام|الاجمالي|كل المناطق|جميع المناطق|all regions|general index)(\s|$)", re.I)
QUARTER = re.compile(r"^(q[1-4]|الربع (الاول|الثاني|الثالث|الرابع)|ر[1-4])$", re.I)


def _nonempty(g, r, c0=0):
    return [(c, g.cells[r][c]) for c in range(c0, g.ncols) if kind(g.cells[r][c]) != "empty"]


def _row_info(g, r):
    ks = [g.k(r, c) for c in range(g.ncols)]
    nums = [c for c, k in enumerate(ks) if k in ("num", "numtext")]
    def _yr(c):
        v = g.cells[r][c]
        try:
            return is_year(float(str(v).strip()))
        except ValueError:
            return False
    yearish = bool(nums) and all(_yr(c) for c in nums)
    if yearish:
        vals = []
        for c in nums:
            v = float(str(g.cells[r][c]).strip())
            if not vals or vals[-1] != v:
                vals.append(v)
        yearish = (len(vals) >= 2 and len(nums) >= 2) or any(m[0] == r for m in g.merges) or not any(k == 'text' and g.anchor[r][c] for c, k in enumerate(ks))  # header row of years
    first = next((c for c, k in enumerate(ks) if k != "empty"), None)
    text = [clean(g.cells[r][c]) for c, k in enumerate(ks) if k == "text"]
    return dict(ks=ks, nums=nums, yearish=yearish, first=first, empty=first is None,
                foot=bool(text) and bool(FOOT.match(norm(text[0]))) and ks[first] == "text" and not nums,   # a "*Higher education" row with numbers is data, not a footnote
                dates=[c for c, k in enumerate(ks) if k == "date"],
                distinct=len({clean(g.cells[r][c]) if k != "date" else str(g.cells[r][c]) for c, k in enumerate(ks) if k != "empty"}))


def value_start(g, infos):
    """Return (c0, c1): the densest run of numeric columns (not interrupted by text columns).
    Row-index columns (1..N) and year/date row labels are excluded from the run."""
    cand = [i for i, inf in enumerate(infos) if not inf["yearish"] and not inf["foot"] and len(inf["nums"]) >= 2]
    if not cand:
        cand = [i for i, inf in enumerate(infos) if not inf["yearish"] and not inf["foot"] and len(inf["nums"]) >= 1]
    if not cand:
        return None
    typ, cnt = [], []
    for c in range(g.ncols):
        n = t = 0
        for i in cand:
            k = infos[i]["ks"][c]
            n += k in ("num", "numtext"); t += k == "text"
        cnt.append(n)
        typ.append("num" if n >= 0.4 * len(cand) else ("text" if t >= 0.5 * len(cand) else "sparse"))

    def index_like(c):
        vs = [infos[i]["ks"][c] in ("num", "numtext") and float(str(g.cells[i][c]).replace(",", "")) for i in cand if infos[i]["ks"][c] in ("num", "numtext")]
        vs = [float(str(g.cells[i][c]).replace(",", "")) for i in cand if infos[i]["ks"][c] in ("num", "numtext")]
        if len(vs) < 3: return False
        if all(v.is_integer() for v in vs) and vs == sorted(vs) and len(set(vs)) == len(vs):
            return (vs[-1] - vs[0]) <= 2 * len(vs) or (1950 <= vs[0] <= 2100)  # 1..N counters or years/dates as row labels
        return False
    runs, cur = [], []
    for c in range(g.ncols):
        if typ[c] == "text":
            if cur: runs.append(cur); cur = []
        else:
            cur.append(c)
    if cur: runs.append(cur)
    best, bestscore = None, -1
    for run in runs:
        cols = [c for c in run if typ[c] == "num" and not index_like(c)]
        if not cols: continue
        score = sum(cnt[c] for c in cols)
        if score > bestscore: best, bestscore = (cols[0], cols[-1]), score
    if best is None:
        # fall back: index-like columns are the only numerics
        cols = [c for c in range(g.ncols) if typ[c] == "num"]
        return (cols[-1], cols[-1]) if cols else None
    return best


def segment(g):
    infos = [_row_info(g, r) for r in range(g.nrows)]
    vs = value_start(g, infos)
    if vs is None:
        return infos, None, []
    c0, c1 = vs
    g.c1 = c1

    def is_data(r):
        inf = infos[r]
        return (not inf["yearish"] and not inf["foot"] and any(c0 <= c <= c1 for c in inf["nums"]))

    tl = {}
    for r in range(g.nrows):
        if is_data(r):
            for c in range(g.ncols):
                if not c0 <= c <= c1 and g.k(r, c) == "text":
                    tl[c] = tl.get(c, 0) + len(str(g.cells[r][c]))
    main_label = max(tl, key=tl.get) if tl else 0
    g.main_label = main_label
    numcols = {c for r in range(g.nrows) if is_data(r) for c in infos[r]["nums"] if c0 <= c <= c1}

    def is_category(r):
        inf = infos[r]
        return (not inf["empty"] and not inf["foot"] and not is_data(r) and not any(g.k(r, c) != "empty" and g.anchor[r][c] for c in numcols)
                and g.k(r, main_label) == "text" and g.anchor[r][main_label])
    blocks, r = [], 0
    n = g.nrows
    while r < n:
        if not is_data(r):
            r += 1
            continue
        start = r
        end = r
        prev_end0 = blocks[-1]["end"] if blocks else -1
        while start - 1 > prev_end0 and is_category(start - 1):
            start -= 1  # category rows sitting between the header and the first data row belong to the block
        while end + 1 < n:
            nx = end + 1
            if is_data(nx):
                end = nx
            elif is_category(nx) and any(is_data(k) for k in range(nx + 1, min(n, nx + 3))):
                end = nx
            else:
                break
        # header rows above `start`
        hdr, up = [], start - 1
        prev_end = blocks[-1]["end"] if blocks else -1
        while up > prev_end:
            inf = infos[up]
            if inf["empty"] or inf["foot"]:
                break
            valcells = [c for c in range(c0, g.c1 + 1) if g.k(up, c) != "empty"]
            vcols_all = sorted(numcols)
            spans_all = bool(vcols_all) and all(g.k(up, c) != "empty" for c in vcols_all)
            if inf["distinct"] == 1 and inf["first"] is not None and (inf["first"] < c0 or spans_all):
                break  # a title (starts in label area or spans every value column)
            hdr.insert(0, up)
            up -= 1
        # title context: text rows above header until previous block end
        t, up2 = [], (hdr[0] if hdr else start) - 1
        while up2 > prev_end and len(t) < 12:
            if not infos[up2]["empty"]:
                t.insert(0, up2)
            up2 -= 1
        blocks.append(dict(start=start, end=end, header=hdr, title=t))
        r = end + 1
    merged = []
    for i, b in enumerate(blocks):
        nb = blocks[i + 1] if i + 1 < len(blocks) else None
        if nb and (b["end"] - b["start"] + 1) <= 2 and nb["header"] and nb["header"][0] == b["end"] + 1 and not b["header"][:0]:
            nb["header"] = list(range(b["start"], b["end"] + 1)) + nb["header"]
            nb["title"] = b["title"] + nb["title"]
            continue
        merged.append(b)
    return infos, c0, merged


def build_col_tokens(g, hdr, val_cols, fill_right=False, stars=False):
    """Header tokens per value column. fill_right: a label written once over a run of columns (not merged) also applies to the empty cells on its right, in every header row but the last."""
    col_tokens = {}
    carry = {}
    for c in val_cols:
        toks = []
        for hi, h in enumerate(hdr):
            v = g.cells[h][c]; k = kind(v)
            if k == "empty" and fill_right and hi < len(hdr) - 1:
                if h in carry:
                    v = carry[h]; k = kind(v)
            elif k != "empty":
                carry[h] = v
            if k == "empty":
                continue
            if k == "date":
                tok = ("date", v)
            elif k == "num" and is_year(v):
                tok = ("year", int(v))
            elif k == "num":
                tok = ("text", str(v))
            elif stars and re.fullmatch(r"\*{0,3}\s*(19|20)\d\d\s*\*{0,3}", clean(v)) and re.search(r"\*", clean(v)):
                tok = ("year", int(re.search(r"(19|20)\d\d", clean(v)).group()))       # "2026*": provisional year
            elif stars and k == "text" and re.search(r"(^|\s|/)(q[1-4]|الربع\s*(الاول|الأول|الثاني|الثالث|الرابع))($|\s|/)", norm(v).replace("ا", "ا")):
                tok = ("quarter", clean(v))
            elif stars and k == "text" and _month_in(v):
                tok = ("month", _month_in(v))           # "يناير/Jan": the column is that month of the year above it
            elif QUARTER.match(norm(v)):
                tok = ("quarter", clean(v))
            else:
                tok = ("text", clean(v))
            if not toks or toks[-1][1] != tok[1]:
                toks.append(tok)
        col_tokens[c] = toks
    return col_tokens


def _month_in(v):
    ws = [w for w in re.split(r"[\s/]+", clean(v)) if w]
    if len(ws) > 2:                                       # a sentence that merely mentions a month ("annual change in August") is a label
        return 0
    for w in ws:
        n_ = norm(w)
        if n_ in MONTHS_AR:
            return MONTHS_AR.index(n_) + 1
        if re.fullmatch(r"[a-z]{3,9}", n_.lower()) and n_.lower()[:3] in MONTHS_EN and n_.lower() in ("january","february","march","april","may","june","july","august","september","october","november","december","jan","feb","mar","apr","jun","jul","aug","sep","sept","oct","nov","dec"):
            return MONTHS_EN.index(n_.lower()[:3]) + 1
    return 0



def describe_block(g, infos, c0, b):  # c1 is carried on the grid
    """Structure of one block: label columns with roles, value columns with header paths."""
    data_rows = [r for r in range(b["start"], b["end"] + 1) if any(c0 <= c <= g.c1 for c in infos[r]["nums"])]
    hdr = b["header"]
    c1 = getattr(g, "c1", g.ncols - 1)
    val_cols = [c for c in range(c0, c1 + 1) if any(infos[r]["ks"][c] in ("num", "numtext") for r in data_rows)]
    def _rowno(c):  # a trailing 1..N counter column is not data
        vs = [g.cells[r][c] for r in data_rows if infos[r]["ks"][c] in ("num", "numtext")]
        return len(vs) >= 3 and all(float(str(v)) == i + 1 for i, v in enumerate(vs))
    label_cols = [c for c in range(0, g.ncols) if not (c0 <= c <= c1) and not _rowno(c) and (any(g.k(r, c) != "empty" for r in range(b["start"], b["end"] + 1)) or
                  any(g.k(h, c) != "empty" for h in hdr))]
    lab = []
    for c in label_cols:
        vals = [g.cells[r][c] for r in data_rows if kind(g.cells[r][c]) not in ("empty",)]
        txt = [clean(v) for v in vals]
        hdr_txt = " ".join(clean(g.cells[h][c]) for h in hdr if kind(g.cells[h][c]) != "empty")
        nh = norm(hdr_txt)
        if re.search(r"^(الدرجه|المستوي|level|درجه)", nh) and txt and all(re.fullmatch(r"\d", t) for t in txt[:60]):
            role = "level"
        elif re.search(r"(العام|السنه|year)", nh) and txt and all(re.fullmatch(r"20\d\d|19\d\d", t) for t in txt[:60]):
            role = "year"
        elif re.search(r"(الشهر|month)", nh) and txt and all(re.fullmatch(r"\d{1,2}", t) for t in txt[:60]):
            role = "month"
        elif re.search(r"كود|رمز|code", nh):
            role = "code"
        elif re.search(r"وحد|unit", nh):
            role = "unit"
        elif txt and all(re.fullmatch(r"[\d.\-]{1,8}|[A-Za-z]{1,3}[\d.]*|[ء-ي]", t) for t in txt[: 40]):
            role = "code"
        else:
            sc = [script(t) for t in txt]
            role = ("label_ar" if sc.count("ar") >= sc.count("en") else "label_en") if sc else "label_ar"
        lab.append(dict(col=c, role=role, header=hdr_txt))
    # per-column header tokens (kept in reading order, consecutive duplicates removed)
    col_tokens = build_col_tokens(g, hdr, val_cols)
    # header rows -> per-row type
    rows_desc = []
    for h in hdr:
        cells = [g.cells[h][c] for c in val_cols]
        ks = [kind(v) for v in cells]
        if all(k in ("empty",) for k in ks):
            continue
        if any(k == "date" for k in ks):
            typ = "date"
        elif all(k in ("num", "empty") for k in ks) and all(is_year(v) for v, k in zip(cells, ks) if k == "num"):
            typ = "year"
        elif all(QUARTER.match(norm(v)) for v, k in zip(cells, ks) if k == "text") and any(k == "text" for k in ks):
            typ = "quarter"
        else:
            txt = [clean(v) for v, k in zip(cells, ks) if k == "text"]
            sc = {script(t) for t in txt}
            typ = "ar" if sc == {"ar"} else ("en" if sc == {"en"} else "mixed")
        rows_desc.append(dict(row=h, type=typ))
    return dict(label_cols=lab, val_cols=val_cols, data_rows=data_rows, header_rows=rows_desc, col_tokens=col_tokens)


LEGACY_FINGERPRINT = False   # True reproduces the hashes made before "أكتوبر2026" and "أكتوبر 2026م" were treated as one layout (used once to migrate recipes)
MONTH_TOKEN = re.compile("|".join(MONTHS_AR + MONTHS_EN), re.I)


def fingerprint(g, infos, c0, b, d):
    """Hash of the normalized header structure. Periods and years are tokenized so a new release reuses the recipe."""
    parts = [f"L:{[x['role'] for x in d['label_cols']]}", f"H:{[x['type'] for x in d['header_rows']]}"]
    seen = []
    for hr in d["header_rows"]:
        toks = []
        for c in d["val_cols"]:
            v = g.cells[hr["row"]][c]
            k = kind(v)
            if k == "date":
                t = "DATE"
            elif k == "num":
                t = "YEAR"
            elif k == "empty":
                continue
            else:
                t = MONTH_TOKEN.sub("MONTH", norm(clean(v)))
                t = re.sub(r"\d{4}", "YEAR", t)
                if not LEGACY_FINGERPRINT:
                    t = re.sub(r"MONTH\s*YEAR(?:\s*\u0645)?\s*", lambda m_: "MONTH YEAR" + (" " if m_.end() < len(t) else ""), t)   # "أكتوبر2026م" and "يناير 2026م" are the same layout
                t = re.sub(r"\d+", "N", t)
            if t not in toks:
                toks.append(t)
        parts.append(f"R:{hr['type']}:{sorted(toks)}")
    for x in d["label_cols"]:
        parts.append("LH:" + re.sub(r"\d+", "N", norm(x["header"])))
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:12], parts
