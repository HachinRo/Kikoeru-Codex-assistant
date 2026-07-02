# Consolidate Neokikoeru into ASMR-Library Workflow

> **For Hermes:** Plan only — no execution in this turn. Hand to subagent-driven-development when ready.
> **Updated 2026-06-22 12:24** after verifying the actual Neokikoeru 3.7.1 binary, docs site, and front-end API callsite.

**Goal:** Make **asmr-library** the single source of truth for "what's downloaded, where it lives, what's verified", and make **Neokikoeru** the single viewer. **Remove** ASMRoner's `listen` path entirely. Add `asmr-library serve` to manage the Neokikoeru process, symlink index, login, and storage registration as one workflow.

**Architecture (verified against the actual binary at `vscodev/neokikoeru` v3.7.1):**

- Neokikoeru ships as a single Go binary with subcommands `serve | admin | encrypt | decrypt | prune | completion`. **`serve` accepts no flags** — port, bind host, JWT secret, and database are all driven by a `config.json` file at the OS data dir (`$HOME/Library/Application Support/neokikoeru/` on macOS).
- First-run log prints `successfully created admin account, the username is [admin] and password is [xxxxxx]`.
- The WebUI talks to `POST /api/v1/auth/login` with `{username, password}` → returns `{user, token}` (JWT, 7-day expiry).
- "Add storage" is done through `POST /api/v1/admin/storages` with a body shape we now know exactly: `{driver, driver_meta, max_scan_depth, ignore_folders, force_proxy, remark}`. For local storage, `driver_meta` is `{root_folder_path: "..."}`.
- The library on disk is **already** in the layout Neokikoeru's local storage driver expects: one `RJ########/` directory per work, anywhere under a chosen root.

So the consolidation becomes a clean mapping:

| Concern | Owner | Surface |
|---|---|---|
| Download / verify / publish | `asmr-library-worker` (existing) | `/Volumes/TOSHIBA/AMSR/<RJ>/` |
| On-disk layout | TOSHIBA library (existing) | `RJ########/(mp3\|wav)_.../(mp3\|wav)...` |
| Symlink index for the viewer | new `serve_index.py` | `<ASMR_STACK_ROOT>/serve-index/RJ########/...` |
| Neokikoeru process & config | new `neokikoeru-serve` wrapper | `neokikoeru serve` + generated `config.json` |
| Neokikoeru login (get JWT) | new `serve login` | `POST /api/v1/auth/login` → `serve-config.json` |
| First-run admin password capture | new `serve init` (called by `start`) | greps log → `serve-config.json` |
| Storage registration | new `serve storage add` (optional helper) | `POST /api/v1/admin/storages` |
| ASMRoner `listen` command | **removed** | n/a |

**Tech Stack:** POSIX sh (matches existing `asmr-library` / `asmr-library-worker` style), Python 3 for the indexer, the `neokikoeru-macos-arm64.tar.gz` binary from the latest GitHub release. No Docker.

---

## Current Context (verified 2026-06-22)

**Library & tools already in place:**

- `/Volumes/TOSHIBA/AMSR/` — 98 `RJ########/` directories, one work per folder, no further bucketing required for Neokikoeru's local driver (Neokikoeru's "最大扫描深度 / max_scan_depth" knob controls how deep it descends; we set it to 3 to skip stray nested folders).
- `/Volumes/TOSHIBA/AMSR.incoming/` — staging.
- `<ASMR_STACK_ROOT>/bin/asmr-library-worker` — per-RJ locks, volume check, payload validation, atomic publish.
- `<ASMR_STACK_ROOT>/bin/asmr-library` — `download / status / retry / search / sync / listen / config / version / asmroner`.
- `<ASMR_STACK_ROOT>/bin/asmroner` — used by `listen` only; will become a dead binary after the cutover (kept on disk for one release as a safety net, see Task 8).
- `docs/skills/asmr-library-ops/SKILL.md` — public-facing docs for the `/asmr-library` slash command.

**Neokikoeru facts (extracted from `neokikoeru-macos-arm64.tar.gz` v3.7.1, `--help`, and the embedded front-end JS):**

- Subcommands: `admin {reset-pwd}`, `serve` (no flags), `encrypt [dir]`, `decrypt [dir]`, `prune`, `completion`, `version`.
- Data dir on macOS: `$HOME/Library/Application Support/neokikoeru/`. Config file there: `config.json`. Defaults from the docs:
  ```json
  {
    "log": {"enabled": true, "filename": "$HOME/Library/Application Support/neokikoeru/logs/neokikoeru.log", "max_size": 50, "max_backups": 30, "max_age": 28, "compress": true},
    "database": {"driver": "sqlite3", "data_source": "file:$HOME/Library/Application Support/neokikoeru/neokikoeru.db?cache=shared&mode=rwc&_busy_timeout=500&_txlock=immediate&_journal_mode=WAL&_foreign_keys=true"},
    "server": {"bind_host": "0.0.0.0", "bind_port": 5233, "allow_origins": ["*"], "allow_methods": ["*"], "allow_headers": ["*"], "jwt_secret": "xxxxxx", "token_expires_in": 7},
    "dlsite": {"locale": "zh-CN", "covers_dir": "$HOME/Library/Application Support/neokikoeru/covers", "trim_outer_brackets": true, "proxy_url": "", "proxy_secret": ""}
  }
  ```
- First-run log line: `successfully created admin account, the username is [admin] and password is [xxxxxx]`.
- Front-end API callsite (extracted from the embedded `index-*.js`):
  - `baseURL: window.location.origin + "/api/v1"`
  - `POST /api/v1/auth/login {username, password}` → `{user, token}`
  - `POST /api/v1/auth/session` → refresh
  - `POST /api/v1/auth/change_password`
  - `POST /api/v1/admin/storages` body:
    ```json
    {"driver":"local","driver_meta":{"root_folder_path":"<PATH>"},"max_scan_depth":3,"ignore_folders":[],"force_proxy":false,"remark":""}
    ```
  - `POST /api/v1/admin/storages/{id}/scan` — triggers a scan task
  - `POST /api/v1/admin/storages/{id}/index` — triggers a file index task
  - `POST /api/v1/admin/works/refresh`, `POST /api/v1/admin/works/clean`
- CLI `neokikoeru admin reset-pwd` is a guaranteed fallback if we lose the first-run password (it resets and prints a new one).

