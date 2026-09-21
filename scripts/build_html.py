#!/usr/bin/env python3
"""kStrange の字の出典一覧 (docs/index.html) を組み立てる。

    python3 scripts/build_html.py [--category S|all] [--out docs/index.html]
"""
import argparse
import datetime
import html
import json
import pathlib
import re

from common import (CACHE, DATA, DOCS, GLYPHS, UNICODE_VERSION, UTN43_REVISION,
                    blocks, log, manifest, needs_glyph, targets, toml, unihan,
                    usource)

# 康熙字典網上版。ページ画像 (/kangxi/<4 桁>.gif) は Referer でホットリンクを弾かれ、
# 外部から辿ると mainlogos.jpg に飛ばされるので、サイト側の字頭検索へリンクする。
KX = "https://kangxizidian.com/kxhans/{enc}"
MJ = ("https://moji.or.jp/mojikibansearch/info?"
      "MJ%E6%96%87%E5%AD%97%E5%9B%B3%E5%BD%A2%E5%90%8D={mj}")
UNIHAN = "https://www.unicode.org/cgi-bin/GetUnihanData.pl?codepoint={hex}"
ZITOOLS = "https://zi.tools/zi/{enc}"
ZDIC = "https://www.zdic.net/hans/{enc}"
GLYPHWIKI = "https://glyphwiki.org/wiki/u{lhex}"
WIKTIONARY = "https://en.wiktionary.org/wiki/{enc}"
UKDOC = "https://github.com/unicode-org/uk-source-ideographs/blob/main/{doc}.pdf"

BLOCK_JA = {"CJK Unified Ideographs": "基本ブロック (URO)"}
for x in "ABCDEFGHIJ":
    BLOCK_JA[f"CJK Unified Ideographs Extension {x}"] = f"拡張 {x}"

VIRT = ' <span class="virt">(仮想位置 — その字書には載っていない)</span>'

# zi.tools の字義の半分近くが「同=X」「同「X」」「同=X(Y)」の形をしている。
# 訳語表に 1 件ずつ書く意味が無いので、ここで機械的に訳す。空白が入るものは
# 「同=X <語釈>」のように語釈が続いているので、訳語表のほうで訳す。
SAME_AS = re.compile(r"同[=「]([^」\s]+)」?")


# 1 字ぶんの行。狭い画面では表を崩してカードにするので、列ごとの中身に
# それぞれ見出しを持たせてある (<thead> が消えても何の欄か分かるように)。
TR = """
<tr data-search="{search}" data-strokes="{strokes}" data-cp="{n}" data-cats="{catkeys}">
  <td class="g"><img src="glyphs/u{lhex}.svg" alt="{cp}" loading="lazy"></td>
  <td class="id">
    <div class="cp">{cp}</div>
    <div class="sub">{block} · {strokes_txt} 画</div>
    <div class="cats">{cats}</div>
    {readings}
    {df}
    <div class="lk">{links}</div>
  </td>
  <td class="src">
    <details class="dt" open><summary>{summary}<span class="more">出典</span></summary>
    <div class="h">IRG ソース参照</div><ul>{cites}</ul>
    <div class="h">字書索引</div><ul>{dicts}</ul>
    {zi}
    </details>
  </td>
  <td class="ev{evnone}">
    <div class="h evh">提案文書に記録された用例</div>{note}</td>
</tr>"""


def a(url, text):
    return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'


def pct(ch):
    return "".join(f"%{b:02X}" for b in ch.encode())


