# Direct-disk streaming from asmr-view

The asmr-view handlers `/api/media/stream/<hash>`, `/api/media/download/<hash>`,
and the legacy `/api/stream/<file_id>` resolve the file's real disk path
from the Neokikoeru SQLite DB and stream it directly with a local
HTTP `Range` parser. Neokikoeru's `/api/v1/fs/download` is kept only as
a fallback.

This file is the contract: when to use disk, when to fall back, how the
storage root is resolved, and how to verify byte-for-byte that the
stream matches the on-disk file.

## Why direct (not proxy)

User preference (2026-06-22): the kikoeru client (and the hand-rolled
SPA) should never depend on the wedged Neokikoeru Go server for audio
playback. The chain through `:8889/api/v1/fs/download` was failing in
ways that made the kikoeru client show metadata but no audio. Reasons
for the switch:

- Removes the dependency on the Go server being alive (it wedges
  under load — see `troubleshooting-flow.md` § "When the server
  wedges").
- Halves the round-trip latency (no `:8889` hop).
- Eliminates JWT plumbing on the hot path (the token is no longer
  required for streaming; only the Build button still needs it).
- Makes the wedged-server recovery (`serve stop && serve start`)
  unnecessary for playback.
- Keeps a single source of truth for the on-disk bytes: the file
  itself, not Neokikoeru's possibly-stale pre-served version.

## Storage root resolution

The storage root is resolved at request time in this order:

1. `ASMR_STORAGE_ROOT` environment variable.
2. `<ASMR_STACK_ROOT>/serve-config.json` `"storage_root"` key.
3. `/Volumes/TOSHIBA/AMSR` (the default).

```python
def get_storage_root() -> Path:
    env = os.environ.get("ASMR_STORAGE_ROOT")
    if env:
        return Path(env)
    if CONFIG_PATH.exists():
        try:
            cfg_root = json.loads(CONFIG_PATH.read_text()).get("storage_root")
            if cfg_root:
                return Path(cfg_root)
        except Exception:
            pass
    return _DEFAULT_STORAGE_ROOT  # /Volumes/TOSHIBA/AMSR
```

To set it permanently, write `"storage_root": "/Volumes/TOSHIBA/AMSR"`
into `<ASMR_STACK_ROOT>/serve-config.json` (it's already there as of
2026-06-22). For a one-off override (testing a different mount),
export the env var before `asmr-view start`.

## Path resolution from the DB

The `files` table stores paths as `/<RJ>/<filename>.mp3` (leading
slash). The handler concatenates the storage root and the path WITHOUT
doubling the slash:

```python
rel_path = row["path"]                            # "/RJ01010222/01_...mp3"
real = get_storage_root() / rel_path.lstrip("/")  # "/Volumes/TOSHIBA/AMSR/RJ01010222/01_...mp3"
```

`pathlib.Path` concatenation with a trailing slash on the storage
root would produce `//RJ01010222/...` which still works on macOS but
is fragile; `lstrip("/")` is the explicit correct form.

## Disk-direct vs proxy decision

```text
1. SELECT name, work_id, path FROM files WHERE id = ?
2. Resolve real = storage_root / path.lstrip("/")
3. If real.is_file():
       _serve_file_range(real, ...)        # local open(path, "rb")
       return
4. Else (fallback to Neokikoeru):
       If get_token() and neo is up:
           urllib to /api/v1/fs/download
           forward Range + status + Content-Range
       Else:
           503 {"error": "file missing on disk and no neo token (X not found)"}
```

The fallback exists because after `neokikoeru prune -y` and a fresh
re-scan, the `files` table may contain paths the disk no longer
satisfies (partial recovery). For a healthy library, the fallback
should never fire — every hash the kikoeru client requests should
resolve to a real file.

## The `_serve_file_range` helper

All three handlers (kikoeru stream, kikoeru download, legacy
`/api/stream`) use a single helper. It:

- Stats the file for `Content-Length`.
- Guesses `Content-Type` via `mimetypes.guess_type` (mp3 → `audio/mpeg`,
  wav → `audio/wav`, jpg → `image/jpeg`, etc.).
- Parses `Range: bytes=N-M`, `bytes=N-`, `bytes=-N` (suffix range).
- Returns 416 with `Content-Range: bytes */<size>` for unsatisfiable
  ranges.
- Streams 64 KiB chunks via `open(path, "rb")` + `f.seek(start)`.
- Catches `BrokenPipeError` and `ConnectionResetError` quietly (the
  client canceled — that's not a server error).
- Adds `Cache-Control: public, max-age=3600` for stream, and an
  RFC 5987 `Content-Disposition: attachment; filename*=UTF-8''...`
  for download.

The helper is the only place HTTP Range parsing lives. If a future
session needs to add another stream-like endpoint, reuse it — don't
re-implement.

## Byte-for-byte verification recipe

When the user reports "metadata but no audio" or "playback fails",
this recipe proves (or disproves) the disk-direct path is correct:

```sh
# 1. Get a hash for an audio file
HASH=$(sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id FROM files WHERE work_id = 'RJ01010222' AND is_folder = 0 AND size > 1000000 ORDER BY size DESC LIMIT 1;")
echo "hash=$HASH"

# 2. Get the real on-disk path
PATH_REL=$(sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT path FROM files WHERE id = '$HASH';")
REAL="/Volumes/TOSHIBA/AMSR${PATH_REL}"
ls -la "$REAL"

# 3. Compare first 32 bytes
echo "=== first 32 bytes via asmr-view ==="
curl -s "http://127.0.0.1:8890/api/media/stream/$HASH?token=t" -r 0-31 | md5
echo "=== first 32 bytes from disk ==="
dd if="$REAL" bs=1 count=32 2>/dev/null | md5

# 4. Compare a range (verifies Range header + seek + 206 path)
echo "=== bytes 1000-1031 via asmr-view ==="
curl -s "http://127.0.0.1:8890/api/media/stream/$HASH?token=t" -r 1000-1031 | md5
echo "=== bytes 1000-1031 from disk ==="
dd if="$REAL" bs=1 skip=1000 count=32 2>/dev/null | md5

# 5. Random sample of 5 files across 3 works (mp3, wav, jpg, m4a)
sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id, name, work_id, path FROM files WHERE is_folder = 0 AND size > 1000000 ORDER BY RANDOM() LIMIT 5;" \
  | while IFS='|' read id name work path; do
      FULL="/Volumes/TOSHIBA/AMSR${path}"
      [ -f "$FULL" ] || { echo "MISSING $id $name ($FULL)"; continue; }
      curl_md5=$(curl -s "http://127.0.0.1:8890/api/media/stream/$id?token=t" -r 0-15 | md5)
      disk_md5=$(dd if="$FULL" bs=1 count=16 2>/dev/null | md5)
      [ "$curl_md5" = "$disk_md5" ] && echo "OK | $id | $name | $work" \
                                     || echo "MISMATCH | $id | $name | $work"
    done
```

All five should print `OK`. If any prints `MISMATCH`, the byte stream
is being mutated somewhere (mimetype handler, double-conversion,
corrupted path resolution) — debug that handler, not the DB.

If a file prints `MISSING`, the disk really doesn't have it (check
`ls -la "$FULL"`) and the proxy fallback should kick in.

## Storage root pitfalls

- **Leading slash double-up.** `Path("/Volumes/TOSHIBA/AMSR") /
  "/RJ01010222/foo.mp3"` produces
  `Path("/Volumes/TOSHIBA/AMSR/RJ01010222/foo.mp3")` correctly because
  `pathlib` discards the leading `/` from the second component.
  But `Path("/Volumes/TOSHIBA/AMSR/") / "/RJ01010222/foo.mp3"` keeps
  the leading `/` and produces `//RJ01010222/...` (still resolves on
  macOS, but is fragile). Always use `rel_path.lstrip("/")` to be
  safe.
- **Wrong storage root in `serve-config.json`.** If the user mounts
  the drive at `/Volumes/TOSHIBA2/AMSR` or similar, the
  `storage_root` key must be updated. Symptom: every file is
  `MISSING` and the proxy fallback returns 502 from a dead Neokikoeru.
  Fix: edit `serve-config.json` and `asmr-view stop && asmr-view start`.
- **TOSHIBA drive not mounted.** `/Volumes/TOSHIBA/AMSR` doesn't
  exist. `get_storage_root()` doesn't check — it returns the path
  string, and `is_file()` will return False for every file, falling
  through to the proxy. Symptom: audio works only if Neokikoeru is
  also up. Fix: `diskutil mountDisk /dev/disk6s2` (or whatever the
  disk identifier is; check `diskutil list`).
- **`ASMR_STORAGE_ROOT` env var shadows the config.** If you set the
  env var for testing and forget to unset it, future sessions use the
  test path. Document the env var in shell rc or use the config file
  instead for any persistent override.

## Legacy `/api/stream/<file_id>` still exists

The hand-rolled SPA at `<ASMR_STACK_ROOT>/view/index.html` still calls
the legacy `/api/stream/<file_id>` endpoint (UUID form, not kikoeru's
12-char hash). It uses the **same** `_serve_file_range` helper, so
it's already disk-direct. The legacy route is kept for backward
compatibility with the hand-rolled SPA; new code should call
`/api/media/stream/<hash>`.
