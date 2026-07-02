# Kikoeru-compatible API

`asmr-view` (Python stdlib, port 8890) exposes a kikoeru-shaped HTTP API
so the upstream [kikoeru-quasar](https://github.com/kikoeru-project/kikoeru-quasar)
SPA can render against the same SQLite DB Neokikoeru uses. Built because
Neokikoeru v3.7.1's own WebUI is license-gated (see
`webui-limitations.md`) and the user wanted a real file-list view without
paying for a license.

This file is the **API contract** between `asmr-view` and the kikoeru SPA.
The implementation lives in `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py` and
the dispatch in `<ASMR_STACK_ROOT>/bin/asmr-view`.

## Why kikoeru, not a from-scratch SPA

- The kikoeru-quasar project (Vue 2 + Quasar 1) has a polished file tree
  component (`WorkTree.vue`) with breadcrumbs, click-to-play rows,
  context-menu, and queue logic — non-trivial to reimplement.
- It pairs with `vue-plyr` for audio playback (which we shimmed with a
  vanilla `<audio>` element because the original won't build on
  Node 22; see `kikoeru-quasar-build.md`).
- The API surface is small and well-documented (reverse-engineered from
  the kikoeru-express backend; the upstream isn't strictly required).

## Routes

| Method | Path | Purpose | Source of truth |
|---|---|---|---|
| GET | `/api/works?page=N&size=M&search=...` | Paginated work list | `works` table joined with `makers` + `genre_works` for tags |
| GET | `/api/work/<id>` | Work metadata | `works` + `makers` + `artist_works` + `illustrator_works` + `genre_works` |
| GET | `/api/tracks/<id>` | Full file tree | `files` table walked from root folder via `parent_id` |
| GET | `/api/media/stream/<hash>?token=…` | Audio stream | serves `files.path` directly from disk; falls back to Neokikoeru's `/api/v1/fs/download` if the file is missing (see `direct-disk-streaming.md`) |
| GET | `/api/media/download/<hash>` | File download (with `Content-Disposition`) | serves `files.path` directly from disk; falls back to `/api/v1/fs/download` |
| GET | `/api/cover/<id>` | Cover image (numeric or RJ form) | walks `covers/doujin/RJ0{id-bucket}*/` |
| GET | `/api/covers/<id>` | Kikoeru's preferred cover path | same as `/api/cover/<id>` |
| GET | `/api/auth/me` | Current user | mock — returns `{user, auth: true}` |
| POST | `/api/auth/me` | Login | mock — accepts any `{name, password}`, returns `{token: "guest-token", user}` |
| GET | `/api/version` | Server version | mock with `update_available: false`, `lockFileExists: false` |
| GET | `/api/config/shared` | Shared config | mock — wraps in `.sharedConfig` |
| GET | `/api/mylist` | User lists | mock empty `{mylists: []}` |
| PUT | `/api/mylist` | Update list | noop 200 |
| GET | `/api/review` | Reviews | mock empty `{reviews: []}` |
| PUT | `/api/review` | Submit review | noop 200 |
| GET | `/api/track/<hash>` | Single file metadata | `files` table |
| GET | `/api/media/check-lrc/<hash>` | Find sibling `.lrc` | `files` table lookup by name+parent_id |
| POST | `/api/admin/reindex` | **The Build button** | triggers Neokikoeru's `scan` + `index` async tasks, refreshes cover cache |

## Work ID conversion

DLsite assigns RJ codes with **two digit widths**: old works are 6 digits
(`RJ190391`, `RJ439991`) and new works are 8 digits zero-padded
(`RJ01010222`). **Do not pad the numeric id to a fixed width** — that
silently mangles the 6-digit codes into nonexistent forms.

The kikoeru client links to `/work/<id>` using `{id: <numeric>}` from
the work list. The numeric id is whatever we returned in
`_row_to_kikoeru_work`, computed as `rj_to_numeric(row["id"])` (strips
all leading zeros from the `RJ…` form, then parses the digits). So for
`RJ439991` we return `id: 439991`, and for `RJ01010222` we return
`id: 1010222`.

The naive `numeric_to_rj(n) = "RJ" + str(n).zfill(8)` helper looks like
the natural inverse but it is **wrong** for 6-digit codes: it would
return `"RJ0439991"` for `n=439991`, which does not exist in the DB and
causes the work detail page to 404 ("work not found") and the file tree
to return `[]`. The user hit this in 2026-06-22: **28 of 97 works
failed** because of this single bug. Don't reintroduce the zfill(8)
form.

Use `resolve_rj(conn, n)` (in `lib/asmr_view_kikoeru.py`) instead. It
tries the 8-digit, 6-digit, and raw-numeric forms against the `works`
table and returns whichever exists, or `None` if none do. All three
`/api/work/<id>`, `/api/tracks/<id>`, and `/api/covers/<id>` handlers
must call `resolve_rj()` first, then return a 404 if it returns `None`.

`asmr-view` handlers accept both forms in URLs:
- `GET /api/work/1010222` — numeric (the form kikoeru uses)
- `GET /api/work/RJ01010222` — RJ-prefixed (any leading-zero variant)

The DB column is `works.id` (TEXT, `RJ0…` form). Numeric IDs in the
work object (`{id: 1010222}`) are computed at response time via
`rj_to_numeric()`, NOT padded back to a canonical width.

**Verify after any change to this code path** with:

```sh
DB="$HOME/Library/Application Support/neokikoeru/neokikoeru.db"
PASS=0; FAIL=0; FAILED_LIST=""
for rj in $(sqlite3 "$DB" "SELECT id FROM works;"); do
  num=$(echo "$rj" | sed 's/^RJ0*//')
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8890/api/work/$num")
  if [ "$code" = "200" ]; then PASS=$((PASS+1)); else
    FAIL=$((FAIL+1)); FAILED_LIST="$FAILED_LIST $rj"
  fi
done
echo "PASS=$PASS FAIL=$FAIL"
[ -n "$FAILED_LIST" ] && echo "Failures:$FAILED_LIST"
# expected: PASS=97 FAIL=0
```

## Work object shape (kikoeru format)

```json
{
  "id": 1010222,
  "title": "完全舐め下ろし☆蕩ける耳舐めマッサージ聴き比べ",
  "circle": {"id": 0, "name": "ブラックマの嫁"},
  "vas": [{"id": "…", "name": "伊ヶ崎綾香"}],
  "tags": [{"id": 128, "name": "内射/中出"}, …],
  "rate_average_2dp": "4.85",
  "rate_count": 3697,
  "review_count": 28,
  "rate_count_detail": [
    {"review_point": 5, "count": 2218, "ratio": 60}, …
  ],
  "dl_count": 14158,
  "price": 1056,
  "nsfw": true,
  "release": "2023-01-06",
  "create_date": "2026-06-22",
  "userRating": 0,
  "isFavourite": false,
  "type": "doujin",
  "coverUrl": "/api/covers/1010222"
}
```

**Note on `rate_count_detail`**: the SQLite `works` table doesn't store
the rating distribution, only `rating` (avg) and `rating_count` (total).
We synthesize a fake distribution (60/25/10/4/1 ratio around the average)
because the kikoeru UI renders a tooltip with this array. The shape is
correct; the numbers are approximate.

**Extras for our hand-rolled SPA** (when `include_extras=True`):
`rj_id`, `intro`, `maker`, `released`, `rating` (number), `rating_count`,
`wishlist_count`, `file_count`, `total_size`, `age_category`, `has_cover`,
`genres` (string list), `artists`, `illustrators`, `image_main`, `image_thumb`.

## File tree shape (`/api/tracks/<id>`)

```json
[
  {
    "title": "(mp3)_ストーリー",
    "type": "folder",
    "hash": "9rArG2yHdg8",
    "children": [
      {
        "title": "01_いらっしゃいませ.mp3",
        "type": "audio",
        "hash": "hM_wWR0m0oc",
        "children": [],
        "mediaStreamUrl": "/api/media/stream/hM_wWR0m0oc",
        "mediaDownloadUrl": "/api/media/download/hM_wWR0m0oc",
        "lyrics": null
      },
      …
    ],
    "mediaStreamUrl": null,
    "mediaDownloadUrl": null
  },
  …
]
```

The tree is built by walking `files.parent_id` from the work's root folder
record. Folder entries have `type: "folder"` and non-empty `children`;
file entries have a `type` from `{audio, video, image, text, subtitle, other}`
based on extension, and `mediaStreamUrl`/`mediaDownloadUrl` pointing at our
proxies.

Type classification (see `_classify` in `asmr_view_kikoeru.py`):
- `.mp3 .wav .flac .ogg .m4a .aac .opus` → `audio`
- `.lrc .vtt .srt .ass .ssa .txt .pdf .md .log` → `text`
- `.jpg .jpeg .png .webp .gif` → `image`
- `.mp4 .mkv .webm .mov` → `video`
- everything else → `other`

Subtitle extensions (`.lrc/.vtt/.srt/.ass/.ssa`) are intentionally
classified as `text`, not `subtitle`. The kikoeru-quasar SPA's file-row
click handler (in `js/app.<hash>.js`, ~line containing
`"text"===e.type||"image"===e.type`) only knows how to open
`text`/`image`/navigate-`folder`/download-`other`; anything else
defaults to "play as audio" which would try to play a VTT file as MP3.
This is the same contract kikoeru-express follows. Don't introduce a
`subtitle` type without also wiring up a SPA-side handler for it.

## Streaming & download

Both `mediaStreamUrl` and `mediaDownloadUrl` point to our handlers. The
handlers do **not** proxy through Neokikoeru on the happy path — they
read `files.path` from the SQLite DB, prepend the resolved storage root
(`/Volumes/TOSHIBA/AMSR/` by default), and stream the file directly
with `open(path, 'rb')` plus a local HTTP `Range` parser. The path
column is stored with a leading `/` (e.g. `/RJ01010222/...mp3`) and the
handler does `storage_root / path.lstrip('/')` — never `os.path.join`
or `pathlib.Path` concatenation with a trailing `/`, which would
double the slash.

Neokikoeru's `/api/v1/fs/download` is kept only as a **fallback** for
files whose `files.path` exists in the DB but whose on-disk copy is
missing (e.g. partial prune recovery). The proxy is no longer on the
hot path for audio playback — that was a deliberate switch in
2026-06-22 to remove the dependency on the wedged Go server, halve
the latency, and eliminate the JWT plumbing. See
`direct-disk-streaming.md` for the full contract (storage root
resolution, byte-for-byte verification, fallback decision).

`/api/media/download/<hash>` adds an RFC 5987 `Content-Disposition`
header with the original (non-ASCII) filename, so browsers save the
file with its proper name. The hash form is
`filename*=UTF-8''<percent-encoded>`.

## LRC detection (`/api/media/check-lrc/<hash>`)

The kikoeru `AudioElement.vue` polls this for the currently-playing
audio to fetch synced lyrics. We look for a sibling subtitle file in
the same folder (same `parent_id`), with this priority:

1. `<basename>.lrc` (extension-replaced: `01_xxx.mp3` → `01_xxx.lrc`)
2. `<basename><audio_ext>.vtt` (extension-preserved: `01_xxx.mp3.vtt`)
3. `<basename><audio_ext>.srt`
4. `<basename><audio_ext>.ass` / `.ssa`

If a non-LRC sibling wins, the returned `hash` is the VTT/SRT/ASS/SSA
file's id. The stream endpoint then converts the body to LRC on the
fly (see `subtitle-conversion.md` for the parsers). This is the
opposite of upstream kikoeru-express, which only matches `.lrc` —
kikoeru's `lrc-file-parser` is LRC-only, so we do the format work
server-side.

**Response shape** (must include `result` — kikoeru client checks this
truthy/falsy, not just `hash`):

```json
// found (any subtitle format)
{ "result": true,  "hash": "<sub_file_id>" }
// not found
{ "result": false, "hash": null }
```

The user hit a related bug in 2026-06-22: our handler returned only
`{hash: …}` without the `result` field, so kikoeru's `loadLrcFile` did
`if (response.data.result)` and always got `undefined` → `lrcAvailable = false`,
so lyrics were never shown even when the `.lrc` was on disk and being
streamed correctly. Don't drop the `result` field.

The sub bytes are then fetched via `/api/media/stream/<sub_hash>`. The
kikoeru client does `axios.get(...)` (no `responseType: 'text'`) and
calls `lrcObj.setLyric(t.data)` — so the response **must be served as
`text/plain; charset=utf-8`**, NOT `application/octet-stream`, otherwise
axios tries to JSON-parse the body and the lyric parser gets garbage.
The stream handler in `asmr-view` detects subtitle suffixes and
overrides the content type accordingly.

**File-tree classification for subtitles**: `_classify()` returns
`type: "text"` (not `"subtitle"`) for `.lrc/.vtt/.srt/.ass/.ssa/.txt`.
This matches the kikoeru-express contract and is **load-bearing**:
the kikoeru-quasar SPA's file-row click handler (in
`js/app.<hash>.js`, file-tree branch) routes by `type` and falls back
to "play as audio" for unknown types. A subtitle with `type: "subtitle"`
would try to play the VTT in the audio element and fail silently.

