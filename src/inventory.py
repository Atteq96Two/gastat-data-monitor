"""Phase 1 inventory report: register stats + per-file sheet and layout-complexity summary."""
import json, collections, pathlib, warnings, openpyxl
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
NAV = ("المحتو", "الفهرس", "contents", "content", "home", "مقدمة", "الملخص", "ملاحظات", "notes")
def classify(ws):
    name = ws.title.lower()
    first_num = None; numeric = 0
    for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 60)):
        for c in r:
            if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                numeric += 1
                if first_num is None and c.row > 1: first_num = c.row
    if numeric < 4 or any(n in name for n in NAV): return "navigation/notes", 0, 0
    # header depth: rows before first row that has >=2 numeric cells
    depth = 0
    for r in ws.iter_rows(min_row=1, max_row=40):
        if sum(isinstance(c.value, (int, float)) for c in r) >= 2: break
        depth += 1
    merged = len(ws.merged_cells.ranges)
    cls = "A simple" if depth <= 6 and merged <= 6 else ("B multi-header" if depth <= 9 and merged <= 25 else "C complex")
    return cls, depth, merged
def main():
    reg = json.load(open(ROOT / "registry/publications.json"))["publications"]
    L = ["# Phase 1 inventory report", ""]
    by_m = collections.Counter(p["release_date"][:7] for p in reg)
    L += ["## Register (metadata for all 2026 publications)", "", f"- Publications: {len(reg)}; files: {sum(len(p['files']) for p in reg)} (xlsx: {sum(1 for p in reg for f in p['files'] if f['type']=='xlsx')}, pdf: {sum(1 for p in reg for f in p['files'] if f['type']=='pdf')})",
          "- Per month: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_m.items())), ""]
    dom = collections.Counter((p["domain_en"], p["frequency"]) for p in reg)
    L += ["| Domain | Frequency | Publications |", "|---|---|---|"] + [f"| {d} | {f} | {n} |" for (d, f), n in sorted(dom.items(), key=lambda x: str(x[0]))] + [""]
    L += ["## November 2026 files (downloaded and profiled)", "", "| Release | Publication | Domain | Period | Sheets | Data sheets | A | B | C |", "|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for p in sorted([p for p in reg if p["release_date"].startswith("2026-11")], key=lambda p: p["release_date"]):
        wb = openpyxl.load_workbook(ROOT / f"cache/files/{p['publication_id']}/source.xlsx", data_only=True)
        c = collections.Counter(); 
        for ws in wb.worksheets:
            cls, depth, merged = classify(ws); c[cls] += 1
        data = sum(v for k, v in c.items() if k != "navigation/notes")
        L.append(f"| {p['release_date']} | {p['title_en']} | {p['domain_en']} | {p['reference_period']} | {len(wb.worksheets)} | {data} | {c['A simple']} | {c['B multi-header']} | {c['C complex']} |")
        detail.append((p, c))
    L += ["", "Classes: A = header up to 6 rows and few merged cells; B = multi-row merged headers; C = deep headers or heavy merging. These are rough heuristics for planning, not final recipes."]
    (ROOT / "docs").mkdir(exist_ok=True); (ROOT / "docs/inventory.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
main()
