"""asmr-view kikoeru bridge — kikoeru-quasar compatible API endpoints.

Adds these endpoints to asmr-view so the kikoeru-quasar SPA (or any
kikoeru-compatible client) can talk to our SQLite-backed store:

  GET  /api/works?order=&sort=&page=&seed=     paginated work list
  GET  /api/work/<id>                          work metadata
  GET  /api/tracks/<id>                        full file tree
  GET  /api/media/stream/<hash>?token=...      audio stream
  GET  /api/media/download/<hash>?token=...    file download
  GET  /api/cover/<id>?token=...               cover image (alias of /api/cover/<rj>)
  GET  /api/covers/<id>                        cover image (kikoeru path)
  GET  /api/auth/me                            current user (mock)
  POST /api/auth/me                            login (mock — always succeeds)
  GET  /api/version                            asmr-view version
  GET  /api/config/shared                      shared config
  GET  /api/mylist                             mylist (mock — empty)
  PUT  /api/mylist                             noop
  GET  /api/review                             reviews (mock — empty)
  PUT  /api/review                             noop
  GET  /api/track/<hash>                       single file metadata
  GET  /api/media/check-lrc/<hash>             lrc check (mock)
  POST /api/admin/reindex                      trigger Neokikoeru scan + index
  POST /api/admin/rebuild-index                same as reindex

Work IDs:
  Kikoeru uses numeric IDs (e.g. 1010222) which represent RJ01010222.
  The `id` in the work object is the numeric portion. We accept both
  numeric (`1010222`) and string (`RJ0101022` or `RJ01010222`) forms
  in URLs and convert internally.

File tree:
  Kikoeru returns a nested tree at /api/tracks/<id>. We build it from
  the flat `files` table by walking parent_id chains.
"""
from __future__ import annotations

import codecs
import json
import re
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path

# Constants
NEOKIKOERU_DATA = Path.home() / "Library" / "Application Support" / "neokikoeru"
NEOKIKOERU_DB = NEOKIKOERU_DATA / "neokikoeru.db"
NEOKIKOERU_COVERS = NEOKIKOERU_DATA / "covers" / "doujin"
NEOKIKOERU_COVERS_ROOT = NEOKIKOERU_DATA / "covers"
NEOKIKOERU_NO_IMG = NEOKIKOERU_COVERS_ROOT / "no_img_sam.gif"

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
TEXT_EXTS = {".txt", ".pdf", ".md", ".log"}
SUB_EXTS = {".lrc", ".srt", ".vtt", ".ass", ".ssa"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}


def rj_to_numeric(rj: str) -> int:
    """RJ01010222 -> 1010222 (zero-padded to 6 digits, then int)."""
    m = re.match(r"^RJ0*(\d+)$", rj)
    if not m:
        raise ValueError(f"bad rj: {rj!r}")
    return int(m.group(1))


def numeric_to_rj(n: int) -> str:
    """Best-effort: 1010222 -> RJ01010222 (zero-padded to 8 digits).

    This is the LEGACY guess. Some works in the DB have 6-digit RJ codes
    (e.g. RJ190391), so the right answer is to look up the actual row by
    numeric id, not pad. Use resolve_rj() when a DB connection is
    available; callers that only have a number should fall back to this.
    """
    return "RJ" + str(n).zfill(8)


def resolve_rj(conn, n: int) -> str | None:
    """Look up the actual RJ code for a numeric id, accepting any digit width.

    DLsite assigns RJ codes monotonically: older releases are 6 digits
    (RJ190391), newer ones are 8 digits (RJ01010222). zfill(8) mangles
    6-digit codes into nonexistent "RJ0439991" forms. This function
    tries the 6-digit and 8-digit forms (and any 7-digit variants in
    between) and returns whichever one exists in the works table.

    Returns None if no match is found.
    """
    candidates = []
    s = str(n)
    # Try the natural zero-padded form first
    candidates.append("RJ" + s.zfill(8))
    # Then try the 6-digit form (the common old-style)
    candidates.append("RJ" + s.zfill(6))
    # Then try the raw number with no padding
    candidates.append("RJ" + s)
    seen = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        row = conn.execute("SELECT id FROM works WHERE id = ?", (c,)).fetchone()
        if row is not None:
            return row["id"]
    return None


