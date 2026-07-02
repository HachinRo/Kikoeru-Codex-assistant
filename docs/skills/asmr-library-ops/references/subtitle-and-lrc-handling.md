# Subtitle / LRC handling in asmr-view

The kikoeru-quasar audio player (the SPA shipped in
`<ASMR_STACK_ROOT>/kikoeru-spa/`) uses `lrc-file-parser` (LRC-only) to
display lyrics. It calls two endpoints:

1. `GET /api/media/check-lrc/<audio_hash>` — returns
   `{result: bool, hash: <lrc_hash> | null}`. If `result: true`, the
   player fetches the LRC body from `/api/media/stream/<lrc_hash>`.
2. `GET /api/media/stream/<hash>` — returns the raw file body. For
   LRC this is the lyric text. For other formats the player just
   fails to parse and shows no lyrics.

This file documents the contract asmr-view follows (matching
kikoeru-express's behaviour, NOT file conversion) and the gotchas
when integrating with the kikoeru-quasar SPA.

## TL;DR

- **kikoeru-express treats `.lrc` as the only lyric format.** Subtitle
  files of any other type (`.vtt/.srt/.ass/.ssa`) are exposed in the
  file tree as `type: "text"` and served raw, but `check-lrc` never
  returns them. asmr-view follows the same contract.
- **No runtime format conversion.** The previous attempt (VTT→LRC,
  SRT→LRC) was reverted because: (a) it added ~150 lines of brittle
  regex parsing, (b) the kikoeru client's `lrc-file-parser` was
  getting non-LRC data either way and failing to display anything
  visible to the user, (c) the upstream contract is "no conversion"
  — the user explicitly requested kikoeru-express behaviour.
- **`.lrc` siblings are produced by `asmr-subs`.** The worker writes
  every fetched subtitle as `<track-stem>.lrc` next to the audio, so
  content downloaded via the library chain has working lyrics. The
  ~780 pre-existing `.vtt` files in the library come from
  Neokikoeru's filesystem scan and are not used as lyrics — they
  exist as text files in the file tree for download only.
- **`_classify()` must return `type: "text"` for subtitle files, not
  `type: "subtitle"`.** The kikoeru-quasar SPA's file-row click
  handler routes by `type` — see "Why `text` not `subtitle`" below.

## The two endpoints and their contract

### `check-lrc` — kikoeru-express alignment

kikoeru-express's implementation (`routes/media.js` lines 115–155):

```js
const fileLoc = path.join(rootFolder.path, work.dir, track.subtitle || '', track.title);
const lrcFileLoc = fileLoc.substr(0, fileLoc.lastIndexOf(".")) + ".lrc";
if (!fs.existsSync(lrcFileLoc)) {
  res.send({result: false, message:'不存在歌词文件', hash: ''});
} else {
  // Look up the .lrc hash in the track list and return it
}
```

That's it — **one candidate, extension-replaced, `.lrc` only**. No
VTT, SRT, ASS, or SSA detection. The reason is the kikoeru client's
`lrc-file-parser` is LRC-only; matching a VTT and feeding VTT bytes
to an LRC parser gives nothing.

asmr-view's `find_lrc_for_audio()` in
`<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py` follows the same
contract:

```python
def find_lrc_for_audio(conn, work_id, audio_hash):
    audio = conn.execute(
        "SELECT name, parent_id FROM files WHERE id = ?", (audio_hash,)
    ).fetchone()
    if audio is None:
        return None
    name = audio["name"]
    parent_id = audio["parent_id"]
    if "." in name:
        base = name.rsplit(".", 1)[0]   # strip one extension
    else:
        base = name
    row = conn.execute(
        "SELECT id FROM files WHERE work_id = ? AND parent_id = ? AND name = ?",
        (work_id, parent_id, base + ".lrc"),
    ).fetchone()
    return row["id"] if row else None
```

The `_kikoeru_check_lrc` handler in `bin/asmr-view` calls this and
returns `{result: True, hash: lrc_hash}` on a hit, `{result: False,
hash: null}` otherwise. **Do not** add fallback candidates like
`<name>.mp3.lrc` or `<name>.mp3.vtt` — that was the previous
behaviour and it produced broken lyrics because the kikoeru client
couldn't parse non-LRC content anyway.

### `stream` — serve raw, no conversion

For LRC files the body is the lyric text. For VTT/SRT/ASS/SSA files
the body is the raw subtitle bytes, served with
`Content-Type: text/plain; charset=<detected>` and no
`Accept-Ranges` (these files are small). **No decode, no
transformation, no extension detection for the response format.**

A small `detect_text_charset(path)` helper picks the charset
(BOM → UTF-8/UTF-16; UTF-8 strict; GBK heuristic for high-byte
density). This matches kikoeru-express's jschardet path
(`routes/media.js` line 35) without shipping jschardet:

```python
def detect_text_charset(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return "utf-8"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    try:
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    if head and sum(1 for b in head if 0xA1 <= b <= 0xFE) / len(head) > 0.1:
        return "gbk"
    return "utf-8"
```

## Why `text` not `subtitle` in the file tree

The kikoeru-quasar SPA's file-row click handler
(`<ASMR_STACK_ROOT>/kikoeru-spa/js/app.051b603d.js`) routes by `type`:

```js
"folder"===t.type ? this.path.push(t.title)
: "text"===t.type || "image"===t.type ? this.openFile(t)
: "other"===t.type ? this.download(t)
: this.currentPlayingFile.hash!==t.hash && this.$...   // default → play as audio
```

A `type: "subtitle"` value would fall through to the **default
branch — play as audio**. Clicking a VTT row would try to play it
as audio, fail, and produce a confusing 404 from the audio element.
Mapping `.vtt/.srt/.ass/.ssa` to `type: "text"` (alongside
`.txt`/`.pdf`/`.md`/`.log`) puts them in the `openFile(t)` branch,
which opens them in the SPA's text viewer (and lets the user
download). This is exactly what kikoeru-express does
(`filesystem/utils.js` line 109):