## The Build button (`POST /api/admin/reindex`)

This is the "build" the user asked for. It triggers both of Neokikoeru's
async admin tasks in sequence:

1. `POST /api/v1/admin/storage/1/scan` — DLsite metadata scrape
2. `POST /api/v1/admin/storage/1/index` — filesystem file index

Both return 202 with task IDs. The endpoint doesn't wait for them to
finish; it fires both and returns immediately. The caller can poll
`asmr-library serve tasks` to see progress.

After triggering, we call `build_cover_cache()` to pick up any new
covers that may have been added.

Response:

```json
{
  "ok": true,
  "results": {
    "scan": {"status": 202, "body": "{\"task_id\":42}"},
    "index": {"status": 202, "body": "{\"task_id\":43}"}
  },
  "covers": 96
}
```

If Neokikoeru isn't running, returns 502/503. If the JWT is missing,
returns 503. The endpoint requires Neokikoeru to be up and the JWT to be
in `serve-config.json` (run `asmr-library serve login` first).

## Mock auth strategy

We don't implement real kikoeru auth. Instead:

- `GET /api/auth/me` returns `{user: {…, group: "admin"}, auth: true}`
  so kikoeru's MainLayout never redirects to the login page.
- `POST /api/auth/me` returns a static `guest-token` for any creds.
- The MainLayout's role check (`this.$store.state.User.group === "admin"`)
  passes, so the admin pages (Folders/Scanner/Advanced) are reachable.
- All write endpoints (review, mylist, etc.) are noop 200s. Reviews
  don't persist; mylists don't persist. That's fine for a personal
  media server where the user IS the admin.

This is the path of least resistance. If real auth is needed later,
the `kikoeru_auth_me` and `kikoeru_auth_me_post` handlers in
`asmr-view` are the only places to change.

## How the kikoeru SPA finds the backend

The kikoeru-quasar SPA assumes the backend is on the same origin. Since
we serve both the SPA and the API from `http://127.0.0.1:8890`, that
works out of the box — `axios.get('/api/...')` hits our handler.

If you ever split the SPA and the API across origins, you'd need to
add CORS headers to `asmr-view` and the kikoeru boot/axios.js's
`baseURL`. Same-origin is the only tested config.
