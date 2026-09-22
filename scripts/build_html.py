#!/usr/bin/env python3
"""字の出典一覧 (docs/<slug>/index.html) を組み立てる。

    python3 scripts/build_html.py [--category S|all] [--slug kstrange]

出力は docs/<slug>/ の下。字形は docs/glyphs/ に置いて全コレクションで共有するので、
ページからは ../glyphs/ で参照する。並びは data/collections.toml。
"""
import argparse
import datetime
import html
import json
import pathlib
import re

from common import (CACHE, DATA, DOCS, GLYPHS, UNICODE_VERSION, UTN43_REVISION,
                    blocks, log, manifest, needs_glyph, spoofing_pairs, targets,
                    toml, unihan, usource)

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
UGLYPHS = "https://www.unicode.org/Public/UCD/latest/ucd/USourceGlyphs.pdf"
URSCHART = "https://www.unicode.org/Public/UCD/latest/ucd/USourceRSChart.pdf"

# UAX #45 の status。符号化済みのものはこの一覧に出さない。
ENCODED = {"URO", "Comp"} | {f"Ext{x}" for x in "ABCDEFGHIJ"}
STATUS_JA = {"Rejected": "却下", "NoAction": "対応なし", "Variant": "異体字",
             "FutureWS": "先送り", "WS-2024": "審議中"}
STATUS_TIP = {
    "却下": "CJK 統合漢字として符号化するのに適さないと判断された",
    "対応なし": "検討されたが、符号化へ向けた動きが取られていない",
    "異体字": "既に符号化されている字の異体と判断され、別に符号化しない",
    "先送り": "将来の作業集合へ回された",
    "審議中": "IRG Working Set 2024 として提出され、審議が続いている",
    "重複で取り下げ": "同じ字の別の登録があるため取り下げられた (status は残ったほうの識別子)",
}

BLOCK_JA = {"CJK Unified Ideographs": "基本ブロック (URO)"}
for x in "ABCDEFGHIJ":
    BLOCK_JA[f"CJK Unified Ideographs Extension {x}"] = f"拡張 {x}"

VIRT = ' <span class="virt">(仮想位置 — その字書には載っていない)</span>'

# zi.tools の字義の半分近くが「同=X」「同「X」」「同=X(Y)」の形をしている。
# 訳語表に 1 件ずつ書く意味が無いので、ここで機械的に訳す。空白が入るものは
# 「同=X <語釈>」のように語釈が続いているので、訳語表のほうで訳す。
SAME_AS = re.compile(r"同[=「]([^」\s]+)」?")

# 字義の中で「その字のことを言っている」箇所。原文も訳も、参照する字は
# 「X」で囲むか、= の直後に置く形で書かれている。ここだけリンクにする
# (訳の「気の巡りが通じる」のような普通の文まで拾うと、ただうるさい)。
HAN = r"[\u3400-\u4DBF\u4E00-\u9FFF\U00020000-\U0003FFFF]"
REF = re.compile(f"「({HAN})」|=({HAN})(?!{HAN})")


# 1 字ぶんの行。狭い画面では表を崩してカードにするので、列ごとの中身に
# それぞれ見出しを持たせてある (<thead> が消えても何の欄か分かるように)。
TR = """
<tr data-search="{search}" data-strokes="{strokes}" data-cp="{n}" data-cats="{catkeys}">
  <td class="g">{glyph}</td>
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
    {srcbody}
    </details>
  </td>
  <td class="ev{evnone}">
    <div class="h evh">{evhead}</div>{note}</td>
</tr>"""


def a(url, text):
    return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'


def pct(ch):
    return "".join(f"%{b:02X}" for b in ch.encode())


