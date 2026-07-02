# Subtitle→LRC conversion (asmr-view)

The kikoeru-quasar SPA's `AudioElement` uses `lrc-file-parser` (LRC-only).
The on-disk library contains subtitle siblings in five formats —
`.lrc`, `.vtt`, `.srt`, `.ass`, `.ssa` — but the kikoeru `check-lrc`
endpoint traditionally only matches `.lrc` (matching kikoeru-express
strictness). This file documents the asmr-view approach: **find any
sibling, convert to LRC on the fly at serve time**.

## Contract

Sibling priority in `find_lrc_for_audio()`:
`LRC > VTT > SRT > ASS > SSA`

The audio file's name is something like `01_xxx.mp3`. Subtitles can be:
- `01_xxx.lrc` (extension replaced)
- `01_xxx.mp3.vtt` / `01_xxx.mp3.srt` (audio extension preserved + sub ext appended)

`check-lrc` returns `{result: true, hash: <sub_hash>}` for any match.
The stream endpoint detects the sub format and converts to LRC before
returning bytes. The kikoeru player is none the wiser.

## Format parsers

All parsers live in `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py` and share
a common helper `_hms_to_lrc_timestamp(h, m, s, ms)` that returns
`[mm:ss.xx]` (centiseconds, 2 digits). Hours fold into minutes
(so a 65-minute track shows `[65:00.00]` not `[01:05:00.00]`).

### VTT — WebVTT (`.vtt`)

```
WEBVTT
                      ← blank line is mandatory cue separator
1
00:00:02.900 --> 00:00:04.645
Hello
```

Timestamp regex:
```python
r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})\s*-->\s*"
r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})"
```

Hours optional. Strip `WEBVTT`, `NOTE`, `STYLE`, `REGION` block headers.
Multi-line cue text collapses to single line (LRC has no multi-line cue
concept). Cue-internal `\N` is **not** a thing in VTT (it's an ASS
construct) — don't strip it.

### SRT — SubRip (`.srt`)

```
1                                    ← 1-based cue index, DROP
00:00:01,000 --> 00:00:03,500
Hello, world!
```

Note **comma** decimal separator (VTT uses `.`). Cue indices are pure
integers — `line.strip().isdigit()` is the right drop predicate (does
not match `00:00:01,000` because the comma fails `isdigit`).

### ASS / SSA — Advanced SubStation Alpha (`.ass`, `.ssa`)

ASS dialogue lines look like:

```
Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,{\b1}Hello{\b0} world
```

Field layout: `Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text`

**The gotcha** — Text is the **11th capture group**, not the 10th:

| # | Field    | Captures |
|---|----------|----------|
| 1 | Layer    | `([^,]*)` |
| 2-5 | h,m,s,cs (Start) | `(\d+):(\d{2}):(\d{2})\.(\d{2})` |
| 6-10 | Style,Name,MarginL,MarginR,MarginV | `([^,]*),([^,]*),([^,]*),([^,]*),([^,]*)` |
| **11** | **Text** | `(.*)$` |

The naive `m.group(10)` returns `MarginV` (often `"0"`), not the Text
field. **Always count from the start** when writing the regex.

ASS uses **centiseconds** (2 digits) for timestamps, not milliseconds.
Multiply by 10 before passing to `_hms_to_lrc_timestamp()` which expects
milliseconds.

Strip ASS override codes: `re.sub(r"\{[^}]*\}", "", body)` removes
`{\b1}`, `{\i1}`, `{\fs28}`, `{\an8}`, etc.

ASS line breaks: `\N` (hard) and `\n` (soft). Both collapse to space.