def to_work_id(arg: str) -> int:
    """Accept '1010222' or 'RJ01010222' or 'RJ0101022' -> numeric 1010222."""
    if not arg:
        raise ValueError("empty work id")
    if arg.upper().startswith("RJ"):
        return rj_to_numeric(arg.upper())
    if arg.isdigit():
        return int(arg)
    raise ValueError(f"bad work id: {arg!r}")


# ---------------------------------------------------------------------------
# Cover resolution (reused from asmr-view, simplified)
# ---------------------------------------------------------------------------

def find_cover(rj: str) -> Path | None:
    """Find cover image for RJ id, returns absolute path or None."""
    # Walk the bucket structure
    # RJ01010222 -> bucket name = id[0:6] + round-up(id[6:8]) + "00"
    m = re.match(r"^RJ(\d+)$", rj)
    if not m:
        return None
    digits = m.group(1)
    if len(digits) < 6:
        return None
    # Compute bucket: first 6 chars + ceil-to-10 of next 2 chars (with carry) + "00"
    try:
        head = digits[:6]
        rest = int(digits[6:8]) if len(digits) >= 8 else 0
        if rest == 0:
            bucket_suffix = "00"
        else:
            rounded = ((rest + 9) // 10) * 10
            if rounded >= 100:
                # carry into head[4]
                carry = rounded // 100
                rounded = rounded % 100
                head = head[:5] + str(int(head[5]) + carry) + head[6:]
            bucket_suffix = f"{rounded:02d}"
        bucket = f"RJ{head}00" if rounded == 0 else f"RJ{head[:-2]}{bucket_suffix}00"
        # Simpler: just scan the directory
    except Exception:
        pass
    # Fallback: scan for any cover file for this rj
    if not NEOKIKOERU_COVERS.is_dir():
        return None
    for bucket in NEOKIKOERU_COVERS.iterdir():
        if not bucket.is_dir():
            continue
        for f in bucket.iterdir():
            if f.name.startswith(rj + "_img_main"):
                return f
            if f.name.startswith(rj + "_img_sam") and not _has_main_for(bucket, rj):
                return f
            if f.name.startswith(rj + "_img_thumb") and not _has_main_or_sam_for(bucket, rj):
                return f
    return None


def _has_main_for(bucket: Path, rj: str) -> bool:
    return any(f.name.startswith(rj + "_img_main") for f in bucket.iterdir())


def _has_main_or_sam_for(bucket: Path, rj: str) -> bool:
    return any(
        f.name.startswith(rj + "_img_") and ("main" in f.name or "sam" in f.name)
        for f in bucket.iterdir()
    )


# ---------------------------------------------------------------------------
# Kikoeru-format row builders
# ---------------------------------------------------------------------------

def work_to_kikoeru(row: dict, work_id_num: int) -> dict:
    """Convert a DB row into the kikoeru work-object format."""
    rating = float(row.get("rating") or 0)
    rating_count = int(row.get("rating_count") or 0)
    review_count = int(row.get("review_count") or 0)
    return {
        "id": work_id_num,
        "title": row.get("title") or "",
        "circle": {"id": 0, "name": row.get("maker") or ""},
        "vas": row.get("artists") or [],
        "tags": [],  # Kikoeru tags are objects with id+name; we send string array elsewhere
        "rate_average_2dp": f"{rating:.2f}",
        "rate_count": rating_count,
        "review_count": review_count,
        "rate_count_detail": _rating_distribution(rating, rating_count),
        "dl_count": int(row.get("sales") or 0),
        "price": int(row.get("price") or 0),
        "nsfw": int(row.get("age_category") or 0) >= 2,
        "release": row.get("released") or "",
        "create_date": _ts_to_date(row.get("created_at")),
        "userRating": 0,
        "isFavourite": False,
        "type": "doujin",
        "coverUrl": f"/api/covers/{work_id_num}",
    }


def _rating_distribution(avg: float, count: int) -> list:
    """Kikoeru's rate_count_detail is [{review_point, count, ratio}, ...]."""
    if count == 0 or avg == 0:
        return []
    # Distribute ratings roughly around the average (rough approximation;
    # real data has been summed away). We mostly care that the array shape is correct.
    points = [5, 4, 3, 2, 1]
    # Assume 60% are 5-star, 25% 4-star, 10% 3-star, 4% 2-star, 1% 1-star
    ratios = [60, 25, 10, 4, 1]
    out = []
    for p, r in zip(points, ratios):
        c = round(count * r / 100)
        out.append({"review_point": p, "count": c, "ratio": r})
    return out


def _ts_to_date(ts) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(ts) / 1000))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# File tree builder
# ---------------------------------------------------------------------------
#
# kikoeru-quasar SPA click handler (in app.051b603d.js, in the file
# row click branch) routes by ``type``:
#   * "folder"   -> navigate
#   * "text"     -> open in built-in text viewer (download also possible)
#   * "image"    -> open in image viewer
#   * "other"    -> download
#   * default    -> play as audio
#
# kikoeru-express labels .lrc/.srt/.ass/.txt as ``type: "text"`` in
# filesystem/utils.js line 109. We follow that contract: subtitle
# formats are TEXT files, not audio. .lrc is consumed by the audio
# player's lrc-file-parser via /api/media/check-lrc, but in the
# file tree it shows up as text so clicking opens the viewer
# (download also works), never tries to play VTT as audio.