class Builder:
    def __init__(self, category):
        self.category = category
        self.uni = unihan()
        self.blocks = blocks()
        self.usrc = usource()
        self.cats = toml("categories.toml")
        self.srcmap = toml("irg_sources.toml")["prefix"]
        self.books = toml("books.toml")
        self.notes = toml("notes.toml")
        self.utags = toml("usource_tags.toml")["tag"]
        self.zisrc = toml("zi_tools_sources.toml")["tag"]
        # 字義の訳語表はリポジトリに入れていない (.gitignore に理由がある)。
        # 無ければ字義を原文のまま出す。
        self.zija = (toml("zi_tools_ja.toml")["ja"]
                     if (DATA / "zi_tools_ja.toml").exists() else {})
        if not self.zija:
            log("  data/zi_tools_ja.toml が無いので字義は原文のまま出す")
        self.prefixes = sorted(self.srcmap, key=len, reverse=True)
        # 英語版 Wiktionary に項目がある字 (fetch_wiktionary.py が作る)
        wk = CACHE / "wiktionary.json"
        self.wiktionary = json.loads(wk.read_text()) if wk.exists() else {}
        if not self.wiktionary:
            log("  cache/wiktionary.json が無いので Wiktionary のリンクは付けない")
        self.uk = self.cache_json("uk_source.json", "UK-source の用例")
        self.l2 = self.cache_json("l2docs.json", "UTC 文書の題名")
        self.zi = self.cache_json("zi_tools.json", "zi.tools の字義")

    def cache_json(self, name, what):
        p = CACHE / name
        if not p.exists():
            log(f"  cache/{name} が無いので{what}は出さない")
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    # -- 小物 ---------------------------------------------------------------
    def block_of(self, cp):
        n = int(cp[2:], 16)
        for lo, hi, name in self.blocks:
            if lo <= n <= hi:
                return BLOCK_JA.get(name, name)
        return "?"

    def expand_source(self, val, enc):
        """IRG ソース参照 1 件を、読める出典名 (可能ならリンク付き) にする。"""
        if val.startswith("GKX"):
            page, pos = val[4:].split(".")
            # GKX が付く字は康熙字典に実在するので、字頭検索で引ける
            return a(KX.format(enc=enc),
                     f"康熙字典 {int(page)} ページ {int(pos)} 字目 (1958 年第 9 版) 🔎")
        if val.startswith("GHZ") and not val.startswith("GHZR"):
            b = val[4:]
            return (f"漢語大字典 第 {b[0]} 巻 {int(b[1:5])} ページ "
                    f'{int(b.split(".")[1])} 字目')
        if val.startswith("JMJ"):
            mj = val[1:].replace("-", "")          # JMJ-005410 → MJ005410
            return a(MJ.format(mj=mj), f"文字情報基盤 {mj}")
        for p in self.prefixes:
            if val.startswith(p):
                return self.srcmap[p]
        return html.escape(val)

    def dict_entries(self, v, enc):
        # 空白区切りで複数の位置を持つ字がある (kHanYu / kSBGY / kMorohashi など)
        out = []
        for ref in v.get("kKangXi", "").split():
            page, pos = ref.split(".")
            label = f"康熙字典 {int(page)} ページ {int(pos[:-1])} 字目"
            if pos[-1] == "0":
                out.append(a(KX.format(enc=enc), label + " 🔎"))
            else:
                # 仮想位置の字は字頭検索に出てこないのでリンクしない
                out.append(label + VIRT)
        for ref in v.get("kHanYu", "").split():
            head, pos = ref.split(".")
            t = (f"漢語大字典 第 {head[0]} 巻 {int(head[1:])} ページ "
                 f"{int(pos[:-1])} 字目")
            out.append(t + ("" if pos[-1] == "0" else VIRT))
        if "kSBGY" in v:
            for ref in v["kSBGY"].split():
                p, x = ref.split(".")
                out.append(f"宋本広韻 {int(p)} ページ {int(x)} 字目")
        if "kMorohashi" in v:
            n = v["kMorohashi"].split()[0].split(":")[0].lstrip("0")
            out.append(f"大漢和辞典 {n} 番")
        if "kDaeJaweon" in v:
            out.append(f'大字源 (韓国) {v["kDaeJaweon"]}')
        if "kNelson" in v:
            out.append(f'Nelson {v["kNelson"]}')
        return out

    def evidence_html(self, items):
        out = []
        for e in items:
            if "book" in e:
                b = self.books[e["book"]]
                links = " / ".join(a(l["url"], l["label"]) for l in b["links"])
                out.append(f'<li>{b["title"]}{e.get("pages", "")} — {links}</li>')
                continue
            # data/ の記述は HTML 断片を書いてよいことにしてあるので、
            # エスケープはせず、字形の差し替えだけを掛ける
            body = self.glyphs(e["text"], escape=False)
            if "url" in e:
                body = a(e["url"], f'{body} {e.get("label", "")}'.strip())
                if e.get("extra"):
                    body += f' ({html.escape(e["extra"])})'
                if e.get("url2"):
                    body += " / " + a(e["url2"], e.get("label2", "link"))
            if e.get("nolink"):
                body += f' <span class="nolink">— {html.escape(e["nolink"])}</span>'
            out.append(f"<li>{body}</li>")
        return "".join(out)

    def cat_badge(self, c):
        """kStrange の値 1 つを札にする。

        値は「I:U+4EB2:U+8F9B」のように、カテゴリの記号のあとに関連する字が
        並ぶ形。U+2298F は関連字が 31 個あって 382 文字になり、コロン区切りは
        折り返せないので、そのまま出すと札 1 つで幅 2,773px になる。
        2 つ以上並ぶときは数だけ出して、中身は title に回す。
        """
        head, _, rest = c.partition(":")
        parts = rest.split(":") if rest else []
        desc = self.cats.get(head, "")
        label, tip = (f"{head} ({len(parts)})", f"{desc} — {c}") \
            if len(parts) > 1 else (c, desc)
        return (f'<span class="cat" title="{html.escape(tip)}">'
                f"{html.escape(label)}</span>")

    # -- 本文中の字形 --------------------------------------------------------
    def glyphs(self, text, escape=True):
        """フォントが無いと豆腐になる字を GlyphWiki の SVG に差し替える。

        表の左端と同じ理屈。字義の中に出てくる字も拡張 B より後のものが多く、
        macOS の標準フォントでは読めない。字そのものは目に見えない形で残すので、
        コピーしても検索しても字が落ちない。
        """
        out = []
        for ch in text:
            h = f"{ord(ch):x}"
            if needs_glyph(ch) and (GLYPHS / f"u{h}.svg").exists():
                out.append(f'<img class="ig" src="glyphs/u{h}.svg" alt="">'
                           f'<span class="sr">{html.escape(ch)}</span>')
            else:
                out.append(html.escape(ch) if escape else ch)
        return "".join(out)

    # -- zi.tools の字義 -----------------------------------------------------
    def zi_ja(self, text):
        """字義の日本語訳。「同=X」「同「X」」だけは数が多いので機械的に訳す。"""
        if text in self.zija:
            return self.zija[text]
        m = SAME_AS.fullmatch(text)
        return f"「{m[1]}」に同じ" if m else ""

    def zi_source(self, tag):
        """zi.tools の出典タグ → 出典名。IRG のソース接頭辞と重なるものが多い。"""
        if tag in self.zisrc:
            return self.zisrc[tag]
        for p in self.prefixes:
            if tag.startswith(p):
                return self.srcmap[p]
        return tag

    def zi_html(self, cp):
        rows = [r for r in self.zi.get(cp, []) if r.get("def")]
        if not rows:
            return ""
        out = []
        for r in rows:
            body = self.glyphs(r["def"])
            ja = self.zi_ja(r["def"])
            if ja:
                body += f'<span class="ja">{self.glyphs(ja)}</span>'
            body += f'<span class="zisrc">{html.escape(self.zi_source(r["src"]))}</span>'
            if r.get("note"):
                body += f'<div class="zinote">{self.glyphs(r["note"])}</div>'
            out.append(f"<li>{body}</li>")
        return ('<div class="h">字義 (zi.tools)</div>'
                f'<ul class="zi">{"".join(out)}</ul>')

    def zi_summary(self, cp):
        """狭い画面で畳んだときに見出しへ出す 1 行。字義の 1 件目の訳を使う。"""
        for r in self.zi.get(cp, []):
            if r.get("def"):
                return self.glyphs(self.zi_ja(r["def"]) or r["def"])
        return '<span class="none">字義なし</span>'

    # -- 提案文書の自動展開 --------------------------------------------------
    def uk_note(self, sid):
        """UK-source の提出文書 (の添付表) から用例証拠を組み立てる。"""
        r = self.uk.get(sid)
        if not r:
            return ""
        doc = a(UKDOC.format(doc=r["doc"].replace(" ", "")), r["doc"])
        head = f'{sid} / {doc} <span class="sub">({r["ws"]})</span>'
        body = ""
        if r.get("note"):
            body += f'<p>{self.glyphs(r["note"])}</p>'
        ev = "".join(f"<li>{self.glyphs(e)}</li>" for e in r.get("evidence", []))
        if ev:
            body += f'<ul class="ev">{ev}</ul>'
        if r.get("fig"):
            body += (f'<p class="fig">証拠画像: {html.escape(r["fig"])}</p>')
        return f'<div class="note"><b>{head}</b>{body}</div>'

    def u_note(self, sid):
        """U-source の出典欄 (USourceData.txt) を読める形にする。"""
        d = self.usrc.get(sid)
        if not d:
            return ""
        items, docs = [], []
        for part in re.split(r"[*;]", d.get("sources") or ""):
            part = part.strip()
            if not part:
                continue
            tag, _, idx = part.partition(" ")
            if tag == "UTCDoc":
                num = idx.split()[0] if idx else ""
                doc = self.l2.get(num)
                nth = idx.split()[1:] if idx else []
                where = f" (文書内 {nth[0]} 番目の字)" if nth else ""
                if doc:
                    docs.append(
                        f'{a(doc["url"], num)} {html.escape(doc["author"])}'
                        f'「{html.escape(doc["title"])}」({doc["date"]}){where}')
                else:
                    docs.append(f"UTC 文書 {html.escape(num)}{where}")
            elif tag.startswith("http"):
                items.append(a(part.split()[0], html.escape(part.split()[0]))
                             + (f" ({idx.split()[-1]} 時点)" if idx else ""))
            else:
                name = self.utags.get(tag, tag)
                items.append(html.escape(name)
                             + (f" — {html.escape(idx)}" if idx else ""))
        if not (items or docs):
            return ""
        body = "".join(f"<p>{d_}</p>" for d_ in docs)
        if d.get("comment"):
            body += f'<p>コメント欄: {html.escape(d["comment"])}</p>'
        if items:
            body += ('<ul class="ev">'
                     + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        return f'<div class="note"><b>{sid}</b>{body}</div>'

    # -- 1 字ぶん -----------------------------------------------------------
    def row(self, cp):
        v = self.uni[cp]
        ch = chr(int(cp[2:], 16))
        enc, lhex = pct(ch), cp[2:].lower()

        cites = "".join(
            f'<li><b>{k[5:].replace("Source", "")}</b> <code>{html.escape(val)}</code>'
            f"<br>{self.expand_source(val, enc)}</li>"
            for k, val in sorted(v.items()) if k.startswith("kIRG_"))

        dicts = "".join(f"<li>{d}</li>" for d in self.dict_entries(v, enc)) \
            or '<li class="none">索引なし</li>'

        links = [a(UNIHAN.format(hex=cp[2:]), "Unihan"),
                 a(ZITOOLS.format(enc=enc), "zi.tools"),
                 a(ZDIC.format(enc=enc), "漢典"),
                 a(GLYPHWIKI.format(lhex=lhex), "GlyphWiki")]
        if self.wiktionary.get(cp):
            links.append(a(WIKTIONARY.format(enc=enc), "Wiktionary"))
        if v.get("kMojiJoho"):
            mj = v["kMojiJoho"].split()[0]
            links.append(a(MJ.format(mj=mj), mj))
        kx = v.get("kKangXi", "").split()
        if kx and kx[0].endswith("0"):
            pg = int(kx[0].split(".")[0])
            links.append(a(KX.format(enc=enc), f"康熙字典 p.{pg} 🔎"))

        readings = [f"{lab} {html.escape(v[key])}" for key, lab in
                    (("kJapanese", "和"), ("kMandarin", "官"),
                     ("kCantonese", "粤"), ("kKorean", "韓")) if v.get(key)]

        n = self.notes.get(cp)
        if n:
            head = n["source_id"]
            if n.get("doc_url"):
                head += " / " + a(n["doc_url"], n["doc_label"])
            if n.get("doc_suffix"):
                head += " " + n["doc_suffix"]
            ev = self.evidence_html(n.get("evidence", []))
            body = self.glyphs(n["text"].strip(), escape=False)
            note = (f'<div class="note"><b>{head}</b><p>{body}</p>'
                    + (f'<ul class="ev">{ev}</ul>' if ev else "") + "</div>")
        else:
            # 手で書いたメモが無い字は、提出文書の表と USourceData.txt から組み立てる
            note = (self.uk_note(v.get("kIRG_UKSource", ""))
                    or self.u_note(v.get("kIRG_USource", ""))
                    or '<span class="none">提案文書まで遡っていない '
                       "(字書・規格の記載のみ)</span>")

        cats = "".join(self.cat_badge(c) for c in v["kStrange"].split())

        zi = self.zi_html(cp)
        summary = self.zi_summary(cp)
        # 提案文書まで辿れていない字は、狭い画面では列ごと隠す (761 字が同じ文言)
        evnone = " nothing" if cp not in self.notes and not (
            self.uk_note(v.get("kIRG_UKSource", ""))
            or self.u_note(v.get("kIRG_USource", ""))) else ""
        search = " ".join([cp, self.block_of(cp), v["kTotalStrokes"],
                           v.get("kDefinition", ""), v.get("kJapanese", ""),
                           v.get("kMandarin", ""), v.get("kStrange", ""),
                           re.sub("<[^>]+>", " ", cites),
                           re.sub("<[^>]+>", " ", zi),
                           re.sub("<[^>]+>", " ", note)]).lower()

        catkeys = " ".join(sorted({c.split(":")[0] for c in v["kStrange"].split()}))

        return TR.format(
            search=html.escape(search), strokes=int(v["kTotalStrokes"]),
            n=int(cp[2:], 16), catkeys=catkeys, lhex=lhex, cp=cp,
            block=self.block_of(cp), strokes_txt=v["kTotalStrokes"], cats=cats,
            readings=('<div class="rd">' + " / ".join(readings) + "</div>"
                      if readings else ""),
            df=('<div class="df">' + html.escape(v["kDefinition"]) + "</div>"
                if v.get("kDefinition") else ""),
            links=" · ".join(links), summary=summary, cites=cites, dicts=dicts,
            zi=zi, evnone=evnone, note=note)


    def filter_bar(self, cps):
        """対象に 2 つ以上のカテゴリがあるときだけ、絞り込みのボタンを出す。"""
        counts = {}
        for cp in cps:
            for c in {t.split(":")[0] for t in self.uni[cp]["kStrange"].split()}:
                counts[c] = counts.get(c, 0) + 1
        if len(counts) < 2:
            return ""
        chips = [f'<button class="chip on" data-cat="">すべて {len(cps)}</button>']
        for c in sorted(counts, key=lambda x: -counts[x]):
            chips.append(f'<button class="chip" data-cat="{c}" '
                         f'title="{html.escape(self.cats.get(c, ""))}">{c} {counts[c]}</button>')
        return f'<div class="chips">{"".join(chips)}</div>'

    # -- 全体 ---------------------------------------------------------------
    def untranslated(self, cps):
        """訳語表に載っていない字義。取り直したあと足すべきものが分かる。"""
        return sorted({r["def"] for cp in cps for r in self.zi.get(cp, [])
                       if r.get("def") and not self.zi_ja(r["def"])})

    def build(self):
        cps = targets(self.uni, self.category)
        if self.zi:
            miss = self.untranslated(cps)
            if miss:
                log(f"  訳の無い字義が {len(miss)} 件ある "
                    f"(data/zi_tools_ja.toml に足す): {miss[0]}")
        rows = "".join(self.row(cp) for cp in cps)
        chips = self.filter_bar(cps)
        m = manifest()
        files = m.get("files", {})
        hashes = " / ".join(
            f'{k} <code>{v["sha256"][:12]}…</code>' for k, v in files.items()
            if k in ("Unihan.zip", "USourceData.txt"))
        title = (f"kStrange カテゴリ {self.category}" if self.category != "all"
                 else "kStrange 全字")
        catname = self.cats.get(self.category, "")
        catname = f" ({html.escape(catname)})" if catname else""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return TEMPLATE.format(title=title, catname=catname,
                               count=len(cps), rows=rows, now=now, chips=chips,
                               uv=UNICODE_VERSION, utn=UTN43_REVISION,
                               hashes=hashes or "(manifest なし)")


TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — 出典一覧</title>
<script>
// 絞り込みは JS でやっていて、再読み込みすると全 828 行の状態に戻る。
// そこへブラウザがスクロール位置を復元すると、絞り込んでいたときの y 座標のまま
// まったく違う場所へ飛ばされる (26 行の表と 828 行の表では同じ y が別物になる)。
// 復元させず、先頭から始める。復元より前に実行したいので head に置く。
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
</script>
<style>
:root {{
  color-scheme: light dark;       /* 検索欄やスクロールバーも OS の設定に合わせる */
  --bg:#fafafa; --surface:#fff; --bar:rgba(250,250,250,.96);
  --text:#1a1a1a; --soft:#444; --muted:#6b6b6b; --faint:#999; --foot:#333;
  --line:#d8d8d8; --head:#f4f4f4; --code:#f0f0f0;
  --accent:#1a5fb4; --on-accent:#fff;
  --chip-on:#1a1a1a; --on-chip:#fff;
  --cat-bg:#eef2f8; --cat-line:#cfd9e8;
  --virt:#a33; --warn-bg:#fff8e1; --warn-line:#e8d48b;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#16181c; --surface:#1d2025; --bar:rgba(22,24,28,.96);
    --text:#e6e6e6; --soft:#c2c6cc; --muted:#9aa0a6; --faint:#7a7f87; --foot:#c8ccd2;
    --line:#33373e; --head:#22262c; --code:#2a2e35;
    --accent:#83b0ec; --on-accent:#16181c;
    --chip-on:#e6e6e6; --on-chip:#16181c;
    --cat-bg:#22303f; --cat-line:#3a4d63;
    --virt:#e39191; --warn-bg:#332c19; --warn-line:#6b5b2a;
  }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:0 0 4rem; font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
        line-height:1.7; color:var(--text); background:var(--bg) }}