class Builder:
    def __init__(self, category, slug="kstrange"):
        self.category = category
        self.slug = slug
        self.spec = next(c for c in toml("collections.toml")["collection"]
                         if c["slug"] == slug)
        self.evhead = self.spec.get("evhead", "提案文書に記録された用例")
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
        self.pairs = spoofing_pairs(self.uni)
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
            body = self.glyphs(e["text"], escape=False, link="url" not in e)
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
    def glyphs(self, text, escape=True, link=True, refs=False):
        """フォントが無いと豆腐になる字を GlyphWiki の SVG に差し替える。

        表の左端と同じ理屈。字義の中に出てくる字も拡張 B より後のものが多く、
        macOS の標準フォントでは読めない。字そのものは目に見えない形で残すので、
        コピーしても検索しても字が落ちない。

        差し替えた字は zi.tools へのリンクにする。「同=𠷎」のように「知らない字に
        同じ」と言われても、その字を引けなければ意味が無いため。リンクの入れ子に
        なる場所 (用例が丸ごと <a> に包まれるとき) と、押すと開閉してしまう
        <summary> の中では link=False で呼ぶ。
        """
        # 「X」や =X で参照されている字の位置。字形に差し替えない字
        # (基本ブロックの常用漢字など) も、ここに当たればリンクにする
        at = set()
        if refs and link:
            for m in REF.finditer(text):
                at.add(m.start(1) if m.group(1) else m.start(2))
        out = []
        for i, ch in enumerate(text):
            h = f"{ord(ch):x}"
            if i in at and not needs_glyph(ch):
                out.append(self.zi_link(ch, html.escape(ch)))
                continue
            if needs_glyph(ch) and (GLYPHS / f"u{h}.svg").exists():
                g = (f'<img class="ig" src="../glyphs/u{h}.svg" alt="">'
                     f'<span class="sr">{html.escape(ch)}</span>')
                out.append(self.zi_link(ch, g, "igl") if link else g)
            else:
                out.append(html.escape(ch) if escape else ch)
        return "".join(out)

    @staticmethod
    def zi_link(ch, body, cls="zl"):
        return (f'<a class="{cls}" href="{ZITOOLS.format(enc=pct(ch))}" '
                f'target="_blank" rel="noopener" '
                f'title="U+{ord(ch):04X} を zi.tools で見る">{body}</a>')

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
            body = self.glyphs(r["def"], refs=True)
            ja = self.zi_ja(r["def"])
            if ja:
                body += f'<span class="ja">{self.glyphs(ja, refs=True)}</span>'
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
                return self.glyphs(self.zi_ja(r["def"]) or r["def"], link=False)
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

    def usource_items(self, sid):
        """USourceData.txt の出典欄を 1 件ずつ読める形にする。"""
        d = self.usrc.get(sid) or {}
        out = []
        for part in re.split(r"[*;]", d.get("sources") or ""):
            part = part.strip()
            if not part:
                continue
            tag, _, idx = part.partition(" ")
            if tag == "UTCDoc":
                continue                      # 文書は右の列に出す
            if tag.startswith("http"):
                out.append(a(part.split()[0], html.escape(part.split()[0])))
            else:
                out.append(html.escape(self.utags.get(tag, tag))
                           + (f" — {html.escape(idx)}" if idx else ""))
        if out:
            return "".join(f"<li>{i}</li>" for i in out)
        # 出典欄が UTCDoc だけの登録。文書は右の列に出すので、そう断わる
        if "UTCDoc" in (d.get("sources") or ""):
            return '<li class="none">提案文書のみ (右の列)</li>'
        return '<li class="none">出典の記載なし</li>'

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

    def partner_html(self, cp):
        """見間違えやすい相手。並べて出さないと比べようがない。

        字形は本体と同じく GlyphWiki の SVG。片方だけフォント任せにすると
        線の太さが揃わず、どこが違うのかが分からなくなる。
        """
        out = []
        for t in self.pairs.get(cp, []):
            v = self.uni.get(t, {})
            lhex = t[2:].lower()
            g = (f'<img class="pg" src="../glyphs/u{lhex}.svg" alt="{t}">'
                 if (GLYPHS / f"u{lhex}.svg").exists() else "")
            rd = " / ".join(f"{lab} {html.escape(v[k])}" for k, lab in
                            (("kJapanese", "和"), ("kMandarin", "官"))
                            if v.get(k))
            df = html.escape(v.get("kDefinition", ""))
            out.append(
                f'<div class="pair">{g}<div class="pt">'
                f'<div class="cp">{t}</div>'
                + (f'<div class="rd">{rd}</div>' if rd else "")
                + (f'<div class="df">{df}</div>' if df else "")
                + f'<div class="lk">{a(ZITOOLS.format(enc=pct(chr(int(t[2:], 16)))), "zi.tools")}'
                f' · {a(UNIHAN.format(hex=t[2:]), "Unihan")}</div></div></div>')
        return "".join(out) or '<span class="none">相手の記載なし</span>'

    # -- 1 件ぶん (まだ符号化されていない登録) --------------------------------
    def row_usource(self, uid):
        """USourceData.txt の 1 行。コードポイントが無いので Unihan は引けない。

        字形の画像は出せない。UAX #45 の字形表 (USourceGlyphs.pdf) はあるが、
        「You may not extract, copy, modify, or distribute fonts or font data
        from any Unicode Products」と明記されていて、フォントの取り出しが
        禁じられている。代わりに IDS (構成式) を出して、字形表へリンクする。
        """
        v = self.usrc[uid]
        st = self.status_ja(v["status"])
        ids = self.glyphs(v["ids"]) if v["ids"] else '<span class="none">IDS なし</span>'
        rad, _, res = v["rs"].partition(".")
        links = [a(UGLYPHS, "字形表 (PDF)"), a(URSCHART, "部首索引 (PDF)"),
                 a("https://www.unicode.org/reports/tr45/", "UAX #45")]
        note = self.u_note(uid) or '<span class="none">出典の記載のみ</span>'
        src = (f'<div class="h">出典</div><ul>{self.usource_items(uid)}</ul>')
        cats = (f'<span class="cat" title="{html.escape(STATUS_TIP.get(st, ""))}">'
                f"{st}</span>")
        search = " ".join([uid, st, v["ids"], v["rs"], v.get("sources", ""),
                           v.get("comment", ""), re.sub("<[^>]+>", " ", note)]).lower()
        return TR.format(
            search=html.escape(search), strokes=int(res or 0),
            n=int(re.sub(r"\D", "", uid) or 0), catkeys=st, cp=uid,
            glyph=f'<span class="ids">{ids}</span>',
            block=f"部首 {rad}", strokes_txt=res or "0", cats=cats,
            readings="", df="", links=" · ".join(links),
            summary=html.escape(v.get("comment") or st), evhead=self.evhead,
            srcbody=src, evnone="", note=note)

    # -- 1 字ぶん -----------------------------------------------------------
    def row(self, cp):
        if self.spec.get("select") == "usource":
            return self.row_usource(cp)
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
        elif self.spec.get("ev") == "partner":
            note = self.partner_html(cp)
        else:
            # 手で書いたメモが無い字は、提出文書の表と USourceData.txt から組み立てる
            note = (self.uk_note(v.get("kIRG_UKSource", ""))
                    or self.u_note(v.get("kIRG_USource", ""))
                    or '<span class="none">提案文書まで遡っていない '
                       "(字書・規格の記載のみ)</span>")

        cats = self.badges(cp)

        zi = self.zi_html(cp)
        summary = self.zi_summary(cp)
        # 提案文書まで辿れていない字は、狭い画面では列ごと隠す (761 字が同じ文言)
        # 相手を並べる一覧では、この列に必ず中身があるので隠さない
        evnone = "" if self.spec.get("ev") == "partner" else (
            " nothing" if cp not in self.notes and not (
                self.uk_note(v.get("kIRG_UKSource", ""))
                or self.u_note(v.get("kIRG_USource", ""))) else "")
        search = " ".join([cp, self.block_of(cp), v["kTotalStrokes"],
                           v.get("kDefinition", ""), v.get("kJapanese", ""),
                           v.get("kMandarin", ""), v.get("kStrange", ""),
                           v.get("kIRG_UKSource", ""),
                           re.sub("<[^>]+>", " ", cites),
                           re.sub("<[^>]+>", " ", zi),
                           re.sub("<[^>]+>", " ", note)]).lower()

        catkeys = " ".join(self.facets(cp))

        return TR.format(
            search=html.escape(search), strokes=int(v["kTotalStrokes"]),
            n=int(cp[2:], 16), catkeys=catkeys, cp=cp,
            glyph=self.glyph_cell(cp, lhex),
            block=self.block_of(cp), strokes_txt=v["kTotalStrokes"], cats=cats,
            readings=('<div class="rd">' + " / ".join(readings) + "</div>"
                      if readings else ""),
            df=('<div class="df">' + html.escape(v["kDefinition"]) + "</div>"
                if v.get("kDefinition") else ""),
            links=" · ".join(links), summary=summary, cites=cites, dicts=dicts,
            evhead=self.evhead,
            srcbody=('<div class="h">IRG ソース参照</div>'
                     f"<ul>{cites}</ul>"
                     '<div class="h">字書索引</div>'
                     f"<ul>{dicts}</ul>{zi}"),
            evnone=evnone, note=note)


    def filter_bar(self, cps):
        """対象に 2 つ以上のカテゴリがあるときだけ、絞り込みのボタンを出す。"""
        counts = {}
        for cp in cps:
            for c in self.facets(cp):
                counts[c] = counts.get(c, 0) + 1
        if len(counts) < 2:
            return ""
        chips = [f'<button class="chip on" data-cat="">すべて {len(cps)}</button>']
        for c in sorted(counts, key=lambda x: -counts[x]):
            chips.append(f'<button class="chip" data-cat="{c}" '
                         f'title="{html.escape(self.cats.get(c) or STATUS_TIP.get(c, ""))}">'
                         f'{c} {counts[c]:,}</button>')
        return f'<div class="chips">{"".join(chips)}</div>'

    # -- 全体 ---------------------------------------------------------------
    def untranslated(self, cps):
        """訳語表に載っていない字義。取り直したあと足すべきものが分かる。"""
        return sorted({r["def"] for cp in cps for r in self.zi.get(cp, [])
                       if r.get("def") and not self.zi_ja(r["def"])})

    def nav_html(self):
        """ハブと他のコレクションへの行。切り替えは頻繁ではないので貼り付けない。"""
        out = ['<a href="../">漢字</a>']
        for c in toml("collections.toml")["collection"]:
            t = html.escape(c["title"])
            if c["slug"] == self.slug:
                out.append(f"<b>{t}</b>")
            elif (DOCS / c["slug"] / "meta.json").exists():
                out.append(a(f'../{c["slug"]}/', t))
            else:
                # まだ作っていないものはリンクにしない (404 になる)
                out.append(f'<span class="soon">{t}</span>')
        return " · ".join(out)

    @staticmethod
    def status_ja(st):
        return STATUS_JA.get(st, "重複で取り下げ" if re.fullmatch(r"(UTC|UK)-\d+", st)
                             else st)

    def select(self):
        """このコレクションに載せる字。"""
        if self.spec.get("select") == "spoofing":
            return sorted(self.pairs, key=lambda x: int(x[2:], 16))
        if self.spec.get("select") == "usource":
            # まだ符号化されていない登録。コードポイントが無いので、
            # ここだけ Unihan ではなく USourceData.txt の識別子を並べる。
            return sorted(k for k, v in self.usrc.items()
                          if v["status"] not in ENCODED)
        if self.spec.get("select") == "uk":
            return sorted((cp for cp in self.uni if self.uni[cp].get("kIRG_UKSource")),
                          key=lambda x: int(x[2:], 16))
        return targets(self.uni, self.category)

    def facets(self, cp):
        """絞り込みの分類。kStrange はカテゴリ、UK-source は提出した作業集合。"""
        if self.spec.get("facet") == "block":
            return [self.block_of(cp)]
        if self.spec.get("facet") == "status":
            return [self.status_ja(self.usrc[cp]["status"])]
        if self.spec.get("facet") == "ukdoc":
            r = self.uk.get(self.uni[cp].get("kIRG_UKSource", "")) or {}
            return [r["ws"].replace("IRG Working Set ", "WS")] if r.get("ws") else []
        return sorted({c.split(":")[0] for c in self.uni[cp]["kStrange"].split()})

    def badges(self, cp):
        """字の下に出す札。"""
        if self.spec.get("facet") == "ukdoc":
            sid = self.uni[cp].get("kIRG_UKSource", "")
            return f'<span class="cat">{html.escape(sid)}</span>' if sid else ""
        if self.spec.get("select") == "spoofing":
            # 相手が 2 つ以上あるときだけ数を出す (344 字は 1 対 1)
            n = len(self.pairs.get(cp, []))
            return f'<span class="cat">相手 {n}</span>' if n > 1 else ""
        return "".join(self.cat_badge(c)
                       for c in self.uni[cp].get("kStrange", "").split())

    def glyph_cell(self, cp, lhex):
        """字形。kStrange は GlyphWiki の SVG、UK-source は提出文書の添付フォント。"""
        if self.spec.get("glyph") == "ukfont":
            r = self.uk.get(self.uni[cp].get("kIRG_UKSource", "")) or {}
            if r.get("pua") and r.get("font"):
                ch = html.escape(chr(int(cp[2:], 16)))
                return (f'<span class="uk {r["font"]}">&#x{r["pua"]};</span>'
                        f'<span class="sr">{ch}</span>')
            return '<span class="none">字形なし</span>'
        return f'<img src="../glyphs/u{lhex}.svg" alt="{cp}" loading="lazy">'

    def build(self):
        cps = self.select()
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
        common = ("🔎 が付いたリンクは原典の該当箇所。字義や用例の<b>文中</b>に出てくる"
                  "拡張 A 以降の字は GlyphWiki の SVG に差し替えてある "
                  "(選択してコピーすれば字のまま取れる)。")
        if self.spec.get("select") == "spoofing":
            title, catname = self.spec["title"], ""
            lead = (f"取り違えの恐れがあるとして Unicode が組で指定した {len(cps):,} 字。"
                    f"右の列に相手を並べてある。字形はどちらも GlyphWiki の SVG で、"
                    f"片方だけフォント任せにすると線の太さが揃わず比べられないため。"
                    f"関係は相互に登録されていて、この {len(cps):,} 字で閉じている。")
        elif self.spec.get("select") == "usource":
            title, catname = self.spec["title"], ""
            lead = (f"UAX #45 に登録されたが、まだ符号化されていない {len(cps):,} 件。"
                    f"却下されたもの、既存の字の異体と判断されたもの、先送りされたもの、"
                    f"審議が続いているものが混ざっている。<b>コードポイントが無いので"
                    f"字形の画像は出せない</b> — Unicode の字形表はフォントの取り出しを"
                    f"禁じているため、代わりに IDS (構成式) を出している。正式な字形は"
                    f"字形表 (PDF) で引ける。")
        elif self.spec.get("select") == "uk":
            title, catname = self.spec["title"], ""
            lead = (f"英国が IRG へ提出した {len(cps):,} 字。用例に挙げられた書名と"
                    f"ページが提出文書に残っている。<b>字形は提出文書が抱えている"
                    f"フォントそのもの</b>で、英国が「この形で」と出したもの。" + common)
        else:
            title = (f"kStrange カテゴリ {self.category}" if self.category != "all"
                     else "kStrange 全字")
            catname = self.cats.get(self.category, "")
            catname = f" ({html.escape(catname)})" if catname else ""
            lead = (f"Unihan の provisional プロパティ <code>kStrange</code>{catname} が"
                    f"付く {len(cps):,} 字について、字形と出典をまとめたもの。"
                    f"字形は GlyphWiki の SVG なので、フォントの有無にかかわらず"
                    f"表示される。" + common)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.count = len(cps)
        self.page_title = title
        return TEMPLATE.format(title=title, lead=lead, nav=self.nav_html(),
                               count=len(cps), rows=rows, now=now, chips=chips,
                               evhead=self.evhead, slug=self.slug,
                               uv=UNICODE_VERSION, utn=UTN43_REVISION,
                               hashes=hashes or "(manifest なし)")


TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — 出典一覧</title>
<script>
// 絞り込みは JS でやっているので、ブラウザにスクロール位置を復元させると
// 中身が揃う前の y 座標で飛ばされて、まったく違う場所に着く。復元は自分で
// やる (下の restore())。ブラウザより先に止めたいので head に置く。
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
header {{ padding:1.2rem 2rem 1rem; max-width:1500px; margin:0 auto }}
.nav {{ font-size:.82rem; color:var(--muted); margin-bottom:.8rem }}
.nav b {{ color:var(--text) }}
.nav .soon {{ opacity:.5 }}
h1 {{ font-size:1.6rem; margin:0 0 .4rem }}
.lead {{ color:var(--muted); max-width:72ch; font-size:.92rem }}
.meta {{ font-size:.8rem; color:var(--muted); margin-top:.8rem }}
/* 検索欄・並べ替え・フィルタチップをまとめて画面の上に貼り付ける。
   828 行をスクロールしている最中に絞り込みを変えたくなるので、
   チップもここに入れて一緒に残す */
.bar {{ position:sticky; top:0; z-index:9; background:var(--bar);
        backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
        padding:.7rem 2rem }}
.ctl {{ display:flex; gap:1rem; align-items:center; flex-wrap:wrap }}
.bar input {{ padding:.45rem .7rem; border:1px solid var(--line); border-radius:6px;
              font-size:.9rem; width:22rem; max-width:50vw }}
