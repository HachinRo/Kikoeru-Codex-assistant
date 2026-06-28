#!/usr/bin/env python3
"""Build ~/.hermes/asmr/serve-index/ as a flat symlink mirror of ASMR_LIBRARY_ROOT (default ~/ASMR)/.

One directory per work, one symlink per file. No bucketing — Neokikoeru's local
storage driver walks RJ########/ in place and reads audio files where they are.
Skips any RJ whose directory contains .part / .partial / .tmp / .download /
.crdownload files or any zero-byte audio file. Failures are logged to stderr
and do not abort the whole build.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
PARTIAL_EXTS = {".part", ".partial", ".tmp", ".download", ".crdownload"}
RJ_PATTERN = re.compile(r"^RJ\d+$", re.IGNORECASE)


def is_complete(work: Path) -> tuple[bool, str]:
    has_audio = False
    for item in work.rglob("*"):
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix in PARTIAL_EXTS:
            return False, f"partial file present: {item.relative_to(work)}"
        if suffix in AUDIO_EXTS:
            if item.stat().st_size == 0:
                return False, f"zero-byte audio: {item.relative_to(work)}"
            has_audio = True
    if not has_audio:
        return False, "no non-empty audio file"
    return True, "ok"


def build_index(source_root: Path, index_root: Path) -> tuple[int, int, int]:
    if not source_root.is_dir():
        print(f"source root missing: {source_root}", file=sys.stderr)
        return 0, 0, 0
    if index_root.exists():
        shutil.rmtree(index_root)
    index_root.mkdir(parents=True, exist_ok=True)

    works_indexed = 0
    works_skipped = 0
    links_created = 0
    for work in sorted(source_root.iterdir()):
        if not work.is_dir() or not RJ_PATTERN.match(work.name):
            continue
        rj = work.name.upper()
        ok, reason = is_complete(work)
        if not ok:
            print(f"skip {rj}: {reason}", file=sys.stderr)
            works_skipped += 1
            continue
        target = index_root / rj
        target.mkdir(parents=True, exist_ok=True)
        for item in work.rglob("*"):
            if not item.is_file():
                continue
            link = target / item.relative_to(work)
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(item, link)
            except FileExistsError:
                pass
            links_created += 1
        works_indexed += 1
    return works_indexed, works_skipped, links_created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("ASMR_LIBRARY_ROOT", str(Path.home() / "ASMR")),
        help="Library root (default:  or ~/ASMR).",
    )
    parser.add_argument(
        "--index",
        default=os.environ.get(
            "ASMR_SERVE_INDEX_ROOT",
            str(Path.home() / ".hermes" / "asmr" / "serve-index"),
        ),
        help="Symlink index root (default: ~/.hermes/asmr/serve-index).",
    )
    args = parser.parse_args()
    indexed, skipped, links = build_index(Path(args.source), Path(args.index))
    print(f"Indexed {indexed} works, skipped {skipped}, {links} file links -> {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