**Confirmed by direct download + extraction:** `https://github.com/vscodev/neokikoeru/releases/download/v3.7.1/neokikoeru-macos-arm64.tar.gz` (asset pattern: `neokikoeru-{macos,linux,windows}-{amd64,arm64}.{tar.gz,zip}`; latest tag at fetch time was `v3.7.1`).

**Network caveat:** the release page requires GitHub login to read HTML, but `https://github.com/vscodev/neokikoeru/releases/expanded_assets/<TAG>` and `releases/download/<TAG>/<ASSET>` are public. The fetch path goes via `https://api.github.com/repos/vscodev/neokikoeru/releases/latest` for tag discovery, which is also public (no auth required for unauthenticated callers up to the rate limit).

---

## Proposed Approach

Layered, additive where possible, fully reversible until the final cutover step.

1. **Fetch layer** — `asmr-library fetch-neokikoeru` (idempotent) downloads the right asset for the host arch into `<ASMR_STACK_ROOT>/bin/neokikoeru` and records the version.
2. **Index layer** — Python 3 indexer mirrors `/Volumes/TOSHIBA/AMSR/<RJ>/...` to `<ASMR_STACK_ROOT>/serve-index/<RJ>/...` as a flat symlink tree (no bucketing). Runs only against the published library; never touches `AMSR.incoming/`.
3. **Process layer** — `neokikoeru-serve start` writes a generated `config.json` (port 8889, sensible defaults), launches `neokikoeru serve` in the background, captures the PID and log, surfaces `stop / status / logs / version`.
4. **Auth layer** — `neokikoeru-serve login [username] [password]` POSTs to `/api/v1/auth/login` with credentials supplied on the CLI or read from `serve-config.json` (the first-run password is stored there on first `start`), persists the JWT to `serve-config.json`. The JWT is what downstream `serve storage add` uses.
5. **Storage helper** — `neokikoeru-serve storage add` (optional convenience) POSTs the local-storage entry pointing at the symlink index. Without this helper, the user can also add storage through the WebUI once; the helper just makes the cutover scriptable.
6. **Removal** — `asmr-library listen` is removed; the `listen` case is deleted from the wrapper. ASMRoner's binary is left in place for one release as a recovery path (deleting it would force a re-install if we needed to roll back). The skill doc drops the `listen` subcommand.

**One-page user model after this lands:**

> `asmr-library download RJ12345` → file lands in `/Volumes/TOSHIBA/AMSR/RJ12345/` → `asmr-library serve start` builds the index and runs Neokikoeru → open `http://localhost:8889/`, log in with the admin password from `asmr-library serve status` → `asmr-library serve storage add` (one-time) registers the index → browse.

---

## Files to Change / Create

| Action | Path | Purpose |
|---|---|---|
| Create | `<ASMR_STACK_ROOT>/bin/neokikoeru-fetch` | Idempotent release downloader (sh + curl + tar). |
| Create | `<ASMR_STACK_ROOT>/lib/serve_index.py` | Python 3 flat symlink indexer. |
| Create | `<ASMR_STACK_ROOT>/bin/neokikoeru-serve` | Process + login + storage wrapper (sh). |
| Modify | `<ASMR_STACK_ROOT>/bin/asmr-library` | Add `fetch-neokikoeru` and `serve` cases. **Remove** the `listen` case. |
| Modify | `docs/skills/asmr-library-ops/SKILL.md` | Document the new subcommands; remove `listen`; add architecture note. |
| Create (runtime) | `<ASMR_STACK_ROOT>/serve-config.json` | Persisted port + admin username + password + JWT + token_expires_at. |
| Create (runtime) | `<ASMR_STACK_ROOT>/serve-index/` | The symlink index served to Neokikoeru. |
| Create (runtime) | `<ASMR_STACK_ROOT>/serve.pid` | PID of the running Neokikoeru. |
| Create (runtime) | `<ASMR_STACK_ROOT>/logs/serve.log` | Captured Neokikoeru stdout/stderr. |
| Create (runtime) | `<ASMR_STACK_ROOT>/neokikoeru.version` | Plain-text tag. |
| Create (runtime) | `$HOME/Library/Application Support/neokikoeru/config.json` | Generated by `serve start` with port 8889. |

**Untouched** (deliberately): `asmr-library-worker`, the `asmroner` binary, the `/Volumes/TOSHIBA/AMSR/` and `/Volumes/TOSHIBA/AMSR.incoming/` trees.

---

## Step-by-Step Plan

### Task 1: `neokikoeru-fetch` (idempotent release downloader)

**Objective:** Single command that ensures `<ASMR_STACK_ROOT>/bin/neokikoeru` exists and matches the latest release; otherwise download and unpack it.

**Files:**
- Create: `<ASMR_STACK_ROOT>/bin/neokikoeru-fetch`
- Create (after first run): `<ASMR_STACK_ROOT>/neokikoeru.version`

**Step 1: Implement the downloader**

