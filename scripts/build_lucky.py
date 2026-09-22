#!/usr/bin/env python3
"""ひとつずつ引くページ (docs/lucky/index.html) を組み立てる。

    python3 scripts/build_lucky.py

4 つの一覧を合わせた 5,000 字あまりを上から眺めるのは無理なので、全部を
ひとまとめの母集団として 1 字ずつ引く。zi.tools や Wikipedia の「おまかせ
表示」と同じ形。

**このページ自体には字を持たせない。** 一覧の HTML を fetch して、その中から
1 行ぶんを切り出して貼る。字ごとのページを 5,000 枚書き出す手もあるが、

* 同じ内容が 2 か所になる (行を組み立てるのは build_html の仕事)
* 出力が倍になる

ので採らなかった。一覧は 1 度読めばブラウザが持っているので、2 回目からは
取りに行かない。押すたびに 6 MB 読み直すことにはならない。

見た目は 4 つの一覧と同じ CSS (build_html.STYLE) を使う。切り出した行を
そのまま貼るので、同じものが同じように見えないと困る。
"""
import datetime
import html
import json

from build_html import STYLE
from common import DOCS, log, toml

TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ひとつずつ — 漢字</title>
<script>history.scrollRestoration='manual';</script>
<style>{style}
/* このページだけの分。一覧と違って表が 1 行しか無い */
#card table {{ margin-top:1.2rem }}
#card:empty::after {{ content:'読み込み中…'; color:var(--muted); font-size:.9rem;
                      display:block; padding:2rem 0 }}
.err {{ color:var(--virt); font-size:.9rem; padding:2rem 0 }}
#from {{ font-size:.85rem; color:var(--muted); margin-left:auto }}
#from a {{ color:var(--accent) }}
</style></head><body>
<nav class="nav">{nav}</nav>
<header>
<h1>ひとつずつ</h1>
<details class="dt intro" open><summary>このページについて</summary>
<p class="lead">4 つの一覧を合わせた {total:,} 字から、順不同で 1 字ずつ出す。
どこから出たかは右に出る。上から眺めるには多すぎるので、こちらから当たる。</p>
</details>
</header>
<div class="bar">
  <div class="ctl">
    <button id="prev">← 前の字</button>
    <button id="nx" class="pri">次の字 →</button>
    <span id="pos"></span>
    <span class="keys"><kbd>Space</kbd> / <kbd>→</kbd> 次へ &nbsp;<kbd>←</kbd> 前へ</span>
    <span id="from"></span>
  </div>
</div>
<main><div id="card"></div></main>
<footer><p class="meta">生成 {now} ·
<a href="https://github.com/delphinus/unicode-kstrange">生成スクリプト</a></p></footer>
<script>
// 一覧ごとの件数。どの一覧を選ぶかをこの比で決めるので、全体から一様に
// 選んだのと同じことになる。
const COLS={cols};
const TITLES={titles};
const TOTAL=Object.values(COLS).reduce((a,b)=>a+b,0);
const card=document.getElementById('card'),posEl=document.getElementById('pos'),
      fromEl=document.getElementById('from'),navEl=document.querySelector('.nav');
function navh(){{
  document.documentElement.style.setProperty('--navh',navEl.offsetHeight+'px');
}}
addEventListener('resize',navh); navh();

const cache={{}};
async function load(slug){{
  // 1 度読めばブラウザが持っている。2 回目からは取りに行かない。
  if(cache[slug]) return cache[slug];
  const t=await (await fetch('../'+slug+'/')).text();
  cache[slug]={{
    text:t,
    ids:[...t.matchAll(/data-cp="([^"]+)"/g)].map(m=>m[1]),
    colgroup:(t.match(/<colgroup>[\\s\\S]*?<\\/colgroup>/)||[''])[0],
    thead:(t.match(/<thead>[\\s\\S]*?<\\/thead>/)||[''])[0],
  }};
  return cache[slug];
}}
/** 一覧の HTML から 1 行ぶんを切り出す。 */
function rowOf(p,id){{
  const at=p.text.indexOf('data-cp="'+id+'"');
  if(at<0) return null;
  const s=p.text.lastIndexOf('<tr ',at), e=p.text.indexOf('</tr>',at);
  return (s<0||e<0)?null:p.text.slice(s,e+5);
}}

