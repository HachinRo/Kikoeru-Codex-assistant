# ASMR pipeline: current implementation

This document describes the code that is actually installed and running as of
2026-06-23. It deliberately favors live code and database evidence over older
Hermes notes where they disagree.

## Data flow

```text
explicit RJ code
    |
    v
asmr-library
    |
    +-- download/retry/fill --> asmr-library-worker
    |                              |
    |                              v
    |                         ASMRoner v2.0.6
    |                              |
    |                              v
    |                  <ASMR_MEDIA_ROOT>.incoming
    |                              |
    |                    validate + atomic rename
    |                              |
    |                              v
    |                     <ASMR_MEDIA_ROOT>/RJ...
    |
    +-- subs fetch ----------> asmr-subs
                                   |
                    asmr.one edition discovery
                                   |
                      subtitle/audio matching
                                   |
                    subtitle beside local audio

NeoKikoeru scan/index --> neokikoeru.db --> asmr-view --> Kikoeru SPA
```

The TOSHIBA library is canonical. ASMRoner's metadata database, NeoKikoeru's
SQLite database, and the compiled Kikoeru frontend are derived state.

## Source and reference repos

The user-maintained public ASMR-Kikoeru source/reference repo is checked out at:

```text
refs/ASMR-Kikoeru
https://github.com/HachinRo/ASMR-Kikoeru
```

Use it as the canonical ASMR-Kikoeru reference for pipeline-related work. The
other `refs/` checkouts remain comparison references for upstream behavior:
`refs/kikoeru-express`, `refs/asmr-downloader`, and `refs/neokikoeru`.

## ASMRoner

Installed binary:

```text
<ASMR_STACK_ROOT>/bin/asmroner
version v2.0.6, arm64 Mach-O
```

Configuration and state:

```text
<ASMR_STACK_ROOT>/.asmroner-data/config.toml
<ASMR_STACK_ROOT>/.asmroner-data/asmroner.db
<ASMR_STACK_ROOT>/.asmroner-data/download_errors.log
```

The configured download rate is intentionally conservative: two workers,
three retries, download QPS 0.2, and 2–5 seconds of jitter. The binary uses
asmr.one-compatible APIs and currently contains `https://api.asmr-300.com` as
an endpoint string.

Do not use raw `asmroner download` for normal library additions. The worker
adds safeguards the binary lacks:

- validates `RJ` identifiers;
- refuses to run when the external volume is unavailable;
- locks per RJ;
- stages under `<ASMR_MEDIA_ROOT>.incoming`;
- rejects empty audio, zero-byte audio, and partial-download files;
- publishes by same-volume atomic rename;
- preserves failed staging for explicit retry;
- never overwrites a completed RJ folder.

Commands:

```sh
<ASMR_STACK_ROOT>/bin/asmr-library download RJ01234567
<ASMR_STACK_ROOT>/bin/asmr-library retry RJ01234567
<ASMR_STACK_ROOT>/bin/asmr-library fill RJ01234567
<ASMR_STACK_ROOT>/bin/asmr-library status RJ01234567
```

`fill` is different from `retry`: it redownloads an already-published work to
a temporary `.fill` directory and copies only missing files. Existing files,
including conflicting ones, are retained.

## Subtitle fetcher

`asmr-subs` calls:

```text
GET  https://api.asmr-200.com/api/workInfo/<numeric-id>
GET  https://api.asmr-200.com/api/tracks/<numeric-id>
GET  mediaDownloadUrl or mediaStreamUrl from a subtitle leaf
POST https://api.asmr-200.com/api/auth/me       (optional login)
```

For an original Japanese RJ, it discovers translated sibling editions through
`language_editions` and `other_language_editions_in_db`. Selection priority is:

```text
Simplified Chinese > Traditional Chinese > English > Japanese
```

It then:

1. groups remote subtitle leaves by folder and inferred audio format;
2. groups local audio by immediate parent folder and extension;
3. prefers same-extension and equal-size groups;
4. matches exact filenames when possible;
5. otherwise matches tracks by sorted position;
6. names the subtitle after the local audio file.

This is necessarily heuristic. Always use `--dry-run` when inspecting a new or
unusual folder layout:

```sh
<ASMR_STACK_ROOT>/bin/asmr-library subs fetch RJ01234567 --dry-run
```

The source subtitle extension is preserved. VTT remains VTT, LRC remains LRC.
GB2312 data is decoded, with GBK replacement as fallback, and written as UTF-8.

Current library coverage:

```text
97 works total
49 works with at least one on-disk subtitle
48 works without an on-disk subtitle
791 VTT, 168 LRC, and 1 SRT files
```

ASMRoner's local metadata marks 48 exact editions as having subtitles, but
this field does not account for translated sibling editions. `asmr-subs check`
against the live API is authoritative for sibling discovery.

## Viewer ingestion

The Kikoeru backend does not discover new folders directly. `asmr-view` reads:

```text
<NEOKIKOERU_DB>
```

NeoKikoeru storage ID 1 currently points directly to:

```text
<ASMR_MEDIA_ROOT>/
```

Therefore a new download or `fill` needs NeoKikoeru scan/index tasks before it
appears in the Kikoeru viewer. NeoKikoeru must temporarily be running, logged
in, and have a valid JWT. `asmr-library build` now wraps that maintenance
sequence.

The Kikoeru endpoint `POST /api/admin/reindex` currently returns HTTP 200 even
when its internal NeoKikoeru requests fail. Inspect the JSON `results.scan`
and `results.index` values; do not treat HTTP status alone as success.

## Operator dashboard

```sh
<ASMR_STACK_ROOT>/bin/asmr-library build
<ASMR_STACK_ROOT>/bin/asmr-library dashboard --host 127.0.0.1 --port 8891
```

`build` runs the NeoKikoeru maintenance sequence. The dashboard reports stack
health, library counts, subtitle coverage, work lookup, safe
download/retry/fill actions, subtitle dry-run/fetch actions, and the build
workflow. Default bind is localhost.

## Subtitle playback

The installed runtime currently treats VTT/SRT/ASS/SSA siblings as lyrics:

- `/api/media/check-lrc/<audio-hash>` searches in priority order:
  LRC, VTT, SRT, ASS, SSA.
- `/api/media/stream/<subtitle-hash>` converts non-LRC subtitle text to LRC
  dynamically for the Kikoeru player's LRC parser.
- Subtitle rows remain `type: "text"` in the file tree so clicking them opens
  the text viewer instead of attempting audio playback.

Some older Hermes references claim that only native LRC is used. That is not
the behavior of the installed Python code.

## Known gaps

- Download and fill do not automatically refresh NeoKikoeru afterward.
- `status` reports `COMPLETE` based only on the RJ directory existing; it does
  not compare the local file tree with the remote manifest.
- Positional subtitle matching can silently pair the wrong tracks when remote
  and local folder ordering differs.
- The ASMR viewer binds to all interfaces and has mock authentication. It
  should only be exposed on a trusted LAN.
- NeoKikoeru's generated config also currently binds to all interfaces when it
  is started.
