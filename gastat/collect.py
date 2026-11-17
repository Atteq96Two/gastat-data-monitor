"""Scheduled collector: detect new GASTAT publications, download, fingerprint, validate, store, alert.

Modes
  poll      detect and ingest new publications (gated by the release calendar, see should_run)
  calendar  refresh registry/calendar.json
  health    check the endpoints, the calendar and the freshness of the collector

Idempotent: re-running changes nothing unless GASTAT published something new or revised a file.
"""
import argparse, datetime as dt, hashlib, json, os, pathlib, sys, time, traceback, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
import fetch_list, build_register                      # noqa: E402  (src/)
from gastat.run import process                          # noqa: E402
from gastat.store import merge_dataset, append_revisions  # noqa: E402
from gastat import alert, insights, verify, webdata      # noqa: E402

UA = "gastat-data-monitor/0.1"
RIYADH = dt.timezone(dt.timedelta(hours=3))
CAL_URL = ("https://www.stats.gov.sa/o/headless-delivery/v1.0/content-structures/403669/structured-contents"
           "?fields=contentFields,id,friendlyUrlPath,title&pageSize=100&page=1&sort=contentFields/releaseDate:asc"
           "&restrictFields=actions,keywords&filter=contentFields/releaseDate%20ge%20{since}")
GO_LIVE_FROM = "2026-11-01"       # pilot scope: publications released from this date are ingested; older ones stay metadata-only until backfill is approved
REG = ROOT / "registry" / "publications.json"
CAL = ROOT / "registry" / "calendar.json"


def now_riyadh():
    return dt.datetime.now(dt.timezone.utc).astimezone(RIYADH)


