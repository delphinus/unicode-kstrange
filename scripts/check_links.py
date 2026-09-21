#!/usr/bin/env python3
"""生成した HTML の中のリンクを全部叩いて、開けないものを一覧にする。

    python3 scripts/check_links.py [docs/index.html]

ボット検証を置いているホスト (GlyphWiki, Amazon, GitHub) は、スクリプトから叩くと
403 / 429 / 503 を返す。リンク先が失われたわけではないので「確認できず」として分けて数え、
終了コードには含めない。
"""
import re
import sys
import time
import urllib.error
import urllib.request

from common import DOCS, log

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# ホスト → そのホストでボット検証として現れる状態
BOT_GATED = {
    "glyphwiki.org": {403, 503},        # Cloudflare の JS チャレンジ
    "www.amazon.co.jp": {403, 503},
    "github.com": {429},
}


def status(url, retries=1):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception as e:
            if attempt == retries:
                return f"接続できず ({type(e).__name__})"
            time.sleep(2)


def gated(url, code):
    host = re.match(r"https?://([^/]+)", url)[1]
    return isinstance(code, int) and code in BOT_GATED.get(host, set())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DOCS / "index.html"
    doc = open(path, encoding="utf-8").read()
    urls = sorted({u for u in re.findall(r'href="(https?://[^"]+)"', doc)})
    log(f"{len(urls)} 本のリンクを確認する")
    bad, skipped = [], []
    for u in urls:
        s = status(u)
        if s == 200:
            pass
        elif gated(u, s):
            skipped.append((s, u))
        else:
            bad.append((s, u))
            log(f"  {s}  {u}")
        time.sleep(0.2)
    log(f"200: {len(urls) - len(bad) - len(skipped)} / "
        f"確認できず (ボット検証): {len(skipped)} / 要確認: {len(bad)}")
    for s, u in skipped[:5]:
        log(f"  [確認できず] {s}  {u}")
    if len(skipped) > 5:
        log(f"  [確認できず] ほか {len(skipped) - 5} 本")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