header {{ padding:2rem 2rem 1rem; max-width:1500px; margin:0 auto }}
h1 {{ font-size:1.6rem; margin:0 0 .4rem }}
.lead {{ color:var(--muted); max-width:72ch; font-size:.92rem }}
.meta {{ font-size:.8rem; color:var(--muted); margin-top:.8rem }}
.bar {{ position:sticky; top:0; z-index:9; background:var(--bar);
        backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
        padding:.7rem 2rem; display:flex; gap:1rem; align-items:center; flex-wrap:wrap }}
.bar input {{ padding:.45rem .7rem; border:1px solid var(--line); border-radius:6px;
              font-size:.9rem; width:22rem; max-width:50vw }}
.bar button {{ padding:.4rem .7rem; border:1px solid var(--line); background:var(--surface);
               color:inherit;
               border-radius:6px; cursor:pointer; font-size:.85rem }}
.bar button.on {{ background:var(--accent); color:var(--on-accent); border-color:var(--accent) }}
.chips {{ max-width:1500px; margin:.9rem auto 0; padding:0 2rem; display:flex; gap:.4rem; flex-wrap:wrap }}
.chip {{ padding:.25rem .6rem; border:1px solid var(--line); background:var(--surface);
         color:inherit; border-radius:999px;
         cursor:pointer; font-size:.8rem; font-family:ui-monospace,Menlo,monospace }}
