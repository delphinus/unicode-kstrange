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

from common import (CACHE, DOCS, UNICODE_VERSION, UTN43_REVISION, blocks, log,
                    manifest, targets, toml, unihan, usource)

KX = "https://kangxizidian.com/kangxi/{page:04d}.gif"      # 康熙字典網上版 (同文書局原版)
MJ = ("https://moji.or.jp/mojikibansearch/info?"
      "MJ%E6%96%87%E5%AD%97%E5%9B%B3%E5%BD%A2%E5%90%8D={mj}")
UNIHAN = "https://www.unicode.org/cgi-bin/GetUnihanData.pl?codepoint={hex}"
ZITOOLS = "https://zi.tools/zi/{enc}"
ZDIC = "https://www.zdic.net/hans/{enc}"
GLYPHWIKI = "https://glyphwiki.org/wiki/u{lhex}"
WIKTIONARY = "https://en.wiktionary.org/wiki/{enc}"

BLOCK_JA = {"CJK Unified Ideographs": "基本ブロック (URO)"}
for x in "ABCDEFGHIJ":
    BLOCK_JA[f"CJK Unified Ideographs Extension {x}"] = f"拡張 {x}"

VIRT = ' <span class="virt">(仮想位置 — その字書には載っていない)</span>'


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
        self.prefixes = sorted(self.srcmap, key=len, reverse=True)
        # 英語版 Wiktionary に項目がある字 (fetch_wiktionary.py が作る)
        wk = CACHE / "wiktionary.json"
        self.wiktionary = json.loads(wk.read_text()) if wk.exists() else {}
        if not self.wiktionary:
            log("  cache/wiktionary.json が無いので Wiktionary のリンクは付けない")

    # -- 小物 ---------------------------------------------------------------
    def block_of(self, cp):
        n = int(cp[2:], 16)
        for lo, hi, name in self.blocks:
            if lo <= n <= hi:
                return BLOCK_JA.get(name, name)
        return "?"

    def expand_source(self, val):
        """IRG ソース参照 1 件を、読める出典名 (可能ならリンク付き) にする。"""
        if val.startswith("GKX"):
            page, pos = val[4:].split(".")
            return a(KX.format(page=int(page)),
                     f"康熙字典 {int(page)} ページ {int(pos)} 字目 (1958 年第 9 版) 📄")
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

    def dict_entries(self, v):
        # 空白区切りで複数の位置を持つ字がある (kHanYu / kSBGY / kMorohashi など)
        out = []
        for ref in v.get("kKangXi", "").split():
            page, pos = ref.split(".")
            t = a(KX.format(page=int(page)),
                  f"康熙字典 {int(page)} ページ {int(pos[:-1])} 字目 📄")
            out.append(t + ("" if pos[-1] == "0" else VIRT))
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
            body = e["text"]
            if "url" in e:
                body = a(e["url"], f'{e["text"]} {e.get("label", "")}'.strip())
                if e.get("extra"):
                    body += f' ({html.escape(e["extra"])})'
                if e.get("url2"):
                    body += " / " + a(e["url2"], e.get("label2", "link"))
            if e.get("nolink"):
                body += f' <span class="nolink">— {html.escape(e["nolink"])}</span>'
            out.append(f"<li>{body}</li>")
        return "".join(out)

    # -- 1 字ぶん -----------------------------------------------------------
    def row(self, cp):
        v = self.uni[cp]
        ch = chr(int(cp[2:], 16))
        enc, lhex = pct(ch), cp[2:].lower()

        cites = "".join(
            f'<li><b>{k[5:].replace("Source", "")}</b> <code>{html.escape(val)}</code>'
            f"<br>{self.expand_source(val)}</li>"
            for k, val in sorted(v.items()) if k.startswith("kIRG_"))

        dicts = "".join(f"<li>{d}</li>" for d in self.dict_entries(v)) \
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
        if "kKangXi" in v:
            pg = int(v["kKangXi"].split(".")[0])
            links.append(a(KX.format(page=pg), f"康熙字典 p.{pg} 📄"))

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
            note = (f'<div class="note"><b>{head}</b><p>{n["text"].strip()}</p>'
                    + (f'<ul class="ev">{ev}</ul>' if ev else "") + "</div>")
        else:
            note = '<span class="none">提案文書まで遡っていない (字書・規格の記載のみ)</span>'

        cats = "".join(
            f'<span class="cat" title="{html.escape(self.cats.get(c.split(":")[0], ""))}">'
            f"{html.escape(c)}</span>" for c in v["kStrange"].split())

        search = " ".join([cp, self.block_of(cp), v["kTotalStrokes"],
                           v.get("kDefinition", ""), v.get("kJapanese", ""),
                           v.get("kMandarin", ""), v.get("kStrange", ""),
                           re.sub("<[^>]+>", " ", cites),
                           re.sub("<[^>]+>", " ", note)]).lower()

        catkeys = " ".join(sorted({c.split(":")[0] for c in v["kStrange"].split()}))

        return f"""
<tr data-search="{html.escape(search)}" data-strokes="{int(v['kTotalStrokes'])}" data-cp="{int(cp[2:], 16)}" data-cats="{catkeys}">
  <td class="g"><img src="glyphs/u{lhex}.svg" alt="{cp}" loading="lazy"></td>
  <td class="id">
    <div class="cp">{cp}</div>
    <div class="sub">{self.block_of(cp)} · {v['kTotalStrokes']} 画</div>
    <div class="cats">{cats}</div>
    {'<div class="rd">' + ' / '.join(readings) + '</div>' if readings else ''}
    {'<div class="df">' + html.escape(v['kDefinition']) + '</div>' if v.get('kDefinition') else ''}
    <div class="lk">{' · '.join(links)}</div>
  </td>
  <td class="src">
    <div class="h">IRG ソース参照</div><ul>{cites}</ul>
    <div class="h">字書索引</div><ul>{dicts}</ul>
  </td>
  <td class="ev">{note}</td>
</tr>"""

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
    def build(self):
        cps = targets(self.uni, self.category)
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
<style>
:root {{ --line:#d8d8d8; --muted:#6b6b6b; --accent:#1a5fb4 }}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:0 0 4rem; font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
        line-height:1.7; color:#1a1a1a; background:#fafafa }}
header {{ padding:2rem 2rem 1rem; max-width:1500px; margin:0 auto }}
h1 {{ font-size:1.6rem; margin:0 0 .4rem }}
.lead {{ color:var(--muted); max-width:72ch; font-size:.92rem }}
.meta {{ font-size:.8rem; color:var(--muted); margin-top:.8rem }}
.bar {{ position:sticky; top:0; z-index:9; background:rgba(250,250,250,.96);
        backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
        padding:.7rem 2rem; display:flex; gap:1rem; align-items:center; flex-wrap:wrap }}
.bar input {{ padding:.45rem .7rem; border:1px solid var(--line); border-radius:6px;
              font-size:.9rem; width:22rem; max-width:50vw }}
.bar button {{ padding:.4rem .7rem; border:1px solid var(--line); background:#fff;
               border-radius:6px; cursor:pointer; font-size:.85rem }}
.bar button.on {{ background:var(--accent); color:#fff; border-color:var(--accent) }}
.chips {{ max-width:1500px; margin:.9rem auto 0; padding:0 2rem; display:flex; gap:.4rem; flex-wrap:wrap }}
.chip {{ padding:.25rem .6rem; border:1px solid var(--line); background:#fff; border-radius:999px;
         cursor:pointer; font-size:.8rem; font-family:ui-monospace,Menlo,monospace }}
.chip.on {{ background:#1a1a1a; color:#fff; border-color:#1a1a1a }}
#count {{ font-size:.85rem; color:var(--muted); margin-left:auto }}
main {{ max-width:1500px; margin:0 auto; padding:0 2rem }}
table {{ width:100%; border-collapse:collapse; background:#fff; margin-top:1.2rem;
         border:1px solid var(--line); table-layout:fixed }}
/* 800 行を超えると表の描画が重いので、画面外の行の描画を後回しにする */
tbody tr {{ content-visibility:auto; contain-intrinsic-size:auto 220px }}
th {{ text-align:left; font-size:.78rem; color:var(--muted); font-weight:600;
      padding:.6rem .8rem; border-bottom:2px solid var(--line); background:#f4f4f4 }}
td {{ vertical-align:top; padding:1rem .8rem; border-bottom:1px solid var(--line); font-size:.86rem }}
/* table-layout:fixed では先頭行ではなく colgroup で列幅を決める */
col.c-g {{ width:110px }} col.c-id {{ width:250px }} col.c-src {{ width:380px }}
td.g {{ text-align:center }} td.g img {{ width:84px; height:84px }}
.cp {{ font-family:ui-monospace,Menlo,monospace; font-size:1rem; font-weight:600 }}
.sub {{ color:var(--muted); font-size:.8rem }}
.cats {{ margin:.35rem 0 }}
.cat {{ display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:.75rem;
        background:#eef2f8; border:1px solid #cfd9e8; border-radius:4px;
        padding:.05rem .35rem; margin-right:.25rem; cursor:help }}
.rd {{ font-size:.8rem; margin-top:.3rem }}
.df {{ font-size:.8rem; color:#444; font-style:italic; margin-top:.2rem }}
.lk {{ font-size:.78rem; margin-top:.5rem; line-height:2 }}
a {{ color:var(--accent) }}
.h {{ font-size:.72rem; color:var(--muted); font-weight:600; margin:.2rem 0 .1rem; letter-spacing:.04em }}
.src ul {{ margin:0 0 .7rem; padding-left:1.1rem }}
.src li {{ margin-bottom:.3rem; font-size:.8rem }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:.75rem; background:#f0f0f0;
        padding:.05rem .25rem; border-radius:3px }}
.virt {{ color:#a33; font-size:.75rem }}
.nolink {{ color:#999; font-size:.78rem }}
.note {{ border-left:3px solid var(--accent); padding:.1rem 0 .1rem .7rem }}
.note b {{ font-size:.8rem }} .note p {{ margin:.2rem 0 .4rem; font-size:.83rem }}
ul.ev {{ margin:.2rem 0 0; padding-left:1.1rem }}
ul.ev li {{ font-size:.82rem; margin-bottom:.25rem }}
.none {{ color:#999; font-size:.8rem }}
footer {{ max-width:1500px; margin:2.5rem auto 0; padding:0 2rem; font-size:.84rem; color:#333 }}
footer h2 {{ font-size:1rem; margin:1.6rem 0 .4rem }}
footer ul {{ padding-left:1.2rem }}
.warn {{ background:#fff8e1; border:1px solid #e8d48b; border-radius:6px;
         padding:.8rem 1rem; margin-top:1rem }}
</style></head><body>
<header>
<h1>{title} — 出典一覧</h1>
<p class="lead">Unihan の provisional プロパティ <code>kStrange</code>{catname} が付く
{count} 字について、字形と出典をまとめたもの。📄 が付いたリンクは原典のページ画像。
字形は GlyphWiki の SVG なので、フォントの有無にかかわらず表示される。</p>
<p class="meta">Unicode {uv} / UTN #43 ({utn}) &nbsp;·&nbsp; 入力の SHA-256: {hashes}
&nbsp;·&nbsp; 生成 {now} &nbsp;·&nbsp;
<a href="https://github.com/delphinus/unicode-kstrange">生成スクリプト</a></p>
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
<li><b>康熙字典</b> — <a href="https://kangxizidian.com/">康熙字典網上版</a> に同文書局原版のページ画像がある。
Unihan の <code>kKangXi</code> や IRG の <code>GKX</code> のページ番号がそのまま画像の番号に対応するので、
該当ページを直接開ける (📄)。ページ 1537 を開けば 龘 や 𪚥 が並んでいるのが見える。</li>
<li><b>zi.tools (字統網)</b> — IRG のソース参照・字形の分解・異体字に加えて、字義に出典のタグが付く。
ここだけで用例の当たりが付くことがある。</li>
<li><b>漢典 (zdic.net)</b> — 拡張 J の字でも引ける。読み・意味・部首はここが手早い。</li>
<li><b>文字情報基盤 (MJ)</b>・<b>Wiktionary</b>・<b>GlyphWiki</b> — 字ごとのページ。</li>
<li><b>提案文書</b> — UTC 文書 (L2/…) と英国の IRG 提出文書は PDF が公開されている。用例の図版はこの中。</li>
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
