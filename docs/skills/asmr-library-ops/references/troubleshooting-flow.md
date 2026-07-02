# Neokikoeru troubleshooting flow

When the user reports "X is broken in Neokikoeru / the WebUI", work
through this decision tree before guessing. The symptoms map to a small
set of root causes; most are quick to fix once you know which bucket
you're in.

## Symptom → root cause table

| Symptom | Root cause | Fix |
|---|---|---|
| WebUI shows works + covers but no audio plays | Storage `index` task never ran, or DB was wiped since | `asmr-library serve storage index 1` then poll `serve tasks` |
| WebUI shows works + covers but no audio plays (kikoeru / hand-rolled client) | asmr-view's stream/download is not yet disk-direct, or the storage root is wrong | See `direct-disk-streaming.md` — verify with the byte-for-byte recipe, then check `serve-config.json` `storage_root` and `get_storage_root()` resolution |
| WebUI shows works + covers but file sizes are tiny (e.g. <1000) and no audio | `scan` ran but `index` didn't — `files.size` is filename length, not byte count | same as above |
| WebUI shows work metadata + chobit.cc iframe, but no native file/track list and only 5 chobit sample tracks | v3.7.1 WebUI has **no native file list view** — the chobit.cc embed is DLsite's affiliate preview player and intentionally shows only 5 sample tracks, NOT your local files. The `with_files=true` toggle is a no-op; the API doesn't return a `files` array on `/works` or `/work/:id`. | **This is a v3.7.1 frontend limitation, not a config bug.** Your files are indexed (check `SELECT COUNT(*) FROM files`) and streamable via `/api/v1/fs/download?file_id=<id>`. Options: (a) accept the chobit preview for casual listening, (b) write a 30-line CLI that calls `/fs/download` for full file access, (c) upgrade to a Neokikoeru version that adds a native file list (none known at v3.7.1). |
| `curl /api/v1/fs/list` returns 404 | The `/fs/list` and `/file/list` routes appear in the binary string table but are **not registered** in v3.7.1 (likely compiled out or admin-only). The public list API is `/api/v1/works` (no file list) and per-work file access is via `/api/v1/fs/download?file_id=<id>`. | Don't rely on `/fs/list` to enumerate files. Use `sqlite3 ... "SELECT id, name, size, path FROM files WHERE work_id='RJ...' LIMIT 50"` for the file list. |
| Works show metadata with empty titles / intros / cover images | DLsite scrape failed (likely Chinese VPN) — see `dlsite.proxy_url` in `config.json` | Set `proxy_url` in `dlsite` block, restart server, `serve storage scan 1` |
| WebUI: "scan storage 1" shows 0 succeeded on a fresh `prune` | You ran `scan` only. Need `index` too (it populates `files`) | `serve storage index 1` |
| API returns 401 immediately, before any 200 | JWT in `serve-config.json` is stale / never written | `asmr-library serve login admin <pw>` |
| API returns 200 for `/` but every `/api/v1/...` call times out (5s+) | Server is wedged from a prior aborted request (Go goroutine stall) | `asmr-library serve stop && asmr-library serve start` |
| API returns 200 but `fs/download?file_id=X` returns 0 bytes / wrong type | `files` table has no record for that id (scan/index didn't run for that path) | `serve storage index 1` and verify the path is under `root_folder_path` |
| API returns 400 on `fs/download?file_id=X` | File id format wrong, or path doesn't resolve under the storage's `root_folder_path` | `sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" "SELECT id, path, size FROM files WHERE is_folder=0 LIMIT 5"` — verify the path |
| `serve storage add` returns 200 but new storage isn't shown in `serve storage list` | The response was a create-confirmation, not a list. Re-run `list` to verify. | (no fix needed) |
| Admin password lost | First-run log line is gone AND `serve-config.json` is empty | `neokikoeru admin reset-pwd` prints a new one |
| `prune` deleted everything | `prune -y` wipes the data dir but NOT the audio on disk | `serve start` recreates the data dir, then `serve login` → `serve storage add /Volumes/TOSHIBA/AMSR/` → `serve storage scan 1` → `serve storage index 1` |

## Fast diagnosis commands

Run these in order — they take 2-5 seconds each and answer 80% of
"what's wrong":

```sh
# 1. Server alive?
curl -s -m 3 -o /dev/null -w "/ -> %{http_code}\n" http://localhost:8889/

# 2. Auth works?
asmr-library serve status

# 3. Storage config — is root_folder_path correct?
asmr-library serve storage list

# 4. Files table — are there any real-sized files?
sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT COUNT(*), MIN(size), MAX(size) FROM files WHERE is_folder=0"

# 5. Are there any recent stuck tasks?
asmr-library serve tasks

# 6. Audio actually serves?
TOK=$(python3 -c "import json; print(json.load(open('<ASMR_STACK_ROOT>/serve-config.json'))['token'])")
FID=$(sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id FROM files WHERE is_folder=0 AND name LIKE '%.mp3' ORDER BY size DESC LIMIT 1")
curl -s -m 5 -o /tmp/test.mp3 -w "HTTP %{http_code}, %{size_download} bytes, type=%{content_type}\n" \
  -H "Authorization: Bearer *** "http://localhost:8889/api/v1/fs/download?file_id=$FID"
```

If step 6 returns `200` with `audio/mpeg` and the expected size, the
system is healthy. Otherwise, the symptom → root cause table above
points at the fix.

## How the v3.7.1 WebUI actually displays audio (important!)

If the user complains "I can't see files in the WebUI" but the API
returns real audio, **do not assume a config bug.** Verify what the
WebUI actually renders. From a browser logged into `http://localhost:8889/`:

1. **Home page (`/`)**: shows `Recently added` cover grid + `Recently played`. No files, no tracks, just thumbnails.
2. **List page (`/works`)**: shows a card per work with cover, title, rating, genres, maker, DLsite link. The `with_files` toggle in the search bar is a **no-op** (it toggles a UI flag but the API doesn't honor it).
3. **Work page (`/work/RJ...`)**: shows the full metadata card + **a single chobit.cc `<iframe>` embed**. The chobit iframe is DLsite's affiliate player — it intentionally shows only **5 preview tracks** (DLsite's public sample), not your local files. Even if the work has 117 audio files in your library, the iframe shows 5.
4. **No native file list, no native track list, no native audio player** is rendered by the v3.7.1 WebUI. The hidden `q-card audio-player` element is `display: none` until something starts playing (and nothing in the v3.7.1 UI can start it — the chobit iframe plays its own preview tracks, not the user's files).

**How to verify a file plays correctly** (the right way to answer
"can the user hear their files?"):

```sh
TOK=$(python3 -c "import json; print(json.load(open('<ASMR_STACK_ROOT>/serve-config.json'))['token'])")
FID=$(sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id FROM files WHERE is_folder=0 AND name LIKE '%.mp3' ORDER BY size DESC LIMIT 1")
curl -sS -H "Authorization: Bearer *** -o /tmp/probe.mp3 \
  "http://localhost:8889/api/v1/fs/download?file_id=$FID"
file /tmp/probe.mp3    # → "Audio file with ID3 ... MPEG ADTS, layer III"
```

If that returns a real MP3, **the server is correct** — the v3.7.1
WebUI just has no UI for it. Options:

- Build a 30-line CLI wrapper that calls `/fs/download` for full file access (`asmr-library play RJ01010222`).
- Wait for a Neokikoeru release that adds a native file list (3.8+ if it ships).
- Use chobit.cc for previews + the API for full tracks.

## Reading the task queue

`asmr-library serve tasks` shows the last 20 admin tasks. State meanings:

- `1` running — wait, or `POST /admin/task/{id}/cancel`
- `2` done (the `cancelled` label is misleading — see the `status` field
  for actual results like `"97 succeeded, 0 skipped, 0 failed"`)
- `3` cancelled — server shutdown mid-task; re-issue
- `4` failed — check the `error` field

When a `scan` or `index` task shows `0 succeeded` after running, the
typical causes are: (a) the storage's `root_folder_path` is wrong, (b)
the RJ folders don't match `RJ\d+`, or (c) the audio files are
under a path deeper than `max_scan_depth` (default 3).

## Recovering from `prune` (full DB wipe)

`neokikoeru prune -y` deletes the entire data dir
(`$HOME/Library/Application Support/neokikoeru/`) — DB, config, covers,
log. Recovery is a 4-step dance:

```sh
asmr-library serve start    # recreates data dir + fresh DB, prints new admin pw
asmr-library serve login admin <new-password>
asmr-library serve storage add /Volumes/TOSHIBA/AMSR/   # default ID=1
asmr-library serve storage scan 1   # metadata (async; poll with `tasks`)
asmr-library serve storage index 1  # filesystem walker (async; required for audio)
```

Watch `serve tasks` — wait for both scan and index to show
`97 succeeded, 0 skipped, 0 failed` before declaring the system healthy.

## Reverse-engineering undocumented routes

The bundled docs are incomplete and contain path inconsistencies. When
you need to know a route the docs don't list, the binary is the source
of truth. The Go string table embeds route templates like
`/file/:id/duration/work/:id/metadata/...` (multiple routes concatenated
on a single string). Extract with:

```sh
strings <ASMR_STACK_ROOT>/bin/neokikoeru \
  | grep -oE '/(api|admin|auth|file|fs|works|storage|user|task|tag|search|history|like|sysinfo|proxy)/[a-zA-Z0-9/_:.-]+' \
  | sort -u
```

Routes are typically prefixed with `/api/v1` at runtime (the front-end
axios baseURL). After identifying a candidate, probe it:

```sh
TOK=$(python3 -c "import json; print(json.load(open('<ASMR_STACK_ROOT>/serve-config.json'))['token'])")
for method in GET POST; do
  for path in /api/v1/candidate /api/v1/admin/candidate; do
    printf "%s %-50s -> " "$method" "$path"
    curl -s -m 3 -o /dev/null -w "%{http_code}\n" \
      -X "$method" -H "Authorization: Bearer *** \
      "http://localhost:8889$path"
  done
done
```

A `404` means wrong path; `401` means right path, missing auth (use the
JWT); `200`/`202` means it works.

## When the server wedges

If `curl` / `urllib` requests start timing out on a server that was
responding a moment ago, the Go server is in a goroutine stall. Three
confirming signals:

- `top -pid $(pgrep -f neokikoeru)` shows 0% CPU and `STAT S` (sleeping)
- `sample $(pgrep -f neokikoeru) 1` shows all threads in
  `_pthread_cond_wait`
- New `nc localhost 8889 <<< $'GET / HTTP/1.0\r\n\r\n'` gets `200` —
  the listener is up, the handler is the problem

**Recovery:** `asmr-library serve stop && asmr-library serve start`. The
DB is unaffected (WAL mode, clean shutdown). JWT survives. This is a
known pattern for `database/sql` + sqlite when a writer transaction
gets cancelled mid-flight — the connection pool's subsequent
acquisitions block on the dead handle. A clean restart resets the pool.

## Direct DB edits (last resort)

The wrapper doesn't expose storage-move or storage-update. To change
`root_folder_path` on an existing storage without re-registering:

```sh
python3 -c "
import sqlite3
db = sqlite3.connect('\$HOME/Library/Application Support/neokikoeru/neokikoeru.db')
db.execute(\"UPDATE storages SET driver_meta=json_object('root_folder_path','/new/path/') WHERE id=1\")
db.commit()
print(db.execute('SELECT id, driver_meta FROM storages WHERE id=1').fetchone())
"
```

Then trigger `serve storage index 1` to re-populate `files` with paths
under the new root.
