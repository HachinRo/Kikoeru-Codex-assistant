# ASMR Pipeline

Local ASMR download, subtitle, indexing, and Kikoeru-compatible playback stack.

## Operator entry points

```sh
./scripts/status.sh
./Web-UI/bin/media-stack-health
./Web-UI/bin/asmr-library dashboard
./Web-UI/bin/asmr-library build
./Web-UI/bin/asmr-library subs list-missing
```

Viewer and integrated dashboard:

- `http://127.0.0.1:8890`
- `http://127.0.0.1:8890/asmr-library`

Port 8890 intentionally remains reachable on the trusted LAN. Operational
mutations require the admin credential stored in the local, ignored
`Web-UI/serve-config.json`.

## Development checks

```sh
make test
make health
make verify-binaries
make check-skills
```

Sanitized runtime source is tracked under `Web-UI/`; cookies, databases, logs,
downloaded binaries, indexes, backups, and media are excluded. Canonical Codex
skills live under `docs/skills/` and are installed with `make sync-skills`.