def _classify(name: str) -> str:
    """Map a filename to kikoeru's 'type' field.

    kikoeru-quasar branch order: folder, text, image, other (download),
    default (play). Subtitle/text files must be "text" so clicking
    them opens the viewer instead of trying to play them as audio.
    """
    ext = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in SUB_EXTS or ext in TEXT_EXTS:
        return "text"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"


def _file_to_kikoeru(conn, row) -> dict:
    """Convert a files table row into a kikoeru tree node."""
    is_folder = bool(row["is_folder"])
    name = row["name"]
    node = {
        "title": name,
        "type": "folder" if is_folder else _classify(name),
        "hash": row["id"],
        "children": [],
        "mediaStreamUrl": None,
        "mediaDownloadUrl": None,
        "lyrics": None,
    }
    if not is_folder:
        node["mediaStreamUrl"] = f"/api/media/stream/{row['id']}"
        node["mediaDownloadUrl"] = f"/api/media/download/{row['id']}"
    return node


def build_tree(conn, work_id: str) -> list:
    """Build the full kikoeru file tree for a work.

    The tree starts with the root folder as the first item, but kikoeru
    actually starts at the top-level of the work. The WorkTree component
    uses `path[]` for sub-navigation, so we return the children of the
    root folder (i.e. the top-level folders and files).
    """
    # Find the work
    work = conn.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
    if work is None:
        return []

    # Find root folder (parent_id IS NULL)
    root = conn.execute(
        "SELECT id FROM files WHERE work_id = ? AND parent_id IS NULL AND is_folder = 1 LIMIT 1",
        (work_id,),
    ).fetchone()
    if root is None:
        return []

    def _children_of(parent_id):
        out = []
        rows = conn.execute(
            """SELECT id, name, size, duration, is_folder, parent_id, path
               FROM files
               WHERE parent_id = ?
               ORDER BY is_folder DESC, name""",
            (parent_id,),
        ).fetchall()
        for r in rows:
            node = _file_to_kikoeru(conn, r)
            if r["is_folder"]:
                node["children"] = _children_of(r["id"])
            out.append(node)
        return out

    return _children_of(root["id"])