```js
if (track.ext === '.txt' || track.ext === '.lrc' || track.ext === '.srt' || track.ext === '.ass') {
  fatherFolder.push({type: 'text', ...});
}
```

asmr-view's `_classify()` mirrors this:

```python
def _classify(name: str) -> str:
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
```

## What the user sees in practice

- **For works downloaded via `asmr-library` (the worker chain):**
  `asmr-subs` writes a `<track-stem>.lrc` next to each audio file
  it fetched subtitles for. `check-lrc` returns the LRC hash, the
  player fetches the LRC, `lrc-file-parser` parses it, lyrics
  display. **This is the happy path and it works.**
- **For works with pre-existing `.vtt`/`.srt` from Neokikoeru's
  scan (no `.lrc` sibling):** `check-lrc` returns `{result: false,
  hash: null}`. The audio plays. The VTT file is visible in the
  file tree as `type: "text"` and can be opened/downloaded. **No
  lyrics are shown.** This is the kikoeru-express behaviour the
  user asked for.
- **For works with no subtitle of any kind:** `check-lrc` returns
  `{result: false, hash: null}`. The audio plays. The file tree has
  no subtitle rows. No regression.

## Verifying the contract

Live end-to-end checks against a running asmr-view (port 8890):

```sh
DB="$HOME/Library/Application Support/neokikoeru/neokikoeru.db"

# 1. Audio with ONLY .vtt sibling → check-lrc must be false
AUDIO_NO_LRC=$(sqlite3 "$DB" "SELECT a.id FROM files a
  JOIN files s ON s.parent_id = a.parent_id
  WHERE a.is_folder=0 AND a.name LIKE '%.m4a' AND s.name LIKE '%.vtt'
    AND a.work_id NOT IN (
      SELECT a2.work_id FROM files a2 JOIN files s2 ON s2.parent_id=a2.parent_id
      WHERE a2.is_folder=0 AND s2.name LIKE '%.lrc'
    ) LIMIT 1;")
curl -s "http://127.0.0.1:8890/api/media/check-lrc/$AUDIO_NO_LRC"
# expected: {"result": false, "hash": null}

# 2. Audio with .lrc sibling → check-lrc must be true
AUDIO_WITH_LRC=$(sqlite3 "$DB" "SELECT a.id FROM files a
  JOIN files s ON s.parent_id = a.parent_id
  WHERE a.is_folder=0 AND a.name LIKE '%.mp3' AND s.name LIKE '%.lrc'
  LIMIT 1;")
curl -s "http://127.0.0.1:8890/api/media/check-lrc/$AUDIO_WITH_LRC"
# expected: {"result": true, "hash": "<lrc_hash>"}

# 3. VTT stream returns raw bytes (no conversion)
VTT_HASH=$(sqlite3 "$DB" "SELECT id FROM files WHERE name LIKE '%.vtt' LIMIT 1;")
curl -s "http://127.0.0.1:8890/api/media/stream/$VTT_HASH" | head -1
# expected: WEBVTT
curl -sI "http://127.0.0.1:8890/api/media/stream/$VTT_HASH" | grep -i content-type
# expected: text/plain; charset=utf-8

# 4. LRC stream returns raw LRC
LRC_HASH=$(sqlite3 "$DB" "SELECT id FROM files WHERE name LIKE '%.lrc' LIMIT 1;")
curl -s "http://127.0.0.1:8890/api/media/stream/$LRC_HASH" | head -1
# expected: [ti:...] or [ar:...] or [00:00.00]...

# 5. File tree: subtitle files must be type:text, NOT type:subtitle
RJ=$(sqlite3 "$DB" "SELECT work_id FROM files a JOIN files s ON s.parent_id=a.parent_id
  WHERE a.is_folder=0 AND a.name LIKE '%.m4a' AND s.name LIKE '%.vtt' LIMIT 1;")
curl -s "http://127.0.0.1:8890/api/tracks/$RJ" | python3 -c "
import json, sys
def walk(nodes):
    for n in nodes:
        if n.get('title','').endswith('.vtt'):
            assert n['type'] == 'text', f'FAIL: {n[\"title\"]} is {n[\"type\"]}'
            print('OK', n['title'], 'is text')
        if n.get('children'): walk(n['children'])
walk(json.load(sys.stdin))
"
```

