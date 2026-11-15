"""Download xlsx files of selected publications to cache/files/<pub_id>/ and record sha256 in the register."""
import json, sys, hashlib, time, pathlib, urllib.request, urllib.parse
ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "gastat-data-monitor/0.1"
def main(month):
    reg = json.load(open(ROOT / "registry/publications.json"))
    for p in reg["publications"]:
        if not p["release_date"].startswith(month): continue
        for f in p["files"]:
            if f["type"] != "xlsx": continue
            d = ROOT / "cache/files" / str(p["publication_id"]); d.mkdir(parents=True, exist_ok=True)
            dest = d / "source.xlsx"
            url = f["url"].replace(" ", "%20")
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
            dest.write_bytes(data)
            f["sha256"] = hashlib.sha256(data).hexdigest(); f["size_bytes"] = len(data)
            print(p["publication_id"], len(data), f["sha256"][:12], f["name"]); time.sleep(1)
    json.dump(reg, open(ROOT / "registry/publications.json", "w"), ensure_ascii=False, indent=1)
main(sys.argv[1])
