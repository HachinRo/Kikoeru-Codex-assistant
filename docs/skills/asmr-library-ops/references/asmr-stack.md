# ASMR stack reference

Use this file when diagnosing ASMR-library/Kikoeru/NeoKikoeru failures, routing gaps, subtitle issues, or UI regressions.

## Live components

| Component | Location / URL | Notes |
| --- | --- | --- |
| Main viewer | `http://127.0.0.1:8890` | Kikoeru-compatible frontend and API served by `asmr-view`. This is the only normal browser/operator port. |
| Integrated dashboard | `http://127.0.0.1:8890/asmr-library` | Namespaced ASMR-library UI inside the main viewer. |
| Standalone dashboard | retired | Do not use a separate `8891` dashboard; use `/asmr-library` on `8890`. |
| NeoKikoeru maintenance | on-demand internal service | May be started temporarily by build/reindex, but should not be left as a persistent browser/admin port. |
| ASMR commands | `<ASMR_STACK_ROOT>/bin` | `asmr-view`, `asmr-library`, `asmr-subs`, `asmr-neo`, `neokikoeru-serve`. |
| ASMR library code | `<ASMR_STACK_ROOT>/lib` | Includes `asmr_view_kikoeru.py`, the main viewer backend. |
| Kikoeru SPA | `<ASMR_STACK_ROOT>/kikoeru-spa` | Compiled frontend bundle; patches are brittle. |
| Media root | `<ASMR_MEDIA_ROOT>` | Do not bulk-mutate media casually. |
| NeoKikoeru DB | `<NEOKIKOERU_DB>` | Treat as live state. Back up before direct DB edits. |

## Important files

- `<ASMR_STACK_ROOT>/bin/asmr-view`: process manager / entrypoint for port `8890`.
- `<ASMR_STACK_ROOT>/bin/asmr-dashboard`: integrated/standalone dashboard server logic.
- `<ASMR_STACK_ROOT>/bin/asmr-library`: umbrella CLI for build, dashboard, works, and subtitles.
- `<ASMR_STACK_ROOT>/bin/asmr-subs`: subtitle download/refetch/encoding CLI.
- `<ASMR_STACK_ROOT>/bin/asmr-neo`: work/file lookup CLI now expected to use viewer API/stream routes on `8890`.
- `<ASMR_STACK_ROOT>/bin/neokikoeru-serve`: NeoKikoeru adapter; previously had a float progress formatting crash in tasks output.
- `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py`: Kikoeru-compatible routes, media streaming, search, grouping.
- `<ASMR_STACK_ROOT>/kikoeru-spa/js/app.051b603f.fix2.js`: patched SPA bundle.
- `<ASMR_STACK_ROOT>/kikoeru-spa/index.html`: points the frontend to the patched bundle.

## Expected API surface

Dashboard:

- `/asmr-library`
- `/api/asmr-library/health`
- `/api/asmr-library/library/summary`
- `/api/asmr-library/subtitles/missing`
- `/api/asmr-library/work/<RJ>`
- `/api/asmr-library/actions/<action>`

Kikoeru-compatible work/search/grouping routes:

- `/api/search/<keyword>`
- `/api/tags`
- `/api/tags/<id>`
- `/api/tags/<id>/works`
- `/api/circles`
- `/api/circles/<id>`
- `/api/circles/<id>/works`
- `/api/vas`
- `/api/vas/<id>`
- `/api/vas/<id>/works`
- `/api/duration/<file_id>`
- `/api/media/stream/<file_id_or_subtitle_hash>?token=`

Search must match title, RJ, intro, maker/circle, series, tags/genres, artists/VAs, and illustrators.

## Subtitle encoding notes

Subtitle failures usually come in two flavors:

1. Download/refetch failure from transient remote API or SSL EOF errors.
2. Encoding corruption either on disk or during `/api/media/stream/...`.

`asmr-subs` should:

- Retry subtitle downloads.
- Retry transient API GET/POST SSL EOF failures.
- Decode subtitle bytes using `utf-8-sig`, `utf-8`, `gb18030`, `gbk`, `gb2312`.
- Log the actual detected encoding instead of always reporting GB2312.

Stream-time charset detection in `asmr_view_kikoeru.py` must not strict-decode a short UTF-8 sample as final input. If the sample ends mid-multibyte character, use an incremental UTF-8 decoder with `final=False`; otherwise valid UTF-8 can be mislabeled as GBK and Traditional Chinese becomes mojibake.

Known fixed stream:

```text
http://localhost:8890/api/media/stream/ylelmK2e_kI?token=
```

Expected content starts:

```text
[00:01.43]二人「製作人，恭喜您~」
[00:09.35]螢「讓您久等了，您被選為“SS級製作人適應性測試”的對象了~」
```

Previously refetched/fixed RJ examples:

- `RJ01100316`
- `RJ278635`
- `RJ01218071`
- `RJ424363`
- `RJ01010222`
- `RJ01495866`

## Regression checks

Use these after code changes:

```bash
rtk ./bin/media-stack-health
rtk "<ASMR_STACK_ROOT>/bin/asmr-view" status
rtk curl -fsS "http://127.0.0.1:8890/asmr-library"
rtk curl -fsS "http://127.0.0.1:8890/api/search/RJ01571688?count=20&page=1"
rtk curl -fsS "http://127.0.0.1:8890/api/tags/500/works"
rtk curl -fsS "http://127.0.0.1:8890/api/circles/RG74824/works"
rtk curl -fsS "http://127.0.0.1:8890/api/vas/eRGTnmW8/works"
rtk curl -fsS "http://127.0.0.1:8890/api/duration/ylelmK2e_kI"
rtk curl -fsS -I "http://127.0.0.1:8890/api/media/stream/ylelmK2e_kI?token="
```

## Reference repos

Use these for behavior comparison and source-level ideas:

- `refs/ASMR-Kikoeru`: user-maintained public GitHub repo, remote `https://github.com/HachinRo/ASMR-Kikoeru`; treat as the canonical ASMR-Kikoeru source/reference for pipeline-related work.
- `refs/kikoeru-express`: original Kikoeru API/UI behavior, especially search, tags, groups, and works.
- `refs/asmr-downloader`: ASMR download/subtitle reference behavior.
- `refs/neokikoeru`: NeoKikoeru indexing/storage/task model.

Do not treat these repos as live deployment targets unless the user asks.
