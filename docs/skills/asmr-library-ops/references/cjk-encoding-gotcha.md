# CJK encoding pitfall (cross-class gotcha)

This is a class-level trap that bites any skill fetching CJK content
from a server: asmr.one, DLsite mirror sites, kikoeru, some legacy
CMSes, IRC logs, BBS archives, etc.

## Symptom

You `fetch()` a `.lrc` / `.srt` / `.txt` / `.json` file, the response
body is CJK-looking, but the content is unreadable: lots of `�` (U+FFFD
replacement characters) interspersed. Example mojibake from asmr.one's
`track00_读标题.lrc`:

```
[ti:track00_������]
[00:15.60]Q����Χ���ֱ��ء����ҲҪ��
```

The first line *should* read `[ti:track00_读标题]` (the work's title in
Chinese). The first half of each `�` is a U+FFFD replacement; the bytes
are real CJK but were decoded with the wrong charset.

## Root cause

Many Asian-origin servers (and a few legacy Western CMSes) serve plain
text and subtitle files as `text/plain; charset=GB2312` (China),
`Shift_JIS` / `EUC-JP` (Japan), or `EUC-KR` (Korea). They rarely include
a `<meta charset>` tag in the body. When a browser or `urllib` defaults
to UTF-8, the GB2312 bytes (which use 2-byte sequences with both bytes
≥ 0x80) are invalid UTF-8, so every byte pair becomes a single U+FFFD.

**Always check the response's `Content-Type` header FIRST** and decode
with the declared charset, not the default.

## Fixes by tool

**Browser-driven (camofox `evaluate`):**

```js
// ❌ BROKEN — uses UTF-8 default, mangles GB2312 bytes
const text = await (await fetch(url, {credentials: "include"})).text();

// ✅ WORKS — explicit charset via TextDecoder
const r = await fetch(url, {credentials: "include"});
const buf = await r.arrayBuffer();
const text = new TextDecoder("gb2312").decode(buf);
```

`TextDecoder` labels that work in modern Firefox: `gb2312`, `gbk`,
`gb18030`, `big5`, `shift_jis`, `euc-jp`, `euc-kr`. (Not all encodings
are bundled; check with a probe if uncertain.)

**Python (urllib / httpx / requests):**

```python
import urllib.request
req = urllib.request.Request(url, headers={"Accept": "*/*"})
with urllib.request.urlopen(req, timeout=30) as r:
    raw = r.read()                            # bytes
    ctype = r.headers.get("Content-Type", "")
    charset = ctype.split("charset=", 1)[-1].strip().split(";")[0] if "charset=" in ctype else "utf-8"
    text = raw.decode(charset, errors="replace")
```

GB2312 is a strict subset of GBK; if GB2312 fails, fall back to GBK
(which decodes every valid GB2312 byte sequence and accepts many more).

## Related pitfalls

- The TypedArray Xray restriction in camofox blocks `Array.from(u8)`,
  `String.fromCharCode.apply(null, u8)`, and `u8.subarray()` from
  crossing the privileged boundary. See `camofox-browser` skill,
  "TypedArray Xray restriction" pitfall. `TextDecoder.decode(buf)`
  is the workaround that DOES work.
- `web_extract` and the `text/plain` default content-type are independent
  failure modes. `web_extract` may strip the `<meta>` tag from the body
  before sanitizing, but here the body has no `<meta>` to begin with —
  the content-type is the only signal. Use `curl` and decode yourself.
- Don't pass the result through `print()` to "see if it works" — mojibake
  is silent. Always verify a known-good sample (e.g. one specific
  character that should appear in the output) is present.

## What this is NOT

- Not a malware or prompt-injection vector. Mojibake is just data loss.
- Not a server bug to "fix" — the server is correctly serving GB2312
  bytes; the client is the one mis-decoding.
- Not specific to any one service. asmr.one, kikoeru, DLsite mirror
  sites, and most Asian-hosting CDNs do this.
