#!/usr/bin/env python3
"""zi.tools の API から字義と、その典拠になっている字書・論文を取り出して
cache/zi_tools.json に残す。

    python3 scripts/fetch_zi_tools.py [--category S|all] [--force]

zi.tools は 1 字ぶんの情報を `https://zi.tools/api/zi/<字>` で JSON で返す。
そのうち `yi.nodes` が字ごとの行で、値は 17 要素の配列になっている。

    [0] 行 ID        "K3-2122-0"
    [1] 出典タグ     "K3" (韓国の第 3 次提出) / "GHZR" (漢語大字典) / "ZITOOLS" (編集部)
    [2] 出典中の位置 "2122"
    [4] [5] [6] 字   "㐃"
    [7] 字義         "讀音마(ma)。錘子"
    [13] 注記        典拠の書誌・論文・URL、または韓国語の語釈

同じ字に複数の行が付くことがある (字書ごとに語釈が違う)。ここでは問い合わせた字と
一致する行だけを残す。Unihan の kDefinition は 828 字中 88 字にしか無いので、
これで語釈のある字が大きく増える。
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from common import CACHE, UA, log, targets, unihan

API = "https://zi.tools/api/zi/"
# 0.4 秒で叩いたところ、600 件あたりから応答が返らなくなった。1.5 秒では完走した。
# 応答は 1 件 20〜260 KB あるので、リクエスト数より転送量のほうが相手の負担になる。
# UK-source の 3,409 件だと 320 MB ほど出させることになる。急ぐ理由が無いので
# 0.1 req/s (9.5 KB/s) まで落とす。人が 1 人ゆっくり読んでいるのと変わらない水準。
# 3,409 件で 9 時間半掛かるが、取得済みは飛ばして再開できるので中断しても損はない。
WAIT = 10.0         # 1 件ごとに空ける間隔 (秒)
TIMEOUT = 30


def get(char: str, retries: int = 3) -> dict | None:
    """取れなければ None。1 字でも落とすと全体が止まるので、例外にはしない。"""
    url = API + urllib.parse.quote(char)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            if attempt == retries:
                return None
            time.sleep(3)
        except Exception:
            if attempt == retries:
                return None
            time.sleep(3)
    return None


# API が字義の代わりに返す記号。zi.tools の画面ではこう表示される。
# 「@」は 828 字中 40 字にあり、どれも漢語大字典の行。そのまま出しても読めないので
# 画面と同じ文字列に直しておく (U+204D9 の頁は「xiong4 (1) (义不详)」と出る)。
PLACEHOLDER = {"@": "义不详"}


def rows(doc: dict, char: str) -> list[dict]:
    """問い合わせた字の行だけを取り出す。"""
    out = []
    for node in (doc.get("yi", {}).get("nodes") or {}).values():
        if not isinstance(node, list) or len(node) < 14:
            continue
        if char not in (node[4], node[5], node[6]):
            continue
        entry = {"src": node[1] or "", "pos": node[2] or ""}
        if node[7]:
            entry["def"] = PLACEHOLDER.get(node[7].strip(), node[7].strip())
        if node[13]:
            entry["note"] = node[13].strip()
        if len(entry) > 2:
            out.append(entry)
    # 出典タグ順に並べて、同じ入力からは同じ出力が出るようにする
    return sorted(out, key=lambda e: (e["src"], e["pos"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="S")
    ap.add_argument("--uk", action="store_true",
                    help="kStrange ではなく UK-source の字を取る")
    ap.add_argument("--wait", type=float, default=WAIT,
                    help=f"1 件ごとに空ける間隔 (秒、既定 {WAIT})")
    ap.add_argument("--force", action="store_true",
                    help="取得済みの字も取り直す")
    args = ap.parse_args()

    uni = unihan()
    cps = (sorted((c for c in uni if uni[c].get("kIRG_UKSource")),
                  key=lambda x: int(x[2:], 16))
           if args.uk else targets(uni, args.category))
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "zi_tools.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    todo = [cp for cp in cps if args.force or cp not in known]
    log(f"{len(todo)} 字を取得 (取得済み {len(cps) - len(todo)} 字)")
    failed = []
    for i, cp in enumerate(todo, 1):
        char = chr(int(cp[2:], 16))
        doc = get(char)
        if doc is None:
            failed.append(cp)          # 記録しないので、次に流せば取り直す
        else:
            known[cp] = rows(doc, char)
        if i % 25 == 0 or i == len(todo):
            log(f"  {i} / {len(todo)}")
            path.write_text(json.dumps(known, indent=0, ensure_ascii=False,
                                       sort_keys=True), encoding="utf-8")
        time.sleep(args.wait)

    path.write_text(json.dumps(known, indent=0, ensure_ascii=False,
                               sort_keys=True), encoding="utf-8")
    n = sum(1 for cp in cps if any("def" in e for e in known.get(cp, [])))
    log(f"字義あり {n} / {len(cps)} 字")
    if failed:
        log(f"取れなかった {len(failed)} 字 (もう一度流せば取りに行く): "
            + " ".join(failed))


if __name__ == "__main__":
    main()
