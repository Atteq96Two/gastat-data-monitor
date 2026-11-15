"""Print a compact grid of one sheet: python3 -I src/peek.py <pub_id|path> <sheet> [rows] [cols]"""
import sys, warnings, openpyxl, pathlib
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
a = sys.argv[1]; p = pathlib.Path(a) if "/" in a else ROOT / f"cache/files/{a}/source.xlsx"
wb = openpyxl.load_workbook(p, data_only=True); 
if sys.argv[2] == "?": print([w.title for w in wb.worksheets]); sys.exit()
ws = wb[sys.argv[2]]; R = int(sys.argv[3]) if len(sys.argv) > 3 else 14; C = int(sys.argv[4]) if len(sys.argv) > 4 else 9
print("dims", ws.dimensions, "merged", [str(m) for m in list(ws.merged_cells.ranges)[:8]])
for r in ws.iter_rows(min_row=1, max_row=R, max_col=C):
    v = [("" if c.value is None else str(c.value).replace("\n", " ")[:22]) for c in r]
    if any(v): print(r[0].row, "|".join(v))
