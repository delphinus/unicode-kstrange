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


def toml(name: str) -> dict:
    return tomllib.loads((DATA / name).read_text(encoding="utf-8"))