# ---------------------------------------------------------------------------
# Subtitle / LRC detection + on-the-fly conversion
# ---------------------------------------------------------------------------
#
# The kikoeru client's `lrc-file-parser` only understands LRC. For
# audio files that have a non-LRC subtitle sibling (VTT / SRT / ASS /
# SSA), we treat that subtitle as a lyric and convert it to LRC at
# serve time. Sibling lookup priority: LRC > VTT > SRT > ASS > SSA.
#
# The audio file's name is something like ``01_xxx.mp3``. Subtitles
# can be named any of:
#   * ``01_xxx.lrc``       (extension replaced)
#   * ``01_xxx.mp3.vtt``   (extension preserved + .vtt appended)
#   * ``01_xxx.mp3.srt``   (same for srt)
# The audio's "base" is the full name without its final extension
# (e.g. ``01_xxx.mp3`` for vtt/srt) or without any extension at all
# (e.g. ``01_xxx`` for lrc).
#
# Kikoeru's AudioElement does: GET /api/media/check-lrc/<hash> ->
# { result: bool, hash: <sub_hash> }. We return the hash of whatever
# sibling wins the priority race, and the stream endpoint converts
# the body to LRC on the way out.

SUBTITLE_EXTS = (".lrc", ".vtt", ".srt", ".ass", ".ssa")


def find_lrc_for_audio(conn, work_id: str, audio_hash: str) -> str | None:
    """Given an audio file's hash, find a sibling subtitle file.

    Returns the hash of the first matching subtitle, or None. Prefers
    LRC, then VTT, then SRT, then ASS/SSA. Kikoeru's AudioElement
    polls GET /api/media/check-lrc/<hash> and uses response.data.hash
    to fetch the lyric body.
    """
    audio = conn.execute(
        "SELECT name, parent_id FROM files WHERE id = ?",
        (audio_hash,),
    ).fetchone()
    if audio is None:
        return None
    name = audio["name"]
    parent_id = audio["parent_id"]
    # Build candidate basenames: the full name, and the name stripped
    # of one or more extensions. We try each against each subtitle ext.
    candidates = [name]
    if "." in name:
        head, _ = name.rsplit(".", 1)
        candidates.append(head)
    for ext in SUBTITLE_EXTS:
        for base in candidates:
            sub_name = base + ext
            row = conn.execute(
                "SELECT id FROM files WHERE work_id = ? AND parent_id = ? AND name = ?",
                (work_id, parent_id, sub_name),
            ).fetchone()
            if row:
                return row["id"]
    return None