.chip.on {{ background:var(--chip-on); color:var(--on-chip); border-color:var(--chip-on) }}
#count {{ font-size:.85rem; color:var(--muted); margin-left:auto }}
main {{ max-width:1500px; margin:0 auto; padding:0 2rem }}
table {{ width:100%; border-collapse:collapse; background:var(--surface); margin-top:1.2rem;
         border:1px solid var(--line); table-layout:fixed }}
/* 800 行を超えると表の描画が重いので、画面外の行の描画を後回しにする */
tbody tr {{ content-visibility:auto; contain-intrinsic-size:auto 220px }}
th {{ text-align:left; font-size:.78rem; color:var(--muted); font-weight:600;
      padding:.6rem .8rem; border-bottom:2px solid var(--line); background:var(--head) }}
td {{ vertical-align:top; padding:1rem .8rem; border-bottom:1px solid var(--line);
      font-size:.86rem; overflow-wrap:anywhere }}
/* table-layout:fixed では先頭行ではなく colgroup で列幅を決める */
col.c-g {{ width:110px }} col.c-id {{ width:250px }} col.c-src {{ width:380px }}
td.g {{ text-align:center }} td.g img {{ width:84px; height:84px }}
/* GlyphWiki の SVG は fill="black" 固定。暗い配色では地に沈むので反転させる
   (黒一色・背景は透明なので、反転すると白抜きになる) */
