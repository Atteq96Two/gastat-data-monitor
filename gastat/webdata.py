"""Export everything the web page and the News Tracker need as plain JSON (no database, no server).

  catalog/catalog.json        every stored dataset with freshness, keywords, units and where to download it
  catalog/search_index.json   all distinct labels per dataset (for keyword search)
  web/data/*                  the same plus per-dataset series, the release feed, freshness board and data quality

Run after every ingest (collect.py does it) or by hand: python3 -I gastat/webdata.py
"""
import collections, datetime as dt, json, math, pathlib, re, shutil, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gastat import insights as I                      # noqa: E402
from gastat.grid import norm                          # noqa: E402
from gastat.run import family                         # noqa: E402

WEB = ROOT / "web" / "data"
RAW = "https://raw.githubusercontent.com/Atteq96Two/gastat-data-monitor/main/"
INTERVAL = {"monthly": 31, "quarterly": 92, "annual": 366, "biennial": 731}
GRACE = 10
RIYADH = dt.timezone(dt.timedelta(hours=3))
from gastat.grid import MONTHS_AR                      # noqa: E402
STOP = {"لعام", "لشهر", "في", "من", "حسب", "و", "the", "of", "for", "and", "by", "in", "الرقم", "القياسي", "احصاءات", "نشره", "الربع", "الاول", "الثاني", "الثالث", "الرابع", "لعام", "للربع"} | set(MONTHS_AR)
FREQ_AR = {"monthly": "شهري", "quarterly": "ربع سنوي", "annual": "سنوي", "biennial": "كل سنتين"}


LATIN_RUN = re.compile(r"\s*[A-Za-z][A-Za-z0-9 .,'&()%/-]*[A-Za-z0-9)]|\s*[A-Za-z]")


def ar_only(s):
    """Arabic label without the English half of a bilingual header (the English half lives in label_en)."""
    if not re.search("[\u0600-\u06FF]", s or ""):
        return s
    t = re.sub(r"\s+", " ", LATIN_RUN.sub(" ", s)).strip(" |/-")
    t = re.sub(r"(\s*\|\s*)+", " | ", t).strip(" |")
    return t or s


def jdump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(I.clean(obj), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load(p, default=None):
    p = pathlib.Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def tokens(t, keep_dates=False):
    return {w for w in norm(t).replace("/", " ").split() if (keep_dates or (w not in STOP and not w.isdigit())) and w not in {"لعام", "لشهر", "في", "من", "حسب", "و"} and len(w) > 2}


def today():
    return dt.datetime.now(dt.timezone.utc).astimezone(RIYADH).date()


# ------------------------------------------------------------------ datasets and series
def sig(v):
    return float(f"{v:.7g}")


def build_datasets(pubs):
    byid = {str(p["publication_id"]): p for p in pubs}
    cat, search = [], {}
    WEB.joinpath("series").mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "data").glob("*/*.parquet")):
        raw = pd.read_parquet(f)
        if raw.empty:
            continue
        pid = str(raw["publication_id"].iloc[0])
        pub = byid.get(pid)
        if not pub:
            continue
        df = I.prepare(raw)
        if df.empty:
            continue
        ds = f.stem
        periods = sorted(df["period"].unique(), key=lambda p: I.ordinal(p)[0])
        pidx = {p: i for i, p in enumerate(periods)}
        series = []
        for k, g in df.groupby("_key", sort=False):
            r = g.iloc[0].to_dict()
            vals = [None] * len(periods)
            for p, v in zip(g["period"], g["value"]):
                vals[pidx[p]] = sig(v)
            series.append(dict(label=ar_only(I.label(r)), label_en=I.label(r, "en"), measure=r["measure_type"], unit=r["_unit"], unit_ok=I.unit_ok(r),
                               unit_text=I.unit_text(r, "ar"), base=r["base_period"], total=bool(r["is_total_row"]), cell=r["source_cell"], values=vals))
        seen = collections.Counter(x["label"] for x in series)
        for x, (k, g) in zip(series, df.groupby("_key", sort=False)):   # same name in two places of one table (a division and a group): tell them apart
            if seen[x["label"]] > 1:
                lv = g.iloc[0]["row_level"]
                x["label"] += f" (المستوى {lv})" if lv else f" ({x['cell'].split('!')[-1]})"
                x["label_en"] += f" (level {lv})" if lv else f" ({x['cell'].split('!')[-1]})"
        title = raw["table_title"].iloc[0] or ""
        ttl_ar, ttl_en = I.short_title(title, "ar", 150), I.short_title(title, "en", 150)
        labels = []
        for s in series:
            for x in (s["label"], s["label_en"]):
                if x and x not in labels:
                    labels.append(x)
        mts = sorted({s["measure"] for s in series})
        item = dict(dataset_id=ds, publication_id=int(pid), publication_title_ar=pub["title_ar"], publication_title_en=pub["title_en"], family=family(pub),
                    domain=pub["domain_id"], domain_ar=pub["domain_ar"], frequency=pub["frequency"], frequency_ar=FREQ_AR.get(pub["frequency"], pub["frequency"]),
                    release_date=pub["release_date"], sheet=raw["sheet"].iloc[0], title_ar=ttl_ar or pub["title_ar"], title_en=ttl_en,
                    period_type=sorted(df["period_type"].unique().tolist()), first_period=periods[0], last_period=periods[-1], periods=len(periods),
                    series=len(series), values=int(len(raw)), measure_types=mts, units=sorted({s["unit_text"] for s in series if s["unit_text"]}),
                    keywords=labels[:30], parquet=f"data/{pub['domain_id']}/{ds}.parquet", parquet_url=RAW + f"data/{pub['domain_id']}/{ds}.parquet",
                    csv_url=(RAW + f"data/{pub['domain_id']}/{ds}.csv") if f.with_suffix(".csv").exists() else None)
        cat.append(item)
        search[ds] = labels[:400]
        jdump(WEB / "series" / f"{ds}.json", dict(dataset_id=ds, title_ar=item["title_ar"], periods=periods, series=series))
    return cat, search