.bar button {{ padding:.4rem .7rem; border:1px solid var(--line); background:var(--surface);
               color:inherit;
               border-radius:6px; cursor:pointer; font-size:.85rem }}
.bar button.on {{ background:var(--accent); color:var(--on-accent); border-color:var(--accent) }}
.chips {{ margin:.6rem 0 0; display:flex; gap:.4rem; flex-wrap:wrap }}
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
/* 直接の子だけ。構成式の中に埋めた字形 (img.ig) まで 84px にしない */
td.g {{ text-align:center }} td.g > img {{ width:84px; height:84px }}
/* UK-source の字形は提出文書が抱えているフォントで出す。私用領域に置かれていて、
   対応は Excel の PUA 欄。GlyphWiki から 3,409 件の SVG を取るより速く、
   英国が提出した字形そのもの。テキストなので暗い配色でも色が付いてくる */
@font-face {{ font-family:uk2015; src:url(../fonts/uk2015.ttf); font-display:block }}
@font-face {{ font-family:uk2017; src:url(../fonts/uk2017.ttf); font-display:block }}
@font-face {{ font-family:uk2021; src:url(../fonts/uk2021.ttf); font-display:block }}
.uk {{ font-size:84px; line-height:1.05 }}
/* まだ符号化されていない字は画像を出せないので、構成式をそのまま見せる */
.ids {{ font-size:1.5rem; line-height:1.4; word-break:break-all }}
/* 見間違えやすい相手。本体と同じ大きさで並べないと比べられない */
.pair {{ display:flex; gap:.8rem; align-items:flex-start; margin-bottom:.8rem }}
img.pg {{ width:84px; height:84px; flex:0 0 auto }}
@media (prefers-color-scheme: dark) {{ img.pg {{ filter:invert(1) }} }}
.pt {{ min-width:0 }}
.uk2015 {{ font-family:uk2015 }}
.uk2017 {{ font-family:uk2017 }}
.uk2021 {{ font-family:uk2021 }}
/* GlyphWiki の SVG は fill="black" 固定。暗い配色では地に沈むので反転させる
   (黒一色・背景は透明なので、反転すると白抜きになる) */
