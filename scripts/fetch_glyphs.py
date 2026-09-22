#!/usr/bin/env python3
"""対象の字の字形 SVG を GlyphWiki から docs/glyphs/ へ取得する。

GlyphWiki のグリフデータは「あらゆる改変の有無に関わらず、また商業的な利用であっても、
自由に利用、複製、再配布することができます」(GlyphWiki:データ・記事のライセンス) なので、
このリポジトリに同梱して配布できる。

    python3 scripts/fetch_glyphs.py [--category S|all] [--force]
"""
import argparse
import json
import time
import urllib.error
import urllib.request

from common import (CACHE, DATA, GLYPHS, UA, log, mentioned, spoofing_pairs,
                    targets, toml, unihan, usource)

URL = "https://glyphwiki.org/glyph/u{hex}.svg"


def texts_in_page():
    """生成物の本文に出てくる文字列。ここから字形が要る字を拾う。"""
    out = []
    p = CACHE / "zi_tools.json"
    if p.exists():
        for rows in json.loads(p.read_text(encoding="utf-8")).values():
            out += [r.get("def") for r in rows] + [r.get("note") for r in rows]
    p = CACHE / "uk_source.json"
    if p.exists():
        for r in json.loads(p.read_text(encoding="utf-8")).values():
            out += r.get("evidence", []) + [r.get("note")]
    if (DATA / "zi_tools_ja.toml").exists():
        out += list(toml("zi_tools_ja.toml")["ja"].values())
    for n in toml("notes.toml").values():
        out.append(n.get("text"))
        out += [e.get("text", "") for e in n.get("evidence", [])]
    # まだ符号化されていない字は IDS (構成式) しか見せるものが無いので、
    # そこに出てくる部品と ⿰⿱⿳ の記号も要る
    out += [v["ids"] for v in usource().values() if v.get("ids")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S", help="kStrange のカテゴリ (既定 S、all で全部)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3, help="1 件ごとの待ち (秒)")
    args = ap.parse_args()

    GLYPHS.mkdir(parents=True, exist_ok=True)
    cps = targets(unihan(), args.category)
    log(f"カテゴリ {args.category}: {len(cps)} 字")
    # 見間違えやすい字の一覧は本体と相手を並べて見比べるページ。片方だけ
    # フォント任せだと太さが揃わず比べられないので、基本ブロックの字も用意する。
    uni = unihan()
    pairs = spoofing_pairs(uni)
    want = set(mentioned(texts_in_page()))
    want |= set(pairs) | {t for ts in pairs.values() for t in ts}
    extra = [c for c in sorted(want, key=lambda x: int(x[2:], 16))
             if c not in set(cps)]
    if extra:
        log(f"本文中に出てくる字 (表の対象外): {len(extra)} 字")
        cps = cps + extra

    got = skipped = 0
    failed = []
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
            failed.append(cp)
            continue
        if not body.lstrip().startswith(b"<svg"):
            log(f"  {cp} SVG ではない応答")
            failed.append(cp)
            continue
        dest.write_bytes(body)
        got += 1
        time.sleep(args.sleep)
    log(f"取得 {got} / 既存 {skipped} / 失敗 {len(failed)}")
    # 表に出す字が欠けるのは困るが、文中に出てくるだけの字は素のテキストで出せば
    # 済む (GlyphWiki に無い新しい字がある)。落とすのは前者のときだけ。
    if set(failed) - set(extra):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