# ------------------------------------------------------------------ freshness
def build_freshness(pubs, cal, processed_families):
    fam = collections.defaultdict(list)
    for p in pubs:
        fam[family(p)].append(p)
    t = today()
    entries = cal.get("entries", [])
    out = []
    for fk, ps in fam.items():
        ps.sort(key=lambda p: (p["release_date"], p["publication_id"]))
        last = ps[-1]
        freq = last["frequency"]
        want = tokens(last["title_ar"])
        # calendar match: ignore years and months, which change from release to release
        done = tokens(last["title_ar"], True)
        upcoming = [e for e in entries if e["release_date"] >= t.isoformat() and want and len(want & tokens(e["title_ar"])) >= 0.8 * max(1, min(len(want), len(tokens(e["title_ar"]))))
                    and len(tokens(e["title_ar"], True) & done) < 0.99 * len(tokens(e["title_ar"], True))]   # an entry that is the release already published is not "next"
        upcoming.sort(key=lambda e: e["release_date"])
        last_d = dt.date.fromisoformat(last["release_date"])
        expected = last_d + dt.timedelta(days=INTERVAL.get(freq, 31))
        nxt = upcoming[0]["release_date"] if upcoming else None
        if t > expected + dt.timedelta(days=GRACE):
            status = "overdue"            # more than a full cycle plus 10 days since the last release, even if the next one is already scheduled
        elif nxt:
            status = "scheduled"
        else:
            status = "current"
        out.append(dict(family=fk, title_ar=last["title_ar"], title_en=last["title_en"], domain_ar=last["domain_ar"], frequency=freq, frequency_ar=FREQ_AR.get(freq, freq),
                        last_release=last["release_date"], releases_seen=len(ps), days_since=(t - last_d).days, expected_next=expected.isoformat(), calendar_next=nxt,
                        status=status, has_data=fk in processed_families))
    order = {"overdue": 0, "scheduled": 1, "current": 2}
    out.sort(key=lambda x: (order[x["status"]], not x["has_data"], x["last_release"]))
    return out