@media (prefers-color-scheme: dark) {{ td.g > img {{ filter:invert(1) }} }}
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
   file:// から開くと読み込みに失敗し、字形が消える。手元で open docs/<slug>/index.html
   する使い方があるので <img> のままにして、暗い配色では反転させる */
img.ig {{ height:1.05em; width:1.05em; vertical-align:-.17em }}
@media (prefers-color-scheme: dark) {{ img.ig {{ filter:invert(1) }} }}
/* 字義の中で参照されている字は zi.tools へのリンクにする。1,300 か所を超えるので
   青い下線では画面がうるさい。点線だけ引いて、押せることが分かる程度にする */
a.zl {{ color:inherit; text-decoration:underline dotted;
        text-decoration-color:var(--muted); text-underline-offset:.2em }}
a.zl:hover {{ text-decoration-color:var(--accent) }}
/* 中身が画像だと text-decoration が描かれないので、こちらは border で引く */
a.igl {{ text-decoration:none; border-bottom:1px dotted var(--muted) }}
a.igl:hover {{ border-bottom-color:var(--accent) }}
a.igl:hover img.ig {{ opacity:.55 }}
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
  header {{ padding:.9rem 1rem .6rem }}
  .nav {{ margin-bottom:.5rem }}
  h1 {{ font-size:1.25rem }}
  .bar {{ padding:.6rem 1rem }}
  .ctl {{ gap:.5rem }}
  .bar input {{ width:100%; max-width:none }}
  #count {{ margin-left:0 }}
  main, footer {{ padding:0 1rem }}
  /* チップは 13 個あって折り返すと 3 行になる。貼り付けている帯が
     画面の高さを食うので、1 行にして横に送る */
  .chips {{ margin-top:.5rem; flex-wrap:nowrap;
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
  td.g > img {{ width:56px; height:56px }}
  .uk {{ font-size:56px }}
  img.pg {{ width:56px; height:56px }}
  .ids {{ font-size:1.2rem }}
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
<nav class="nav">{nav}</nav>
<h1>{title} — 出典一覧</h1>
<details class="dt intro" open><summary>このページについて</summary>
<p class="lead">{lead}</p>
<p class="meta">Unicode {uv} / UTN #43 ({utn}) &nbsp;·&nbsp; 入力の SHA-256: {hashes}
&nbsp;·&nbsp; 生成 {now} &nbsp;·&nbsp;
<a href="https://github.com/delphinus/unicode-kstrange">生成スクリプト</a></p>
</details>
</header>
<div class="bar">
  <div class="ctl">
    <input id="q" type="search" placeholder="検索 (コードポイント・書名・読み・意味…)">
    <button data-sort="cp" class="on">コードポイント順</button>
    <button data-sort="strokes">画数順</button>
    <span id="count"></span>
  </div>
  {chips}
</div>
<main>
<table>
<colgroup><col class="c-g"><col class="c-id"><col class="c-src"><col></colgroup>
<thead><tr><th>字形</th><th>字</th><th>ソース参照・字書索引</th><th>{evhead}</th></tr></thead>
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
let cat='',sort='cp';
function apply(){{
  const s=q.value.trim().toLowerCase(); let n=0;
  for(const r of rows){{
    const hit=(!s||r.dataset.search.includes(s))
            &&(!cat||(r.dataset.cats||'').split(' ').includes(cat));
    r.style.display=hit?'':'none'; if(hit)n++; }}
  count.textContent=n+' / '+rows.length+' 字';
}}
function setCat(v){{
  cat=v;
  for(const c of document.querySelectorAll('.chip')) c.classList.toggle('on',c.dataset.cat===v);
}}
function setSort(k){{
  sort=k;
  for(const b of document.querySelectorAll('[data-sort]')) b.classList.toggle('on',b.dataset.sort===k);
  rows.slice().sort((x,y)=>(+x.dataset[k])-(+y.dataset[k])).forEach(r=>tb.appendChild(r));
}}

// 出典は <details open> で出しておいて、狭い画面のときだけ畳む。
// CSS だけでやる手 (::details-content) は対応が新しく、外すと
// 広い画面で開けなくなるので、失敗しても開いたままになるこちらにした。
const narrow=matchMedia('(max-width: 900px)');
function fold(){{ for(const d of document.querySelectorAll('details.dt')) d.open=!narrow.matches; }}
narrow.addEventListener('change',fold);

// ⌘R したときに見た目を戻す。絞り込みも並べ替えもここでやっているので、
// ブラウザ任せの復元 (フォームの値とスクロール位置だけ) では中身と食い違う。
// head で scrollRestoration を manual にしてあるのはそのため。自分で覚える。
// コレクションごとに分ける。1 つの鍵を使い回していたため、kStrange で
// カテゴリ S を選んだ状態が UK-source でも復元され、そのチップが無いので
// 1 件も出なくなっていた。
const KEY='kanji:{slug}:view';
// チップごとの読みかけの位置は、しばらく経ったら捨てる。半日前に見ていた
// 途中に連れ戻されるより、先頭から始めたほうがよい。
const KEEP=30*60*1000;
let hold=false, pos={{}}, stamp=Date.now();   // pos: チップ → 画面の上に来ていた行
function anchor(){{
  // スクロール位置は画素ではなく「画面の上に来ている行」で覚える。
  // content-visibility で画面外の行の高さは見積もりなので、画素だとずれる。
  for(const r of rows){{
    if(r.style.display==='none') continue;
    const b=r.getBoundingClientRect();
    if(b.bottom>0) return {{top:r.dataset.cp,off:-b.top}};
  }}
  return null;
}}
// touch=false は「保存はするが、最後に触った時刻は進めない」。離脱時 (pagehide) に
// 進めてしまうと、何時間放置して ⌘R しても時間切れにならない。
function save(touch){{
  if(touch!==false) stamp=Date.now();
  if(!hold) pos[cat]=anchor();       // 寄せ直している最中は触らない
  const open=[...document.querySelectorAll('tr details.dt[open]')]
    .map(d=>d.closest('tr').dataset.cp);
  try{{ sessionStorage.setItem(KEY,JSON.stringify(
    {{q:q.value,cat:cat,sort:sort,open:open,pos:pos,t:stamp}})); }}catch(e){{}}
}}
// 目印の行が狙った位置に来るまで寄せ直す。画面外の行の高さは見積もりなので、
// 実際に描かれるたびに位置が動く。t が無ければ先頭へ。
function goTo(t){{
  const r=t&&t.top&&rows.find(x=>x.dataset.cp===t.top&&x.style.display!=='none');
  if(!r){{ scrollTo(0,0); hold=false; return; }}
  hold=true;
  let n=0,stop=false;
  // 寄せ直しは 1 秒半ほど続くので、その間に自分でスクロールされたら譲る
  const ac=new AbortController();
  for(const ev of ['wheel','touchstart','keydown','pointerdown'])
    addEventListener(ev,()=>{{stop=true;}},{{signal:ac.signal,passive:true}});
  const go=()=>{{
    if(stop||++n>90){{ hold=false; ac.abort(); save(false); return; }}
    const d=r.getBoundingClientRect().top+(t.off||0);   // 0 になれば狙いどおり
    if(Math.abs(d)>1) scrollTo(0,Math.max(0,scrollY+d));
    requestAnimationFrame(go);
  }};
  requestAnimationFrame(go);
}}
function restore(){{
  let v=null;
  try{{ v=JSON.parse(sessionStorage.getItem(KEY)||'null'); }}catch(e){{}}
  if(!v){{ apply(); fold(); return; }}
  q.value=v.q||'';
  // 鍵を分けたうえで、念のため無いものは無視する。作り直しで分類が
  // 変わっても、古い状態で 0 件にならないように。
  const cats=[...document.querySelectorAll('.chip')].map(c=>c.dataset.cat);
  setCat(cats.includes(v.cat)?v.cat:'');
  if(v.sort&&v.sort!=='cp'&&document.querySelector('[data-sort="'+v.sort+'"]'))
    setSort(v.sort);
  apply(); fold();
  if(narrow.matches&&v.open) for(const cp of v.open){{
    const r=rows.find(x=>x.dataset.cp===cp), d=r&&r.querySelector('details.dt');
    if(d) d.open=true;
  }}
  stamp=v.t||Date.now();
  pos=(v.t&&Date.now()-v.t<KEEP&&v.pos)||{{}};
  goTo(pos[cat]);
}}
q.addEventListener('input',()=>{{apply();save();}});
for(const c of document.querySelectorAll('.chip'))
  c.addEventListener('click',()=>{{
    if(c.dataset.cat===cat) return;
    save();                          // 今いる場所を、今のチップのぶんとして残す
    setCat(c.dataset.cat); apply();
    goTo(pos[cat]);                  // 前に見ていた場所へ。無ければ先頭
    save();
  }});
for(const b of document.querySelectorAll('[data-sort]'))
  b.addEventListener('click',()=>{{setSort(b.dataset.sort);save();}});
tb.addEventListener('toggle',save,true);
let timer; addEventListener('scroll',()=>{{clearTimeout(timer);timer=setTimeout(save,150);}},
                            {{passive:true}});
addEventListener('pagehide',()=>save(false));
restore();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S")
    ap.add_argument("--slug", default="kstrange")
    ap.add_argument("--out", help="既定は docs/<slug>/index.html")
    args = ap.parse_args()

    out = pathlib.Path(args.out or DOCS / args.slug / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    b = Builder(args.category, args.slug)
    out.write_text(b.build(), encoding="utf-8")
    # ハブはこれを読んで件数を出す。数え方を 2 か所に持たないため
    (out.parent / "meta.json").write_text(json.dumps(
        {"title": b.page_title, "count": b.count,
         "generated": datetime.datetime.now().isoformat(timespec="minutes")},
        ensure_ascii=False), encoding="utf-8")
    log(f"{out} を書いた ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