@media (prefers-color-scheme: dark) {{ td.g img {{ filter:invert(1) }} }}
.cp {{ font-family:ui-monospace,Menlo,monospace; font-size:1rem; font-weight:600 }}
.sub {{ color:var(--muted); font-size:.8rem }}
.cats {{ margin:.35rem 0 }}
.cat {{ display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:.75rem;
        background:var(--cat-bg); border:1px solid var(--cat-line); border-radius:4px;
        padding:.05rem .35rem; margin-right:.25rem; cursor:help }}
.rd {{ font-size:.8rem; margin-top:.3rem }}
.df {{ font-size:.8rem; color:var(--soft); font-style:italic; margin-top:.2rem }}
.lk {{ font-size:.78rem; margin-top:.5rem; line-height:2 }}
a {{ color:var(--accent) }}
.h {{ font-size:.72rem; color:var(--muted); font-weight:600; margin:.2rem 0 .1rem; letter-spacing:.04em }}
.src ul {{ margin:0 0 .7rem; padding-left:1.1rem }}
.src li {{ margin-bottom:.3rem; font-size:.8rem }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:.75rem; background:var(--code);
        padding:.05rem .25rem; border-radius:3px }}
.virt {{ color:var(--virt); font-size:.75rem }}
.nolink {{ color:var(--faint); font-size:.78rem }}
/* 本文中に埋める字形。フォントが持っていない字の代わりなので、前後の文字と
   同じ大きさに合わせる。
   CSS mask にして currentColor で塗る手もあるが、mask 画像は CORS の対象で
   file:// から開くと読み込みに失敗し、字形が消える。手元で open docs/index.html
   する使い方があるので <img> のままにして、暗い配色では反転させる */