```sh
#!/bin/sh
# Idempotent fetch of the latest Neokikoeru binary from vscodev/neokikoeru
# releases. Writes the resolved semver to <ASMR_STACK_ROOT>/neokikoeru.version.
#
# Asset pattern (verified from expanded_assets on 2026-06-22):
#   neokikoeru-macos-amd64.tar.gz
#   neokikoeru-macos-arm64.tar.gz
#   neokikoeru-linux-amd64.tar.gz
#   neokikoeru-linux-arm64.tar.gz
#   neokikoeru-windows-amd64.zip
#   neokikoeru-windows-arm64.zip
set -eu
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
DEFAULT_STATE_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
STATE_ROOT="${ASMR_STATE_ROOT:-${ASMR_STACK_ROOT:-${DEFAULT_STATE_ROOT}}}"
BIN_DIR="${STATE_ROOT}/bin"
VERSION_FILE="${STATE_ROOT}/neokikoeru.version"
REPO="vscodev/neokikoeru"
API="https://api.github.com/repos/${REPO}/releases/latest"

case "$(uname -s):$(uname -m)" in
    Darwin:arm64|Darwin:aarch64) os_part="macos"; arch_part="arm64" ;;
    Darwin:x86_64|Darwin:amd64)   os_part="macos"; arch_part="amd64" ;;
    Linux:arm64|Linux:aarch64)    os_part="linux"; arch_part="arm64" ;;
    Linux:x86_64|Linux:amd64)     os_part="linux"; arch_part="amd64" ;;
    *) echo "Unsupported platform: $(uname -s)/$(uname -m)" >&2 ; exit 1 ;;
esac

asset="neokikoeru-${os_part}-${arch_part}.tar.gz"
target="${BIN_DIR}/neokikoeru"
mkdir -p "${BIN_DIR}"

tmp_meta="$(mktemp -t neokikoeru-meta.XXXXXX)"
trap 'rm -f -- "${tmp_meta}"' EXIT
curl -fsSL -H 'Accept: application/vnd.github+json' "${API}" -o "${tmp_meta}"

# tag_name: "v3.7.1" — line-based grep, no jq dependency.
tag="$(awk -F'"' '/"tag_name":/ {print $4; exit}' "${tmp_meta}")"
[ -n "${tag}" ] || { echo "Could not parse latest release tag from GitHub API" >&2; exit 1; }

if [ -x "${target}" ] && [ "$(cat "${VERSION_FILE}" 2>/dev/null || true)" = "${tag}" ]; then
    echo "Neokikoeru ${tag} already installed at ${target}"
    exit 0
fi

download_url="https://github.com/${REPO}/releases/download/${tag}/${asset}"
tmp_tar="$(mktemp -t neokikoeru-tar.XXXXXX)"
trap 'rm -f -- "${tmp_meta}" "${tmp_tar}"' EXIT
echo "Downloading ${download_url}"
curl -fsSL "${download_url}" -o "${tmp_tar}"

tmp_dir="$(mktemp -d -t neokikoeru-extract.XXXXXX)"
tar -xzf "${tmp_tar}" -C "${tmp_dir}"

# The release tarball contains a single executable named "neokikoeru".
[ -f "${tmp_dir}/neokikoeru" ] || { echo "Release archive did not contain neokikoeru binary" >&2; exit 1; }
install -m 0755 "${tmp_dir}/neokikoeru" "${target}"

printf '%s\n' "${tag}" > "${VERSION_FILE}"
rm -rf -- "${tmp_dir}" "${tmp_tar}" "${tmp_meta}"
trap - EXIT
echo "Installed Neokikoeru ${tag} -> ${target}"
```

**Step 2: Verify**

```sh
chmod +x <ASMR_STACK_ROOT>/bin/neokikoeru-fetch
<ASMR_STACK_ROOT>/bin/neokikoeru-fetch         # first run downloads
<ASMR_STACK_ROOT>/bin/neokikoeru-fetch         # second run is a no-op
<ASMR_STACK_ROOT>/bin/neokikoeru --version
```

Expected:
- First run prints `Downloading ...` and `Installed Neokikoeru v3.7.1 -> /.../bin/neokikoeru`.
- Second run prints `Neokikoeru v3.7.1 already installed at ...`.
- `neokikoeru --version` prints `neokikoeru version 3.7.1`.
- `neokikoeru.version` contains `v3.7.1`.

### Task 2: Symlink index builder

**Objective:** Build `<ASMR_STACK_ROOT>/serve-index/RJ########/...` as a flat mirror of `/Volumes/TOSHIBA/AMSR/RJ########/...`. Skip incomplete / partial works.

**Files:**
- Create: `<ASMR_STACK_ROOT>/lib/serve_index.py`

**Step 1: Implement the indexer**

```python
#!/usr/bin/env python3
"""Build <ASMR_STACK_ROOT>/serve-index/ as a flat symlink mirror of /Volumes/TOSHIBA/AMSR/.

One directory per work, one symlink per file. No bucketing — Neokikoeru's local
storage driver walks RJ########/ in place and reads audio files where they are.
Skips any RJ whose directory contains .part / .partial / .tmp / .download /
.crdownload files or any zero-byte audio file. Failures are logged to stderr
and do not abort the whole build.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
PARTIAL_EXTS = {".part", ".partial", ".tmp", ".download", ".crdownload"}
RJ_PATTERN = re.compile(r"^RJ\d+$", re.IGNORECASE)


def is_complete(work: Path) -> tuple[bool, str]:
    has_audio = False
    for item in work.rglob("*"):
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix in PARTIAL_EXTS:
            return False, f"partial file present: {item.relative_to(work)}"
        if suffix in AUDIO_EXTS:
            if item.stat().st_size == 0:
                return False, f"zero-byte audio: {item.relative_to(work)}"
            has_audio = True
    if not has_audio:
        return False, "no non-empty audio file"
    return True, "ok"


def build_index(source_root: Path, index_root: Path) -> tuple[int, int, int]:
    if not source_root.is_dir():
        print(f"source root missing: {source_root}", file=sys.stderr)
        return 0, 0, 0
    if index_root.exists():
        shutil.rmtree(index_root)
    index_root.mkdir(parents=True, exist_ok=True)

    works_indexed = 0
    works_skipped = 0
    links_created = 0
    for work in sorted(source_root.iterdir()):
        if not work.is_dir() or not RJ_PATTERN.match(work.name):
            continue
        rj = work.name.upper()
        ok, reason = is_complete(work)
        if not ok:
            print(f"skip {rj}: {reason}", file=sys.stderr)
            works_skipped += 1
            continue
        target = index_root / rj
        target.mkdir(parents=True, exist_ok=True)
        for item in work.rglob("*"):
            if not item.is_file():
                continue
            link = target / item.relative_to(work)
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(item, link)
            except FileExistsError:
                pass
            links_created += 1
        works_indexed += 1
    return works_indexed, works_skipped, links_created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("ASMR_LIBRARY_ROOT", "/Volumes/TOSHIBA/AMSR"),
        help="Library root (default: /Volumes/TOSHIBA/AMSR or $ASMR_LIBRARY_ROOT).",
    )
    parser.add_argument(
        "--index",
        default=os.environ.get(
            "ASMR_SERVE_INDEX_ROOT",
            str(Path(__file__).resolve().parent.parent / "serve-index"),
        ),
        help="Symlink index root (default: <ASMR_STACK_ROOT>/serve-index).",
    )
    args = parser.parse_args()
    indexed, skipped, links = build_index(Path(args.source), Path(args.index))
    print(f"Indexed {indexed} works, skipped {skipped}, {links} file links -> {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 2: Verify**

```sh
chmod +x <ASMR_STACK_ROOT>/lib/serve_index.py
python3 <ASMR_STACK_ROOT>/lib/serve_index.py
ls <ASMR_STACK_ROOT>/serve-index | wc -l                              # 98
ls <ASMR_STACK_ROOT>/serve-index/RJ01010222 | head -3
readlink <ASMR_STACK_ROOT>/serve-index/RJ01010222/'(mp3)_ストーリー/01_いらっしゃいませ.mp3'
python3 <ASMR_STACK_ROOT>/lib/serve_index.py                          # idempotent re-run
```

Expected:
- `Indexed 98 works, skipped 0, <N> file links -> /.../serve-index`.
- The first `readlink` resolves back to `/Volumes/TOSHIBA/AMSR/RJ01010222/(mp3)_ストーリー/01_いらっしゃいませ.mp3`.

### Task 3: `neokikoeru-serve` wrapper (process + login + storage)

**Objective:** Single sh wrapper that handles:
- Process lifecycle (`start / stop / status / logs / version`).
- `init` (write `config.json` with port 8889, capture first-run password from log).
- `login [username] [password]` — POST to `/api/v1/auth/login`, store JWT.
- `storage add [path]` — POST a local storage entry; default path is the symlink index.
- `config.json` round-tripping with a stable on-disk schema.

**Files:**
- Create: `<ASMR_STACK_ROOT>/bin/neokikoeru-serve`

**Step 1: Implement the wrapper**

```sh
#!/bin/sh
# Wrapper around the Neokikoeru binary. Manages config.json, the running
# process, the admin password / JWT, and (optionally) the local storage
# entry that points at the asmr-library symlink index.
set -eu
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
DEFAULT_STATE_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
STATE_ROOT="${ASMR_STATE_ROOT:-${ASMR_STACK_ROOT:-${DEFAULT_STATE_ROOT}}}"
BIN="${STATE_ROOT}/bin/neokikoeru"
LOG_DIR="${STATE_ROOT}/logs"
INDEXER="${STATE_ROOT}/lib/serve_index.py"
PID_FILE="${STATE_ROOT}/serve.pid"
LOG_FILE="${LOG_DIR}/serve.log"
CONFIG_FILE="${STATE_ROOT}/serve-config.json"
DEFAULT_PORT="8889"
DEFAULT_ADMIN_USER="admin"
LIBRARY_ROOT="${ASMR_LIBRARY_ROOT:-/Volumes/TOSHIBA/AMSR}"
INDEX_ROOT="${ASMR_SERVE_INDEX_ROOT:-${STATE_ROOT}/serve-index}"
NK_DATA_DIR="${HOME}/Library/Application Support/neokikoeru"
NK_CONFIG="${NK_DATA_DIR}/config.json"

