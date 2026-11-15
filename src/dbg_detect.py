import sys, warnings, openpyxl, pathlib
warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from gastat.grid import Grid
from gastat.detect import segment, describe_block, fingerprint
ROOT = pathlib.Path(__file__).resolve().parent.parent
wb = openpyxl.load_workbook(ROOT / f"cache/files/{sys.argv[1]}/source.xlsx", data_only=True)
names = sys.argv[2:] or [w.title for w in wb.worksheets]
for n in names:
    g = Grid(wb[n]); infos, c0, blocks = segment(g)
    print(f"-- {n!r} rows={g.nrows} c0={c0} blocks={len(blocks)}")
    for b in blocks:
        d = describe_block(g, infos, c0, b); fp, _ = fingerprint(g, infos, c0, b, d)
        print("   data", b["start"]+1, b["end"]+1, "hdr", [h+1 for h in b["header"]], "labels", [(x["col"], x["role"]) for x in d["label_cols"]],
              "nval", len(d["val_cols"]), "hdrtypes", [x["type"] for x in d["header_rows"]], fp)
