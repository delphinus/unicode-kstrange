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
# まだ符号化されていない登録にも GlyphWiki は字形を持っている。コードポイントが
# 無いので u<16 進> では引けないが、U-source 識別子を小文字にした名前 (utc-00086)
# で登録されている。UAX #45 の字形表 (USourceGlyphs.pdf) はフォントの取り出しが
# 禁じられているので、こちらが唯一の出どころ。
USRC_URL = "https://glyphwiki.org/glyph/{sid}.svg"
ENCODED = {"URO", "Comp"} | {f"Ext{x}" for x in "ABCDEFGHIJ"}


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

    def grab(url, dest, label, quiet=False):
        """1 枚取る。取れたら True。無い字は 404 が返る (中身は PNG の案内画像)。"""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            if not quiet:
                log(f"  {label} 取得できず ({e.code})")
            return False
        if not body.lstrip().startswith(b"<svg"):
            if not quiet:
                log(f"  {label} SVG ではない応答")
            return False
        dest.write_bytes(body)
        time.sleep(args.sleep)
        return True

    got = skipped = 0
    failed = []
    for cp in cps:
        h = cp[2:].lower()
        dest = GLYPHS / f"u{h}.svg"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        if grab(URL.format(hex=h), dest, cp):
            got += 1
        else:
            failed.append(cp)
    log(f"取得 {got} / 既存 {skipped} / 失敗 {len(failed)}")

    # まだ符号化されていない登録。GlyphWiki に無いものもあるので、取れなくても
    # 落とさない (構成式を出す元の形に戻るだけ)。
    # 一覧に出す対象と同じ条件で引く (build_html の select と揃える)
    ids = [s for s, v in usource().items() if v["status"] not in ENCODED]
    ug = us = un = 0
    for sid in ids:
        dest = GLYPHS / f"{sid.lower()}.svg"
        if dest.exists() and not args.force:
            us += 1
            continue
        if grab(USRC_URL.format(sid=sid.lower()), dest, sid, quiet=True):
            ug += 1
        else:
            un += 1
    log(f"まだ符号化されていない登録: 取得 {ug} / 既存 {us} / GlyphWiki に無い {un}")
    # 表に出す字が欠けるのは困るが、文中に出てくるだけの字は素のテキストで出せば
    # 済む (GlyphWiki に無い新しい字がある)。落とすのは前者のときだけ。
    if set(failed) - set(extra):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
