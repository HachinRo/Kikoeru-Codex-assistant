# Full project audit — 2026-07-11

## Scope and method

Read-only audit of the tracked repository, local runtime configuration, live
service on port 8890, NeoKikoeru database consistency, media/subtitle counts,
HTTP route behavior, test suite, source-sanitization checks, binary checksums,
skill synchronization, documentation, and principal trust boundaries. Media
and database contents were not modified.

## Executive summary

The stack is operational and its core safeguards are working. All 11 tests
pass; source validation, binary verification, Python compilation, and skill
synchronization pass; the live viewer and dashboard are healthy; all 116 works
and 8,770 indexed file rows resolve without missing paths; and unauthenticated
admin reindex requests correctly receive HTTP 401.

No critical issue was found. Two medium-priority robustness/security issues,
two low-priority trust-boundary/availability issues, and two maintenance gaps
remain. The most concrete correctness defect is malformed HTTP range handling,
reproduced against the live service.

## Findings

### P2 — Explicit HTTP ranges are not clamped to EOF

`AsmrViewHandler._serve_file_range` accepts an explicit end offset without
clamping it to `file_size - 1` (`Web-UI/bin/asmr-view:2135-2149`). The service
then advertises a body larger than the file and writes fewer bytes than its
`Content-Length` promises.

Live reproduction against a file of 874,773 bytes:

```text
Range: bytes=0-875772
HTTP/1.0 206 Partial Content
Content-Length: 875773
Content-Range: bytes 0-875772/874773
```

This violates byte-range semantics and can cause clients or proxies to wait
for bytes that never arrive. Clamp `end = min(end, file_size - 1)` before
validation and add tests for open, suffix, overlong, empty, and unsatisfiable
ranges.

### P2 — LAN-facing request bodies are unbounded

POST, PUT, and DELETE parse `Content-Length` and call `rfile.read(clen)` without
an upper bound (`Web-UI/bin/asmr-view:1076-1081`, `1148-1152`, `1170-1174`).
Because the viewer is a `ThreadingHTTPServer` bound to `0.0.0.0`, any host on
the trusted LAN can hold threads with slow bodies or request excessive memory.
Review text and progress are also persisted without size limits
(`Web-UI/bin/asmr-view:1246-1265`).

Reject missing, negative, or excessive body lengths with HTTP 411/413, use a
small route-appropriate cap (for example 64 KiB), set socket/request timeouts,
and cap persisted text fields.

### P3 — Compatibility auth permits unauthenticated personal-data writes

Kikoeru compatibility authentication deliberately accepts any credentials and
reports a guest user in the admin group (`Web-UI/bin/asmr-view:2307-2329`).
POST/PUT/DELETE review routes do not require dashboard authentication
(`Web-UI/bin/asmr-view:1131-1134`, `1153-1156`, `1175-1176`). Any trusted-LAN
client can therefore overwrite or remove the single local user's ratings,
reviews, and progress. Media deletion and maintenance actions are separately
protected and were verified to return HTTP 401 without credentials.

Either document review state as intentionally shared LAN state or require the
same admin credential for review mutations. Avoid labeling the compatibility
guest as `group: admin`, which obscures the actual authorization boundary.

### Resolved 2026-07-12 — Serve-index rebuild was destructive rather than atomic

The indexer previously removed the current index before constructing its
replacement. It now builds in a sibling temporary directory, installs only a
completed replacement, restores the old index after an installation failure,
and preserves the backup for manual recovery if restoration itself fails.
Success, build-failure, and install-failure paths have automated coverage.

### P3 — Automated coverage is narrow relative to runtime surface

The suite has 11 tests. Operational coverage checks four high-value invariants,
but the 2,720-line HTTP service has no end-to-end handler tests. The reproduced
range defect, request-size handling, route authentication, path containment,
subtitle conversion edge cases, and delete confirmation are not exercised.
Add a temporary-database HTTP fixture and prioritize boundary and mutation
tests over additional static string assertions.

### P4 — Current-state documentation has drifted

`docs/ASMR_PIPELINE.md:150` reports 2,562 VTT files; the current media tree has
2,528 VTT, 214 LRC, and 1 SRT file (2,743 total), matching the live dashboard's
`subs=2743`. Work coverage remains correct at 107 of 116, with nine missing.
Generate volatile counts through a command or label them with a capture date to
avoid presenting snapshots as durable facts.

## Verified controls and health

- `scripts/test.sh`: 11/11 tests passed.
- `scripts/validate-source.sh`: passed; runtime secrets and downloaded binaries
  are not tracked.
- `scripts/verify-binaries.sh`: both local binary SHA-256 checks passed.
- `scripts/sync-skills.sh --check`: passed.
- Python `compileall`: passed.
- `ruff` and `shellcheck`: unavailable locally, so those lint passes were not
  executed.
- Viewer: running on intentional `0.0.0.0:8890`; health endpoint OK.
- Dashboard: health and summary endpoints OK.
- Library: 116 folders/works, 4,043 audio files, 2,743 subtitle files.
- NeoKikoeru: 116 works, 8,770 file rows, zero missing indexed paths.
- Missing subtitles: nine RJs, consistent across CLI and dashboard.
- Representative works, search, tag, circle, and VA endpoints returned HTTP
  200.
- Admin endpoint: unauthenticated `POST /api/admin/reindex` returned HTTP 401.
- `Web-UI/serve-config.json`: ignored by Git and mode `0600`; its sensitive
  values were not copied into this report.
- Working tree was clean at audit start; no runtime state was changed.

## Recommended order

1. Fix and test range clamping.
2. Add request-body caps and timeouts.
3. Decide whether review/progress state is shared or authenticated, then encode
   that decision in tests and documentation.
4. Make serve-index replacement atomic.
5. Add HTTP integration coverage and install `ruff`/`shellcheck` in the
   development or CI workflow.
6. Refresh or generate documentation counts.
