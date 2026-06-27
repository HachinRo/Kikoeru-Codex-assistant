# Media stack handoff

This workspace is the control point for the local media system originally built
with Hermes. It documents the live installation without copying credentials,
databases, downloaded media, or generated frontend bundles into Git.

## Services

| Service | Local URL | Role |
| --- | --- | --- |
| Kikoeru-compatible ASMR viewer | http://127.0.0.1:8890 | Browse and stream the ASMR library |
| ani-rss | http://127.0.0.1:7789 | RSS matching, download submission, and episode renaming |
| qBittorrent WebUI | http://127.0.0.1:8088 | Torrent download engine |
| Emby | http://127.0.0.1:8096 | Anime library and playback |

Run `./bin/media-stack-health` for a read-only status report.

The downloader, subtitle matcher, indexing boundary, and known ASMR
implementation gaps are mapped in [ASMR_PIPELINE.md](ASMR_PIPELINE.md). The
anime ANI-RSS → qBittorrent → Emby handoff is mapped in
[ANIME_PIPELINE.md](ANIME_PIPELINE.md).

## Live data and code

- ASMR commands and custom backend: `<ASMR_STACK_ROOT>/bin` and `<ASMR_STACK_ROOT>/lib`
- Compiled Kikoeru SPA: `<ASMR_STACK_ROOT>/kikoeru-spa`
- ASMR metadata database: `<NEOKIKOERU_DB>`
- ASMR media: `<ASMR_MEDIA_ROOT>`
- ani-rss config and subscriptions: `<ANI_RSS_CONFIG_DIR>`
- qBittorrent state: `<QBITTORRENT_DATA_DIR>`
- Emby config: `<EMBY_CONFIG_DIR>`
- Anime media: `<ANIME_MEDIA_ROOT>`

The external volume must be mounted at `<EXTERNAL_VOLUME_ROOT>` before scanning,
renaming, or downloading. Do not commit any live config file: several contain
passwords, tokens, or cookies.

## Common operations

```sh
# ASMR viewer
<ASMR_STACK_ROOT>/bin/asmr-view status
<ASMR_STACK_ROOT>/bin/asmr-view --host 0.0.0.0 --port 8890 start
<ASMR_STACK_ROOT>/bin/asmr-view stop
<ASMR_STACK_ROOT>/bin/asmr-view logs -f

# Neokikoeru indexing/maintenance layer
<ASMR_STACK_ROOT>/bin/asmr-library serve status
<ASMR_STACK_ROOT>/bin/asmr-library serve start
<ASMR_STACK_ROOT>/bin/asmr-library build

# ASMR operator dashboard
<ASMR_STACK_ROOT>/bin/asmr-library dashboard --host 127.0.0.1 --port 8891

# ASMR library tools
<ASMR_STACK_ROOT>/bin/asmr-library status RJ01234567
<ASMR_STACK_ROOT>/bin/asmr-library download RJ01234567
```

ani-rss, qBittorrent, and Emby are installed as macOS applications. Their
normal workflow is:

```text
RSS feed -> ani-rss -> qBittorrent -> <ANIME_MEDIA_ROOT> -> Emby
```

qBittorrent restores hundreds of torrents at launch. During that window,
ani-rss may log connection-refused errors against port 8088; they are harmless
if the port appears shortly afterward and the health check passes.

## Known limitations

- The Kikoeru frontend is a compiled upstream SPA; the custom source of record
  is the Python compatibility backend in `<ASMR_STACK_ROOT>`.
- NeoKikoeru may log DLsite cover-image 404s for stale metadata URLs. Existing
  local covers and audio playback are unaffected.
- The ASMR viewer currently has no real authentication and binds to the LAN.
  Keep it on a trusted network or change the host to `127.0.0.1`.
