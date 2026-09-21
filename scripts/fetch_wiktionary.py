#!/usr/bin/env python3
"""対象の字に英語版 Wiktionary の項目があるかを調べ、cache/wiktionary.json に残す。

項目の無い字にリンクを張ると 404 になるので、build_html.py はこの結果を見て
ある字にだけリンクを付ける。

    python3 scripts/fetch_wiktionary.py [--category S|all]
"""
import argparse
import json
import urllib.parse
import urllib.request

from common import CACHE, UA, log, targets, unihan

API = "https://en.wiktionary.org/w/api.php"
BATCH = 50          # titles= に一度に渡せる上限


def exists(chars):
    found = set()
    for i in range(0, len(chars), BATCH):
        chunk = chars[i:i + BATCH]
        q = urllib.parse.urlencode({"action": "query", "format": "json",
                                    "titles": "|".join(chunk)})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        for pid, page in d["query"]["pages"].items():
            if int(pid) > 0:
                found.add(page["title"])
        log(f"  {min(i + BATCH, len(chars))} / {len(chars)}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S")
    args = ap.parse_args()

    cps = targets(unihan(), args.category)
    chars = [chr(int(cp[2:], 16)) for cp in cps]
    found = exists(chars)

    CACHE.mkdir(exist_ok=True)
    path = CACHE / "wiktionary.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    known.update({cp: (ch in found) for cp, ch in zip(cps, chars)})
    path.write_text(json.dumps(known, indent=0, sort_keys=True))
    n = sum(1 for cp in cps if known[cp])
    log(f"項目あり {n} / {len(cps)} 字")


if __name__ == "__main__":
    main()
