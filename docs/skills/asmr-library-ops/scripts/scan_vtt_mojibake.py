#!/usr/bin/env python3
"""Scan ASMR subtitle files for likely Chinese mojibake.

Usage:
    scan_vtt_mojibake.py [root]

Default root is /Volumes/TOSHIBA/AMSR.
The scanner is intentionally conservative: it flags common mojibake marker
characters and replacement characters, then prints affected RJ folders/files.
"""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_ROOT = Path("/Volumes/TOSHIBA/AMSR")
SUBTITLE_SUFFIXES = {".vtt", ".lrc", ".srt", ".ass"}
BAD_MARKERS = ("�", "è", "é", "å", "æ", "ã", "ä", "ï¼", "ã€", "çš", "çš„", "æˆ", "ä¸")


def looks_bad(text: str) -> bool:
    return any(marker in text for marker in BAD_MARKERS)


def find_rj(path: Path) -> str:
    for part in reversed(path.parts):
        upper = part.upper()
        if upper.startswith("RJ") and any(ch.isdigit() for ch in upper[2:]):
            return upper
    return "(unknown)"


def read_text_best_effort(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    affected: dict[str, list[Path]] = {}
    total = 0

    for path in args.root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUBTITLE_SUFFIXES:
            continue
        total += 1
        try:
            text = read_text_best_effort(path)
        except OSError as exc:
            print(f"read_error\t{path}\t{exc}")
            continue
        if looks_bad(text):
            affected.setdefault(find_rj(path), []).append(path)

    affected_files = sum(len(paths) for paths in affected.values())
    print(f"scanned_files {total}")
    print(f"affected_rjs {len(affected)}")
    print(f"affected_files {affected_files}")
    for rj in sorted(affected):
        print(rj)
        for path in affected[rj]:
            print(f"  {path}")

    return 1 if affected_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
