#!/usr/bin/env python3
"""UTN #43 の PDF の記述と Unihan の実データを比べる (任意。poppler が要る)。

    python3 scripts/check_utn43.py

見るもの:
  * 各カテゴリの本文にある「covering N Han ideographs」と、Unihan の件数
  * PDF の表に並んでいるコードポイントと、Unihan で同じカテゴリが付く字

2026-09-21 時点の tn43-5 では Category S の本文が「24」、表と Unihan は 26 字でずれている。
"""
import collections
import re
import shutil
import subprocess

from common import UTN43_REVISION, fetch, log, unihan

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def pdf_text():
    if not shutil.which("pdftotext"):
        raise SystemExit("pdftotext が無い (brew install poppler)")
    pdf = fetch(f"{UTN43_REVISION}.pdf")
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout


def main():
    text = pdf_text()
    uni = unihan()

    actual = collections.Counter()
    by_cat = collections.defaultdict(set)
    for cp, v in uni.items():
        for tok in v.get("kStrange", "").split():
            c = tok.split(":")[0]
            actual[c] += 1
            by_cat[c].add(cp)

    # 本文の「covering N Han ideographs」。節ごとに区切ってから探す
    # (文書全体に対して非貪欲マッチを掛けると、別の節の文を拾ってしまう)
    log("== 本文の件数と Unihan の件数 ==")
    chunks = re.split(r"Category ([A-Z])—", text)[1:]
    found = 0
    for cat, body in zip(chunks[::2], chunks[1::2]):
        m = re.search(r"covering (\S+) Han ideographs", body)
        if not m:
            continue
        found += 1
        said = WORDS.get(m[1].lower(), m[1])
        got = actual[cat]
        mark = "" if str(said) == str(got) else "   ← ずれ"
        log(f"  {cat}: 本文 {said} / Unihan {got}{mark}")
    if not found:
        log("  (件数を書いている節が無い)")

    # 表の行と Unihan
    log("== 表のコードポイントと Unihan ==")
    rows = collections.defaultdict(set)
    for m in re.finditer(r"^ +([A-Z]) +[A-Z]+ +(U\+[0-9A-F]+)", text, re.M):
        rows[m[1]].add(m[2])
    for cat in sorted(rows):
        only_pdf = rows[cat] - by_cat[cat]
        only_uni = by_cat[cat] - rows[cat]
        if only_pdf or only_uni:
            log(f"  {cat}: PDF のみ {sorted(only_pdf)} / Unihan のみ {sorted(only_uni)}")
        else:
            log(f"  {cat}: 一致 ({len(rows[cat])} 字)")


if __name__ == "__main__":
    main()