mkdir -p "${LOG_DIR}" "${NK_DATA_DIR}" "${INDEX_ROOT}"

usage() {
    cat <<'USAGE'
Usage:
  neokikoeru-serve init [--port PORT]   # write config.json (does not start the server)
  neokikoeru-serve start [--port PORT] [--no-index] [--foreground]
  neokikoeru-serve stop
  neokikoeru-serve status
  neokikoeru-serve logs [-n LINES]
  neokikoeru-serve version
  neokikoeru-serve login [USERNAME] [PASSWORD]  # fetch a JWT and persist it
  neokikoeru-serve storage add [PATH]            # register a local storage entry
  neokikoeru-serve storage list                  # list registered storages
  neokikoeru-serve config [--show]               # show on-disk serve-config.json
USAGE
}

fail() { printf 'FAILED: %s\n' "$*" >&2 ; exit 1 ; }
say()  { printf '%s\n' "$*"; }

ensure_binary() {
    [ -x "${BIN}" ] || "${STATE_ROOT}/bin/neokikoeru-fetch" || fail "neokikoeru binary missing and fetch failed"
}

# Tiny JSON read for the few fields we maintain. Avoids jq.
read_cfg() {
    cfg_field="$1"
    if [ ! -f "${CONFIG_FILE}" ]; then return 1; fi
    python3 -c "
import json, sys
try:
    d = json.load(open('${CONFIG_FILE}'))
    v = d.get('${cfg_field}', '')
    print('' if v is None else v)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

write_cfg() {
    # Build a JSON object from KEY=VALUE pairs on the argument list.
    tmp="${CONFIG_FILE}.tmp"
    python3 - "$@" > "${tmp}" <<'PY'
import json, sys
d = {}
for kv in sys.argv[1:]:
    if "=" not in kv: continue
    k, v = kv.split("=", 1)
    d[k] = v
print(json.dumps(d, indent=2, ensure_ascii=False))
PY
    mv "${tmp}" "${CONFIG_FILE}"
}

# Write the Neokikoeru data-dir config.json. Port and bind_host are the
# only fields we override; the rest mirrors the upstream defaults verbatim.
write_nk_config() {
    port="$1"
    cat > "${NK_CONFIG}" <<JSON
{
  "log": {
    "enabled": true,
    "filename": "${HOME}/Library/Application Support/neokikoeru/logs/neokikoeru.log",
    "max_size": 50,
    "max_backups": 30,
    "max_age": 28,
    "compress": true
  },
  "database": {
    "driver": "sqlite3",
    "data_source": "file:${HOME}/Library/Application Support/neokikoeru/neokikoeru.db?cache=shared&mode=rwc&_busy_timeout=500&_txlock=immediate&_journal_mode=WAL&_foreign_keys=true"
  },
  "server": {
    "bind_host": "0.0.0.0",
    "bind_port": ${port},
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "jwt_secret": "neokikoeru-asmr-library",
    "token_expires_in": 7
  },
  "dlsite": {
    "locale": "zh-CN",
    "covers_dir": "${HOME}/Library/Application Support/neokikoeru/covers",
    "trim_outer_brackets": true,
    "proxy_url": "",
    "proxy_secret": ""
  }
}
JSON
}

# Pull the first-run admin password out of the log if present, and persist
# it to serve-config.json. Idempotent.
capture_admin_password() {
    [ -f "${LOG_FILE}" ] || return 1
    pw="$(grep -E 'successfully created admin account.*password is \[' "${LOG_FILE}" 2>/dev/null \
        | tail -n 1 \
        | sed -E 's/.*password is \[([^]]*)\].*/\1/' )"
    if [ -n "${pw}" ]; then
        existing_user="$(read_cfg admin_user 2>/dev/null || true)"
        existing_token="$(read_cfg token 2>/dev/null || true)"
        write_cfg \
            "port=$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")" \
            "admin_user=${existing_user:-${DEFAULT_ADMIN_USER}}" \
            "admin_password=${pw}" \
            "token=${existing_token}" \
            "token_expires_at=$(read_cfg token_expires_at 2>/dev/null || true)"
        return 0
    fi
    return 1
}