A leading comma artifact appears in `group(11)` when the Effect field
is empty (the comma itself isn't consumed by group 10). Strip a single
leading comma defensively.

## Charset detection

`detect_text_charset(path)` in the same file:

1. Read first 4096 bytes
2. Check BOM: `EF BB BF` → utf-8, `FF FE` / `FE FF` → utf-16
3. Try strict UTF-8 decode
4. Heuristic: if >10% of bytes are in `0xA1-0xFE` range → gbk
5. Default: utf-8

The `0xA1-0xFE` range is the GBK second-byte range. The heuristic
catches asmr.one subtitles that arrive as `text/plain; charset=GB2312`
without a BOM.

After detection, decode the body with the detected charset and re-encode
as UTF-8 in the response (the kikoeru player's lrc-file-parser expects
UTF-8).

## Stream endpoint contract

`/api/media/stream/<hash>` for subtitle files:

| Header | Value |
|---|---|
| `Content-Type` | `text/plain; charset=<detected>` |
| `Content-Length` | **post-conversion** UTF-8 byte length |
| `Accept-Ranges` | `none` |
| `Cache-Control` | `public, max-age=3600` |

**The HEAD/GET length match trap.** HEAD must compute the conversion
and report its output size, NOT `real.stat().st_size` (which is the raw
input file size, not the LRC output). Forgetting this makes
`curl -I` claim a 8802-byte file when GET actually returns 6028 bytes —
which breaks the kikoeru player's content-length-based fetch logic.

The fix: run the conversion in the HEAD branch too, just throw away
the body and report `len(lrc_text.encode("utf-8"))`. Cheap (small
files), correct.

## File-tree classification

Subtitle files appear in `/api/tracks/<rj>` as `type: "text"`, NOT
`type: "subtitle"`. The kikoeru-quasar SPA's click handler is:

```js
type === "folder"   ? navigate
type === "text"     ? open in text viewer
type === "image"    ? open in image viewer
type === "other"    ? download
default             ? play as audio
```

`type: "subtitle"` would fall into the default branch and try to play
VTT as audio. **Always use `type: "text"`** for `.lrc/.vtt/.srt/.ass/.ssa`
in `_classify()`.

## End-to-end verification recipe

```bash
# 1. Pick an audio file with a non-LRC subtitle sibling.
DB="$HOME/Library/Application Support/neokikoeru/neokikoeru.db"
sqlite3 "$DB" "SELECT a.id, a.name, s.name, s.id
  FROM files a JOIN files s ON s.parent_id = a.parent_id
  WHERE a.is_folder=0 AND a.name LIKE '%.m4a'
    AND s.name LIKE '%.vtt'
    AND NOT EXISTS (SELECT 1 FROM files s2
                    WHERE s2.parent_id = a.parent_id
                      AND s2.name = REPLACE(a.name,'.m4a','.lrc'))
  LIMIT 1;"

# 2. check-lrc must return the sub hash, not null.
AUDIO="<id from step 1>"
curl -s "http://127.0.0.1:8890/api/media/check-lrc/$AUDIO"
# Expected: {"result": true, "hash": "<vtt_hash>"}

# 3. The returned sub hash streams as converted LRC.
HASH="<sub hash from step 2>"
echo "HEAD Content-Length:"
curl -sI "http://127.0.0.1:8890/api/media/stream/$HASH" | awk '/Content-Length/ {print $2}'
echo "GET actual byte count:"
curl -s "http://127.0.0.1:8890/api/media/stream/$HASH" | wc -c
# The two MUST match. If HEAD > GET, the size was computed from
# the raw file, not the converted LRC.

echo "First 6 lines of converted LRC:"
curl -s "http://127.0.0.1:8890/api/media/stream/$HASH" | head -6
# Expected: [00:02.90] / 我明白了 / blank / [00:05.20] / ...
```

## SPA-side gotcha (kikoeru-quasar)

The `AudioElement` only polls `check-lrc` from `loadLrcFile()`, which
fires on:
- Component mount
- The `source` watcher (queue item change)
- User-initiated replay

`lrcAvailable` is a Vue `data` field on the component instance — it
persists for the lifetime of the page. If a user played a track while
`check-lrc` was still returning `false` (during a server-side bug
window), the component will keep reporting "no lyrics" until a hard
refresh (`Cmd+Shift+R`).

If "VTT subtitles not loading" gets reported:
1. First verify the server side with the recipe above.
2. If server is correct, ask the user to hard-refresh the SPA.
3. If still wrong, check the browser console — `console.log('读入歌词')`
   fires when `check-lrc` returns true, `'歌词读入成功'` fires when
   the converted LRC body parses. If the first fires but not the
   second, the converted body is unparseable by `lrc-file-parser`.

## Files

- `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py` — `find_lrc_for_audio`,
  `get_subtitle_format`, `vtt_to_lrc`, `srt_to_lrc`, `ass_to_lrc`,
  `convert_subtitle_to_lrc`, `detect_text_charset`, `_classify`
- `<ASMR_STACK_ROOT>/bin/asmr-view` — `_kikoeru_stream` subtitle branch
  (handles the decode, convert, re-encode, and HEAD/GET length match)
