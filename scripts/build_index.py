#!/usr/bin/env python3
"""コレクションの一覧 (docs/index.html) を組み立てる。

    python3 scripts/build_index.py

並びは data/collections.toml、件数は各コレクションが書いた
docs/<slug>/meta.json から取る。数え方を 2 か所に持たないため。
まだ作っていないコレクションは、その旨を出して並べる。
"""
import datetime
import html
import json

from common import DOCS, log, toml

TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>漢字</title>
<style>
:root {{
  color-scheme: light dark;
  --bg:#fafafa; --surface:#fff; --text:#1a1a1a; --muted:#6b6b6b;
  --line:#d8d8d8; --accent:#1a5fb4;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#16181c; --surface:#1d2025; --text:#e6e6e6; --muted:#9aa0a6;
    --line:#33373e; --accent:#83b0ec;
  }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:2.5rem 1.5rem 4rem;
        font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
        line-height:1.7; color:var(--text); background:var(--bg) }}
main {{ max-width:44rem; margin:0 auto }}
h1 {{ font-size:1.6rem; margin:0 0 .3rem }}
.lead {{ color:var(--muted); font-size:.92rem; margin:0 0 2rem }}
a.card {{ display:block; text-decoration:none; color:inherit;
          background:var(--surface); border:1px solid var(--line);
          border-radius:10px; padding:1rem 1.2rem; margin-bottom:.8rem }}
a.card:hover {{ border-color:var(--accent) }}
.t {{ font-size:1.05rem; font-weight:600; color:var(--accent) }}
.n {{ float:right; color:var(--muted); font-size:.85rem; font-weight:400 }}
.d {{ color:var(--muted); font-size:.85rem; margin-top:.2rem }}
.soon {{ opacity:.55 }}
footer {{ color:var(--muted); font-size:.8rem; margin-top:2rem }}
footer a {{ color:var(--accent) }}
</style></head><body>
<main>
<h1>漢字</h1>
<p class="lead">Unihan から、<b>その字がどこで使われていたのか</b>を辿れるところまで辿って
一覧にしたもの。字形は GlyphWiki の SVG なので、フォントの有無にかかわらず表示される。</p>
{cards}
<footer>生成 {now} ·
<a href="https://github.com/delphinus/unicode-kstrange">生成スクリプト</a></footer>
</main></body></html>
"""


def main():
    cards = []
    for c in toml("collections.toml")["collection"]:
        meta = DOCS / c["slug"] / "meta.json"
        title, lead = html.escape(c["title"]), html.escape(c["lead"])
        if meta.exists():
            m = json.loads(meta.read_text(encoding="utf-8"))
            cards.append(
                f'<a class="card" href="{c["slug"]}/">'
                f'<span class="n">{m["count"]:,} 字</span>'
                f'<div class="t">{title}</div>'
                f'<div class="d">{lead}</div></a>')
        else:
            log(f"  docs/{c['slug']}/meta.json が無いので、まだ作っていない扱いにする")
            cards.append(
                f'<div class="card soon"><span class="n">これから</span>'
                f'<div class="t">{title}</div>'
                f'<div class="d">{lead}</div></div>')

    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / "index.html"
    out.write_text(TEMPLATE.format(
        cards="\n".join(cards),
        now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")), encoding="utf-8")
    log(f"{out} を書いた ({len(cards)} 件)")


if __name__ == "__main__":
    main()
