"""Phase 2 runner: detect, extract and validate every data sheet of the selected publications."""
import json, re, sys, pathlib, warnings, csv, collections, datetime as dt, yaml, openpyxl
from .grid import Grid, norm
from .detect import segment, describe_block, fingerprint
from .extract import extract_block
from .validate import validate_table
warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parent.parent
NAV = re.compile(r"^(index|المحتو|الفهرس|القائمه الرئيسيه|contents?|home|مقدمه|الصفحه الرئيسيه|ملاحظات|notes)", re.I)


def load_recipe(fp):
    p = ROOT / "recipes" / f"{fp}.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "sheet"


def family(pub):
    s = re.sub(r"-(january|february|march|april|may|june|july|august|september|october|november|december|20\d\d|q[1-4]|flash|estimate)", "", pub["slug"])
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def write_draft_recipe(fp, pub, sheet, d, rows, meta, status):
    """Auto-draft recipe. status stays 'draft' until a human confirms it; notes record answers given by the user."""
    mts = sorted({r["measure_type"] for r in rows})
    ci = list(meta["col_info"].values())
    rec = {"fingerprint": fp, "status": "draft", "first_seen": {"publication_id": pub["publication_id"], "sheet": sheet, "release_date": pub["release_date"]},
           "label_roles": [x["role"] for x in d["label_cols"]], "header_level_types": [x["type"] for x in d["header_rows"]],
           "value_columns": len(d["val_cols"]), "measure_types": mts, "units": sorted({c["unit"] or "" for c in ci}),
           "scales": sorted({c["scale"] for c in ci}), "period_sources": sorted({c["period_source"] for c in ci}),
           "title_sample": meta["title"][:120], "validation_on_first_run": status, "notes": []}
    (ROOT / "recipes").mkdir(exist_ok=True)
    (ROOT / "recipes" / f"{fp}.yaml").write_text(yaml.safe_dump(rec, allow_unicode=True, sort_keys=False))


def process(pub, xlsx, strict=False):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    tables, all_rows = [], []
    for ws in wb.worksheets:
        g = Grid(ws)
        sheet_id = f"{family(pub)}_{slug(ws.title)}"
        infos, c0, blocks = segment(g)
        nnum = sum(len(i["nums"]) for i in infos)
        if c0 is None or not blocks or nnum < 2 or (NAV.match(norm(ws.title)) and nnum < 40):
            tables.append(dict(pub=pub["publication_id"], sheet=ws.title, dataset_id=sheet_id, status="skipped_navigation", checks=[], rows=0))
            continue
        for bi, b in enumerate(blocks):
            d = describe_block(g, infos, c0, b)
            fp, _ = fingerprint(g, infos, c0, b, d)
            recipe = load_recipe(fp)
            rows, meta = extract_block(g, infos, c0, b, d, pub, ws.title, bi, recipe)
            if strict and (recipe is None or recipe.get("status") == "pending_review"):
                # never-seen layout: quarantine (Phase 0 decision a). A pending recipe is saved for the next Claude Code session.
                if recipe is None:
                    st0, _ = validate_table(rows)
                    write_draft_recipe(fp, pub, ws.title, d, rows, meta, st0)
                    p_ = ROOT / "recipes" / f"{fp}.yaml"; r_ = yaml.safe_load(p_.read_text()); r_["status"] = "pending_review"
                    p_.write_text(yaml.safe_dump(r_, allow_unicode=True, sort_keys=False))
                tables.append(dict(pub=pub["publication_id"], sheet=ws.title, block=bi, dataset_id=sheet_id, fingerprint=fp,
                                   status="quarantined_new_layout", checks=[], rows=len(rows), title=meta["title"], measure_types=[], recipe="pending_review"))
                continue
            if rows and all(not (r["row_label_ar"] or r["row_label_en"] or r["row_code"] or r["row_level"]) and r["period_source"] != "row" for r in rows) and len(rows) <= 12:
                tables.append(dict(pub=pub["publication_id"], sheet=ws.title, block=bi, dataset_id=sheet_id, fingerprint=fp, status="skipped_decoration",
                                   checks=[], rows=len(rows), title=meta["title"], measure_types=[], recipe="auto-draft"))
                continue
            status, checks = validate_table(rows, (recipe or {}).get('skip_checks', ()))
            if recipe and recipe.get("status") == "reviewed" and recipe.get("accept_review") and status == "review":
                status = "pass"
            if recipe is None:
                write_draft_recipe(fp, pub, ws.title, d, rows, meta, status)
            tables.append(dict(pub=pub["publication_id"], sheet=ws.title, block=bi, dataset_id=sheet_id, fingerprint=fp,
                               status=status, checks=checks, rows=len(rows), title=meta["title"],
                               measure_types=sorted({r["measure_type"] for r in rows}),
                               recipe="reviewed" if recipe else "auto-draft"))
            for r in rows:
                r.update(dataset_id=sheet_id, fingerprint=fp, table_status=status)
            all_rows += rows
    return tables, all_rows


def main(month):
    reg = json.load(open(ROOT / "registry/publications.json"))["publications"]
    out_tables, out_rows = [], collections.defaultdict(list)
    for pub in reg:
        if not pub["release_date"].startswith(month):
            continue
        t, rows = process(pub, ROOT / f"cache/files/{pub['publication_id']}/source.xlsx")
        out_tables += t
        for r in rows:
            r.update(publication_id=pub["publication_id"], release_date=pub["release_date"], domain=pub["domain_id"])
            out_rows[pub["publication_id"]].append(r)
        c = collections.Counter(x["status"] for x in t)
        print(pub["publication_id"], pub["title_en"][:48], dict(c), sum(len(v) for v in [rows]), "rows")
    json.dump(out_tables, open(ROOT / "cache/phase2_tables.json", "w"), ensure_ascii=False, indent=1)
    import pickle; pickle.dump(dict(out_rows), open(ROOT / "cache/phase2_rows.pkl", "wb"))
if __name__ == "__main__":
    main(sys.argv[1])