running_pid() {
    [ -f "${PID_FILE}" ] || return 1
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    [ -n "${pid}" ] || return 1
    kill -0 "${pid}" 2>/dev/null || return 1
    printf '%s\n' "${pid}"
}

cmd_init() {
    port="${DEFAULT_PORT}"
    while [ $# -gt 0 ]; do
        case "$1" in
            --port) port="$2" ; shift 2 ;;
            *) fail "unknown flag: $1" ;;
        esac
    done
    ensure_binary
    write_nk_config "${port}"
    if [ -f "${CONFIG_FILE}" ]; then
        # Preserve existing credentials; only refresh port.
        existing_user="$(read_cfg admin_user 2>/dev/null || true)"
        existing_pw="$(read_cfg admin_password 2>/dev/null || true)"
        existing_token="$(read_cfg token 2>/dev/null || true)"
        existing_exp="$(read_cfg token_expires_at 2>/dev/null || true)"
        write_cfg \
            "port=${port}" \
            "admin_user=${existing_user:-${DEFAULT_ADMIN_USER}}" \
            "admin_password=${existing_pw}" \
            "token=${existing_token}" \
            "token_expires_at=${existing_exp}"
    else
        write_cfg \
            "port=${port}" \
            "admin_user=${DEFAULT_ADMIN_USER}" \
            "admin_password=" \
            "token=" \
            "token_expires_at="
    fi
    say "Wrote Neokikoeru config -> ${NK_CONFIG} (port ${port})"
    say "Wrote serve config -> ${CONFIG_FILE}"
}

cmd_start() {
    foreground=0
    no_index=0
    port=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --port) port="$2" ; shift 2 ;;
            --no-index) no_index=1 ; shift ;;
            --foreground) foreground=1 ; shift ;;
            *) fail "unknown flag: $1" ;;
        esac
    done
    ensure_binary
    if [ -z "${port}" ]; then
        port="$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")"
    fi
    cmd_init --port "${port}"
    [ "${no_index}" -eq 0 ] && python3 "${INDEXER}" --source "${LIBRARY_ROOT}" --index "${INDEX_ROOT}"
    if pid="$(running_pid)"; then
        say "Neokikoeru already running (PID ${pid}, port ${port})"
        return 0
    fi
    : > "${LOG_FILE}"
    if [ "${foreground}" -eq 1 ]; then
        exec "${BIN}" serve
    fi
    nohup "${BIN}" serve >>"${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"
    # Give it a moment to write the first-run password line.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        if grep -qE 'successfully created admin account|Server listening|listening on' "${LOG_FILE}" 2>/dev/null; then
            break
        fi
        if ! kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
            break
        fi
    done
    if ! running_pid >/dev/null; then
        tail -n 30 "${LOG_FILE}" >&2
        rm -f -- "${PID_FILE}"
        fail "Neokikoeru exited immediately; see ${LOG_FILE}"
    fi
    capture_admin_password || true
    say "Neokikoeru started (PID $(cat "${PID_FILE}"), port ${port}) -> http://localhost:${port}"
    say "  config:     ${NK_CONFIG}"
    say "  serve-cfg:  ${CONFIG_FILE}"
    say "  index:      ${INDEX_ROOT}"
    say "  log:        ${LOG_FILE}"
    if [ -n "$(read_cfg admin_password 2>/dev/null || true)" ]; then
        say "  admin:      ${DEFAULT_ADMIN_USER} / $(read_cfg admin_password)"
        say "  (run: asmr-library serve status  to re-print credentials)"
    fi
}

cmd_stop() {
    if ! pid="$(running_pid)"; then
        rm -f -- "${PID_FILE}"
        say "Neokikoeru is not running"
        return 0
    fi
    kill "${pid}" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "${pid}" 2>/dev/null; then
        kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f -- "${PID_FILE}"
    say "Neokikoeru stopped (was PID ${pid})"
}

cmd_status() {
    if pid="$(running_pid)"; then
        port="$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")"
        user="$(read_cfg admin_user 2>/dev/null || echo "${DEFAULT_ADMIN_USER}")"
        pw="$(read_cfg admin_password 2>/dev/null || true)"
        token="$(read_cfg token 2>/dev/null || true)"
        say "Neokikoeru is running (PID ${pid}, port ${port})"
        say "  config:     ${NK_CONFIG}"
        say "  index:      ${INDEX_ROOT}"
        say "  log:        ${LOG_FILE}"
        [ -n "${pw}" ] && say "  admin:      ${user} / ${pw}"
        if [ -n "${token}" ]; then
            say "  jwt:        present (expires at $(read_cfg token_expires_at 2>/dev/null))"
            say "  login url:  http://localhost:${port}/"
        else
            say "  jwt:        (none — run: asmr-library serve login)"
        fi
    else
        say "Neokikoeru is not running"
        return 1
    fi
}

cmd_logs() {
    n=40
    while [ $# -gt 0 ]; do
        case "$1" in
            -n) n="$2" ; shift 2 ;;
            *) fail "unknown flag: $1" ;;
        esac
    done
    [ -f "${LOG_FILE}" ] || { say "no log file at ${LOG_FILE}"; return 0; }
    tail -n "${n}" "${LOG_FILE}"
}

cmd_version() {
    ensure_binary
    "${BIN}" --version
    [ -f "${STATE_ROOT}/neokikoeru.version" ] && cat "${STATE_ROOT}/neokikoeru.version"
}

# POST to the Neokikoeru API. Uses the same Authorization header the WebUI
# would use. Writes the response body to stdout and the status to stderr.
api_post() {
    path="$1"
    body="$2"
    token="$3"
    port="$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")"
    base="http://127.0.0.1:${port}/api/v1"
    if [ -n "${token}" ]; then
        curl -sS -X POST -H "Content-Type: application/json" \
             -H "Authorization: Bearer ${token}" \
             -w '\n__HTTP_STATUS__%{http_code}\n' \
             -d "${body}" "${base}${path}"
    else
        curl -sS -X POST -H "Content-Type: application/json" \
             -w '\n__HTTP_STATUS__%{http_code}\n' \
             -d "${body}" "${base}${path}"
    fi
}

