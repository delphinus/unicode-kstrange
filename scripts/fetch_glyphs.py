#!/usr/bin/env python3
"""対象の字の字形 SVG を GlyphWiki から docs/glyphs/ へ取得する。

GlyphWiki のグリフデータは「あらゆる改変の有無に関わらず、また商業的な利用であっても、
自由に利用、複製、再配布することができます」(GlyphWiki:データ・記事のライセンス) なので、
このリポジトリに同梱して配布できる。

    python3 scripts/fetch_glyphs.py [--category S|all] [--force]
"""
import argparse
import time
import urllib.error
import urllib.request

from common import GLYPHS, UA, log, targets, unihan

URL = "https://glyphwiki.org/glyph/u{hex}.svg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S", help="kStrange のカテゴリ (既定 S、all で全部)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3, help="1 件ごとの待ち (秒)")
    args = ap.parse_args()

    GLYPHS.mkdir(parents=True, exist_ok=True)
    cps = targets(unihan(), args.category)
    log(f"カテゴリ {args.category}: {len(cps)} 字")

    got = skipped = failed = 0
    for cp in cps:
        h = cp[2:].lower()
        dest = GLYPHS / f"u{h}.svg"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        url = URL.format(hex=h)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            log(f"  {cp} 取得できず ({e.code})")
            failed += 1
            continue
        if not body.lstrip().startswith(b"<svg"):
            log(f"  {cp} SVG ではない応答")
            failed += 1
            continue
        dest.write_bytes(body)
        got += 1
        time.sleep(args.sleep)
    log(f"取得 {got} / 既存 {skipped} / 失敗 {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
