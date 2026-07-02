---
name: asmr-view-lrc-format
description: kikoeru-quasar SPA's lrc-file-parser v1.2.7 requires single-line [time]text LRC; multi-line (timestamp then text on next line) silently produces zero parsed lines.
version: 1.0.0
platforms: [macos]
metadata:
  hermes:
    tags: [lrc, kikoeru, asmr-view, subtitle]
    category: media
---

# kikoeru-quasar SPA's lrc-file-parser v1.2.7 format requirement

The kikoeru-quasar SPA at `<ASMR_STACK_ROOT>/kikoeru-spa/` bundles
`lrc-file-parser.js v1.2.7` (lyswhut). Its `_initLines` uses:

```js
var s = /^\[([\d:.]*)\]{1}/g;
// ...
const line = raw.trim();
if (s.exec(line)) {
  const t = RegExp.$1;                  // the time string
  const text = line.replace(s, '').trim(); // everything after [time]
  // ... build { time, text }
}
```

The regex matches `[time]` AND strips it from the same line. The
remaining `text` is what becomes the lyric. So `time` and `text`
**MUST be on the same line**:

```
[00:02.90]我明白了              <- WORKS
[00:05.20]就是说会长想和我交往是吗？
```

If you emit multi-line LRC like:

```
[00:02.90]
我明白了
[00:05.20]
就是说会长想和我交往是吗？
```

The parser produces 2 lines with `text: ""` (timestamps parsed but
no text). The kikoeru player receives the body, calls
`lrcObj.setLyric(body)`, the parser builds an empty lines array,
and lyrics never display. **The error is silent** — no exception,
no console error in the SPA.

## Why this matters for asmr-view's subtitle→LRC converters

`asmr_view_kikoeru.py` `vtt_to_lrc`, `srt_to_lrc`, `ass_to_lrc`
must emit single-line LRC. The current implementation does:

```python
out.append(pending_ts + " ".join(
    s.strip() for s in pending_text if s.strip()
))
```

instead of the more common (and kikoeru-express-style) multi-line:

```python
out.append(pending_ts)
# ... next iteration ...
out.append(text)
```

## Detection: did I just emit multi-line LRC?

If `lrc-file-parser` is producing zero lines, the converted LRC body
on the wire is multi-line. Quick check:

```sh
curl -s "http://127.0.0.1:8890/api/media/stream/<hash>" | head -5
# Should look like: [00:02.90]text on one line
# NOT like:        [00:02.90]   then text on next line
```

## Verification (run the actual v1.2.7 parser against the output)

```js
import { readFileSync } from 'fs';
const s = /^\[([\d:.]*)\]{1}/g;
const text = readFileSync('/tmp/converted.lrc', 'utf8');
const parsed = [];
for (const raw of text.split(/\r\n|\n|\r/)) {
  const line = raw.trim();
  s.lastIndex = 0;
  if (s.exec(line)) {
    const t = RegExp.$1;
    const x = line.replace(s, '').trim();
    parsed.push({ time: t, text: x });
  }
}
console.log(parsed.length, 'lines;', parsed.filter(p => p.text).length, 'with text');
```

`lines > 0` AND `with text == lines` = correct.

## Don't upgrade lrc-file-parser without checking

Newer lrc-file-parser versions (2.x) use a different regex
(`/^(?:[\d:.]+)+/g`, no brackets) and would need a different LRC
shape. The kikoeru-quasar SPA's `vendor.86022408.js` bundle is pinned
to 1.2.7. Upgrading the SPA's parser requires rebuilding
`kikoeru-spa` from source (see
`docs/skills/asmr-library-ops/references/kikoeru-quasar-build.md`).

## Related

- `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py` — VTT / SRT / ASS / SSA
  → LRC converters (lines ~430-600). The `flush()` helper in each
  emits `[time]text` joined on one line.
- `docs/skills/asmr-library-ops/SKILL.md` — asmr-library
  skill with the broader workflow.
- The bug was discovered when the user reported "VTT subtitles don't
  auto-load" after my multi-line fix. The server was correct (HTTP
  200, valid timestamps) but the SPA's lrc-file-parser silently
  produced zero lines.
