#!/usr/bin/env python3
"""USourceData.txt が挙げている UTC 文書 (L2/…) の題名・著者・PDF の URL を
cache/l2docs.json に残す。

    python3 scripts/fetch_l2docs.py [--category S|all]

Unicode のサイトには年ごとの文書登録簿 (Register-<年>.html) があり、文書番号・題名・
著者・日付・PDF のファイル名が表になっている。PDF のファイル名は文書番号から
機械的には決まらない (末尾に内容を表す語が付く) ので、この登録簿を引く。
"""
import argparse
import html
import json
import re
import urllib.request

from common import CACHE, UA, log, targets, unihan, usource

REGISTER = "https://www.unicode.org/L2/L20{yy}/Register-20{yy}.html"
ROW = re.compile(
    r'<tr>\s*<td[^>]*>\s*<a href="([^"]+)"[^>]*>\s*(L2/\d\d-\d+)\s*</a>\s*</td>\s*'
    r"<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>",
    re.S | re.I)


def text(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def register(yy: str) -> dict[str, dict]:
    url = REGISTER.format(yy=yy)
    log(f"  取得 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    out = {}
    for href, num, title, author, date in ROW.findall(body):
        out[num] = {"url": f"https://www.unicode.org/L2/L20{yy}/{href}",
                    "title": text(title), "author": text(author),
                    "date": text(date)}
    return out


def wanted(category: str) -> set[str]:
    uni = unihan()
    us = usource()
    docs = set()
    for cp in targets(uni, category):
        sid = uni[cp].get("kIRG_USource")
        if not sid:
            continue
        for part in (us.get(sid, {}).get("sources") or "").split(";"):
            m = re.match(r"\s*UTCDoc\s+(L2/\d\d-\d+)", part)
            if m:
                docs.add(m[1])
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S")
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    path = CACHE / "l2docs.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    need = wanted(args.category) - set(known)
    for yy in sorted({d[3:5] for d in need}):
        known.update({k: v for k, v in register(yy).items()
                      if k in need or k in known})
    path.write_text(json.dumps(known, indent=0, ensure_ascii=False,
                               sort_keys=True), encoding="utf-8")
    missing = wanted(args.category) - set(known)
    log(f"UTC 文書 {len(known)} 件" + (f" / 引けなかったもの {sorted(missing)}"
                                       if missing else ""))


if __name__ == "__main__":
    main()
