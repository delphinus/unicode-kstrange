#!/usr/bin/env python3
"""生成した HTML の中のリンクを全部叩いて、開けないものを一覧にする。

    python3 scripts/check_links.py [docs/index.html]

ボット検証を置いているホスト (GlyphWiki, Amazon, GitHub) は、スクリプトから叩くと
403 / 429 / 503 を返す。リンク先が失われたわけではないので「確認できず」として分けて数え、
終了コードには含めない。
"""
import argparse
import collections
import random
import re
import time
import urllib.error
import urllib.request

from common import DOCS, log

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# 公開先を Referer として送る。ホットリンクを弾くサイトがあり、Referer 無しで叩くと
# 素通りしてしまって、実際にクリックしたときだけ失敗する状態を見逃す
# (kangxizidian.com のページ画像がこれだった)。
REFERER = "https://delphinus.github.io/unicode-kstrange/"

# ホスト → そのホストでボット検証として現れる状態
BOT_GATED = {
    "glyphwiki.org": {403, 503},        # Cloudflare の JS チャレンジ
    "www.amazon.co.jp": {403, 503},
    "github.com": {429},
}


def status(url, retries=1):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA,
                                               "Referer": REFERER})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except urllib.error.URLError as e:
            # リダイレクトの輪に落ちるのもホットリンク対策でよくある形
            if "redirect" in str(e.reason).lower():
                return "リダイレクトの輪"
            if attempt == retries:
                return f"接続できず ({type(e).__name__})"
            time.sleep(2)
        except Exception as e:
            if attempt == retries:
                return f"接続できず ({type(e).__name__})"
            time.sleep(2)


def gated(url, code):
    host = re.match(r"https?://([^/]+)", url)[1]
    return isinstance(code, int) and code in BOT_GATED.get(host, set())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(DOCS / "index.html"))
    ap.add_argument("--sample", type=int, default=0,
                    help="ホストごとにこの本数だけ確認する (0 なら全部)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    doc = open(args.path, encoding="utf-8").read()
    urls = sorted({u for u in re.findall(r'href="(https?://[^"]+)"', doc)})
    total = len(urls)
    if args.sample:
        by_host = collections.defaultdict(list)
        for u in urls:
            by_host[re.match(r"https?://([^/]+)", u)[1]].append(u)
        rnd = random.Random(args.seed)
        urls = sorted(u for host, us in by_host.items()
                      for u in rnd.sample(us, min(args.sample, len(us))))
        log(f"{total} 本のうち、{len(by_host)} ホストから {len(urls)} 本を抜き出して確認する")
    else:
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