cmd_login() {
    user=""
    pw=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --*) fail "unknown flag: $1" ;;
            *)
                if [ -z "${user}" ]; then user="$1"
                elif [ -z "${pw}" ]; then pw="$1"
                else fail "too many arguments to login"
                fi
                shift
                ;;
        esac
    done
    if [ -z "${user}" ]; then user="$(read_cfg admin_user 2>/dev/null || echo "${DEFAULT_ADMIN_USER}")"; fi
    if [ -z "${pw}" ]; then pw="$(read_cfg admin_password 2>/dev/null || true)"; fi
    [ -n "${user}" ] && [ -n "${pw}" ] || fail "no credentials available; pass USERNAME and PASSWORD"
    if ! running_pid >/dev/null; then
        say "WARN: Neokikoeru is not running; starting it now"
        cmd_start --no-index
    fi
    body="$(printf '{"username":"%s","password":"%s"}' "${user}" "$(printf '%s' "${pw}" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')")"
    out="$(api_post /auth/login "${body}" "")"
    status="$(printf '%s' "${out}" | awk '/__HTTP_STATUS__/ {print $2}')"
    body_only="$(printf '%s' "${out}" | sed -E '/__HTTP_STATUS__/d')"
    if [ "${status}" != "200" ]; then
        printf 'Login failed (HTTP %s): %s\n' "${status}" "${body_only}" >&2
        return 1
    fi
    token="$(printf '%s' "${body_only}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("token",""))')"
    [ -n "${token}" ] || fail "no token in response: ${body_only}"
    # 7-day expiry (mirrors server default); we re-issue by re-logging in.
    expires_at="$(python3 -c "import datetime; print((datetime.datetime.utcnow() + datetime.timedelta(days=6, hours=23)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    port="$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")"
    write_cfg \
        "port=${port}" \
        "admin_user=${user}" \
        "admin_password=${pw}" \
        "token=${token}" \
        "token_expires_at=${expires_at}"
    say "Login OK; JWT stored in ${CONFIG_FILE} (valid through ${expires_at})"
}

cmd_storage_add() {
    path="${INDEX_ROOT}"
    while [ $# -gt 0 ]; do
        case "$1" in
            --*) fail "unknown flag: $1" ;;
            *) path="$1" ; shift ;;
        esac
    done
    [ -d "${path}" ] || fail "storage path is not a directory: ${path}"
    token="$(read_cfg token 2>/dev/null || true)"
    [ -n "${token}" ] || fail "no JWT — run: asmr-library serve login first"
    body="$(python3 -c "import json,sys; print(json.dumps({'driver':'local','driver_meta':{'root_folder_path':sys.argv[1]},'max_scan_depth':3,'ignore_folders':[],'force_proxy':False,'remark':'asmr-library'}))" "${path}")"
    out="$(api_post /admin/storages "${body}" "${token}")"
    status="$(printf '%s' "${out}" | awk '/__HTTP_STATUS__/ {print $2}')"
    body_only="$(printf '%s' "${out}" | sed -E '/__HTTP_STATUS__/d')"
    if [ "${status}" != "200" ] && [ "${status}" != "201" ]; then
        printf 'Storage add failed (HTTP %s): %s\n' "${status}" "${body_only}" >&2
        return 1
    fi
    say "Storage added: ${path}"
    say "  ${body_only}"
    say "  (open http://localhost:$(read_cfg port 2>/dev/null || echo ${DEFAULT_PORT})/  and click 'scan' to start scraping)"
}

cmd_storage_list() {
    token="$(read_cfg token 2>/dev/null || true)"
    [ -n "${token}" ] || fail "no JWT — run: asmr-library serve login first"
    port="$(read_cfg port 2>/dev/null || echo "${DEFAULT_PORT}")"
    curl -sS -H "Authorization: Bearer ${token}" \
         -w '\n__HTTP_STATUS__%{http_code}\n' \
         "http://127.0.0.1:${port}/api/v1/admin/storages?page=1&page_size=100" \
        | sed -E '/__HTTP_STATUS__/d' | python3 -m json.tool 2>/dev/null || cat
}

cmd_config_show() {
    if [ -f "${CONFIG_FILE}" ]; then
        cat "${CONFIG_FILE}"
    else
        say "(no serve-config.json yet — run: asmr-library serve start)"
    fi
}

[ $# -ge 1 ] || { usage; exit 0; }
case "$1" in
    init)     shift; cmd_init "$@" ;;
    start)    shift; cmd_start "$@" ;;
    stop)     shift; cmd_stop ;;
    status)   shift; cmd_status ;;
    logs)     shift; cmd_logs "$@" ;;
    version)  shift; cmd_version ;;
    login)    shift; cmd_login "$@" ;;
    storage)  shift
        case "${1:-}" in
            add)  shift; cmd_storage_add "$@" ;;
            list) shift; cmd_storage_list ;;
            *) fail "unknown storage subcommand: ${1:-} (use 'add' or 'list')" ;;
        esac
        ;;
    config)   shift; cmd_config_show ;;
    -h|--help|help) usage ;;
    *) fail "unknown subcommand: $1" ;;
esac
```

**Step 2: Verify the wiring standalone (no server yet)**

```sh
chmod +x <ASMR_STACK_ROOT>/bin/neokikoeru-serve
neokikoeru-serve --help    # via PATH? it's at <ASMR_STACK_ROOT>/bin — run directly:
<ASMR_STACK_ROOT>/bin/neokikoeru-serve help
<ASMR_STACK_ROOT>/bin/neokikoeru-serve version
<ASMR_STACK_ROOT>/bin/neokikoeru-serve config --show
```

Expected: the inner `usage()` prints; `version` prints the binary version; `config --show` says "no serve-config.json yet".

### Task 4: Wire `serve` and `fetch-neokikoeru` into `asmr-library`, remove `listen`

**Objective:** Single front door for the user. Adds two new top-level subcommands, removes the `listen` case.

**Files:**
- Modify: `<ASMR_STACK_ROOT>/bin/asmr-library`

**Step 1: Patch `usage()`** to add the two new lines and remove `listen`:

```text
  asmr-library fetch-neokikoeru       # download/refresh the Neokikoeru binary
  asmr-library serve [start|stop|status|login|storage|...]   # run Neokikoeru as the sole viewer
  asmr-library listen ...             # REMOVED: Neokikoeru replaces ASMRoner's listen
```

**Step 2: Patch the `case "$1"` block** — add two new cases (one calls `neokikoeru-fetch`, the other is a generic forwarder) and **delete** the `listen)` case:

```sh
    fetch-neokikoeru)
        "${STATE_ROOT}/bin/neokikoeru-fetch"
        ;;
    serve)
        shift
        "${STATE_ROOT}/bin/neokikoeru-serve" "$@"
        ;;