def get_subtitle_format(conn, sub_hash: str) -> str:
    """Return the lowercase extension of a subtitle file (.lrc/.vtt/etc)
    or "" if not found. Used to pick the conversion path when serving.
    """
    row = conn.execute(
        "SELECT name FROM files WHERE id = ?", (sub_hash,)
    ).fetchone()
    if row is None:
        return ""
    name = row["name"]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _hms_to_lrc_timestamp(h: int, m: int, s: int, ms: int) -> str:
    """Build an LRC [mm:ss.xx] timestamp from components.

    LRC is conventionally minutes + seconds + centiseconds (2 digits).
    Hours are folded into minutes. The kikoeru player's lrc-file-parser
    uses minutes as the first component, so we always include minutes
    even for short clips. ``xx`` is centiseconds, not milliseconds —
    we drop the trailing digit (e.g. 645 ms -> 64 cs).
    """
    total_min = h * 60 + m
    cs = (ms // 10) if ms else 0
    return f"[{total_min:02d}:{s:02d}.{cs:02d}]"


def vtt_to_lrc(vtt_text: str) -> str:
    """Convert WebVTT subtitle text to LRC.

    VTT cues use ``HH:MM:SS.mmm --> HH:MM:SS.mmm`` and a header line
    ``WEBVTT``. LRC uses ``[MM:SS.xx]`` per line. We use the cue's
    start time as the LRC timestamp and pass the cue text through
    verbatim. **Timestamp and text are emitted on the SAME line**
    (e.g. ``[00:02.90]我明白了``) — the kikoeru client's
    `lrc-file-parser` v1.2.7 (the version bundled with the SPA)
    parses each line with a regex that captures ``[time]text`` as a
    single unit. Emitting them on separate lines (timestamp on one
    line, text on the next) silently produces zero parsed lines.
    Cue-internal newlines are collapsed to spaces (LRC is single-line
    per cue).
    """
    import re
    text = vtt_text.lstrip("\ufeff")
    pat = re.compile(
        r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})\s*-->\s*"
        r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})"
    )
    out: list[str] = []
    pending_text: list[str] = []
    pending_ts: str | None = None

    def flush():
        nonlocal pending_text, pending_ts
        if pending_ts is not None:
            if pending_text:
                # Collapse multi-line cue text into a single line
                # (LRC is single-line per cue) and emit [time]text
                # together so lrc-file-parser v1.2.7 picks it up.
                out.append(pending_ts + " ".join(
                    s.strip() for s in pending_text if s.strip()
                ))
            else:
                out.append(pending_ts)
        pending_text = []
        pending_ts = None

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = pat.match(line)
        if m:
            flush()
            h = int(m.group(1) or 0)
            mn = int(m.group(2))
            sc = int(m.group(3))
            ms = int(m.group(4) or 0)
            pending_ts = _hms_to_lrc_timestamp(h, mn, sc, ms)
            continue
        # Skip headers, NOTE blocks, and STYLE blocks.
        if line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if line.strip() == "":
            flush()
            continue
        if pending_ts is not None:
            pending_text.append(line)
    flush()
    return "\n".join(out) + "\n"


def srt_to_lrc(srt_text: str) -> str:
    """Convert SRT to LRC.

    SRT uses 1-based cue numbers and ``HH:MM:SS,mmm --> HH:MM:SS,mmm``
    timestamps with comma decimals. Cue numbers are dropped. As with
    vtt_to_lrc, timestamp and text are emitted on the same line so
    the kikoeru lrc-file-parser v1.2.7 can pick them up.
    """
    import re
    pat = re.compile(
        r"(\d{1,2}):(\d{1,2}):(\d{1,2}),(\d{1,3})\s*-->\s*"
        r"(\d{1,2}):(\d{1,2}):(\d{1,2}),(\d{1,3})"
    )
    out: list[str] = []
    pending_text: list[str] = []
    pending_ts: str | None = None

    def flush():
        nonlocal pending_text, pending_ts
        if pending_ts is not None:
            if pending_text:
                out.append(pending_ts + " ".join(
                    s.strip() for s in pending_text if s.strip()
                ))
            else:
                out.append(pending_ts)
        pending_text = []
        pending_ts = None

    for raw in srt_text.splitlines():
        line = raw.rstrip("\r")
        m = pat.match(line)
        if m:
            flush()
            h = int(m.group(1))
            mn = int(m.group(2))
            sc = int(m.group(3))
            ms = int(m.group(4) or 0)
            pending_ts = _hms_to_lrc_timestamp(h, mn, sc, ms)
            continue
        if line.strip().isdigit():
            # SRT cue index — skip.
            continue
        if line.strip() == "":
            flush()
            continue
        if pending_ts is not None:
            pending_text.append(line)
    flush()
    return "\n".join(out) + "\n"


