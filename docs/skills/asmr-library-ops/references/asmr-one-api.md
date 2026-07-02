# asmr.one API reference (verified 2026-06-22)

## Endpoint map

asmr.one is a Vue SPA at `https://asmr.one/`. The API lives at a **separate
host** that's only discoverable via the SPA's `<link rel=preconnect>` —
not `api.asmr.one` (which is also a 401 wall), and not the legacy
`kiko-play-niptan.one` (which is the static CDN).

| URL | Role |
|-----|------|
| `https://asmr.one/` | Vue SPA shell |
| `https://api.asmr-200.com/` | **Real API host** (fallbacks: `api.asmr.one`, `api.asmr-100.com`, `api.asmr-300.com`) |
| `https://raw.kiko-play-niptan.one/media/...` | Static CDN for audio + subtitle files (cookie required) |

All `/api/v1/...` paths are **not** the right base. The asmr.one API uses
`/api/...` without the version segment.

## Auth

- **Login endpoint: `POST /api/auth/me`** with body
  `{"name": "<username>", "password": "<password>"}`. (Yes, the sign-in
  endpoint is named `/me`; the JS bundle at
  `https://asmr.one/js/app.<hash>.js` calls it that way. `auth/me` for
  fetching the current user is a separate `GET`.)
- Response: `{"user": {"loggedIn": true, "name": "...", "group": "user", "email": null, "recommenderUuid": "..."}, "token": "<jwt>"}`.
- Cookie set is **HttpOnly** — JS can't read it; the browser sends it
  automatically on same-origin requests. Direct `urllib` calls need the
  cookie captured via a real browser session (camofox is the right tool).
- The asmr.subs script persists cookies to
  `<ASMR_STACK_ROOT>/.asmr-one-cookies.txt` (Mozilla cookie jar format).

## ID conversion

`RJ01010222` → asmr.one internal ID `1010222` (drop the `RJ` prefix; the
remaining digits — including any leading zero — are the ID as a string).

## Endpoints used by `asmr-subs`

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/search/<RJ>` | `{"works": [{id, title, circle_id, name, nsfw, release, dl_count, price, review_count, rate_count, rate_average_2dp, ...}]}` |
| GET | `/api/workInfo/<asmr-id>` | Single work object with `has_subtitle: bool` (the source of truth for "is subs available?") |
| GET | `/api/tracks/<asmr-id>` | Tree of folders + leaves; subtitle leaves have `type: "text"` and a `.vtt`/`.lrc`/`.srt`/`.ass` title; `mediaDownloadUrl` and `mediaStreamUrl` give the actual file URLs |

## Subtitle file format

- `Content-Type: text/plain; charset=GB2312`. **Always decode as GB2312**
  (or its superset GBK with replacement for any undecodable byte). See
  `references/cjk-encoding-gotcha.md` for the full pitfall.
- Filename pattern: `<track-stem>.<subtitle-ext>`, e.g.
  `track00_读标题.lrc` (Chinese titles preserved verbatim).
- Storage path on the CDN: `https://raw.kiko-play-niptan.one/media/download/daily/<YYYY-MM-DD>/<RJ>/<path>/<title>.<ext>`.
- Cookie required even for the CDN URL (HttpOnly session cookie from
  `api.asmr-200.com` is sent on cross-origin requests with
  `credentials: include`).

## Subtitle coverage reality check

For the user's library of 97 RJs as of 2026-06-22:

- **48 RJs** already had Chinese subs on disk (from a prior fetch / pack).
- **49 RJs** had no on-disk subs.
  - **1** (`RJ01182623`): asmr.one has subs; **fetched successfully** (8 .lrc files).
  - **47**: asmr.one reports `has_subtitle: false` — they were never uploaded to asmr.one with subs.
  - **1** (`RJ01610404`): not on asmr.one at all (404 / search returns 0 works).

**Implication**: asmr.one is the *most complete* Chinese-sub source but
not exhaustive. For RJs that have subs, the source-of-truth is
`/api/workInfo/<id>.has_subtitle`; for RJs that don't, the only
options are user-provided subs (manual copy into the RJ folder) or
different sources (DLsite, kikoeru mirror, etc.).

## Reference: how the asmr.one SPA loads its JS

Initial HTML contains `<link rel=preconnect href=https://api.asmr-200.com>`,
but the **app bundle URL is NOT in the initial HTML** — it's loaded
asynchronously by the Quasar runtime, and the bundle path is something
like `https://asmr.one/js/app.c5f7e7ac.js` (8-char hash, not the
`/assets/index-*.js` pattern used by Vite/Vue defaults). The bundle
itself is served without strict Cloudflare checks; `curl` with a real
User-Agent can fetch it.
