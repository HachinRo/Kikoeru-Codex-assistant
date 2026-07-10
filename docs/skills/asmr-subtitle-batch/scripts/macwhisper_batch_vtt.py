#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import unicodedata
from pathlib import Path

MEDIA_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".mp4", ".mov", ".mkv"}
SOURCE_PREF = {".mp3": 0, ".m4a": 1, ".flac": 2, ".ogg": 3, ".opus": 4, ".mp4": 5, ".mov": 6, ".mkv": 7, ".wav": 8}
DB = Path.home() / "Library/Application Support/MacWhisper/Database/main.sqlite"
MW = "/Applications/MacWhisper.app/Contents/MacOS/mw"
KANA_RE = re.compile(r"[\u3040-\u30ff]")
TIMING_RE = re.compile(r"^\d\d:\d\d:\d\d\.\d{3} --> ")
LEADING_TRACK_RE = re.compile(r"^\s*([0-9０-９]{1,3})(?![0-9０-９])")
TRACK_STEM_RE = re.compile(r"^((?:Track|Chapter)[0-9０-９]{1,3}|Extrack)[_＿](.+)$", re.IGNORECASE)
SECUT_SUFFIX_RE = re.compile(r"\s*[（(]\s*SE\s*Cut\s*[）)]\s*$", re.IGNORECASE)
BAD_VTT_NAME_RE = re.compile(r"\.(?:mp3|wav|flac|m4a|ogg|opus|mp4|mov|mkv)\.vtt$", re.IGNORECASE)
RJ_PART_RE = re.compile(r"^RJ[0-9]+$", re.IGNORECASE)
FORMAT_PREFIX_RE = re.compile(
    r"^\(?(?:mp3|wav|wave|flac|m4a|aac|ogg|opus|video)\)?(?:版)?(?=$|[\s._＿-])[\s._＿-]*",
    re.IGNORECASE,
)
WRAPPER_ONLY_RE = re.compile(
    r"^(?:[0-9０-９]{1,3}[\s._＿-]*)?"
    r"(?:mp3|wav|wave|flac|m4a|aac|ogg|opus|audio|video|動画|音声(?:データ|ファイル)?|字幕|subtitles?|with japanese subtitled)$",
    re.IGNORECASE,
)
VARIANT_FOLDER_RE = re.compile(
    r"^(?:[0-9０-９]{1,3}[\s._＿-]*)?"
    r"(?:main|本編|差分(?:ファイル)?|se\s*(?:あり|なし|cut)|効果音(?:あり|なし)|bgm(?:あり|なし)|反転|位置反転|アレンジ|改[編编])"
    r"(?:[（(].*[）)])?$",
    re.IGNORECASE,
)
VARIANT_SUFFIX_RE = re.compile(
    r"(?:[\s_＿.-]*[（(\[]?(?:SE\s*(?:あり|なし|Cut)|効果音(?:あり|なし)(?:[（(][^）)]*[）)])?|BGM(?:あり|なし)|重低音なし|射精ボイスなし|位置反転|反転|アレンジ|改[編编])[）)\]]?)+$",
    re.IGNORECASE,
)
PREFIX_VARIANT_RE = re.compile(r"^(?:位置)?反転[\s._＿-]*", re.IGNORECASE)
SESSION_NOTE_RE = re.compile(r"^NOTE Generated from MacWhisper session ([0-9A-F]+);", re.MULTILINE)
DURATION_CACHE: dict[str, int] = {}
SHA_CACHE: dict[str, str] = {}
GROUPS_CACHE: dict[str, dict[str, list[Path]]] = {}


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def fmt_ms(ms: int) -> str:
    h, rem = divmod(int(ms), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"


def media(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXTS)


def duration_ms(path: Path) -> int:
    cache_key = str(path)
    if cache_key in DURATION_CACHE:
        return DURATION_CACHE[cache_key]
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    DURATION_CACHE[cache_key] = int(round(float(proc.stdout.strip() or 0) * 1000))
    return DURATION_CACHE[cache_key]


def content_scope(path: Path) -> str:
    """Return semantic parent folders while ignoring format/variant wrappers."""
    parts = list(path.parts[:-1])
    for idx in range(len(parts) - 1, -1, -1):
        if RJ_PART_RE.fullmatch(unicodedata.normalize("NFKC", parts[idx])):
            parts = parts[idx + 1 :]
            break
    meaningful = []
    for part in parts:
        value = unicodedata.normalize("NFKC", nfc(part)).strip()
        subtitle_video_wrapper = "字幕" in value and any(marker in value.casefold() for marker in ("動画", "动画", "video", "音声"))
        if not value or subtitle_video_wrapper or WRAPPER_ONLY_RE.fullmatch(value) or VARIANT_FOLDER_RE.fullmatch(value):
            continue
        value = FORMAT_PREFIX_RE.sub("", value).strip(" ._＿-")
        if not value or WRAPPER_ONLY_RE.fullmatch(value) or VARIANT_FOLDER_RE.fullmatch(value):
            continue
        meaningful.append(value.casefold())
    return "/".join(meaningful[-2:])


def canonical_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", nfc(value)).strip()
    value = SECUT_SUFFIX_RE.sub("", value)
    previous = None
    while value != previous:
        previous = value
        value = VARIANT_SUFFIX_RE.sub("", value).strip(" ._＿-")
    return re.sub(r"\s+", " ", value).casefold()


def track_identity(path: Path) -> tuple[str, str] | None:
    stem = unicodedata.normalize("NFKC", nfc(path.stem)).strip()
    stem = PREFIX_VARIANT_RE.sub("", stem)
    match = TRACK_STEM_RE.match(stem)
    if match:
        raw_track = unicodedata.normalize("NFKC", match.group(1))
        number = re.search(r"[0-9]+", raw_track)
        token = f"{int(number.group(0)):03d}" if number else "extra"
        title = canonical_title(match.group(2)) if raw_track.casefold() == "extrack" else ""
        return token, title
    match = LEADING_TRACK_RE.match(stem)
    if not match:
        return None
    digits = unicodedata.normalize("NFKC", match.group(1))
    title = stem[match.end() :].lstrip(" ._＿-）)]】")
    return f"{int(digits):03d}", canonical_title(title)


def group_key(path: Path) -> str:
    scope = content_scope(path)
    identity = track_identity(path)
    if identity:
        token, title = identity
        return f"track:{scope}:{token}:{title or '~'}"
    return f"stem:{scope}:{canonical_title(path.stem)}"


def groups(root: Path) -> dict[str, list[Path]]:
    cache_key = str(root)
    if cache_key in GROUPS_CACHE:
        return GROUPS_CACHE[cache_key]
    out: dict[str, list[Path]] = {}
    for path in media(root):
        out.setdefault(group_key(path), []).append(path)
    GROUPS_CACHE[cache_key] = out
    return out


def choose_source(paths: list[Path]) -> Path:
    def priority(path: Path) -> tuple[int, int, int, str]:
        text = nfc(str(path))
        stem = nfc(path.stem)
        variant_penalty = 0
        if "/差分/" in text or "/差分ファイル/" in text:
            variant_penalty += 10
        if "なし" in stem or "無し" in stem:
            variant_penalty += 5
        if "/With Japanese subtitled/" in text:
            variant_penalty += 10
        return (variant_penalty, SOURCE_PREF.get(path.suffix.lower(), 99), path.stat().st_size, str(path))

    return sorted(paths, key=priority)[0]


def source_files(root: Path) -> list[Path]:
    chosen = []
    for paths in groups(root).values():
        chosen.append(choose_source(paths))
    return sorted(chosen, key=lambda p: str(p))


def file_sha256(path: Path) -> str:
    cache_key = str(path)
    if cache_key in SHA_CACHE:
        return SHA_CACHE[cache_key]
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    SHA_CACHE[cache_key] = digest.hexdigest()
    return SHA_CACHE[cache_key]


def require_work(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"work directory does not exist: {root}")
    if not media(root):
        raise SystemExit(f"work directory contains no supported media: {root}")
    return root


def connect(db: Path) -> sqlite3.Connection:
    db = db.expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"MacWhisper database does not exist: {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def session_for(con: sqlite3.Connection, source: Path) -> sqlite3.Row | None:
    dur = duration_ms(source) / 1000
    sha = file_sha256(source)
    exact = con.execute(
        "select hex(id) as id, originalFilename, originalExtension, originalFileHash from session "
        "where originalFileHash=? and transcriptionDidSucceed=1 "
        "order by dateCreated desc limit 1",
        (sha,),
    ).fetchone()
    if exact:
        return exact
    candidates = []
    rows = con.execute(
        "select hex(id) as id, originalFilename, originalExtension, originalFileHash, playbackDuration from session "
        "where originalExtension=? and transcriptionDidSucceed=1 and playbackDuration between ? and ? "
        "order by dateCreated desc",
        (source.suffix.lower().lstrip("."), dur - 2, dur + 2),
    )
    for row in rows:
        if nfc(row["originalFilename"]) == nfc(source.stem):
            candidates.append(row)
    if not candidates:
        return None
    for row in candidates:
        if row["originalFileHash"] == sha:
            return row
    return None


def cues(con: sqlite3.Connection, session_id: str) -> list[dict[str, object]]:
    rows = con.execute(
        "select orderIndex,start,end,text from transcriptline where hex(sessionId)=? "
        "order by coalesce(orderIndex,0),start,end",
        (session_id,),
    )
    out = []
    for idx, row in enumerate(rows, 1):
        text = str(row["text"]).strip()
        if text:
            out.append({"id": f"cue-{idx}", "index": idx, "start": int(row["start"]), "end": int(row["end"]), "text": text})
    return out


def targets(root: Path, source: Path) -> list[Path]:
    return [p.with_suffix(".vtt") for p in groups(root).get(group_key(source), [])]


def resolve_source(root: Path, track: dict[str, object]) -> Path:
    if track.get("source"):
        source = Path(str(track["source"])).expanduser().resolve()
    else:
        source = next((p for p in source_files(root) if nfc(p.stem) == nfc(str(track.get("stem", "")))), None)
        if source is None:
            raise SystemExit(f"missing source for {track.get('stem')}")
        source = source.resolve()
    try:
        source.relative_to(root)
    except ValueError:
        raise SystemExit(f"translation source is outside work directory: {source}")
    if not source.is_file() or source.suffix.lower() not in MEDIA_EXTS:
        raise SystemExit(f"translation source is not supported media: {source}")
    return source


def cmd_inspect(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    for source in source_files(root):
        sess = session_for(con, source)
        count = len(cues(con, sess["id"])) if sess else 0
        target_list = targets(root, source)
        done = sum(1 for t in target_list if t.exists())
        print(f"{source.stem}\tsource={source.suffix.lower()}\tsession={bool(sess)}\tcues={count}\tsidecars={done}/{len(target_list)}")
    return 0


def cmd_transcribe_missing(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    for source in source_files(root):
        if session_for(con, source):
            continue
        print(f"[mw] {source}")
        subprocess.run([args.mw, "transcribe", str(source), "--persist"], check=True)
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    tracks = []
    for source in source_files(root):
        target_list = targets(root, source)
        if not args.all and all(t.exists() for t in target_list):
            continue
        sess = session_for(con, source)
        if not sess:
            raise SystemExit(f"missing MacWhisper session for {source}")
        tracks.append({"stem": source.stem, "key": group_key(source), "session": sess["id"], "source": str(source), "targets": [str(t) for t in target_list], "items": cues(con, sess["id"])})
    payload = {"work": str(root), "tracks": tracks}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    Path(args.out).write_text(text, encoding="utf-8") if args.out else print(text)
    return 0


def translation_texts(track: dict[str, object]) -> list[str] | None:
    values = track.get("translations") or track.get("translated") or track.get("zh")
    if values is not None:
        return [str(value).strip() for value in values]  # type: ignore[arg-type]
    items = track.get("items")
    if isinstance(items, list) and all(isinstance(item, dict) and "text" in item for item in items):
        return [str(item["text"]).strip() for item in items]
    return None


def check_translation_values(stem: str, values: list[str], allow_kana: bool = False) -> int:
    bad = 0
    for idx, value in enumerate(values, 1):
        if not value:
            print(f"EMPTY\t{stem}\t{idx}")
            bad += 1
        elif not allow_kana and KANA_RE.search(value):
            print(f"KANA\t{stem}\t{idx}\t{value[:80]}")
            bad += 1
    return bad


def cmd_pack(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    tracks = []
    total_cues = 0
    for source in source_files(root):
        target_list = targets(root, source)
        if not args.all and all(t.exists() for t in target_list):
            continue
        if args.stem and args.stem not in source.stem:
            continue
        sess = session_for(con, source)
        if not sess:
            if args.skip_missing:
                continue
            raise SystemExit(f"missing MacWhisper session for {source}")
        items = cues(con, sess["id"])
        if args.max_cues and tracks and total_cues + len(items) > args.max_cues:
            break
        tracks.append(
            {
                "stem": source.stem,
                "source": str(source),
                "count": len(items),
                "target_count": len(target_list),
                "texts": [str(item["text"]) for item in items],
            }
        )
        total_cues += len(items)
        if args.max_tracks and len(tracks) >= args.max_tracks:
            break
    payload = {
        "schema": "asmr-simple-v1",
        "work": str(root),
        "instructions": "Translate each texts entry to Simplified Chinese. Return tracks with source and same-length translations arrays only.",
        "track_count": len(tracks),
        "cue_count": total_cues,
        "tracks": tracks,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    Path(args.out).write_text(text, encoding="utf-8") if args.out else print(text)
    return 0


def cmd_apply_simple(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    data = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    con = connect(Path(args.db).expanduser())
    bad = 0
    writes: list[tuple[Path, str]] = []
    for track in data["tracks"]:
        source = resolve_source(root, track)
        sess = session_for(con, source)
        if not sess:
            raise SystemExit(f"missing MacWhisper session for {source}")
        source_cues = cues(con, sess["id"])
        values = translation_texts(track)
        if values is None:
            raise SystemExit(f"missing translations for {source.stem}")
        if len(values) != len(source_cues):
            print(f"COUNT\t{source.stem}\t{len(values)}/{len(source_cues)}")
            bad += 1
            continue
        bad += check_translation_values(source.stem, values, args.allow_kana)
        lookup = {str(cue["id"]): value for cue, value in zip(source_cues, values)}
        text = render(sess["id"], source_cues, lookup)
        for out in targets(root, source):
            writes.append((out, text))
    if bad:
        return 1
    if args.dry_run:
        print(f"OK\ttracks={len(data['tracks'])}\twrites={len(writes)}")
        return 0
    for out, text in writes:
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, out)
        print(out)
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    bad = 0
    total = 0
    for track in data["tracks"]:
        stem = str(track.get("stem") or Path(str(track.get("source", ""))).stem)
        values = translation_texts(track)
        if values is None:
            print(f"MISSING\t{stem}")
            bad += 1
            continue
        total += len(values)
        bad += check_translation_values(stem, values, args.allow_kana)
    if not bad:
        print(f"OK\ttracks={len(data['tracks'])}\tcues={total}")
    return 1 if bad else 0


def cmd_todo(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    complete = available = pending = 0
    rows = []
    for source in source_files(root):
        target_list = targets(root, source)
        done = sum(1 for t in target_list if t.exists())
        sess = session_for(con, source)
        cue_count = len(cues(con, sess["id"])) if sess else 0
        if done == len(target_list):
            complete += 1
        elif sess:
            available += 1
            rows.append((cue_count, source.stem, done, len(target_list)))
        else:
            pending += 1
    print(f"complete_groups {complete} available_untranslated {available} pending_transcription {pending}")
    for cue_count, stem, done, total in sorted(rows):
        print(f"{cue_count}\t{stem}\t{done}/{total}")
    return 0


def render(session_id: str, source_cues: list[dict[str, object]], lookup: dict[str, str]) -> str:
    lines = ["WEBVTT", "", f"NOTE Generated from MacWhisper session {session_id}; translated to Simplified Chinese by Codex", ""]
    for cue in source_cues:
        cid = str(cue["id"])
        if cid not in lookup:
            raise SystemExit(f"missing translation for {cid}")
        lines += [str(cue["index"]), f"{fmt_ms(int(cue['start']))} --> {fmt_ms(int(cue['end']))}", lookup[cid], ""]
    return "\n".join(lines)


def cmd_apply(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    data = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    con = connect(Path(args.db).expanduser())
    for track in data["tracks"]:
        source = resolve_source(root, track)
        sess = session_for(con, source)
        if not sess:
            raise SystemExit(f"missing MacWhisper session for {source}")
        lookup = {item["id"]: item["text"] for item in track["items"]}
        text = render(sess["id"], cues(con, sess["id"]), lookup)
        for out in targets(root, source):
            tmp = out.with_name(out.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, out)
            print(out)
    return 0


def generated_session_id(path: Path) -> str | None:
    try:
        match = SESSION_NOTE_RE.search(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None
    return match.group(1).upper() if match else None


def session_by_id(con: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return con.execute(
        "select hex(id) as id, originalFilename, originalExtension, originalFileHash "
        "from session where hex(id)=? limit 1",
        (session_id.upper(),),
    ).fetchone()


def cmd_audit(args: argparse.Namespace) -> int:
    """Find helper-generated VTTs whose MacWhisper session belongs to another track."""
    root = require_work(Path(args.work))
    con = connect(Path(args.db))
    generated = 0
    mismatches = []
    for key, paths in groups(root).items():
        for media_path in paths:
            vtt = media_path.with_suffix(".vtt")
            if not vtt.is_file():
                continue
            actual_id = generated_session_id(vtt)
            if not actual_id:
                continue
            generated += 1
            actual = session_by_id(con, actual_id)
            reason = None
            if actual is None:
                reason = "session_missing_from_macwhisper_db"
            else:
                identity = track_identity(media_path)
                target_title = identity[1] if identity else canonical_title(media_path.stem)
                session_name = str(actual["originalFilename"] or "")
                session_identity = track_identity(Path(session_name))
                session_title = session_identity[1] if session_identity else canonical_title(session_name)
                if target_title and session_title and target_title != session_title:
                    reason = "session_filename_differs_from_media"
            if reason:
                mismatches.append(
                    {
                        "reason": reason,
                        "group": key,
                        "media": str(media_path),
                        "vtt": str(vtt),
                        "actual_session": actual_id,
                        "session_filename": str(actual["originalFilename"] or "") if actual else None,
                    }
                )
    payload = {
        "work": str(root),
        "generated_sidecars": generated,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    if args.json or args.out:
        if args.json:
            print(rendered)
        elif args.out:
            print(f"audit_report {args.out}")
        print(f"generated_sidecars {generated} mismatches {len(mismatches)}")
    else:
        print(f"generated_sidecars {generated} mismatches {len(mismatches)}")
        for item in mismatches:
            print(f"MISMATCH\t{item['reason']}\t{item['media']}\t{item['session_filename'] or '-'}")
    return 1 if mismatches else 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    con = connect(Path(args.db).expanduser())
    expected: dict[str, int] = {}
    for source in source_files(root):
        sess = session_for(con, source)
        if sess:
            expected[group_key(source)] = len(cues(con, sess["id"]))
    bad = 0
    for vtt in root.rglob("*.vtt"):
        if BAD_VTT_NAME_RE.search(vtt.name) or ".zh-Hans" in vtt.name:
            print(f"BADNAME\t{vtt}")
            bad += 1
    for path in media(root):
        vtt = path.with_suffix(".vtt")
        if not vtt.exists():
            print(f"BAD\t{vtt}")
            bad += 1
            continue
        lines = vtt.read_text(encoding="utf-8").splitlines()
        cue_count = sum(1 for line in lines if TIMING_RE.match(line))
        exp = expected.get(group_key(path))
        if exp is not None and cue_count != exp:
            print(f"CUECOUNT\t{cue_count}/{exp}\t{vtt}")
            bad += 1
            continue
        payload = "\n".join(line for line in lines if line and not line.isdigit() and not TIMING_RE.match(line) and not line.startswith(("WEBVTT", "NOTE")))
        if KANA_RE.search(payload):
            print(f"KANA\t{vtt}")
            bad += 1
        else:
            print(f"OK\t{cue_count}\t{vtt}")
    return 1 if bad else 0


def cmd_sweep(args: argparse.Namespace) -> int:
    root = require_work(Path(args.work))
    bad = 0
    count = 0
    for vtt in sorted(root.rglob("*.vtt")):
        count += 1
        if BAD_VTT_NAME_RE.search(vtt.name) or ".zh-Hans" in vtt.name:
            print(f"BADNAME\t{vtt}")
            bad += 1
            continue
        lines = vtt.read_text(encoding="utf-8").splitlines()
        cue_count = sum(1 for line in lines if TIMING_RE.match(line))
        if cue_count == 0:
            print(f"NOCUES\t{vtt}")
            bad += 1
            continue
        payload = "\n".join(
            line
            for line in lines
            if line and not line.isdigit() and not TIMING_RE.match(line) and not line.startswith(("WEBVTT", "NOTE"))
        )
        if not args.allow_kana and KANA_RE.search(payload):
            print(f"KANA\t{vtt}")
            bad += 1
    print(f"existing_vtts {count} bad {bad}")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DB))
    p.add_argument("--mw", default=MW)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("inspect", cmd_inspect), ("transcribe-missing", cmd_transcribe_missing), ("verify", cmd_verify), ("todo", cmd_todo)]:
        s = sub.add_parser(name); s.add_argument("work"); s.set_defaults(fn=fn)
    sweep = sub.add_parser("sweep")
    sweep.add_argument("work")
    sweep.add_argument("--allow-kana", action="store_true")
    sweep.set_defaults(fn=cmd_sweep)
    d = sub.add_parser("dump"); d.add_argument("work"); d.add_argument("--out"); d.add_argument("--all", action="store_true"); d.set_defaults(fn=cmd_dump)
    pack = sub.add_parser("pack")
    pack.add_argument("work")
    pack.add_argument("--out")
    pack.add_argument("--all", action="store_true")
    pack.add_argument("--skip-missing", action="store_true")
    pack.add_argument("--stem")
    pack.add_argument("--max-cues", type=int, default=0)
    pack.add_argument("--max-tracks", type=int, default=0)
    pack.set_defaults(fn=cmd_pack)
    simple = sub.add_parser("apply-simple")
    simple.add_argument("work")
    simple.add_argument("--translations", required=True)
    simple.add_argument("--dry-run", action="store_true")
    simple.add_argument("--allow-kana", action="store_true")
    simple.set_defaults(fn=cmd_apply_simple)
    qa = sub.add_parser("qa")
    qa.add_argument("--translations", required=True)
    qa.add_argument("--allow-kana", action="store_true")
    qa.set_defaults(fn=cmd_qa)
    a = sub.add_parser("apply"); a.add_argument("work"); a.add_argument("--translations", required=True); a.set_defaults(fn=cmd_apply)
    audit = sub.add_parser("audit")
    audit.add_argument("work")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--out")
    audit.set_defaults(fn=cmd_audit)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
