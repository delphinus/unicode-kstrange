#!/usr/bin/env python3
"""英国が IRG へ出した UK-source の提出文書から、字ごとの用例証拠を取り出して
cache/uk_source.json に残す。

    python3 scripts/fetch_uk_source.py

unicode-org/uk-source-ideographs には 3 通の提出文書が PDF で置いてある。
どれも Excel ファイルを添付として抱えていて、そこに UK-xxxxx 1 件ずつの
IDS・異体字・**用例証拠の書誌**・図版番号が入っている。PDF の本文を読まなくても、
この添付を開けば「どの本の何ページに出てくる字か」まで辿れる。

添付は PDF の中の zlib 圧縮ストリームなので、poppler を入れなくても
標準ライブラリだけで取り出せる (zip の署名 PK\\x03\\x04 で見分ける)。
"""
import json
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from io import BytesIO

from common import CACHE, fetch, log

RAW = "https://github.com/unicode-org/uk-source-ideographs/raw/main/{}.pdf"

# 文書ごとに列の並びが違う。値は 0 始まりの列番号。
DOCS = {
    "IRGN2107R2": {"label": "IRG N2107R2", "ws": "IRG Working Set 2015",
                   "src": 1, "ids": 7, "var": 8, "ev": 9, "fig": 10, "note": 16},
    "IRGN2232R": {"label": "IRG N2232R", "ws": "IRG Working Set 2017",
                  "src": 1, "ids": 7, "var": 8, "title": 10, "page": 11,
                  "fig": 12, "note": 17},
    "IRGN2487": {"label": "IRG N2487", "ws": "IRG Working Set 2021",
                 "src": 1, "ids": 10, "var": 11, "ev": 12, "fig": 13, "note": 14},
}

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def embedded_xlsx(pdf: bytes) -> bytes:
    """PDF が抱えている xlsx を取り出す。"""
    for m in re.finditer(rb"stream\r?\n", pdf):
        end = pdf.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            out = zlib.decompress(pdf[m.end():end])
        except zlib.error:
            continue
        if out[:4] == b"PK\x03\x04" and b"xl/workbook.xml" in out:
            return out
    raise SystemExit("PDF の中に xlsx が見つからない")


def column(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheet_rows(xlsx: bytes):
    """先頭シートを {列番号: 値} の列として返す。空のセルは現れない。"""
    z = zipfile.ZipFile(BytesIO(xlsx))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(M + "t")) for si in root]
    name = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    for row in ET.fromstring(z.read(name)).iter(M + "row"):
        cells = {}
        for c in row:
            v = c.find(M + "v")
            s = v.text if v is not None else ""
            if c.get("t") == "s" and s:
                s = shared[int(s)]
            elif c.get("t") == "inlineStr":
                s = "".join(x.text or "" for x in c.iter(M + "t"))
            if s:
                cells[column(c.get("r"))] = s.strip()
        yield cells


def citations(text: str) -> list[str]:
    """「{1} …; {2} …」や「… ; … ; …」を 1 件ずつに割る。"""
    if not text:
        return []
    parts = re.split(r"\s*;\s*(?=\{|\S)", text) if ";" in text else [text]
    out = []
    for p in parts:
        p = re.sub(r"^\{\d+\}\s*", "", p).strip(" ;")
        if p:
            out.append(p)
    return out


def main():
    out: dict[str, dict] = {}
    for name, col in DOCS.items():
        path = fetch(f"{name}.pdf", RAW.format(name))
        rows = list(sheet_rows(embedded_xlsx(path.read_bytes())))
        n = 0
        for cells in rows[1:]:                      # 1 行目は見出し
            sid = cells.get(col["src"], "")
            if not re.fullmatch(r"UK-\d{5}", sid):
                continue
            if "title" in col:                      # N2232R は書名とページが別の列
                title = cells.get(col["title"], "")
                page = cells.get(col["page"], "")
                ev = [f"{title} p. {page}" if page else title] if title else []
            else:
                ev = citations(cells.get(col["ev"], ""))
            rec = {"doc": col["label"], "ws": col["ws"], "evidence": ev}
            for key in ("ids", "var", "fig", "note"):
                if cells.get(col.get(key, -1)):
                    rec[key] = cells[col[key]]
            out[sid] = rec
            n += 1
        log(f"  {col['label']}: {n} 件")

    CACHE.mkdir(exist_ok=True)
    (CACHE / "uk_source.json").write_text(
        json.dumps(out, indent=0, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")
    log(f"UK-source {len(out)} 件を cache/uk_source.json に書いた")


if __name__ == "__main__":
    main()
