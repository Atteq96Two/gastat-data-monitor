"""Fetch the full GASTAT publication list (AR + EN) from the Liferay headless API, month by month.
The API returns at most 100 results per query, so we window by release date."""
import json, sys, time, urllib.request, urllib.parse, pathlib
UA = "gastat-data-monitor/0.1"
BASE = "https://www.stats.gov.sa/o/headless-delivery/v1.0/content-structures/118514/structured-contents"
def get(lang, start, end, page):
    flt = f"contentFields/releaseDate ge {start} and contentFields/releaseDate lt {end}"
    q = urllib.parse.urlencode({"pageSize": 100, "page": page, "sort": "contentFields/releaseDate:desc",
                                "filter": flt, "restrictFields": "actions,keywords"}, quote_via=urllib.parse.quote)
    req = urllib.request.Request(f"{BASE}?{q}", headers={"User-Agent": UA, "Accept-Language": lang})
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:
            time.sleep(2 ** i)
    raise RuntimeError("failed")
def month_windows(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y}-{m:02d}-01", f"{ny}-{nm:02d}-01"
        y, m = ny, nm
if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for lang, tag in (("ar-SA", "ar"), ("en-US", "en")):
        items = {}
        for s, e in month_windows(2026, 1, 2026, 12):
            d = get(lang, s, e, 1)
            n = d.get("totalCount", 0)
            assert n <= 100, f"window {s} has {n}"
            for it in d["items"]: items[it["id"]] = it
            time.sleep(0.5)
        json.dump(list(items.values()), open(out / f"all_{tag}.json", "w"), ensure_ascii=False)
        print(tag, len(items))
