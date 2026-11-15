"""Golden test sheets: side-by-side comparison of original Excel rows and decomposed tidy rows for 5 complex tables."""
import pickle, json, pathlib, warnings, openpyxl
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
R = pickle.load(open(ROOT / "cache/phase2_rows.pkl", "rb"))
reg = {p["publication_id"]: p for p in json.load(open(ROOT / "registry/publications.json"))["publications"]}
GOLD = [(27800375, "1.1 ", 0, "CPI summary: weights, index numbers and rates of change in one table"),
        (27489192, "4", 0, "ICT distribution crossing nationality x gender (9 value columns)"),
        (27489085, "التقديرات السريعة Q3_2026", 0, "GDP flash estimate: year/quarter header, three activity rows plus totals"),
        (27743334, "1", 0, "Industrial production: weight, index and rates with dates in headers"),
        (27548335, "1-1", 0, "Road transport: region > governorate > border crossing, year x arrivals/departures")]
L = ["# Golden tests: original Excel versus decomposed data", "", "Each section shows the original cells (rows and columns as they appear in the file) followed by sampled decomposed values with the exact source cell.", ""]
def cell(v):
    return "" if v is None else str(v).replace("\n", " ").replace("|", "/")[:26]
for pid, sheet, blk, why in GOLD:
    wb = openpyxl.load_workbook(ROOT / f"cache/files/{pid}/source.xlsx", data_only=True); ws = wb[sheet]
    rows = [r for r in R[pid] if r["sheet"] == sheet and r["block"] == blk]
    srows = sorted({r["source_row"] for r in rows}); hdr0 = max(1, srows[0] - 6)
    L += [f"## {reg[pid]['title_en']}, sheet `{sheet}`", "", f"*{why}.* Table status: {rows[0]['table_status']}. Fingerprint `{rows[0]['fingerprint']}`.", "", "**Original (excerpt)**", ""]
    cols = min(ws.max_column, 9)
    L.append("| row | " + " | ".join(f"c{c}" for c in range(1, cols + 1)) + " |"); L.append("|" + "---|" * (cols + 1))
    for rr in list(range(hdr0, srows[0] + 3)) + ([srows[len(srows) // 2]] if len(srows) > 6 else []) + [srows[-1]]:
        L.append(f"| {rr} | " + " | ".join(cell(ws.cell(row=rr, column=c).value) for c in range(1, cols + 1)) + " |")
    picks, seen = [], set()
    scs = sorted({r["source_col"] for r in rows})
    for rr in (srows[0], srows[len(srows) // 2], srows[-1]):
        for cc in (scs[0], scs[len(scs) // 2], scs[-1]):
            m = [r for r in rows if r["source_row"] == rr and r["source_col"] == cc]
            if m and (rr, cc) not in seen: picks.append(m[0]); seen.add((rr, cc))
    L += ["", "**Decomposed (sample of values)**", "", "| source cell | row (ar) | column | period | measure type | unit | value |", "|---|---|---|---|---|---|---|"]
    for r in picks:
        colname = " / ".join(x for x in (r["col_label_ar"], r["col_label_en"]) if x) or "-"
        L.append(f"| {r['sheet']}!R{r['source_row']}C{r['source_col']} | {r['row_label_ar'] or r['row_label_en']} | {colname[:50]} | {r['period']} | {r['measure_type']} | {r['unit'] or '-'} | {r['value']:.6g} |")
    L.append("")
(ROOT / "docs/golden_tests.md").write_text("\n".join(L) + "\n"); print("\n".join(L[:60]))