def http_get(url, binary=False, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r:
                data = r.read()
            time.sleep(1)  # polite rate limit
            return data if binary else json.loads(data)
        except Exception as e:  # noqa: BLE001
            last = e; time.sleep(2 ** (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url[:120]} ({last})")


def load_json(p, default):
    return json.load(open(p, encoding="utf-8")) if p.exists() else default


def save_json(p, obj):
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- calendar
def refresh_calendar():
    since = (now_riyadh().date() - dt.timedelta(days=14)).isoformat()
    d = http_get(CAL_URL.format(since=since))
    entries = []
    for it in d["items"]:
        g = {f["fieldReference"]: f["contentFieldValue"] for f in it["contentFields"]}
        raw = g["releaseDate"]["data"]
        date = (dt.datetime.fromisoformat(raw.replace("Z", "+00:00")) + dt.timedelta(hours=3)).date().isoformat()
        entries.append({"id": it["id"], "title_ar": it["title"], "release_date": date})
    entries.sort(key=lambda e: (e["release_date"], e["id"]))
    old = load_json(CAL, {}).get("entries")
    if old == entries:
        return len(entries)
    save_json(CAL, {"source": "statistical-calendar-releases", "refreshed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "count": len(entries), "entries": entries})
    return len(entries)


def release_days():
    return {e["release_date"] for e in load_json(CAL, {"entries": []})["entries"] if "release_date" in e}


def should_run(force=False, now=None):
    """Release days: every 15 min from 08:45 to 12:00 Riyadh. Other days: hourly (first slot of each hour). Cron runs in UTC."""
    if force:
        return True, "forced"
    now = now or now_riyadh()
    minutes = now.hour * 60 + now.minute
    if now.date().isoformat() in release_days():
        if 8 * 60 + 45 <= minutes <= 12 * 60:
            return True, "release-day window"
        return (now.minute < 15), "release day, outside window: hourly slot"
    return (now.minute < 15), "regular day: hourly slot"


# ---------------------------------------------------------------- polling
def fetch_recent(days=45):
    start = now_riyadh().date() - dt.timedelta(days=days)
    items = {"ar-SA": {}, "en-US": {}}
    end_next = (now_riyadh().date() + dt.timedelta(days=2))
    wins = list(fetch_list.month_windows(start.year, start.month, end_next.year, end_next.month))
    for lang in items:
        for s, e in wins:
            d = fetch_list.get(lang, s, e, 1)
            for it in d.get("items", []):
                items[lang][it["id"]] = it
            time.sleep(0.5)
    return items["ar-SA"], items["en-US"]


def poll(dry_run=False):
    run_ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    reg = load_json(REG, {"publications": []})
    orig = json.loads(json.dumps(reg["publications"]))   # snapshot to detect real changes
    pubs = {p["publication_id"]: p for p in reg["publications"]}
    ar, en = fetch_recent()
    events, new_ids = [], []
    for pid, it in ar.items():
        rec = build_register.make_record(it, en.get(pid, {}))
        if pid not in pubs:
            rec["status"] = "new"; pubs[pid] = rec; new_ids.append(pid)
        else:
            old = pubs[pid]
            # a revised or replaced file shows up as a different URL or size
            ofiles = {f["type"]: f for f in old["files"]}
            for f in rec["files"]:
                o = ofiles.get(f["type"])
                if not o:
                    continue
                if o.get("version") is None:
                    o["version"] = f["version"]          # adopt the current version token silently (records created before it was tracked)
                elif o["url"] != f["url"] or o["version"] != f["version"]:
                    if old.get("status", "").startswith("processed"):
                        old["status"] = "revised_file"; new_ids.append(pid)
                        for k2 in ("url", "version", "name"): o[k2] = f[k2]
            for k in ("title_ar", "title_en"): old[k] = rec[k] or old.get(k)
    todo = [pid for pid in set(new_ids) | {p for p, v in pubs.items() if v.get("status") in ("failed", "new")}
            if pubs[pid]["release_date"] >= GO_LIVE_FROM]
    for pid in sorted(todo):
        p = pubs[pid]
        xl = next((f for f in p["files"] if f["type"] == "xlsx"), None)
        if not xl:
            p["status"] = "no_excel"; events.append(("info", f"{p['title_en']}: published without an Excel file")); continue
        try:
            if dry_run:
                print("DRY RUN would ingest", pid, p["title_en"]); continue
            data = http_get(xl["url"].replace(" ", "%20"), binary=True)
            sha = hashlib.sha256(data).hexdigest()
            if p.get("status") == "revised_file" and xl.get("sha256") == sha:
                p["status"] = "processed"; continue
            xl["sha256"] = sha; xl["size_bytes"] = len(data)
            tmp = ROOT / "cache" / "incoming" / str(pid); tmp.mkdir(parents=True, exist_ok=True)
            (tmp / "source.xlsx").write_bytes(data)
            tables, rows = process(p, tmp / "source.xlsx", strict=True)
            rows = [r for r in rows if r["table_status"] == "pass"]
            by = {}
            for r in rows:
                r.update(publication_id=pid, release_date=p["release_date"], domain=p["domain_id"], source_file_url=xl["url"], ingested_at=run_ts,
                         unit=r["unit"] or "", source_cell=f"{r['sheet']}!R{r['source_row']}C{r['source_col']}")
                by.setdefault((p["domain_id"], r["dataset_id"]), []).append(r)
            added = revised = 0
            for (dom, ds), rs in by.items():
                a, rv, _, revs = merge_dataset(dom, ds, rs, run_ts); added += a; revised += rv; append_revisions(revs)
            counts = {}
            for t in tables:
                counts[t["status"]] = counts.get(t["status"], 0) + 1
            bad = [t for t in tables if t["status"] in ("review", "fail", "quarantined_new_layout")]
            qdir = ROOT / "quarantine"; qdir.mkdir(exist_ok=True)
            if bad:
                save_json(qdir / f"{pid}.json", {"publication_id": pid, "title_en": p["title_en"], "release_date": p["release_date"], "tables": bad})
            elif (qdir / f"{pid}.json").exists():
                (qdir / f"{pid}.json").unlink()
            p.update(status="processed" if not bad else "processed_with_quarantine", processed_at=run_ts, tables=counts, values_added=added, values_revised=revised)
            try:   # computed insights for this release; a failure here must never block the ingest
                ir = insights.write_for_publication(p, run_ts); insights.write_latest()
                vr = verify.verify([pid])
                if vr["total_different"]:
                    events.append(("warn", f"{p['title_en']}: {vr['total_different']} stored values differ from the Excel cells"))
                webdata.main()
                events.append(("ok", f"{p['title_en']}: {ir['insight_count']} insights computed"))
            except Exception as e:  # noqa: BLE001
                events.append(("warn", f"{p['title_en']}: insights not computed ({e})")); traceback.print_exc()
            msg = f"{p['title_en']} ({p['release_date']}): {added} new values, {revised} revised, tables {counts}"
            events.append(("warn" if bad else "ok", msg))
            if bad:
                events.append(("warn", "Quarantined tables (not published): " + "; ".join(f"{t['sheet']} [{t['status']}]" for t in bad[:15])))
        except Exception as e:  # noqa: BLE001
            p["status"] = "failed"; p["last_error"] = str(e)[:300]
            events.append(("error", f"{p['title_en']}: {e}")); traceback.print_exc()
    if not dry_run:
        new_pubs = sorted(pubs.values(), key=lambda x: (x["release_date"], x["publication_id"]), reverse=True)
        if new_pubs != orig:      # write only on real change: no empty hourly commits
            reg["publications"] = new_pubs; reg["count"] = len(new_pubs); reg["generated_at"] = run_ts
            save_json(REG, reg)
            latest = [{"publication_id": p["publication_id"], "title_ar": p["title_ar"], "title_en": p["title_en"], "release_date": p["release_date"],
                       "domain": p["domain_en"], "reference_period": p["reference_period"], "status": p.get("status", "registered")}
                      for p in new_pubs[:30]]
            (ROOT / "catalog").mkdir(exist_ok=True); save_json(ROOT / "catalog" / "latest_releases.json", {"generated_at": run_ts, "releases": latest})
    for lvl, m in events:
        print(lvl.upper(), m)
    problems = [m for lvl, m in events if lvl in ("warn", "error")]
    if problems:
        alert.send("Attention needed: new release", "\n".join(f"- {m}" for m in problems) +
                   "\n\nQuarantined tables are not published. Open a Claude Code session in the gastat-data-monitor folder and say: resolve quarantine.")
    return events


# ---------------------------------------------------------------- health
def health():
    problems = []
    try:  # structure of the publications endpoint
        d = fetch_list.get("ar-SA", now_riyadh().date().replace(day=1).isoformat(), (now_riyadh().date() + dt.timedelta(days=40)).isoformat(), 1)
        it = (d.get("items") or [None])[0]
        if it is None:
            problems.append("publications endpoint returned no items for the current window")
        else:
            refs = {f["fieldReference"] for f in it["contentFields"]}
            for need in ("releaseDate", "publicationFiles"):
                if need not in refs:
                    problems.append(f"site structure changed: field '{need}' missing from publication entries")
    except Exception as e:  # noqa: BLE001
        problems.append(f"publications endpoint unreachable: {e}")
    try:
        n = refresh_calendar()
        if n == 0:
            problems.append("calendar endpoint returned no entries")
    except Exception as e:  # noqa: BLE001
        problems.append(f"calendar endpoint failed: {e}")
    # releases scheduled for a past day (after 12:30 Riyadh on that day) that never appeared in the register
    reg = {p["title_ar"].strip() for p in load_json(REG, {"publications": []})["publications"]}
    now = now_riyadh()
    for e in load_json(CAL, {"entries": []})["entries"]:
        due = dt.datetime.fromisoformat(e["release_date"]).replace(hour=12, minute=30, tzinfo=RIYADH)
        if due < now - dt.timedelta(hours=2) and now - due < dt.timedelta(days=4) and e["title_ar"].strip() not in reg and not _fuzzy_in(e["title_ar"], reg):
            problems.append(f"scheduled release not seen yet: {e['title_ar']} ({e['release_date']})")
    # collector freshness (last successful poll run) via the GitHub API, when available
    repo, tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if repo and tok:
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/collect.yml/runs?status=success&per_page=1",
                                         headers={"Authorization": f"Bearer {tok}", "User-Agent": UA})
            runs = json.load(urllib.request.urlopen(req, timeout=30))["workflow_runs"]
            if not runs:
                problems.append("collector has no successful run yet")
            else:
                age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(runs[0]["updated_at"].replace("Z", "+00:00"))
                if age > dt.timedelta(hours=6):
                    problems.append(f"collector last succeeded {age.total_seconds()/3600:.1f} hours ago")
        except Exception as e:  # noqa: BLE001
            problems.append(f"could not read collector run history: {e}")
    if problems:
        alert.send("Health check failed", "\n".join(f"- {p}" for p in problems) + "\n\nSee docs/RUNBOOK.md.")
        print("HEALTH PROBLEMS:", *problems, sep="\n- ")
        return 1
    print("health ok")
    return 0


_STOP = {"لعام", "لشهر", "شهر", "للربع", "ربع", "الربع", "عام", "لسنه", "في", "من", "و"}


def _tokens(t):
    from gastat.grid import norm
    return {w for w in norm(t).replace("/", " ").split() if w not in _STOP}


def _fuzzy_in(title, reg_titles):
    """A calendar title matches a publication when >= 80% of its words (years and months included) appear in the publication title."""
    want = _tokens(title)
    return bool(want) and any(len(want & _tokens(t)) >= 0.8 * len(want) for t in reg_titles)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["poll", "calendar", "health"])
    ap.add_argument("--force", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.mode == "calendar":
        print("calendar entries:", refresh_calendar()); return 0
    if a.mode == "health":
        return health()
    ok, why = should_run(a.force)
    print(f"{now_riyadh():%Y-%m-%d %H:%M} Riyadh: {'RUN' if ok else 'skip'} ({why})")
    if ok:
        poll(a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
