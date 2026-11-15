"""Build registry/publications.json from the raw API dumps (metadata only)."""
import json, re, sys, datetime as dt, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://www.stats.gov.sa"
DOMAINS = {119021: ("economic", "الإحصاءات الاقتصادية", "Economic Statistics"),
           119025: ("social", "الإحصاءات الاجتماعية", "Social Statistics"),
           124295: ("environment_spatial", "الإحصاءات البيئية والمكانية", "Environmental and Spatial Statistics")}
FREQ = {121424: "monthly", 120046: "quarterly", 120156: "annual", 1421253: "every_5_years", 1421256: "semiannual",
        1421259: "periodic", 2241604: "biennial", 511472: "every_3_years"}
MONTHS = {"يناير":1,"فبراير":2,"مارس":3,"أبريل":4,"ابريل":4,"مايو":5,"يونيو":6,"يوليو":7,"أغسطس":8,"اغسطس":8,
          "سبتمبر":9,"أكتوبر":10,"اكتوبر":10,"نوفمبر":11,"ديسمبر":12}
QUARTERS = {"الأول":1,"الاول":1,"الثاني":2,"الثالث":3,"الرابع":4}
def ref_period(title):
    t = title
    m = re.search(r"الربع\s+(\S+)\s+(?:من\s+)?(?:عام\s+)?(20\d\d)", t)
    if m and m.group(1) in QUARTERS: return f"{m.group(2)}-Q{QUARTERS[m.group(1)]}", "quarter"
    m = re.search(r"Q([1-4])\s*/\s*(20\d\d)", t)
    if m: return f"{m.group(2)}-Q{m.group(1)}", "quarter"
    for name, n in MONTHS.items():
        m = re.search(name + r"\s+(20\d\d)", t)
        if m: return f"{m.group(1)}-{n:02d}", "month"
    m = re.search(r"(20\d\d)", t)
    if m: return m.group(1), "year"
    return None, None
def field(it, ref):
    return [f for f in it["contentFields"] if f["fieldReference"] == ref]
def main():
    ar = json.load(open(ROOT / "cache/raw/all_ar.json"))
    en = {i["id"]: i for i in json.load(open(ROOT / "cache/raw/all_en.json"))}
    out = []
    for it in ar:
        raw = field(it, "releaseDate")[0]["contentFieldValue"]["data"]
        rel = (dt.datetime.fromisoformat(raw.replace("Z", "+00:00")) + dt.timedelta(hours=3)).date().isoformat()
        cats = it["taxonomyCategoryBriefs"]
        ids = {c["taxonomyCategoryId"]: c["taxonomyCategoryName"] for c in cats}
        dom = next((DOMAINS[i] for i in ids if i in DOMAINS), (None, None, None))
        freq = next((FREQ[i] for i in ids if i in FREQ), None)
        subs = sorted({n.strip() for i, n in ids.items() if i not in DOMAINS and i not in FREQ and i != 436312
                       and not re.fullmatch(r"20\d\d", n) and n not in MONTHS and not n.startswith("إدارة") and n != "النشرات"
                       and not any(n == v[1] for v in DOMAINS.values())})
        files = []
        for f in field(it, "publicationFiles"):
            d = f["contentFieldValue"].get("document")
            if not d: continue
            files.append({"type": d["fileExtension"], "name": d["title"], "size_bytes": d["sizeInBytes"],
                          "url": BASE + d["contentUrl"].split("?")[0], "sha256": None})
        rp, rpt = ref_period(it["title"])
        e = en.get(it["id"], {})
        out.append({"publication_id": it["id"], "slug": it["friendlyUrlPath"], "title_ar": it["title"], "title_en": e.get("title"),
                    "domain_id": dom[0], "domain_ar": dom[1], "domain_en": dom[2], "subjects_ar": subs, "frequency": freq,
                    "release_date": rel, "published_at_utc": it["datePublished"], "reference_period": rp, "period_type": rpt,
                    "files": files})
    out.sort(key=lambda x: (x["release_date"], x["publication_id"]), reverse=True)
    json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "count": len(out), "publications": out},
              open(ROOT / "registry/publications.json", "w"), ensure_ascii=False, indent=1)
    print(len(out), "publications;", sum(len(p["files"]) for p in out), "files;",
          sum(1 for p in out for f in p["files"] if f["type"] == "xlsx"), "xlsx")
    print("no period:", [p["title_ar"] for p in out if not p["reference_period"]])
    print("no freq:", sum(1 for p in out if not p["frequency"]), "no domain:", sum(1 for p in out if not p["domain_id"]))
main()