def ass_to_lrc(ass_text: str) -> str:
    """Convert ASS/SSA to LRC.

    ASS dialogue lines look like::

        Dialogue: 0,0:00:02.90,0:00:04.64,Default,,0,0,0,,Hello world

    Format is ``Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,
    MarginV,Effect,Text``. We extract Start, fold it into LRC format,
    and pass the Text field (which can contain ASS override codes like
    ``{\\b1}`` — we strip them so the LRC body is plain text).
    """
    import re
    out: list[str] = []
    # Strip BOM.
    text = ass_text.lstrip("\ufeff")
    # ASS timestamp: H:MM:SS.cc (centiseconds, 2 digits)
    # Field layout: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,
    # Effect,Text. The Text is the LAST field and may contain commas,
    # so we match the first 9 fields strictly and let ``.*`` consume
    # the rest of the line.
    line_pat = re.compile(
        r"^Dialogue:\s*([^,]*),"
        r"(\d+):(\d{2}):(\d{2})\.(\d{2}),"
        r"\d+:\d{2}:\d{2}\.\d{2},"
        r"([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),"
        r"(.*)$"
    )
    # ASS override codes: {\\b1}, {\\i1}, {\\fs28}, etc. Strip them.
    override_pat = re.compile(r"\{[^}]*\}")

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = line_pat.match(line)
        if not m:
            continue
        h = int(m.group(2))
        mn = int(m.group(3))
        sc = int(m.group(4))
        # ASS uses centiseconds, _hms_to_lrc_timestamp expects
        # milliseconds — multiply by 10.
        ms = int(m.group(5)) * 10
        ts = _hms_to_lrc_timestamp(h, mn, sc, ms)
        # Group 11 is the Text field (group 1 = Layer, 2-5 = Start,
        # 6-10 = Style/Name/MarginL/MarginR/MarginV, 11 = Text).
        body = m.group(11)
        # The Text field starts right after the 9th comma; the comma
        # itself isn't included in group 11, but if the previous
        # field (Effect) was empty, the parser can leave a leading
        # comma artifact. Strip a single leading comma to be safe.
        if body.startswith(","):
            body = body[1:]
        # ASS uses `\N` for hard line breaks and `\n` for soft line
        # breaks within a cue. LRC is single-line per cue, so collapse
        # both to spaces.
        body = body.replace("\\N", " ").replace("\\n", " ")
        # Strip override codes.
        body = override_pat.sub("", body).strip()
        # Emit [time]text on the SAME line so the kikoeru
        # lrc-file-parser v1.2.7 picks it up. (See vtt_to_lrc.)
        if body:
            out.append(ts + body)
        else:
            out.append(ts)
    return "\n".join(out) + "\n"


def convert_subtitle_to_lrc(text: str, suffix: str) -> str:
    """Dispatch subtitle→LRC conversion by file extension.

    Returns the LRC body as a string. If the format is already LRC
    the input is returned unchanged (after a light normalization pass).
    Unknown / unsupported formats raise ValueError so the caller can
    fall back to raw passthrough.
    """
    s = suffix.lower()
    if s == ".lrc":
        # Lightly normalize: ensure trailing newline, strip BOM.
        return text.lstrip("\ufeff").rstrip() + "\n"
    if s == ".vtt":
        return vtt_to_lrc(text)
    if s == ".srt":
        return srt_to_lrc(text)
    if s in (".ass", ".ssa"):
        return ass_to_lrc(text)
    raise ValueError(f"unsupported subtitle format: {suffix!r}")


def detect_text_charset(path: Path) -> str:
    """Best-effort text charset detection for subtitle/text files.

    Returns a charset name suitable for the ``charset=`` MIME parameter.
    Defaults to ``utf-8``. Mirrors kikoeru-express's jschardet path
    (routes/media.js) — we don't ship jschardet, so this is a small
    fallback: BOM sniff → UTF-8 strict decode → GBK heuristic.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return "utf-8"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    try:
        # `head` is a prefix sample and may end in the middle of a UTF-8
        # multibyte sequence.  A normal strict decode can falsely fail at the
        # sample boundary and make valid UTF-8 subtitles look like GBK.
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        pass
    if head and sum(1 for b in head if 0xA1 <= b <= 0xFE) / max(len(head), 1) > 0.1:
        return "gbk"
    return "utf-8"
