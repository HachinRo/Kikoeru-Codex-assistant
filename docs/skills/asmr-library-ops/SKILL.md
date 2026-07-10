---
name: asmr-library-ops
description: Operate, debug, repair, and extend a local ASMR-library/Kikoeru/NeoKikoeru media stack. Use when working on ASMR-library UI/features, Kikoeru-compatible search/tag/grouping routes, subtitle fetching or .vtt/.lrc encoding issues, RJ work lookup problems, NeoKikoeru indexing, local services on ports 8889/8890, or the ASMR pipeline under <ASMR_STACK_ROOT>.
---

# ASMR Library Ops

Work on the local ASMR stack assuming it is a live media service. Preserve media, databases, and user edits. Prefer read-only checks and targeted repairs, then verify through local HTTP routes the user actually sees.

Run normal shell commands directly; the former command wrapper is no longer installed.

## Fast Orientation

Primary paths and ports:

- Commands/backend: `<ASMR_STACK_ROOT>/bin`, `<ASMR_STACK_ROOT>/lib`
- Single browser/operator port: `http://127.0.0.1:8890`
- Main viewer/Kikoeru-compatible app: `http://127.0.0.1:8890`
- Integrated ASMR dashboard: `http://127.0.0.1:8890/asmr-library`
- Port `8890` intentionally binds to `0.0.0.0` for trusted-LAN playback. Preserve that behavior unless the user asks to change it. Maintenance and media-mutating dashboard actions still require admin credentials.
- Do not start standalone dashboard on `8891`; `asmr-library dashboard` should point to the integrated dashboard.
- NeoKikoeru maintenance service may be started temporarily by build/reindex, but should not remain a normal listening web port.
- ASMR media root: `<ASMR_MEDIA_ROOT>`
- NeoKikoeru DB: `<NEOKIKOERU_DB>`
- Local reference repos: `refs/ASMR-Kikoeru` (`https://github.com/HachinRo/ASMR-Kikoeru`), `refs/kikoeru-express`, `refs/asmr-downloader`, `refs/neokikoeru`

Before changing behavior, run a quick health/status pass:

```bash
"<ASMR_STACK_ROOT>/bin/media-stack-health"
"<ASMR_STACK_ROOT>/bin/asmr-view" status
"<ASMR_STACK_ROOT>/bin/asmr-library" subs list-missing
```

If the task concerns routes, search, grouping, subtitle streaming, or file locations, read `references/asmr-stack.md`.

## Common Workflows

### Restart / Hard-Refresh Kikoeru Viewer

Use `asmr-view` as the owning process for port `8890`. The local build uses `stop` + `start` rather than a `restart` subcommand. Check status first, restart cleanly, then verify `/`, `/asmr-library`, and one API route.

```bash
"<ASMR_STACK_ROOT>/bin/asmr-view" status
"<ASMR_STACK_ROOT>/bin/asmr-view" stop
"<ASMR_STACK_ROOT>/bin/asmr-view" --port 8890 start
curl -fsS "http://127.0.0.1:8890/api/health"
curl -fsS "http://127.0.0.1:8890/asmr-library"
```

If the CLI lacks a requested action, inspect `<ASMR_STACK_ROOT>/bin/asmr-view` before killing processes manually.

### Refresh/Index ASMR Works

Use the local CLI for a quick metadata/cover reindex. The HTTP admin route is authenticated and should not be scripted with embedded credentials:

```bash
"<ASMR_STACK_ROOT>/bin/asmr-library" reindex
```

For a deeper NeoKikoeru/import refresh, use:

```bash
"<ASMR_STACK_ROOT>/bin/asmr-library" build
```

Then verify disk/database counts and a known RJ lookup.

### Fetch Or Repair Subtitles

For one RJ:

```bash
"<ASMR_STACK_ROOT>/bin/asmr-library" subs fetch RJ01495866
"<ASMR_STACK_ROOT>/bin/asmr-library" work RJ01495866
```

For every work currently missing subtitles:

```bash
"<ASMR_STACK_ROOT>/bin/asmr-library" subs list-missing
"<ASMR_STACK_ROOT>/bin/asmr-library" subs fetch-missing
```

If `.vtt` or `.lrc` text is mojibake, verify both on-disk files and stream-time charset handling. Run `scripts/scan_vtt_mojibake.py` against the ASMR media root, then test the exact stream URL the user reported.

### Repair Search/Tag/Grouping Issues

Kikoeru-compatible search should cover title, RJ, intro, maker/circle, series, tags/genres, artists/VAs, and illustrators. It should not only search work titles.

Verify route families after changes:

```bash
curl -fsS "http://127.0.0.1:8890/api/search/RJ01571688?count=20&page=1"
curl -fsS "http://127.0.0.1:8890/api/tags"
curl -fsS "http://127.0.0.1:8890/api/tags/500/works"
curl -fsS "http://127.0.0.1:8890/api/circles/RG74824/works"
curl -fsS "http://127.0.0.1:8890/api/vas/eRGTnmW8/works"
```

## Editing Guidance

- Patch source-like Python/CLI files under `<ASMR_STACK_ROOT>/bin` and `<ASMR_STACK_ROOT>/lib` carefully; these are live service files.
- Treat compiled SPA bundle edits as fragile. If patching `kikoeru-spa/js/app.*.js`, create a suffixed file and update `kikoeru-spa/index.html` to point to it.
- Use `refs/ASMR-Kikoeru` as the user-maintained GitHub source/reference repo for ASMR-Kikoeru pipeline work; pull it before source comparisons when network is available.
- Treat `docs/skills/` as the canonical skill source. Run `scripts/sync-skills.sh --check` before handoff and `scripts/sync-skills.sh --install` after approved changes.
- Never modify media files or the NeoKikoeru database unless the task explicitly requires that operation and it is understood.
- Keep cloned upstream repos as references unless the user asks for source-level porting.
- After repair, verify local HTTP endpoints with one realistic work/RJ example.

## Known Good Examples

- Subtitle stream fixed previously: `http://localhost:8890/api/media/stream/ylelmK2e_kI?token=`
- Expected first line: `[00:01.43]二人「製作人，恭喜您~」`
- Tag example: `/api/tags/500/works` returns tag `舔耳` and many works.
- Circle example: `/api/circles/RG74824/works` returns Clover Voice works.
- VA example: `/api/vas/eRGTnmW8/works` returns `しましまはかせ` works.
