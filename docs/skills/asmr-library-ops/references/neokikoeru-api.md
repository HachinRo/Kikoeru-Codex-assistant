# Neokikoeru API Reference (verified 2026-06-22, v3.7.1)

Probed directly from the binary at `vscodev/neokikoeru` v3.7.1
(`https://github.com/vscodev/neokikoeru/releases/download/v3.7.1/neokikoeru-macos-arm64.tar.gz`)
and from the embedded front-end JS (`index-Om2D9EGB.js` inside the Go binary).
Docs at `https://neokikoeru.voicehub.top` are incomplete and contain
singular/plural path inconsistencies; this reference is authoritative.

## CLI subcommands

| Subcommand | Flags | Notes |
|---|---|---|
| `serve` | none | Port + bind_host + JWT secret are in `config.json`, not flags. |
| `admin reset-pwd` | none | CLI fallback if the admin password is lost. Prints a new password. |
| `encrypt <dir>` | recursive | Encrypts audio files in place (`.ncrypt` suffix). |
| `decrypt <dir>` | recursive | Inverse of `encrypt`. |
| `prune` | none | Wipes all data (DB + caches). |
| `version` / `--version` | | |
| `completion <shell>` | bash/zsh/fish | Shell completion script. |

## HTTP API base

All routes are under `${ORIGIN}/api/v1`. The front-end axios instance:

```js
const API = `${window.location.origin}/api/v1`
```

## Routes (full table)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| `GET` | `/sysinfo` | no | | Returns `{version, license}`. |
| `POST` | `/auth/login` | no | `{username, password}` | Returns `{user, token}` (JWT, 7-day). |
| `POST` | `/auth/session` | yes | | Refreshes / re-validates the session. |
| `POST` | `/auth/change_password` | yes | `{old_password, new_password}` | |
| `GET` | `/works` | yes | | Paginated list — returns `{data: [...], pagination: {page, page_size, total_page, total_count}}`. Query params: `page`, `page_size`, `q`, `sort`, `order`. **Accepts `with_files=true`/`lastFileId=` but ignores both** — work objects never have a `files` field. |
| `GET` | `/works/newest` | yes | | Returns a flat **list** of works (NOT a paginated wrapper). |
| `GET` | `/fs/list?path=<PATH>` | yes | | **Returns 404 in v3.7.1** — the route appears in `strings` output but is not registered. The public file list is the SQLite `files` table directly. |
| `GET` | `/file/list` | yes | | **Returns 404 in v3.7.1** — same as above. |
| `GET` | `/artists` `/genres` `/illustrators` `/makers` `/series` | yes | | |
| `GET` | `/histories` | yes | | Listening history. |
| `POST` | `/histories/clear` | yes | | |
| `POST` | `/admin/storages` | admin | `{driver, driver_meta, max_scan_depth, ignore_folders, force_proxy, remark}` | Create a storage. **Does NOT auto-scan**; the front-end calls `/admin/storage/:id/scan` (singular) afterwards. |
| `GET` | `/admin/storages` | admin | | List storages (paginated). |
| `PATCH` | `/admin/storage/:id` | admin | | Update storage. **Singular** `storage` (not `storages`). |
| `POST` | `/admin/storage/:id/scan` | admin | | Trigger a scan task. **Singular** `storage`. |
| `POST` | `/admin/storage/:id/index` | admin | | Trigger a file-index task. **Singular**. |
| `POST` | `/admin/storage/:id/unmount` | admin | | Unmount a storage (drops the task, keeps the file). **Singular**. |
| `DELETE` | `/admin/storage/:id` | admin | | Delete storage. **Singular**. |
| `POST` | `/admin/tasks/clear` | admin | | Clear completed tasks. |
| `GET` | `/admin/tasks` | admin | | Returns a flat **list** of task objects `{id, name, state, progress, status, error, created_at, updated_at}`. State 4 = done. |
| `POST` | `/admin/works/refresh` | admin | `{}` | Re-scrapes metadata for all known works. Returns `{id, name, state, progress, status, error, ...}`. |
| `POST` | `/admin/works/clean` | admin | | Removes works that no longer exist on disk. |
| `POST` | `/admin/license/activate` | admin | | License activation. |
| `GET` | `/admin/users` | admin | | |

**Singular vs plural is the #1 source of 404s.** Collection routes use
`/admin/storages` (plural); per-id operations use `/admin/storage/:id/...`
(singular). When the docs say one thing and the binary says another, the
binary wins.

## Auth header