If any check fails:
- `check-lrc` returns a hash for a non-LRC sibling → `find_lrc_for_audio`
  was widened. Restore the single-candidate `.lrc` lookup.
- VTT stream returns LRC-shaped content → `_kikoeru_stream` still has
  conversion code. Remove the `vtt_to_lrc`/`srt_to_lrc` branches and
  serve raw bytes.
- File tree shows `type: "subtitle"` → `_classify` wasn't updated.
  Add the `SUB_EXTS` and `TEXT_EXTS` merge into the `text` branch.

## Pitfalls

- **Don't add a multi-format `check-lrc` "for robustness".** The
  previous design (LRC, then VTT, then SRT, then ASS/SSA) was
  technically more permissive, but the kikoeru client can only
  display LRC. Returning a VTT hash to `check-lrc` produced the
  same broken state (no lyrics) as returning `false`, with the
  extra cost of ~150 lines of regex parsers in `vtt_to_lrc` /
  `srt_to_lrc` that were never used effectively. kikoeru-express
  solved this at the contract level; copy that, don't try to
  outsmart the player.
- **Don't strip the BOM and re-encode subtitle files.** kikoeru
  uses jschardet and serves the bytes as-is. asmr-view's
  `detect_text_charset` returns the charset name for the
  `Content-Type` header but the body is the original bytes —
  exactly as on disk. The kikoeru client can display UTF-8/UTF-16
  text directly; re-encoding risks mangling GBK/GB2312 source.
- **Don't promote `.vtt`/`.srt` to `type: "subtitle"`.** The SPA's
  default click handler treats unknown types as audio and will try
  to play them. `type: "text"` is the only safe classification for
  any non-audio, non-image file that should open in the viewer.
- **If the user asks for "lyrics for everything"**, the right fix
  is to extend `asmr-subs` with a one-time converter that walks
  the library, reads existing `.vtt`/`.srt` siblings, and writes
  real `.lrc` files next to them. That keeps `check-lrc` simple
  and gives the player real LRC data. Reach for that before
  touching the runtime conversion path.
- **The `lrc-file-parser` library version matters.** The kikoeru-quasar
  bundle ships `lrc-file-parser.js v1.2.7` (in
  `<ASMR_STACK_ROOT>/kikoeru-spa/js/vendor.86022408.js`). It only
  understands `[mm:ss.xx]` timestamps. `[hh:mm:ss.xx]` from any
  external LRC source must be re-formatted, or `setLyric` will
  silently fail to register any lines. This is also true of LRCs
  that use `[mm:ss.fff]` (3-digit milliseconds) — the centiseconds
  must be rounded, not truncated.

## The bigger picture

The kikoeru-quasar project (2020) was built for an ecosystem where
the only subtitle format that mattered was `.lrc`. The author
shipped `lrc-file-parser` and built the player around it. Modern
content ships with `.vtt` (YouTube-style), `.srt` (broadly
compatible), and occasionally `.ass/.ssa` (anime-style). Three
approaches are possible:

1. **Match the upstream contract** (kikoeru-express, what asmr-view
   now does): only `.lrc` is a lyric; other subtitle formats are
   text files. No conversion, no parser. Cheap, simple, and
   exactly aligned with what the player can display.
2. **Convert on disk**: extend `asmr-subs` with a one-time
   `convert` subcommand that walks existing `.vtt`/`.srt` and
   writes `.lrc` siblings. The player sees real LRC and displays
   it. Persistent on disk, no runtime cost, works for any future
   player.
3. **Convert on the fly at stream time**: rejected. Adds runtime
   cost on every stream request, requires maintaining parsers
   that mirror what the player could do better itself, and the
   kikoeru player can't display non-LRC anyway, so the only
   benefit is wasted.

If the user wants lyrics for the 780 existing VTT works, use
option 2. Don't reach for option 3 again.

## Reference

- kikoeru-express `routes/media.js` lines 14–70 (stream with
  charset detection), 115–155 (check-lrc, `.lrc` only).
- kikoeru-express `filesystem/utils.js` lines 14–51 (track
  discovery), 109–118 (`type: "text"` classification for
  .lrc/.srt/.ass/.txt).
- asmr-view `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py`
  `find_lrc_for_audio` (line 326), `_classify` (line 252),
  `detect_text_charset` (line 376).
- asmr-view `<ASMR_STACK_ROOT>/bin/asmr-view` `_kikoeru_stream`
  (line 820), `_kikoeru_check_lrc` (line 1112).
- kikoeru-quasar SPA `<ASMR_STACK_ROOT>/kikoeru-spa/js/app.051b603d.js`
  (`check-lrc` consumer, click-handler `type` branch).