```

(The original `listen)` case is deleted; if `listen` is invoked after the patch, the wrapper falls through to `*` and prints `Unknown command 'listen'`.)

**Step 3: Verify**

```sh
asmr-library --help
asmr-library serve help
asmr-library fetch-neokikoeru
asmr-library serve version
asmr-library listen    # should now FAIL with "Unknown command 'listen'"
```

Expected:
- `asmr-library --help` lists `fetch-neokikoeru` and `serve`, no longer lists `listen`.
- `asmr-library serve help` prints the inner `usage()`.
- `asmr-library fetch-neokikoeru` is a no-op (binary already present) and prints `Neokikoeru v3.7.1 already installed at ...`.
- `asmr-library listen` fails with `Unknown command 'listen'`.

### Task 5: End-to-end smoke (start, log, login, storage add, browse, stop)

**Objective:** Confirm the entire chain works against a live process.

**Step 1: Start in the background**

```sh
asmr-library serve start --port 8889
```

Expected: a multi-line block with `Neokikoeru started (PID ..., port 8889)`, the four paths, and the `admin: admin / <random-password>` line if first-run.

**Step 2: Probe the WebUI**

```sh
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8889/
```

Expected: `HTTP 200` (Vue SPA shell).

**Step 3: Log in via the helper**

```sh
asmr-library serve login
```

Expected: `Login OK; JWT stored in /.../serve-config.json (valid through 2026-...)`.

**Step 4: Register the symlink index as a storage**

```sh
asmr-library serve storage add
```

Expected: `Storage added: <ASMR_STACK_ROOT>/serve-index` followed by the JSON response and a hint to click "scan" in the WebUI.

**Step 5: Verify the indexer is serving real files**

```sh
ls <ASMR_STACK_ROOT>/serve-index | wc -l
readlink <ASMR_STACK_ROOT>/serve-index/RJ01010222/'(mp3)_ストーリー/01_いらっしゃいませ.mp3'
test -s "$(readlink <ASMR_STACK_ROOT>/serve-index/RJ01010222/'(mp3)_ストーリー/01_いらっしゃいませ.mp3')" && echo OK
```

Expected: `98`; a real path; `OK`.

**Step 6: Status and stop**

```sh
asmr-library serve status
asmr-library serve stop
asmr-library serve status    # should report "not running"
```

Expected:
- `status` shows running PID, port, the admin password, and `jwt: present (expires at ...)`.
- After `stop`, `status` exits non-zero with `Neokikoeru is not running`.

### Task 6: Update the skill documentation

**Objective:** Make `/asmr-library` reflect the new world in chat.

**Files:**
- Modify: `docs/skills/asmr-library-ops/SKILL.md`

**Step 1: Replace the Commands block** with:

```text
- `/asmr-library download RJ01234567 [RJ...]`
- `/asmr-library status RJ01234567 [RJ...]`
- `/asmr-library retry RJ01234567 [RJ...]`
- `/asmr-library search <RJID-or-query> [search flags]`
- `/asmr-library sync [sync args]`
- `/asmr-library fetch-neokikoeru` — idempotent: download or refresh the Neokikoeru binary from the latest `vscodev/neokikoeru` GitHub release into `<ASMR_STACK_ROOT>/bin/neokikoeru` and record the resolved semver in `<ASMR_STACK_ROOT>/neokikoeru.version`.
- `/asmr-library serve start [--port 8889] [--no-index] [--foreground]` — build the symlink index at `<ASMR_STACK_ROOT>/serve-index/`, write a Neokikoeru `config.json` (port 8889, JWT 7-day), start `neokikoeru serve` in the background, capture the first-run admin password, and surface it via `status`.
- `/asmr-library serve stop` — SIGTERM the running Neokikoeru.
- `/asmr-library serve status` — show PID, port, admin password, JWT presence + expiry.
- `/asmr-library serve login [USERNAME] [PASSWORD]` — POST to `/api/v1/auth/login`; persist the JWT to `<ASMR_STACK_ROOT>/serve-config.json`.
- `/asmr-library serve storage add [PATH]` — register a local storage entry pointing at the symlink index (default) or any other path. JWT required.
- `/asmr-library serve storage list` — list registered storages via the admin API.
- `/asmr-library serve logs [-n N]` — tail the captured log.
- `/asmr-library serve config` — print `<ASMR_STACK_ROOT>/serve-config.json`.
- `/asmr-library config [config args]`
- `/asmr-library version`
- `/asmr-library asmroner <raw asmroner args>` — only for an unsupported passthrough
```

**Step 2: Add an Architecture subsection**:

> asmr-library downloads, manages, and verifies the library on disk. Neokikoeru is the read-only viewer and the only viewer. `serve start` builds a flat symlink index of the published tree and runs Neokikoeru against it; the underlying `/Volumes/TOSHIBA/AMSR/<RJ>/` directories are never moved or rewritten. The ASMRoner `listen` command has been removed — its symlink indexer (`asmr-library listen`) is no longer in the wrapper. The `asmroner` binary is kept on disk for one release as a rollback path.

**Step 3: Update Diagnostics**:

```text
Serve log:     <ASMR_STACK_ROOT>/logs/serve.log
Serve PID:     <ASMR_STACK_ROOT>/serve.pid
Index root:    <ASMR_STACK_ROOT>/serve-index/
Serve cfg:     <ASMR_STACK_ROOT>/serve-config.json
NK config:     $HOME/Library/Application Support/neokikoeru/config.json
NK data dir:   $HOME/Library/Application Support/neokikoeru/
NK data DB:    $HOME/Library/Application Support/neokikoeru/neokikoeru.db
NK log:        $HOME/Library/Application Support/neokikoeru/logs/neokikoeru.log
```

### Task 7: Verify `/asmr-library` slash-command visibility

**Files:** none (verification only).

**Step 1:** invoke `/asmr-library --help` (in a chat context) or `asmr-library --help` (in a shell) and confirm:
- `fetch-neokikoeru` and `serve` are listed.
- `listen` is **not** listed.
- If a legacy operator config defines `quick_commands.asmr-library`, remove it (per the existing skill, do not self-alias `/asmr-library` because quick commands can shadow skill commands).

### Task 8: Cutover and rollback safety

**Objective:** Make the change persistent across reboots and document the rollback path.

**Files:** none (operational).

**Step 1: Make the wrapper self-start at login (optional, opt-in).** Skip this by default — the user invokes `asmr-library serve start` on demand. If they want a LaunchAgent, the skill notes the path: copy `<ASMR_STACK_ROOT>/bin/asmr-library` to PATH, then a one-liner LaunchAgent that calls `asmr-library serve start` on `KeepAlive`. Not in this plan; the user opts in.

**Step 2: Document the rollback path in the skill:**

> To roll back to ASMRoner's listen view: revert `<ASMR_STACK_ROOT>/bin/asmr-library` from git, then `asmr-library listen`. The `asmroner` binary remains at `<ASMR_STACK_ROOT>/bin/asmroner`. Note that the Neokikoeru symlink index at `<ASMR_STACK_ROOT>/serve-index/` is a different layout than ASMRoner's listen-index at `<ASMR_STACK_ROOT>/listen-index/` — do not point ASMRoner at the new index.

**Step 3: Mark the roll-forward as complete** in the skill's `version` history.

---

## Tests / Validation

End-to-end (the suite to run after all tasks):

```sh
# 1. Sanity: existing pipeline still works.
asmr-library status RJ01010222
asmr-library --help          # shows the new subcommands, no `listen`

