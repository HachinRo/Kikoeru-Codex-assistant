#!/usr/bin/env python3
"""
ask-file-list: list files for a Neokikoeru work via the local SQLite DB.

v3.7.1's WebUI has no native file list view, and `/api/v1/fs/list` returns
404. The actual source of truth is the SQLite `files` table. This script
mirrors the `/api/v1/fs/download?file_id=<id>` URL format so a click
on a file_id can be copy-pasted into a `curl` command.

Usage:
    ask-file-list                          # all works, summary
    ask-file-list RJ01010222               # files for one work
    ask-file-list --biggest 5              # top 5 files by size
    ask-file-list --no-audio RJ01010222    # subtitles/text only
    ask-file-list --json RJ01010222        # JSON output
    ask-file-list --download RJ01010222 3  # print the curl command for file #3
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / "Library/Application Support/neokikoeru/neokikoeru.db"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STACK_ROOT = PROJECT_ROOT / "Web-UI"
STACK_ROOT = Path(os.environ.get("ASMR_STATE_ROOT") or os.environ.get("ASMR_STACK_ROOT") or DEFAULT_STACK_ROOT)
CFG_PATH = STACK_ROOT / "serve-config.json"
API_BASE = "http://localhost:8889/api/v1"
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
SUB_EXTS = {".lrc", ".vtt", ".srt", ".ass", ".ssa"}


def db():
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH} (is Neokikoeru running and the data dir present?)")
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def get_token() -> str | None:
    if not CFG_PATH.exists():
        return None
    try:
        return json.loads(CFG_PATH.read_text())["token"]
    except Exception:
        return None


def is_audio_row(row) -> bool:
    return Path(row["name"]).suffix.lower() in AUDIO_EXTS


def is_sub_row(row) -> bool:
    return Path(row["name"]).suffix.lower() in SUB_EXTS


def list_all_work_summaries(con):
    rows = con.execute(
        """
        SELECT work_id,
               COUNT(*) AS file_count,
               SUM(size) AS total_size,
               SUM(CASE WHEN name LIKE '%.mp3' OR name LIKE '%.wav'
                         OR name LIKE '%.flac' OR name LIKE '%.m4a'
                         OR name LIKE '%.aac' OR name LIKE '%.ogg'
                         OR name LIKE '%.opus' THEN 1 ELSE 0 END) AS audio_count,
               SUM(CASE WHEN name LIKE '%.lrc' OR name LIKE '%.vtt'
                         OR name LIKE '%.srt' OR name LIKE '%.ass'
                         OR name LIKE '%.ssa' THEN 1 ELSE 0 END) AS sub_count
        FROM files
        WHERE is_folder = 0 AND work_id IS NOT NULL
        GROUP BY work_id
        ORDER BY work_id
        """
    ).fetchall()
    return rows


def list_files_for_work(con, work_id: str, audio_only=False, sub_only=False):
    where = "WHERE is_folder = 0 AND work_id = ?"
    params = [work_id]
    if audio_only:
        where += " AND (" + " OR ".join(["name LIKE ?" for _ in AUDIO_EXTS]) + ")"
        params.extend(f"%{ext}" for ext in AUDIO_EXTS)
    elif sub_only:
        where += " AND (" + " OR ".join(["name LIKE ?" for _ in SUB_EXTS]) + ")"
        params.extend(f"%{ext}" for ext in SUB_EXTS)
    rows = con.execute(
        f"SELECT id, name, path, size FROM files {where} ORDER BY name",
        params,
    ).fetchall()
    return rows


def main():
    global DB_PATH

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work", nargs="?", help="Work ID (e.g. RJ01010222). Omit for summary.")
    p.add_argument("--biggest", type=int, metavar="N", help="Show top N files by size")
    p.add_argument("--no-audio", action="store_true", help="Subtitles/text only")
    p.add_argument("--audio-only", action="store_true", help="Audio files only")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--download", type=int, metavar="N", help="Print curl command for the Nth file (1-based) of <work>")
    p.add_argument("--db", type=Path, default=DB_PATH, help=f"Override DB path (default: {DB_PATH})")
    args = p.parse_args()

    if args.db != DB_PATH:
        DB_PATH = args.db

    con = db()

    if args.biggest:
        rows = con.execute(
            "SELECT work_id, id, name, size FROM files WHERE is_folder=0 ORDER BY size DESC LIMIT ?",
            (args.biggest,),
        ).fetchall()
        if args.json:
            print(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False))
        else:
            print(f"Top {len(rows)} files by size:")
            for r in rows:
                print(f"  {fmt_size(r['size']):>10}  {r['work_id']}/{r['name']}  (id={r['id']})")
        return

    if not args.work:
        rows = list_all_work_summaries(con)
        if args.json:
            print(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False))
            return
        print(f"{'Work':<12}  {'Files':>6}  {'Audio':>6}  {'Subs':>5}  {'Total size':>12}")
        print("-" * 50)
        total_files = total_size = 0
        for r in rows:
            print(
                f"  {r['work_id']:<10}  {r['file_count']:>6}  {r['audio_count']:>6}  "
                f"{r['sub_count']:>5}  {fmt_size(r['total_size'] or 0):>12}"
            )
            total_files += r["file_count"]
            total_size += r["total_size"] or 0
        print("-" * 50)
        print(f"  {'TOTAL':<10}  {total_files:>6}                                    {fmt_size(total_size):>12}")
        print(f"\n  Use: ask-file-list RJ01010222  to see a specific work's files")
        print(f"  Use: ask-file-list --biggest 10  to find the largest files")
        return

    rows = list_files_for_work(con, args.work, audio_only=args.audio_only, sub_only=args.no_audio)
    if not rows:
        sys.exit(f"No files found for {args.work} (or work not indexed — run `asmr-library serve storage index 1`)")

    if args.download:
        if args.download < 1 or args.download > len(rows):
            sys.exit(f"--download N must be 1..{len(rows)} (got {args.download})")
        token = get_token()
        if not token:
            sys.exit(f"Token not found in {CFG_PATH} (run `asmr-library serve login admin <pw>`)")
        r = rows[args.download - 1]
        print(
            f"curl -H 'Authorization: Bearer *** {API_BASE}/fs/download?file_id={r['id']} "
            f"-o '{args.work}_{r['name']}'"
        )
        return

    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False))
        return

    print(f"{args.work}  ({len(rows)} files)")
    print(f"  {'#':>3}  {'Size':>10}  {'Kind':<6}  {'Name':<48}  file_id")
    print("  " + "-" * 90)
    for i, r in enumerate(rows, 1):
        kind = "audio" if is_audio_row(r) else "sub" if is_sub_row(r) else "other"
        print(f"  {i:>3}  {fmt_size(r['size']):>10}  {kind:<6}  {r['name']:<48}  {r['id']}")
    if any(is_audio_row(r) for r in rows):
        print(f"\n  To download file #N: ask-file-list {args.work} --download N")
    print(f"  Raw JSON: ask-file-list {args.work} --json")


if __name__ == "__main__":
    main()