img.ig {{ height:1.05em; width:1.05em; vertical-align:-.17em }}
@media (prefers-color-scheme: dark) {{ img.ig {{ filter:invert(1) }} }}
/* 差し替えた字そのもの。見せないが、選択とコピー、ページ内検索には乗る */
.sr {{ position:absolute; width:1px; height:1px; overflow:hidden;
       clip-path:inset(50%); white-space:nowrap }}
/* 字義はこの表で唯一「読む」ところ。まわりの索引に合わせて小さくすると、
   差し替えた字形 (明朝体なので線が細い) が潰れて読めない */
ul.zi {{ margin:0 0 .7rem; padding-left:1.1rem }}
ul.zi li {{ margin-bottom:.45rem; font-size:1rem }}
.ja {{ color:var(--text) }} .ja::before {{ content:" — "; color:var(--muted) }}
.zisrc {{ color:var(--muted); font-size:.8rem }}
.zisrc::before {{ content:" / " }}
.zinote {{ color:var(--muted); font-size:.8rem; line-height:1.5 }}
.fig {{ color:var(--muted); font-size:.75rem; margin:.2rem 0 0 }}
.note {{ border-left:3px solid var(--accent); padding:.1rem 0 .1rem .7rem }}
.note b {{ font-size:.8rem }} .note p {{ margin:.2rem 0 .4rem; font-size:.83rem }}
ul.ev {{ margin:.2rem 0 0; padding-left:1.1rem }}
ul.ev li {{ font-size:.82rem; margin-bottom:.25rem }}
.none {{ color:var(--faint); font-size:.8rem }}
footer {{ max-width:1500px; margin:2.5rem auto 0; padding:0 2rem; font-size:.84rem; color:var(--foot) }}
footer h2 {{ font-size:1rem; margin:1.6rem 0 .4rem }}
footer ul {{ padding-left:1.2rem }}
.warn {{ background:var(--warn-bg); border:1px solid var(--warn-line); border-radius:6px;
         padding:.8rem 1rem; margin-top:1rem }}
/* 狭い画面で畳むための入れ物。広い画面では開いたまま使うので、見出しは消す */
details.dt > summary {{ display:none }}
.evh {{ display:none }}

/* ── 狭い画面 ─────────────────────────────────────────────
   4 列の表は幅 1,500px 前提で、スマホでは潰れて読めない。
   表を崩して 1 字 1 枚のカードにし、出典は畳んでおく。 */