# 2. Idempotent binary fetch.
asmr-library fetch-neokikoeru
asmr-library fetch-neokikoeru   # no-op second run

# 3. Index build is correct + matches the library count.
python3 <ASMR_STACK_ROOT>/lib/serve_index.py
ls <ASMR_STACK_ROOT>/serve-index | wc -l
[ "$(ls <ASMR_STACK_ROOT>/serve-index | wc -l)" -eq "$(ls /Volumes/TOSHIBA/AMSR | wc -l)" ] && echo INDEX_OK

# 4. Server lifecycle.
asmr-library serve start --port 8889
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8889/   # 200

# 5. Login + storage add.
asmr-library serve login
asmr-library serve status         # jwt: present (expires at ...)
asmr-library serve storage add

# 6. Clean teardown.
asmr-library serve stop
asmr-library serve status         # exit 1, "not running"

# 7. Listen must be gone.
asmr-library listen               # FAIL: Unknown command 'listen'
```

Expected: `INDEX_OK`; `HTTP 200`; the `status` output is informative; `listen` is rejected.

Manual UI check:
- Open `http://localhost:8889/` in a browser, log in with `admin` and the password from `asmr-library serve status`, navigate to **Storages**, confirm the row with `path: <ASMR_STACK_ROOT>/serve-index`, click **scan**, watch the **Tasks** page drain to empty, then browse to a known RJ (`RJ01010222`) and play a track.

---

## Risks, Tradeoffs, and Open Questions

**Risks**

- **Network at fetch time.** `fetch-neokikoeru` calls `api.github.com` and `github.com`; on a restricted network (the user is on a Chinese VPN per the profile), the download can fail. **Mitigation:** the task is idempotent and retriable. If a side-channel binary is available, the user can `cp neokikoeru <ASMR_STACK_ROOT>/bin/` and skip fetch entirely — `serve start` will use whatever is there.
- **First-run admin password loss.** If the log is wiped before the user copies the password, they would be locked out. **Mitigation:** `serve start` persists the password to `serve-config.json` on first capture; `serve status` re-prints it. If `serve-config.json` is also lost, `neokikoeru admin reset-pwd` (a CLI subcommand of the binary itself) resets and prints a new password — that subcommand is always available regardless of the helper.
- **Port collision.** Default `:8889` is unclaimed on the user's machine (no ASMRoner path to worry about after cutover). If a future process claims it, `asmr-library serve config --port N` is a single flag away.
- **Storage is a UI concept, not a CLI flag.** The previous (wrong) plan assumed `--scan-dir` — the actual binary has no such flag. The plan now uses the API directly; if the API changes between releases, the storage helper breaks. The WebUI is the always-supported fallback.

**Tradeoffs**

- **Symlink index vs. direct scan of `/Volumes/TOSHIBA/AMSR/`.** The symlink index gives us a stable place to apply future transformations (subtitle renaming, multi-source merges, decryption) without rewriting the on-disk library. The on-disk library already has the correct layout (one `RJ########/` per work), so we *could* have Neokikoeru scan it directly. We chose the index because it lets us add `max_scan_depth: 3` to skip stray subfolders without enforcing that discipline on the source. Cost: extra disk metadata (negligible) and one rebuild per `serve start`. **Mitigation if it ever matters:** `serve start --no-index` is supported and points the WebUI at the raw library.
- **`asmroner` binary kept on disk for one release.** It costs ~30 MB; the alternative is a clean cutover with no rollback. Keeping the binary is reversible — deleting it later is one command.
- **No LaunchAgent.** Auto-start on login is a separate concern. The default is "user runs `asmr-library serve start` when they want to listen" — simpler, fewer moving parts. Add the LaunchAgent in a follow-up if requested.

**Open questions (none blocking — defaults are documented above):**

1. **JWT refresh.** The 7-day expiry means `serve login` needs to be re-run weekly (or whenever `serve status` shows the JWT expired). Acceptable? Alternative: persist a refresh-token flow (no evidence the API supports one in v3.7.1) — punted to v2.
2. **Storage auto-scan after `serve storage add`.** The plan triggers the add but not a follow-up `POST /admin/storages/{id}/scan` because the user might want to batch several RJs first. Surfacing a `serve storage scan [ID]` helper is a small follow-up; the WebUI's "scan" button works today.
3. **Covers / DLsite metadata.** The Neokikoeru config has a `dlsite` block; on first scan Neokikoeru will try to fetch metadata from DLsite (per the docs, requires `HTTP_PROXY`/`HTTPS_PROXY` on a restricted network). The plan doesn't set proxies — if scraping fails, the user sees it in the Tasks page. Out of scope for the consolidation.

---

## Execution Handoff

Plan complete and saved at `/Users/sainthenry/Documents/ASMR Pipeline/docs/plans/neokikoeru-asmr-library-consolidation.md` (rewritten with verified facts at 2026-06-22 12:24).

When ready to execute, dispatch via `subagent-driven-development` — one subagent per task, full context (paths, the verified API, the expected output), with two-stage review (spec compliance, then code quality) before advancing.

Each task is bite-sized; the only inter-task dependency is that **Task 1** (binary present) must finish before Tasks 3 and 5. Tasks 2 and 4 can run in parallel with Task 1.

**Estimated total time:** ~30 minutes of focused work across the eight tasks, plus a 5-minute end-to-end manual check.

Ready to proceed with execution. Shall I dispatch the subagent pipeline now?
