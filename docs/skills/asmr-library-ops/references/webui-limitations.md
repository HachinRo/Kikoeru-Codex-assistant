# Neokikoeru v3.7.1 WebUI limitations

**Read this first when the user says "I can't see files / tracks / a
player" in the WebUI.** The most likely cause is that v3.7.1's WebUI
intentionally does not render what the user expects — not a config
bug, not a missing scan, not a broken API.

## TL;DR — the license gate

The `WorkFiles` component (native file tree with breadcrumbs,
click-to-play rows, duration chips, and image/PDF preview dialogs)
**exists in the v3.7.1 JS bundle and is registered as a Vue
component**. It is **not** rendered because the `WorkPage` template
guards it behind a license check:

```js
u.value.created_at && T(a).license?.activated
  ? m(ai, {work: u.value}, null, 8, ["work"])   // native WorkFiles
  : m(ci, {ids: ...}, null, 8, ["ids"])        // chobit.cc iframe fallback
```

When `/api/v1/sysinfo` returns `"license": {"activated": false}` (the
default state), the work page falls back to the chobit.cc iframe
preview. The encrypted `/api/v1/fs/list` endpoint also returns 400
for unlicensed installs (the encryption itself works — see
`references/neokikoeru-encryption.md` — but the server's
`Handler.FsList` rejects the request after decryption).

**There is no v3.8+ to upgrade to.** `vscodev/neokikoeru` GitHub
releases atom feed returns only one tag: `v3.7.1` (2026-06-17). The
repo has been quiet since. So the workarounds are the only path
without paying for a license key.

## What v3.7.1 actually renders

Verified 2026-06-22 by logging in via browser and inspecting the DOM
(`document.querySelectorAll('.audio-player, .q-list, iframe, audio, [class*="file"], [class*="track"]')`).

| Page | What you see | What you DON'T see |
|---|---|---|
| `/` (home) | `Recently added` cover grid (6 thumbnails) + `Recently played` list | No files, no tracks, no player |
| `/works` (list) | Card per work: cover, title, rating stars, genres, maker, DLsite link, like/edit/delete buttons (admin only) | No audio player, no file list per card. The `with_files` toggle in the search bar is a no-op for unlicensed builds. |
| `/work/RJ...` (detail) | Full metadata card + **a single chobit.cc `<iframe>` embed** (DLsite affiliate player, 5 sample tracks) | No native file/track list. The hidden `q-card audio-player` element is `display: none` because nothing in the unlicensed UI starts playback. |
| `/histories` | Play history | No files |
| `/admin` (admin only) | Storage list, task list, user list | No files |

## The chobit.cc iframe is the wrong thing to look at

