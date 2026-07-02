# `asmr-library fill` — backfilling missing files into a published work

The `fill` subcommand (added 2026-06-22) is the canonical answer
to the user complaint "this work is incomplete / has missing
tracks". It reuses the existing `asmroner` downloader — no
hand-rolled Python script is required, even when the torrent
source has fewer files than asmr.one.

## When to use which subcommand

| Scenario | Subcommand |
|---|---|
| Nothing on disk, fresh download | `asmr-library download X` (stages via asmroner, atomic rename) |
| Partial staging data exists under `AMSR.incoming/<RJ>.partial` from a previous failed download | `asmr-library retry X` (resumes the staging) |
| **The published folder exists but is missing some files** | **`asmr-library fill X`** (re-downloads to a `.fill` staging temp, `cp -n`-merges into the published folder) |
| The published folder is fine but the Neokikoeru DB is stale (e.g. files added manually) | `asmr-library build` (refreshes the index) |

The wrapper's case statement routes `fill` to the worker's
`run_fill` function, which:

1. Verifies the published folder exists — fails fast if not,
   pointing the user at `download` instead.
2. Acquires the per-RJ lock.
3. Creates a `.fill` staging temp under
   `AMSR.incoming/<RJ>.fill` (distinct from the `.partial` pattern
   so `retry` and `status` don't see it).
4. Runs `asmroner download <RJ> -d <.fill staging>` to get the
   full work from the torrent/magnet source.
5. Locates the payload (the directory `asmroner` creates inside
   the staging temp, named `<RJ>-<date>-sub-…`).
6. Walks the payload, `cp -p` each file into the published folder
   with **no-clobber** (`cp -n` semantics implemented via
   existence check) — files already on disk are preserved
   untouched. Size conflicts (existing file differs in size from
   the torrent) are logged as warnings but the existing file is
   kept.
7. `rm -rf` the staging temp.
8. Log a summary line: `fill_added=N fill_kept=N fill_conflicts=N
   fill_bytes_added=N`.

## Critical: the `status` lie

The worker's `status_one` reports `COMPLETE` whenever
`/Volumes/TOSHIBA/AMSR/<RJ>/` exists, regardless of how many files
are actually inside. This is why the user may say "this work is
incomplete" while `asmr-library status X` says it's complete. The
correct diagnostic sequence is:

1. `asmr-library status X` — confirms the folder exists.
2. `find /Volumes/TOSHIBA/AMSR/X -type f | wc -l` — counts what's
   actually on disk.
3. Compare to asmr.one's track tree (`asmr-subs check X` is
   lighter than `tracks` but doesn't give a count; the asmr.one
   `tracks` API at `/api/tracks/<asmr-id>` is the authoritative
   source).
4. If there are missing files, `asmr-library fill X` backfills
   them.

## After fill: refresh the Neokikoeru index

`asmr-library build` re-indexes Neokikoeru's SQLite DB so the new
files appear in `/api/tracks/<RJ>` on the asmr-view server.
**This step is required** — fill writes to disk, but asmr-view
reads the DB, not the disk, so without `build` the new files
won't show up in the kikoeru-quasar SPA.

The full clean-up sequence after a `fill`:

```sh
asmr-library fill RJ01555607
# wait for "FILLED" or "FILL_NOOP" line in the output
asmr-library build               # refreshes Neokikoeru index
# verify in browser at http://<lan-ip>:8890/work/RJ01555607
```

## How long fill takes

`fill` is a blocking call. asmroner can take anywhere from 30
seconds (cached torrent) to 30+ minutes (fresh torrent with many
large files like WAVs). Always run `asmr-library fill X` from a
terminal that can stay open, or in the background mode of the
agent's terminal tool. The wrapper does NOT background the
worker; it blocks until `run_fill` returns.

For a work with 12+ files including WAVs (a 558MB WAV per
track), expect 5-15 minutes for the re-download alone, plus
another 30-60s for the merge step.

## Log locations

- `<ASMR_STACK_ROOT>/logs/<RJ>.log` — fill run
  summary, asmroner output, conflict warnings.
- `<ASMR_STACK_ROOT>/serve.log` — Neokikoeru
  re-index from `asmr-library build`.

The fill log appends with a marker line per run:

```
=== 2026-06-22T17:54:40Z fill RJ01555607 ===
fill_stage=/Volumes/TOSHIBA/AMSR.incoming/RJ01555607.fill
final=/Volumes/TOSHIBA/AMSR/RJ01555607
2026/06/23 01:54:40 📥 正在下载以下资源: [RJ01555607]
…
2026/06/23 01:57:19 ✅ 资源下载完成！
fill_completed=2026-06-22T17:57:19Z
fill_added=0
fill_kept=31
fill_conflicts=1
fill_bytes_added=0
```

## Anti-pattern: writing a Python downloader

A common mistake (caught by the user on 2026-06-22) is to write
a Python script that pulls files from asmr.one directly when
`asmr-library fill` already does the equivalent via asmroner.
Don't do this — the asmr.one API is gated, requires the
asmr-subs login, and bypasses the worker's verification
(no_partial_files / has_nonempty_audio / has_zero_byte_audio).
Use `fill` and let asmroner + the worker pipeline handle the
fetch and verify. The only case where a direct asmr.one fetch
is justified is when the asmroner torrent source is missing
files that asmr.one has (rare — usually a torrent vs. mirror
divergence). In that case, follow the spirit of the `fill`
implementation: re-use the worker for the part of the work it
can do, and only the missing pieces need a hand-rolled fetch.

## Source code locations

- `<ASMR_STACK_ROOT>/bin/asmr-library-worker` `run_fill` —
  orchestrates the re-download + merge.
- `<ASMR_STACK_ROOT>/bin/asmr-library` — wrapper case statement
  routes `fill` to the worker.
- `<ASMR_STACK_ROOT>/bin/asmr-library-worker` `find_payload` —
  detects the asmroner-created payload dir inside the staging
  temp (name pattern: `<RJ>-<date>-sub-…`).