@media (max-width: 900px) {{
  header {{ padding:1.2rem 1rem .6rem }}
  h1 {{ font-size:1.25rem }}
  .bar {{ padding:.6rem 1rem; gap:.5rem }}
  .bar input {{ width:100%; max-width:none; order:-1 }}
  #count {{ margin-left:0 }}
  main, footer {{ padding:0 1rem }}
  /* チップは 13 個あって折り返すと 3 行になる。1 行にして横に送る */
  .chips {{ padding:0 1rem; margin-top:.7rem; flex-wrap:nowrap;
            overflow-x:auto; scrollbar-width:none }}
  .chips::-webkit-scrollbar {{ display:none }}
  .chip {{ flex:0 0 auto }}

  colgroup, thead {{ display:none }}
  table {{ display:block; border:none; background:none; margin-top:.8rem }}
  tbody {{ display:block }}
  /* 1 行 = 1 枚のカード。字形と見出しだけ横に並べ、残りは下へ流す */
  tbody tr {{ display:grid; grid-template-columns:auto 1fr; gap:0 .7rem;
              background:var(--surface); border:1px solid var(--line);
              border-radius:8px; padding:.8rem; margin-bottom:.7rem;
              contain-intrinsic-size:auto 380px }}
  td {{ display:block; padding:0; border-bottom:none;
        overflow-wrap:anywhere }}   /* 長い書誌や URL で横に溢れさせない */
  td.g img {{ width:56px; height:56px }}
  /* 1 枚あたりの高さを詰める。コードポイントと block・画数は 1 行に収める */
  td.id .cp, td.id .sub {{ display:inline }}
  td.id .sub {{ margin-left:.5rem }}
  .cats {{ margin:.2rem 0 }}
  .cat {{ margin-bottom:.15rem }}
  td.src, td.ev {{ grid-column:1 / -1 }}
  td.src {{ margin-top:.5rem }}
  td.ev {{ margin-top:.6rem }}
  /* 提案文書まで辿れていない字は、同じ文言が 761 字ぶん並ぶだけなので出さない */
  td.ev.nothing {{ display:none }}
  .evh {{ display:block }}
  .lk {{ line-height:1.9 }}

  details.dt > summary {{ display:block; cursor:pointer; list-style:none;
                          font-size:.95rem; margin:0 }}
  details.dt > summary::-webkit-details-marker {{ display:none }}
  details.dt > summary::before {{ content:"▸ "; color:var(--muted) }}
  details.dt[open] > summary::before {{ content:"▾ " }}
  details.dt > summary .more {{ color:var(--muted); font-size:.78rem;
                                margin-left:.4rem }}
  details.dt[open] > summary {{ margin-bottom:.4rem }}
  .intro > summary {{ color:var(--muted); font-size:.85rem }}
  .lead {{ font-size:.88rem }}
}}
</style></head><body>
<header>
<h1>{title} — 出典一覧</h1>
<details class="dt intro" open><summary>このページについて</summary>
<p class="lead">Unihan の provisional プロパティ <code>kStrange</code>{catname} が付く
{count} 字について、字形と出典をまとめたもの。🔎 が付いたリンクは原典の該当箇所。
字形は GlyphWiki の SVG なので、フォントの有無にかかわらず表示される。字義や用例の
<b>文中</b>に出てくる拡張 A 以降の字も同じく SVG に差し替えてある (選択してコピーすれば
字のまま取れる)。</p>
<p class="meta">Unicode {uv} / UTN #43 ({utn}) &nbsp;·&nbsp; 入力の SHA-256: {hashes}
&nbsp;·&nbsp; 生成 {now} &nbsp;·&nbsp;
<a href="https://github.com/delphinus/unicode-kstrange">生成スクリプト</a></p>
</details>
</header>
<div class="bar">
  <input id="q" type="search" placeholder="検索 (コードポイント・書名・読み・意味…)">
  <button data-sort="cp" class="on">コードポイント順</button>
  <button data-sort="strokes">画数順</button>
  <span id="count"></span>