```http
Authorization: Bearer <jwt-t...lace `<jwt-token>` with the value of the `token` field from
the `/auth/login` response. JWT lifetime is 7 days
(`server.token_expires_in` in `config.json`). No refresh-token flow
observed in v3.7.1; re-login via `POST /auth/login` to get a new one.

JWT is 7-day expiry (`server.token_expires_in` in `config.json`). No
refresh-token flow observed in v3.7.1; re-login to get a new one.

## Storage create body (verified)

For a local-disk storage pointing at `/Users/me/asmr/serve-index`:

```json
{
  "driver": "local",
  "driver_meta": {"root_folder_path": "/Users/me/asmr/serve-index"},
  "max_scan_depth": 3,
  "ignore_folders": [],
  "force_proxy": false,
  "remark": "asmr-library"
}
```

Response (200): `{id, driver, driver_meta, max_scan_depth, force_proxy, remark, created_at, updated_at}`.

The front-end has additional shapes for `baidu_netdisk`, `onedrive`,
`google_drive`, `aliyun_drive`, `115_disk`, `123_drive`, `dropbox`,
`box`, `yandex_disk`, `pcloud`, `webdav` — each with their own
`driver_meta`. Use `/admin/storages` POST with the matching shape.

## Config file (data dir)

Path on macOS: `$HOME/Library/Application Support/neokikoeru/config.json`.

```json
{
  "log": {"enabled": true, "filename": ".../neokikoeru.log", "max_size": 50, "max_backups": 30, "max_age": 28, "compress": true},
  "database": {"driver": "sqlite3", "data_source": "file:.../neokikoeru.db?cache=shared&mode=rwc&_busy_timeout=500&_txlock=immediate&_journal_mode=WAL&_foreign_keys=true"},
  "server": {
    "bind_host": "0.0.0.0",
    "bind_port": 5233,
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "jwt_secret": "CHANGE_ME",
    "token_expires_in": 7
  },
  "dlsite": {"locale": "zh-CN", "covers_dir": ".../covers", "trim_outer_brackets": true, "proxy_url": "", "proxy_secret": ""}
}
```

The binary has no CLI override for port — only `config.json`. `serve` ignores
all flags (none defined).

## First-run log line

On first boot the binary prints:

```
{"level":"info","message":"successfully created admin account, the username is [admin] and password is [ABC123xyz]"}
```

Regex: `successfully created admin account.*password is \[([^\]]+)\]`.

The server then prints:

```
{"level":"info","message":"server listening at 0.0.0.0:<port>"}
```

The hermes `neokikoeru-serve` wrapper parses these and persists the password
to `<ASMR_STACK_ROOT>/serve-config.json` before exiting the start function.

## Task states

| State | Meaning |
|---|---|
| 1 | Queued |
| 2 | Running |
| 3 | Cancelled |
| 4 | Done (terminal — check `status` for `N succeeded, M skipped, K failed`) |
| 5 | Failed |

`status` field is human-readable: e.g. `0 removed, 83 succeeded, 0 skipped, 14 failed`.

## DLsite metadata scrape

Works on disk without metadata still have an `id` (the RJ code) but `name`,
`intro`, `maker`, `series`, `artists`, `illustrators`, `genres`,
`release_date`, `price`, `rating`, etc. are all empty. The `image_main`
and `image_thumb` are also empty.

**Triggering a re-scrape requires reaching DLsite**, which is blocked on a
Chinese VPN. Set `proxy_url` in the `dlsite` block of `config.json`, or run
the binary with `HTTP_PROXY` / `HTTPS_PROXY` env vars, then re-issue
`POST /admin/storage/:id/scan` or `POST /admin/works/refresh`.

The 14-of-97 "failed" works during a scan are typically:
- DLsite metadata 404 (delisted works — `failed to scrape work [RJ...]: product not found`).
- DLsite cover image 404 (cover URL changed since release — `failed to download images of work [RJ...]: request ... failed: 404`).
- Sometimes a real filesystem issue (e.g. broken symlink in the index).

These failures do NOT delete the work; the audio files are still browseable.

## Filesystem expectations (local driver)

The local driver expects one `RJ########/` directory per work, anywhere
under the registered `root_folder_path`. Each work's directory may contain
audio files (mp3/wav/flac/m4a/aac/ogg/opus), images (jpg/png/webp/gif),
subtitles (lrc/srt/vtt/ass), and docs (txt/pdf/json) at any nesting level.
`max_scan_depth` controls how deep the scanner descends; **3** is the safe
default for the `asmr-library`-style layout (audio files in `(mp3)_X/`,
`(wav)_X/` subdirs).

Work folder names **must contain the RJ ID** (e.g. `RJ01010222` or
`[みやぢ屋][RJ01010222]タイトル`). The scanner matches `RJ\d+` in the folder
name; works with the ID only in a subpath but not in their own folder name
are missed.