# ------------------------------------------------------------------ quality
def build_quality(pubs, cat):
    import yaml
    rec = collections.Counter()
    for f in (ROOT / "recipes").glob("*.yaml"):
        rec[yaml.safe_load(f.read_text(encoding="utf-8")).get("status", "draft")] += 1
    q = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "quarantine").glob("*.json")}
    revs = [json.loads(x) for x in (ROOT / "registry" / "revisions.jsonl").read_text(encoding="utf-8").splitlines()] if (ROOT / "registry" / "revisions.jsonl").exists() else []
    ver = load(ROOT / "registry" / "verification.json", {})
    per = collections.defaultdict(lambda: dict(datasets=0, values=0))
    for d in cat:
        per[d["publication_id"]]["datasets"] += 1
        per[d["publication_id"]]["values"] += d["values"]
    pub_rows = []
    for p in sorted(pubs, key=lambda x: (x["release_date"], x["publication_id"]), reverse=True):
        if p.get("status", "").startswith("processed"):
            v = ver.get("publications", {}).get(str(p["publication_id"]), {})
            pub_rows.append(dict(publication_id=p["publication_id"], title_ar=p["title_ar"], title_en=p["title_en"], release_date=p["release_date"],
                                 datasets=per[p["publication_id"]]["datasets"], values=per[p["publication_id"]]["values"], cells_checked=v.get("checked"), cells_different=v.get("different"),
                                 quarantined=len(q.get(str(p["publication_id"]), {}).get("tables", [])), revisions=sum(1 for r in revs if r.get("new_release") == p["release_date"] and r["dataset_id"].startswith(family(p)[:20]))))
    ins = load(ROOT / "catalog" / "insights_check.json", {})
    return dict(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                registered=len(pubs), ingested=sum(1 for p in pubs if p.get("status", "").startswith("processed")),
                datasets=len(cat), values=sum(d["values"] for d in cat), recipes=dict(rec), quarantined_releases=len(q),
                cells_checked=ver.get("total_checked"), cells_different=ver.get("total_different"), verified_at=ver.get("verified_at"),
                insights_check=ins, releases=pub_rows, revisions=revs[-60:], revisions_total=len(revs),
                known_issues=load(ROOT / "registry" / "known_issues.json", []))


# ------------------------------------------------------------------ feed
def build_latest(pubs):
    rows = []
    for p in sorted(pubs, key=lambda x: (x["release_date"], x["publication_id"]), reverse=True)[:60]:
        ins = load(ROOT / "catalog" / "insights" / f"{p['publication_id']}.json")
        heads = []
        if ins and ins["insights"]:
            byid = {i["id"]: i for i in ins["insights"]}
            heads = [dict(text_ar=byid[h]["text_ar"], text_en=byid[h]["text_en"], kind=byid[h]["kind"], dataset_id=byid[h]["dataset_id"]) for h in ins["headline_ids"][:5]]
        files = {f["type"]: f["url"] for f in p["files"]}
        rows.append(dict(publication_id=p["publication_id"], title_ar=p["title_ar"], title_en=p["title_en"], release_date=p["release_date"], domain_ar=p["domain_ar"],
                         frequency_ar=FREQ_AR.get(p["frequency"], p["frequency"]), reference_period=p.get("reference_period"), has_data=p.get("status", "").startswith("processed"),
                         insight_count=ins["insight_count"] if ins else 0, headlines=heads, xlsx=files.get("xlsx"), pdf=files.get("pdf")))
    return rows


def main():
    reg = load(ROOT / "registry" / "publications.json")
    pubs = reg["publications"]
    cal = load(ROOT / "registry" / "calendar.json", {"entries": []})
    shutil.rmtree(WEB, ignore_errors=True)
    cat, search = build_datasets(pubs)
    fresh_by_ds = {}
    fam_has = {d["family"] for d in cat}
    fresh = build_freshness(pubs, cal, fam_has)
    fmap = {f["family"]: f for f in fresh}
    for d in cat:
        f = fmap.get(d["family"], {})
        d["freshness"] = dict(status=f.get("status"), last_release=f.get("last_release"), expected_next=f.get("expected_next"), calendar_next=f.get("calendar_next"))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    src = "الهيئة العامة للإحصاء / General Authority for Statistics (stats.gov.sa)"
    catalog = dict(generated_at=now, source=src, coverage="Pilot: releases from 2026-11-01. Earlier releases are registered as metadata only until the backfill is approved.",
                   datasets=cat)
    jdump(ROOT / "catalog" / "catalog.json", catalog)
    jdump(ROOT / "catalog" / "search_index.json", dict(generated_at=now, labels=search))
    jdump(WEB / "catalog.json", catalog)
    jdump(WEB / "search_index.json", dict(generated_at=now, labels=search))
    jdump(WEB / "freshness.json", dict(generated_at=now, today=today().isoformat(), items=fresh))
    jdump(WEB / "latest.json", dict(generated_at=now, source=src, releases=build_latest(pubs)))
    jdump(WEB / "quality.json", build_quality(pubs, cat))
    (WEB / "insights").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "catalog" / "insights").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for i in d["insights"]:
            i.pop("evidence_extra", None)
        jdump(WEB / "insights" / f.name, d)
    print("web data:", len(cat), "datasets,", len(fresh), "families,", sum(1 for _ in WEB.rglob("*.json")), "files,", round(sum(p.stat().st_size for p in WEB.rglob("*.json")) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