</div>
{chips}
<main>
<table>
<colgroup><col class="c-g"><col class="c-id"><col class="c-src"><col></colgroup>
<thead><tr><th>字形</th><th>字</th><th>ソース参照・字書索引</th><th>提案文書に記録された用例</th></tr></thead>
<tbody id="tb">{rows}</tbody>
</table>
</main>
<footer>
<h2>原典をどこまで開けるか</h2>
<ul>
<li><b>康熙字典</b> — <a href="https://kangxizidian.com/">康熙字典網上版</a> の字頭検索へリンクしている (🔎)。
同サイトには同文書局原版のページ画像もあり、Unihan の <code>kKangXi</code> や IRG の <code>GKX</code> の
ページ番号がそのまま画像の番号に対応するが、画像は外部からのリンクを弾く設定なので、
検索ページのほうを指している。<code>kKangXi</code> の末尾が 0 以外の字は康熙字典に実在せず
検索にも出てこないため、リンクを張っていない。</li>
<li><b>zi.tools (字統網)</b> — 字義を出典タグ付きで載せている。この表の「字義」はその API
(<code>/api/zi/&lt;字&gt;</code>) から取ったもので、原文の下に日本語訳を添えてある
(訳は <code>data/zi_tools_ja.toml</code>、「同=X」の形だけは機械的に訳している)。
zi.tools の編集部が付けた字義には典拠の論文・字書が併記されていることがあり、
それも一緒に出している。<b>义不详</b> (義未詳) は、漢語大字典に項目はあるが語釈が無い字に
zi.tools が付けている印で、828 字のうち 40 字がこれ。</li>
<li><b>漢典 (zdic.net)</b> — 拡張 J の字でも引ける。読み・意味・部首はここが手早い。</li>
<li><b>文字情報基盤 (MJ)</b>・<b>Wiktionary</b>・<b>GlyphWiki</b> — 字ごとのページ。</li>
<li><b>提案文書</b> — UTC 文書 (L2/…) と英国の IRG 提出文書は PDF が公開されている。用例の図版はこの中。
UK-source の 3 通の提出文書は字ごとの一覧を Excel で抱えているので、
「どの本の何ページに出てくる字か」まで機械的に取り出せる。右端の列はそれを展開したもので、
手で書き起こしたメモがある字ではそちらを優先している。</li>
<li><b>書籍</b> — Amazon と国立国会図書館サーチ。ISBN の無い古い本は検索リンク。</li>
</ul>
<h2>リンクを付けられなかったもの</h2>
<ul>
<li><b>漢語大字典</b> — 自由に読めるページ画像が見つからなかった。巻・ページ・字順は載せてあるので、
紙か商用の電子版で引く必要がある。</li>
<li><b>大漢和辞典</b>・<b>宋本広韻</b>・<b>大字源</b> — 無料のオンライン版が無い。番号のみ。</li>
</ul>
<h2>読むときの注意</h2>
<ul>
<li><code>kStrange</code> は provisional なので値は変わる。Unicode 18.0 でも 8 字で値が変わり、25 字が追加された。</li>
<li>IRG ソース参照の版と Unihan の字書索引の版は必ずしも同じではない。康熙字典の場合、IRG の
<code>GKX</code> は 1958 年第 9 版、Unihan の <code>kKangXi</code> は 1989 年中華書局第 7 版を指す
(ページ番号はどちらも同文書局原版のものと一致する)。</li>
<li>字書索引の末尾の桁が 0 以外のものは、その字書に実際には載っておらず、並べ替えのために
割り当てられた仮想位置なので赤字で断わってある。</li>
<li>「提案文書に記録された用例」は、その字が使われた場面のすべてではなく、
<b>符号化を通すために提出された証拠</b>にすぎない。</li>
</ul>
<div class="warn">
<b>UTN #43 v5 の記述のずれ</b>: Category S の本文は「covering 24 Han ideographs」と書いているが、
同じ節の表には 26 行あり、Unicode 18.0 の Unihan も 26 字である (17.0 の時点で既に 26 字)。
本文の数字が更新されていない。<code>scripts/check_utn43.py</code> で検出できる。
</div>
</footer>
<script>
const tb=document.getElementById('tb'),q=document.getElementById('q'),count=document.getElementById('count');
const rows=[...tb.rows];
let cat='';
function apply(){{
  const s=q.value.trim().toLowerCase(); let n=0;
  for(const r of rows){{
    const hit=(!s||r.dataset.search.includes(s))
            &&(!cat||(r.dataset.cats||'').split(' ').includes(cat));
    r.style.display=hit?'':'none'; if(hit)n++; }}
  count.textContent=n+' / '+rows.length+' 字';
}}
q.addEventListener('input',apply);
for(const c of document.querySelectorAll('.chip')){{
  c.addEventListener('click',()=>{{
    document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));
    c.classList.add('on'); cat=c.dataset.cat; apply();
  }});
}}
for(const b of document.querySelectorAll('[data-sort]')){{
  b.addEventListener('click',()=>{{
    document.querySelectorAll('[data-sort]').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    const k=b.dataset.sort;
    rows.sort((x,y)=>(+x.dataset[k])-(+y.dataset[k])).forEach(r=>tb.appendChild(r));
  }});
}}
apply();

// 出典は <details open> で出しておいて、狭い画面のときだけ畳む。
// CSS だけでやる手 (::details-content) は対応が新しく、外すと
// 広い画面で開けなくなるので、失敗しても開いたままになるこちらにした。
const narrow=matchMedia('(max-width: 900px)');
function fold(){{ for(const d of document.querySelectorAll('details.dt')) d.open=!narrow.matches; }}
narrow.addEventListener('change',fold); fold();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S")
    ap.add_argument("--out", default=str(DOCS / "index.html"))
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = Builder(args.category).build()
    out.write_text(doc, encoding="utf-8")
    log(f"{out} を書いた ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
