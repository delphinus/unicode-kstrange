"""共通の定数とユーティリティ。標準ライブラリだけで動く。"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tomllib
import urllib.request
import zipfile

# 参照するデータの版。ここを変えると取得先が切り替わる。
UNICODE_VERSION = "18.0.0"
UTN43_REVISION = "tn43-5"          # UTN #43 (kStrange の解説) の版

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"
DOCS = ROOT / "docs"
GLYPHS = DOCS / "glyphs"

UA = "unicode-kstrange/1.0 (+https://github.com/delphinus/unicode-kstrange)"

INPUTS = {
    "Unihan.zip": f"https://www.unicode.org/Public/{UNICODE_VERSION}/ucd/Unihan.zip",
    "Blocks.txt": f"https://www.unicode.org/Public/{UNICODE_VERSION}/ucd/Blocks.txt",
    "USourceData.txt": f"https://www.unicode.org/Public/{UNICODE_VERSION}/ucd/USourceData.txt",
    "CJKRadicals.txt": f"https://www.unicode.org/Public/{UNICODE_VERSION}/ucd/CJKRadicals.txt",
    # UTN #43 の PDF は check_utn43.py (任意) でしか使わない
    f"{UTN43_REVISION}.pdf": f"https://www.unicode.org/notes/tn43/{UTN43_REVISION}.pdf",
}


def log(*a):
    print(*a, file=sys.stderr)


def fetch(name: str, url: str | None = None, force: bool = False) -> pathlib.Path:
    """cache/ に無ければ取得する。取得済みならそのまま返す。"""
    CACHE.mkdir(exist_ok=True)
    dest = CACHE / name
    url = url or INPUTS[name]
    if dest.exists() and not force:
        return dest
    log(f"  取得 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest() -> dict:
    """取得済み入力の版とハッシュ。生成物に埋めて出所を辿れるようにする。"""
    p = CACHE / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_manifest(m: dict):
    (CACHE / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False))


# ---- Unihan --------------------------------------------------------------
def unihan() -> dict[str, dict[str, str]]:
    """Unihan.zip を読んで {コードポイント: {プロパティ: 値}} にする。"""
    path = fetch("Unihan.zip")
    out: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.startswith("Unihan_"):
                continue
            for raw in z.read(name).decode("utf-8").splitlines():
                if raw.startswith("#") or raw.count("\t") != 2:
                    continue
                cp, prop, val = raw.split("\t")
                out.setdefault(cp, {})[prop] = val
    return out


def targets(uni: dict, category: str) -> list[str]:
    """kStrange を持つ字を返す。category='all' なら全部、'S' ならカテゴリ S だけ。"""
    got = []
    for cp, v in uni.items():
        ks = v.get("kStrange")
        if not ks:
            continue
        if category == "all" or any(t.split(":")[0] == category for t in ks.split()):
            got.append(cp)
    return sorted(got, key=lambda x: int(x[2:], 16))


def blocks() -> list[tuple[int, int, str]]:
    import re

    out = []
    for line in fetch("Blocks.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"([0-9A-F]+)\.\.([0-9A-F]+); (.+)", line)
        if m:
            out.append((int(m[1], 16), int(m[2], 16), m[3].strip()))
    return out


def usource() -> dict[str, dict]:
    """USourceData.txt を U-source 識別子で引けるようにする。"""
    out = {}
    for line in fetch("USourceData.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or ";" not in line:
            continue
        f = line.split(";")
        out[f[0]] = {"status": f[1], "cp": f[2], "rs": f[3], "ids": f[5],
                     "sources": f[6], "comment": f[7]}
    return out


def radicals() -> dict[str, str]:
    """部首番号 → その部首の字。kRSUnicode の 74.6 の 74 を引くための表。

    番号だけでは 74 (月) と 130 (肉) の区別が読み手に付かない。同じ形に見える
    字がこの 2 つに分かれていることがあるので、字のほうを添える。

    3 列目 (その部首だけでできた統合漢字) を使う。2 列目は康熙部首ブロックの
    記号で、持っていないフォントがある。簡体字の部首は番号に ' が付く
    (120' = 纟)。kRSUnicode 側も同じ書き方なのでそのまま引ける。
    """
    out = {}
    for line in fetch("CJKRadicals.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or ";" not in line:
            continue
        num, _, uni = (f.strip() for f in line.split(";"))
        out[num] = chr(int(uni, 16))
    return out


def toml(name: str) -> dict:
    return tomllib.loads((DATA / name).read_text(encoding="utf-8"))


# ---- 字形 ----------------------------------------------------------------
def needs_glyph(ch: str) -> bool:
    """この字はフォントが無くて豆腐になりうるか。

    基本ブロック (URO) の字はどの環境にもあるが、拡張 A 以降は無いことが多い。
    macOS の標準フォントは拡張 B より後をほとんど持っていない。当たった字は
    GlyphWiki の SVG に差し替えて出す。

    IDS の記号 (⿰⿱⿳…) も入れてある。基本多言語面だが持っていないフォントが
    多く、まだ符号化されていない字の構成式を出すときに豆腐になる。
    """
    n = ord(ch)
    return (0x2FF0 <= n <= 0x2FFF or 0x3400 <= n <= 0x4DBF
            or 0x20000 <= n <= 0x3FFFF)


def spoofing_pairs(uni) -> dict[str, list[str]]:
    """見間違えやすい字 → その相手。kSpoofingVariant を読む。

    値は「U+340B」や「U+2B7E6<kMatthews」のように、コードポイントの後ろに
    出所が付くことがある。相互に登録されていて、353 字で閉じている。
    """
    import re as _re
    out = {}
    for cp, v in uni.items():
        val = v.get("kSpoofingVariant")
        if not val:
            continue
        out[cp] = [f"U+{m[1]}" for t in val.split()
                   if (m := _re.match(r"U\+([0-9A-F]+)", t))]
    return out


def mentioned(texts) -> list[str]:
    """本文中に出てくる、字形が要る字を U+XXXX の形で返す。

    表の左端に出す 828 字のほかに、字義や用例の**文中**に出てくる字がある。
    そちらもフォントが無ければ読めないので、同じように SVG を用意する。
    """
    chars = {ch for t in texts if t for ch in t if needs_glyph(ch)}
    return sorted((f"U+{ord(c):04X}" for c in chars),
                  key=lambda x: int(x[2:], 16))
