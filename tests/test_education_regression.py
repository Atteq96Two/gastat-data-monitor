"""Regression: the engine must reproduce the user's reference tidy CSV (values and measure types) from the Education 2025 workbook.
Run: python3 tests/test_education_regression.py <path to Education and Training Statistics 2025 AR.xlsx>"""
import sys, csv, warnings, collections, pathlib, openpyxl
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from gastat.grid import Grid
from gastat.detect import segment, describe_block
from gastat.extract import extract_block
wb = openpyxl.load_workbook(sys.argv[1], data_only=True); pub = dict(reference_period="2025", period_type="year")
eng, mt = collections.defaultdict(list), collections.defaultdict(set)
for ws in wb.worksheets:
    g = Grid(ws); infos, c0, blocks = segment(g)
    if c0 is None or ws.title == "المحتويات": continue
    for bi, b in enumerate(blocks):
        rows, _ = extract_block(g, infos, c0, b, describe_block(g, infos, c0, b), pub, ws.title, bi, None)
        for r in rows: eng[ws.title].append(round(r["value"], 6)); mt[ws.title].add(r["measure_type"])
ref, rmt = collections.defaultdict(list), collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "tests/education_2025_reference.csv", encoding="utf-8-sig")):
    ref[r["sheet"]].append(round(float(r["value_pct"]), 6)); rmt[r["sheet"]].add(r["measure_type"])
bad = [s for s in ref if sorted(eng[s]) != sorted(ref[s]) or mt[s] != rmt[s]]
print("sheets:", len(ref), "mismatching:", bad); sys.exit(1 if bad else 0)
