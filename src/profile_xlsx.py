"""Compact profile of xlsx files: sheets, dimensions, merged-cell counts, first non-empty rows. Never dumps whole files."""
import sys, json, pathlib, openpyxl
ROOT = pathlib.Path(__file__).resolve().parent.parent
def profile(path):
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12)):
            vals = [str(c.value).strip()[:40] for c in r if c.value is not None]
            if vals: rows.append(vals[:6])
        title = next((v for row in rows for v in row if len(v) > 12), "")
        numeric = sum(1 for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 400)) for c in r if isinstance(c.value, (int, float)))
        sheets.append({"sheet": ws.title, "rows": ws.max_row, "cols": ws.max_column, "merged": len(ws.merged_cells.ranges),
                       "numeric_cells_first400rows": numeric, "visible": ws.sheet_state, "title_guess": title, "head": rows[:5]})
    return sheets
if __name__ == "__main__":
    reg = {p["publication_id"]: p for p in json.load(open(ROOT / "registry/publications.json"))["publications"]}
    out = {}
    for d in sorted((ROOT / "cache/files").iterdir()):
        s = profile(d / "source.xlsx"); out[d.name] = s
        p = reg[int(d.name)]
        print(f"\n### {d.name} {p['title_en']} | sheets={len(s)} | total rows={sum(x['rows'] for x in s)}")
    json.dump(out, open(ROOT / "cache/profiles.json", "w"), ensure_ascii=False, indent=1)
