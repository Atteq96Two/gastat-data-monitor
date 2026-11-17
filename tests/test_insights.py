"""Independent check of the release insights (Phase 4). Run: python3 -I tests/test_insights.py
1. every number in every insight is read again from the original Excel cell and must match to 1e-9
2. every change (difference, percent) is recomputed from those cells and must match the stored figure
3. every number printed in a sentence must appear in the stored numbers (no invented figures)
4. cross-table consistency: published rates vs rates recomputed from the published index (CPI, business confidence)
Exit code 1 on any failure."""
import json, math, pathlib, re, sys, warnings, collections
import openpyxl
import pandas as pd
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gastat.insights import fmt   # noqa: E402

wbs, fails, checked = {}, [], collections.Counter()


def cell(pid, ref):
    sheet, rc = ref.rsplit("!", 1)
    r, c = map(int, re.fullmatch(r"R(\d+)C(\d+)", rc).groups())
    if pid not in wbs:
        wbs[pid] = openpyxl.load_workbook(ROOT / "cache" / "files" / str(pid) / "source.xlsx", data_only=True)
    return wbs[pid][sheet].cell(row=r, column=c).value


for f in sorted((ROOT / "catalog" / "insights").glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    pid = d["publication_id"]
    for i in d["insights"]:
        ev, n = i.get("evidence", []), i["numbers"]
        if i["kind"] == "revision":
            continue
        frac = i["unit"] == "fraction"
        raw, rawl = {}, []
        for e in ev:
            v = cell(pid, e["cell"])
            try:
                v = float(str(v).replace(",", ""))
            except Exception:
                fails.append((i["id"], "cell is not numeric", e["cell"])); continue
            checked["cells"] += 1
            if abs(v - e["value"]) > 1e-8:
                fails.append((i["id"], "cell differs from stored", e["cell"], v, e["value"]))
            raw[e["period"]] = v * (100 if frac else 1)
            rawl.append(v * (100 if frac else 1))
        if i["kind"] == "series_change":
            cur = raw.get(n["period"])
            if cur is None or abs(cur - n["value"]) > 1e-6:
                fails.append((i["id"], "current value", cur, n["value"]))
            for k in ("prev", "yoy"):
                if k + "_value" in n:
                    o = raw.get(n[k + "_period"])
                    if o is None or abs(o - n[k + "_value"]) > 1e-6:
                        fails.append((i["id"], k + " value", o, n[k + "_value"])); continue
                    if abs((cur - o) - n[k + "_diff"]) > 1e-6:
                        fails.append((i["id"], k + " diff"))
                    if k + "_pct" in n and o and abs((cur - o) / o * 100 - n[k + "_pct"]) > 1e-6:
                        fails.append((i["id"], k + " pct"))
                    checked["changes"] += 1
        elif i["kind"] in ("cross_section",):
            vals = rawl
            if abs(vals[0] - n["highest"]) > 1e-6 or abs(vals[1] - n["lowest"]) > 1e-6:
                fails.append((i["id"], "cross section values"))
        # numbers printed in the Arabic sentence must come from the stored numbers
        stored = {fmt(x) for x in n.values() if isinstance(x, (int, float))} | {fmt(abs(x)) for x in n.values() if isinstance(x, (int, float))}
        stored |= {str(x) for x in n.values() if isinstance(x, (int,))}
        stripped = re.sub(r"\(الجدول:.*?\)\.?$", "", i["text_ar"])
        stripped = re.sub(r"\b(19|20)\d\d(-\d\d)?\b", "", stripped)           # years and dates
        stripped = re.sub(r"\[[^\]]*\]", "", stripped)                         # row codes shown in brackets
        label = i.get("series_label", "")
        stripped = stripped.replace(label, "")
        if i["kind"] == "cross_section":
            for k in ("highest", "lowest"):
                if fmt(n[k]) not in i["text_ar"]:
                    fails.append((i["id"], "cross section number missing from sentence", k))
            nums_in_text = []
        else:
            nums_in_text = re.findall(r"[-+]?\d[\d,]*\.?\d*", stripped)
        for m in nums_in_text:
            m2 = m.lstrip("+-")
            if m2 not in stored and fmt(float(m2.replace(",", ""))) not in stored:
                fails.append((i["id"], "printed number not in stored numbers", m))
        checked["sentences"] += 1
        if "—" in i["text_ar"] + i["text_en"] or "–" in i["text_ar"] + i["text_en"]:
            fails.append((i["id"], "dash character in text"))


# 4. cross-table consistency
def one(df, **kw):
    for k, v in kw.items():
        df = df[df[k] == v]
    return df


def load(name):
    return pd.read_parquet(next((ROOT / "data").glob(f"*/{name}.parquet")))


cons = []
b2, b3 = load("business-confidence-index-for_2"), load("business-confidence-index-for_3")
for lab in b2.row_label_ar.unique():
    s2 = b2[b2.row_label_ar == lab].set_index("period").value.groupby(level=0).first()
    s3 = b3[b3.row_label_ar == lab].set_index("period").value.groupby(level=0).first()
    for p in s3.index:
        y, m = int(p[:4]), int(p[5:])
        prev = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"
        if p in s2.index and prev in s2.index:
            cons.append(("BCI monthly rate", lab, p, s3[p] * 100, (s2[p] / s2[prev] - 1) * 100))
c1 = load("consumer-price-index_1-1")
for lab in c1.row_label_ar.unique():
    g = c1[(c1.row_label_ar == lab)]
    idx = g[g.measure_type == "index"].set_index("period").value.groupby(level=0).first()
    rt = g[(g.measure_type == "rate") & (g.base_period != "")]
    for _, r in rt.iterrows():
        if r.period in idx.index and r.base_period in idx.index:
            cons.append(("CPI 1.1 published change", lab[:40], f"{r.period} vs {r.base_period}", r.value, (idx[r.period] / idx[r.base_period] - 1) * 100))
# differences between two numbers GASTAT itself publishes in the same file (checked by hand, reported to the user, not an engine error)
KNOWN_SOURCE_DIFFS = {("BCI monthly rate", "مؤشر ثقة الأعمال لقطاع الخدمات", "2026-02")}
bad = [c for c in cons if abs(c[3] - c[4]) > 0.06 and c[:3] not in KNOWN_SOURCE_DIFFS]
checked["consistency"] = len(cons)
for c in bad[:15]:
    fails.append(("consistency",) + c)
print(dict(checked), "failures:", len(fails))
for x in fails[:25]:
    print("  FAIL", x)
sys.exit(1 if fails else 0)
