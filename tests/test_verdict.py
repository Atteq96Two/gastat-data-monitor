"""The four verdicts on real stored data. Run: python3 -I tests/test_verdict.py (exit 1 on failure)"""
import pathlib, re, sys, warnings
import openpyxl
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gastat.verdict import check_claim   # noqa: E402

CPI = dict(query="الرقم القياسي لأسعار المستهلك", dataset_id="consumer-price-index_1-1", series="الرقم القياسي العام", as_of="2026-11-17")
YOY = dict(CPI, column="معدل أكتوبر 2025", period="2026-10")
BCI = dict(query="ثقة الأعمال", dataset_id="business-confidence-index-for_2", series="مؤشر ثقة الأعمال العام", period="2026-10", as_of="2026-11-17")
cases = [
    ("supports: inflation 1.7%", dict(YOY, claimed=1.7), "supports"),
    ("supports: 1.70 stated with two decimals", dict(YOY, claimed=1.70), "supports"),
    ("contradicts: inflation 3%", dict(YOY, claimed=3.0), "contradicts"),
    ("contradicts: 1.8 stated with one decimal (data 1.70)", dict(YOY, claimed=1.8), "contradicts"),
    ("supports: confidence fell month on month", dict(BCI, metric="change_prev", direction="down"), "supports"),
    ("contradicts: confidence rose month on month", dict(BCI, metric="change_prev", direction="up"), "contradicts"),
    ("supports: confidence fell 1.9% month on month", dict(BCI, metric="change_prev", claimed=-1.9), "supports"),
    ("data_too_old: December 2026 is not published", dict(YOY, period="2026-12", claimed=2.0), "data_too_old"),
    ("data_too_old: 'latest' claimed three months later", dict(CPI, column="معدل أكتوبر 2025", claimed=1.7, as_of="2027-02-20"), "data_too_old"),
    ("insufficient: period before the data starts", dict(YOY, period="2024-01", claimed=2.0), "insufficient_data"),
    ("insufficient: unknown indicator", dict(query="أسعار الذهب", claimed=5), "insufficient_data"),
    ("insufficient: no number and no direction", dict(YOY), "insufficient_data"),
    ("insufficient: two different series match (GDP quarterly vs yearly growth)", dict(query="الناتج المحلي الإجمالي الحقيقي", series="الناتج المحلي الإجمالي الحقيقي", period="2026-Q3", claimed=1.3, as_of="2026-11-17"), "insufficient_data"),
    ("insufficient: change vs a year earlier when there is no year-earlier value", dict(BCI, period="2023-02", metric="change_yoy", direction="up"), "insufficient_data"),
]
fails = 0
for name, claim, want in cases:
    r = check_claim(claim)
    ok = r["verdict"] == want and "الهيئة العامة للإحصاء" in r["source"]
    print(("ok   " if ok else "FAIL ") + name, "->", r["verdict"], "|", r["reason"][:90])
    fails += not ok
# the evidence of a verdict must be the real cells of GASTAT's files (both periods of a change)
PUB = {"consumer-price-index_1-1": "27800375", "business-confidence-index-for_2": "27714198"}
for claim in (dict(YOY, claimed=1.7), dict(BCI, metric="change_prev", direction="down")):
    r = check_claim(claim)
    wb = openpyxl.load_workbook(ROOT / "cache" / "files" / PUB[r["dataset_id"]] / "source.xlsx", data_only=True)
    for e in r["evidence"]:
        sheet, rc = e["cell"].rsplit("!", 1)
        row, col = map(int, re.fullmatch(r"R(\d+)C(\d+)", rc).groups())
        v = float(wb[sheet].cell(row=row, column=col).value)
        good = abs(v - e["value"]) <= 1e-6 * abs(v)     # web files keep 7 significant digits
        print(("ok   " if good else "FAIL ") + "evidence", e["period"], e["cell"], "equals the Excel cell" if good else f"differs: {v} vs {e['value']}")
        fails += not good
print("failures:", fails)
sys.exit(1 if fails else 0)
