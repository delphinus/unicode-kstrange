#!/usr/bin/env python3
"""生成した HTML の中のリンクを全部叩いて、開けないものを一覧にする。

    python3 scripts/check_links.py [docs/index.html]

Amazon の検索 URL や GitHub は連続アクセスで 503 / 429 を返すことがある。
その場合はリンク先が失われたのではなく、こちらが弾かれているだけ。
"""
import re
import sys
import time
import urllib.error
import urllib.request

from common import DOCS, log

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def status(url):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"接続できず ({type(e).__name__})"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DOCS / "index.html"
    doc = open(path, encoding="utf-8").read()
    urls = sorted({u for u in re.findall(r'href="(https?://[^"]+)"', doc)})
    log(f"{len(urls)} 本のリンクを確認する")
    bad = []
    for u in urls:
        s = status(u)
        if s != 200:
            bad.append((s, u))
            log(f"  {s}  {u}")
        time.sleep(0.2)
    log(f"200 以外: {len(bad)} / {len(urls)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