let hist=[], at=-1, seen=new Set();
function weighted(){{
  let n=Math.random()*TOTAL;
  for(const [s,c] of Object.entries(COLS)) if((n-=c)<0) return s;
  return Object.keys(COLS)[0];
}}
async function draw(){{
  // 同じ字が続けて出ないように、一度出したものは覚えておく。全部出したら
  // 忘れて最初から。
  if(seen.size>=TOTAL) seen.clear();
  for(let i=0;i<60;i++){{
    const slug=weighted(), p=await load(slug);
    if(!p.ids.length) continue;
    const id=p.ids[Math.random()*p.ids.length|0];
    if(seen.has(slug+' '+id)) continue;
    seen.add(slug+' '+id);
    return [slug,id];
  }}
  return null;
}}
async function show(slug,id){{
  const p=await load(slug), tr=rowOf(p,id);
  if(!tr){{ card.innerHTML='<p class="err">'+id+' が '+slug+' に見つからない</p>'; return; }}
  card.innerHTML='<table>'+p.colgroup+p.thead+'<tbody>'+tr+'</tbody></table>';
  for(const d of card.querySelectorAll('details.dt')) d.open=true;
  fromEl.innerHTML='<a href="../'+slug+'/">'+TITLES[slug]+'</a> より';
  posEl.textContent=(at+1)+' 字目 / 全 '+TOTAL.toLocaleString()+' 字';
  save();
}}
async function step(d){{
  if(d>0&&at>=hist.length-1){{
    const pick=await draw();
    if(!pick) return;
    hist.push(pick);
  }}
  at=Math.max(0,Math.min(hist.length-1,at+d));
  scrollTo(0,0);
  await show(...hist[at]);
}}

// ⌘R で同じ字に戻る。辿った道もそのまま。
const KEY='kanji:lucky:view';
function save(){{
  try{{ sessionStorage.setItem(KEY,JSON.stringify({{hist:hist,at:at}})); }}catch(e){{}}
}}
async function boot(){{
  let v=null;
  try{{ v=JSON.parse(sessionStorage.getItem(KEY)||'null'); }}catch(e){{}}
  if(v&&v.hist&&v.hist.length){{
    hist=v.hist; at=Math.min(v.at,hist.length-1);
    seen=new Set(hist.map(h=>h[0]+' '+h[1]));
    await show(...hist[at]);
  }} else {{
    await step(1);
  }}
}}
document.getElementById('nx').addEventListener('click',()=>step(1));
document.getElementById('prev').addEventListener('click',()=>step(-1));
addEventListener('keydown',e=>{{
  if(e.metaKey||e.ctrlKey||e.altKey) return;
  if(e.target.closest('input,textarea,select')) return;
  if(e.key==='ArrowRight'||e.key===' ') {{ e.preventDefault(); step(1); }}
  else if(e.key==='ArrowLeft') {{ e.preventDefault(); step(-1); }}
}});
boot();
</script>
</body></html>
"""


def main():
    cols, titles, nav = {}, {}, ['<a href="../">漢字</a>', "<b>ひとつずつ</b>"]
    for c in toml("collections.toml")["collection"]:
        meta = DOCS / c["slug"] / "meta.json"
        t = html.escape(c["title"])
        if not meta.exists():
            log(f"  docs/{c['slug']}/meta.json が無いので、母集団に入れない")
            nav.append(f'<span class="soon">{t}</span>')
            continue
        cols[c["slug"]] = json.loads(meta.read_text(encoding="utf-8"))["count"]
        titles[c["slug"]] = c["title"]
        nav.append(f'<a href="../{c["slug"]}/">{t}</a>')
    if not cols:
        raise SystemExit("一覧が 1 つも無いので、ひとつずつ引くページは作れない")

    out = DOCS / "lucky"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(TEMPLATE.format(
        style=STYLE, nav=" · ".join(nav), total=sum(cols.values()),
        cols=json.dumps(cols, ensure_ascii=False),
        titles=json.dumps(titles, ensure_ascii=False),
        now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")), encoding="utf-8")
    log(f"{out / 'index.html'} を書いた (母集団 {sum(cols.values()):,} 字)")


if __name__ == "__main__":
    main()