The chobit iframe loads from `https://chobit.cc/embed/<hash>?dlsite=1`
and shows **5 DLsite preview tracks** (DLsite's public sample). This
has nothing to do with the user's local files:

- A work with 117 audio files in the local library → iframe shows 5
- A work with no files in the local library → iframe still shows 5
- The iframe is cross-origin, so the parent app can't read its DOM
- Audio served by the iframe is the DLsite preview CDN, not
  `http://localhost:8889/api/v1/fs/download?file_id=...`

When the user clicks a track in the chobit iframe, the audio plays
from DLsite's CDN inside the iframe. The Neokikoeru `audio-player`
stays hidden.

## What the server actually has (the right way to verify)

The Neokikoeru v3.7.1 server IS indexing all local files and CAN
serve them via the unencrypted download API. Run these to confirm:

```sh
# 1. How many files are indexed?
sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT COUNT(*), COUNT(DISTINCT work_id) FROM files WHERE is_folder=0"

# 2. List files for a specific work
sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id, name, size, path FROM files WHERE work_id='RJ01010222' AND is_folder=0 ORDER BY name"

# 3. Verify a real audio file streams
TOK=$(python3 -c "import json; print(json.load(open('<ASMR_STACK_ROOT>/serve-config.json'))['token'])")
FID=$(sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
  "SELECT id FROM files WHERE work_id='RJ01010222' AND name LIKE '%.mp3' ORDER BY size DESC LIMIT 1")
curl -sS -H "Authorization: Bearer *** -o /tmp/probe.mp3 \
  "http://localhost:8889/api/v1/fs/download?file_id=$FID"
file /tmp/probe.mp3
# → "Audio file with ID3 ... MPEG ADTS, layer III"
```

If all three return real data, the server is healthy and the user
expectation is mismatched with v3.7.1's UI.

## Route gotchas in v3.7.1

`strings <ASMR_STACK_ROOT>/bin/neokikoeru | grep -E '^/(file|fs|admin|works)/'`
shows many route templates, but several are **singular vs plural
traps** and one is **encrypted**:

| Path | Status in v3.7.1 | What it implies |
|---|---|---|
| `GET /api/v1/work/RJ...` | 200 | Returns work metadata (singular — works, but the response never includes files) |
| `GET /api/v1/works/RJ...` | 404 | Plural form is unregistered |
| `GET /api/v1/works?page=N&with_files=true` | 200, but `with_files` is silently ignored on the work objects | The query param is accepted but the response JSON has no `files`/`folders`/`tracks` key on the unencrypted endpoint |
| `GET /api/v1/file/list` | 404 | Unregistered — but `fsListReq` Go struct exists |
| `GET /api/v1/fs/list` | 404 (unencrypted) / 400 (encrypted, for unlicensed) | Encrypted form is the real path; see `references/neokikoeru-encryption.md` |
| `GET /api/v1/fs/download?file_id=X` | 200, returns real MP3/LRC bytes | **Always works**, even on unlicensed installs. This is the unencrypted path. |
| `GET /api/v1/works/refresh` | 404 | Use `POST /admin/works/refresh` instead |
| `GET /api/v1/storage/:id/scan` | 404 | Use `POST /admin/storage/:id/scan` |
| `GET /api/v1/storage/:id/index` | 404 | Use `POST /admin/storage/:id/index` |

**The actual file-listing paths** for an unlicensed CLI client are:

1. **Direct SQLite read** (fastest, no auth, works for any process with
   FS access):

   ```sh
   sqlite3 "$HOME/Library/Application Support/neokikoeru/neokikoeru.db" \
     "SELECT work_id, COUNT(*) c, SUM(size) total FROM files
      WHERE is_folder=0 GROUP BY work_id ORDER BY total DESC"
   ```

2. **`asmr-library files <RJ>`** (DB-backed CLI that wraps the SQL
   above with proper formatting; `--audio` filters to audio, `--json`
   gives machine-readable output).

3. **`asmr-library work <RJ>`** combines metadata (via API) + file
   list (via DB) in one command.

4. **`asmr-library fcat <file_id>`** and **`asmr-library fget
   <file_id> [out]`** fetch via the unencrypted `/fs/download`
   endpoint (works on unlicensed builds).

## What to tell the user

When this comes up, lead with "the API works and your files are
indexed — v3.7.1's WebUI is gated behind a paid license, so it shows
only the chobit preview instead of your files." Then offer:

1. **For casual listening:** the chobit preview covers most works'
   intro/highlights (5 sample tracks).
2. **For full file access without a license:** the `asmr-library
   files` / `work` / `fcat` / `fget` subcommands (added 2026-06-22).
   They bypass the license gate by reading the SQLite DB directly and
   using the unencrypted download endpoint.
3. **For a real file-list UI in the WebUI:** purchase a license
   (Neokikoeru has a paid activation flow at `/license/activate`).
   Without that, there is no upgrade path (v3.7.1 is the latest).

## Why this matters operationally

This bit us three times in one week:
- User reported "I can't see files" → assistant chased storage root /
  scan / index / prune cycle before realizing v3.7.1 was the issue.
- Same user, next day: "restart server, I still can't see files" →
  server was already correct; UI was the issue.
- Same user, after CLI was added: "still can't see files" → confirmed
  the license gate is the actual cause, not a config bug.

**Verification rule for any "files missing in WebUI" report:**

1. Confirm files are indexed (`SELECT COUNT(*) FROM files`).
2. Confirm audio streams (`/fs/download?file_id=X` returns real MP3).
3. Check `/sysinfo` for `license.activated`. If `false`, the WebUI
   will NOT show files regardless of what the server has indexed.
4. **Only then** look at the WebUI. If 1+2 pass and 3 says "unlicensed",
   the answer is "use the CLI subcommands" — not a server fix.

## Other v3.7.1 frontend quirks worth knowing

- The hidden `q-card audio-player` activates only when something calls
  `playTrack()` from within the Vuex store. Nothing in the unlicensed
  build calls it — the chobit iframe plays its own audio.
- Quasar localStorage keys: `auth.token` (`__q_strn|<jwt>`), `auth.user`
  (`__q_objt|<json>`), `theme`. JWT lifetime is 7 days.
- The `with_files` toggle in the search bar is implemented client-side
  and serializes as `?with_files=true` on the URL but the unencrypted
  API endpoint ignores it. (The licensed build's encrypted `/fs/list`
  endpoint honors it via the `refresh` and `with_files` fields in the
  `fsListReq` Go struct.)
- Image URLs in work objects are RELATIVE (`image_main: "doujin/RJ.../RJ..._img_main.jpg"`).
  They resolve under the `/covers/` URL prefix. The Go server serves
  these from the data dir's `covers/` subdirectory, NOT from
  `/Volumes/TOSHIBA/AMSR/`. If covers 404, check that the metadata
  scrape populated them.
