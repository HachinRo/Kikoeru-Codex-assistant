# Neokikoeru Integration Reference

Verified facts about `vscodev/neokikoeru` (the Go + Vue viewer that replaced
ASMRoner's `listen` path) as of v3.7.1 (2026-06-17). This is the condensed
knowledge bank the agent needs to keep the integration working — the upstream
docs site is mostly Chinese and sparse, and web search returns noise. **When
upgrading Neokikoeru, re-verify everything below against the new release.**

## Version this was verified against

`v3.7.1` — released 2026-06-17, fetched 2026-06-22.

## Release assets

Pattern: `neokikoeru-{macos,linux,windows}-{amd64,arm64}.{tar.gz,zip}`

| Platform | Asset |
|---|---|
| macOS arm64 (Apple Silicon) | `neokikoeru-macos-arm64.tar.gz` |
| macOS amd64 (Intel) | `neokikoeru-macos-amd64.tar.gz` |
| Linux arm64 | `neokikoeru-linux-arm64.tar.gz` |
| Linux amd64 | `neokikoeru-linux-amd64.tar.gz` |
| Windows amd64 | `neokikoeru-windows-amd64.zip` |
| Windows arm64 | `neokikoeru-windows-arm64.zip` |

Asset URLs are public even though the release HTML page requires GitHub login.
Discovery: `https://api.github.com/repos/vscodev/neokikoeru/releases/latest`
returns the tag; the download URL is
`https://github.com/vscodev/neokikoeru/releases/download/<tag>/<asset>`.

The release tarball extracts to a single executable named `neokikoeru`
(no extension). `strings` on the binary reveals all routes, log strings, and
default config values — see "Reverse-engineering tips" below.

## CLI surface

`neokikoeru --help`:

```
Available Commands:
  admin       Manage admin account
  completion  Generate the autocompletion script for the specified shell
  decrypt     Decrypt a directory recursively
  encrypt     Encrypt a directory recursively
  help        Help about any command
  prune       Prune all data
  serve       Start the Neokikoeru service
Flags:
  -h, --help      help for neokikoeru
  -v, --version   version for neokikoeru
```

`neokikoeru serve --help` shows **no flags** — all server config goes through
`config.json` at the data dir.

`neokikoeru admin --help`:

```
Available Commands:
  reset-pwd   Reset password
```

`neokikoeru admin reset-pwd` is the hard recovery path if the admin password
is lost. It resets and prints a new one to stdout, regardless of the
serve-config.json state.

## Data dir (macOS)

`$HOME/Library/Application Support/neokikoeru/`

Subpaths:
- `config.json` — port, bind_host, jwt_secret, log path, DB path
- `neokikoeru.db` — sqlite, WAL mode
- `logs/neokikoeru.log` — structured log (rotated by lumberjack config)
- `covers/` — DLsite cover cache

`neokikoeru-serve start` generates `config.json` from a baked-in template
with port 8889 (overridable via `--port`). On every `start`, it preserves
existing `admin_user` / `admin_password` / `token` / `token_expires_at` from
`serve-config.json` so credentials survive restarts.

## Default config.json (verified from v3.7.1)

```json
{
  "log": {
    "enabled": true,
    "filename": "$HOME/Library/Application Support/neokikoeru/logs/neokikoeru.log",
    "max_size": 50,
    "max_backups": 30,
    "max_age": 28,
    "compress": true
  },
  "database": {
    "driver": "sqlite3",
    "data_source": "file:$HOME/Library/Application Support/neokikoeru/neokikoeru.db?cache=shared&mode=rwc&_busy_timeout=500&_txlock=immediate&_journal_mode=WAL&_foreign_keys=true"
  },
  "server": {
    "bind_host": "0.0.0.0",
    "bind_port": 5233,
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "jwt_secret": "xxxxxx",
    "token_expires_in": 7
  },
  "dlsite": {
    "locale": "zh-CN",
    "covers_dir": "$HOME/Library/Application Support/neokikoeru/covers",
    "trim_outer_brackets": true,
    "proxy_url": "",
    "proxy_secret": ""
  }
}
```

We override `server.bind_port` to 8889 and set `jwt_secret` to a stable value
("neokikoeru-asmr-library") so tokens survive config rewrites. The rest
mirrors upstream defaults verbatim — the upstream docs warn "do not modify
unless you know what you are doing."

## First-run admin password

On first boot, Neokikoeru prints a line of the form:

```
successfully created admin account, the username is [admin] and password is [<random>]
```

`neokikoeru-serve start` greps for this regex:

```
successfully created admin account.*password is \[
```

and persists the captured password to `serve-config.json` (key
`admin_password`). `serve status` re-prints it. If both the log and
serve-config.json are lost, use `neokikoeru admin reset-pwd` — the binary
itself handles the recovery.

## HTTP API (extracted from the embedded front-end JS bundle)

Base URL: `<bind_host>:<bind_port>/api/v1`

All authenticated endpoints expect an `Authorization: Bearer <token>`
header (the JWT from `/auth/login`). The front-end stores the token in
`localStorage` under `auth.token`.

### Auth

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/auth/login` | `{username, password}` | `{user, token}` (JWT, 7-day expiry) |
| POST | `/auth/session` | (none) | `{user, token}` — refresh |
| POST | `/auth/change_password` | `{old_password, new_password}` | (no body) |

### Admin

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/admin/storages?page=N&page_size=M` | — | `{data: [...], pagination: {...}}` |
| POST | `/admin/storages` | see below | the new storage row |
| POST | `/admin/storages/{id}/scan` | (none) | task id |
| POST | `/admin/storages/{id}/index` | (none) | task id |
| POST | `/admin/works/refresh` | (none) | task id |
| POST | `/admin/works/clean` | (none) | task id |
| GET | `/sysinfo` | — | `{version, license}` |

### Create-storage body (local driver, verified)

```json
{
  "driver": "local",
  "driver_meta": {"root_folder_path": "/abs/path/to/serve-index"},
  "max_scan_depth": 3,
  "ignore_folders": [],
  "force_proxy": false,
  "remark": "asmr-library"
}
```

`max_scan_depth: 3` lets the scanner descend into `(mp3)_.../`, `(wav)_.../`
subfolders, which is what the existing `asmr-library-worker` publishes. The
list of supported `driver` values (from the bundled front-end):
`local, baidu_netdisk, onedrive, google_drive, aliyun_drive, 115_disk,
123_drive, dropbox, box, yandex_disk, pcloud, webdav`. We only use `local`.

## Reverse-engineering tips (when re-verifying after a version bump)

```bash
# 1. Discover latest tag.
curl -fsSL https://api.github.com/repos/vscodev/neokikoeru/releases/latest \
  -H 'Accept: application/vnd.github+json' \
  | awk -F'"' '/"tag_name":/ {print $4; exit}'

# 2. List all assets for a tag (public endpoint, no login).
curl -fsSL "https://github.com/vscodev/neokikoeru/releases/expanded_assets/<TAG>" \
  | grep -oE 'neokikoeru[^"<]*\.(tar\.gz|zip)' | sort -u

# 3. Download + extract to /tmp.
curl -fsSL "https://github.com/vscodev/neokikoeru/releases/download/<TAG>/<ASSET>" \
  -o /tmp/nk.tar.gz
tar -xzf /tmp/nk.tar.gz -C /tmp/nk && chmod +x /tmp/nk/neokikoeru

# 4. CLI surface.
/tmp/nk/neokikoeru --version
/tmp/nk/neokikoeru --help
/tmp/nk/neokikoeru serve --help
/tmp/nk/neokikoeru admin --help
/tmp/nk/neokikoeru admin reset-pwd --help

# 5. Extract API routes from the Go binary.
strings /tmp/nk/neokikoeru | grep -oE '"/[a-z][a-zA-Z0-9_/-]*"' | sort -u

# 6. Extract the embedded front-end JS callsites (axios.get/post calls
#    show the exact endpoints + bodies the WebUI uses).
strings /tmp/nk/neokikoeru | grep -oE '\.(get|post|put|patch|delete)\(`/[^`]*`\)' | sort -u

# 7. Find the first-run password log line.
strings /tmp/nk/neokikoeru | grep -E 'successfully created|password is'

# 8. Find the default config schema (json tags show field names).
strings /tmp/nk/neokikoeru | grep -E '^json:"[a-z_]+",' | sort -u
```

If any of (1) through (8) returns something different from what's in this
file, the integration will need to be updated. In particular:

- (4) — new subcommands need to be surfaced in `asmr-library` if they're
  user-facing.
- (5) / (6) — new API endpoints may need to be called by `serve login`,
  `serve storage add`, etc.
- (7) — if the log format changes, the first-run password scrape regex
  in `neokikoeru-serve` must be updated.
- (8) — if config.json keys are added/renamed/removed, the template in
  `cmd_init` must be regenerated.

## Local-mode layout (what Neokikoeru expects on disk)

The local storage driver walks `<root_folder_path>/` looking for `RJ########/`
directories. It does **not** require any specific subfolder naming — it just
looks for audio files (`.mp3 .wav .flac .m4a .aac .ogg .opus`) anywhere
under a `RJ########/` tree. Subtitles (`.lrc .vtt .srt .ass`) must live in
the same directory as their audio file with the same basename.

Our `serve-index/` symlink tree is a flat mirror of `/Volumes/TOSHIBA/AMSR/`,
so the existing layout (`(mp3)_ストーリー/01_*.mp3` etc.) works without
restructuring. The `max_scan_depth: 3` setting lets the scanner descend
into the `(mp3)_.../` and `(wav)_.../` subfolders that the
`asmr-library-worker` already publishes.

## Pitfalls (learned the hard way)

- **The release page HTML requires GitHub login.** Don't try to grep it for
  asset names — use `expanded_assets/<tag>` or the API.
- **Asset names use `-macos-` not `darwin` or `osx`.** The first
  `neokikoeru-fetch` attempt with `neokikoeru_<arch>.darwin.tar.gz` 404s.
- **`serve` has no flags.** Don't pass `--port`, `--config`, or `--scan-dir` —
  the binary will error out with "unknown flag."
- **API base path is `/api/v1`**, not `/api` or `/v1`. The WebUI axios
  instance is `baseURL: window.location.origin + "/api/v1"`.
- **Storage is API-managed, not CLI-managed.** There is no `neokikoeru
  storage add` command. Use `POST /api/v1/admin/storages` from the helper
  or click through the WebUI.
- **First-run password log line uses square brackets**, not parens:
  `password is [<pw>]`, not `password is (<pw>)`.
- **The library on the macOS data dir is created on first write**, not
  on first start. `neokikoeru-serve start` creates it explicitly via
  `mkdir -p` so the generated `config.json` lands in the right place
  before the binary starts.

## Related skill files

- `SKILL.md` — top-level asmr-library skill, describes `/asmr-library` and
  the `asmr-library` shell wrapper.
- `/Users/sainthenry/Documents/ASMR Pipeline/docs/plans/neokikoeru-asmr-library-consolidation.md`
  — the full consolidation plan that produced this integration. Read it if
  you need context on the *why*; this file is the *what*.
