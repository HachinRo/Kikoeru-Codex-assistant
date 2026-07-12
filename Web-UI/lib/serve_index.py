#!/usr/bin/env python3
"""Build the ASMR stack serve-index as a flat symlink mirror of ASMR_LIBRARY_ROOT (default /Volumes/TOSHIBA/AMSR)/.

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
import tempfile
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


def _build_index_tree(source_root: Path, build_root: Path) -> tuple[int, int, int]:
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
        target = build_root / rj
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


def _replace_index(build_root: Path, index_root: Path) -> None:
    """Install a completed index, restoring the old one if the swap fails."""
    backup_root = Path(tempfile.mkdtemp(
        prefix=f".{index_root.name}.backup-", dir=index_root.parent
    ))
    backup_root.rmdir()
    had_index = index_root.exists() or index_root.is_symlink()
    if had_index:
        os.replace(index_root, backup_root)
    try:
        os.replace(build_root, index_root)
    except BaseException:
        if had_index:
            try:
                os.replace(backup_root, index_root)
            except BaseException as restore_error:
                raise RuntimeError(
                    f"index install failed and backup restore failed; "
                    f"old index remains at {backup_root}"
                ) from restore_error
        raise
    if backup_root.exists() or backup_root.is_symlink():
        if backup_root.is_dir() and not backup_root.is_symlink():
            shutil.rmtree(backup_root)
        else:
            backup_root.unlink()


def build_index(source_root: Path, index_root: Path) -> tuple[int, int, int]:
    if not source_root.is_dir():
        print(f"source root missing: {source_root}", file=sys.stderr)
        return 0, 0, 0

    index_root.parent.mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(
        prefix=f".{index_root.name}.build-", dir=index_root.parent
    ))
    try:
        result = _build_index_tree(source_root, build_root)
        _replace_index(build_root, index_root)
        return result
    finally:
        if build_root.exists():
            shutil.rmtree(build_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("ASMR_LIBRARY_ROOT") or os.environ.get("ASMR_MEDIA_ROOT") or "/Volumes/TOSHIBA/AMSR",
        help="Library root (default: /Volumes/TOSHIBA/AMSR).",
    )
    parser.add_argument(
        "--index",
        default=os.environ.get(
            "ASMR_SERVE_INDEX_ROOT",
            str(Path(__file__).resolve().parent.parent / "serve-index"),
        ),
        help="Symlink index root (default: <ASMR_STACK_ROOT>/serve-index).",
    )
    args = parser.parse_args()
    indexed, skipped, links = build_index(Path(args.source), Path(args.index))
    print(f"Indexed {indexed} works, skipped {skipped}, {links} file links -> {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
