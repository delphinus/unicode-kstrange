#!/usr/bin/env python3
"""Unicode 側の入力データを cache/ に取得し、版と SHA-256 を manifest.json に残す。

    python3 scripts/fetch_inputs.py [--force]
"""
import argparse
import datetime

from common import INPUTS, UNICODE_VERSION, UTN43_REVISION, fetch, log, sha256, write_manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して取り直す")
    args = ap.parse_args()

    m = {
        "unicode_version": UNICODE_VERSION,
        "utn43_revision": UTN43_REVISION,
        "fetched_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": {},
    }
    for name, url in INPUTS.items():
        p = fetch(name, url, force=args.force)
        m["files"][name] = {"url": url, "sha256": sha256(p), "bytes": p.stat().st_size}
        log(f"  {name}  {p.stat().st_size:>9,} bytes  {m['files'][name]['sha256'][:16]}…")
    write_manifest(m)
    log(f"cache/manifest.json を更新した ({len(m['files'])} 件)")


if __name__ == "__main__":
    main()
