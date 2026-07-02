# Cover image resolution in asmr-view

When the kikoeru client (or any other front-end) requests
`/api/cover/<numeric_id>` or `/api/covers/<numeric_id>` and the response
is the 1.7 KB `no_img_sam.gif` placeholder, the issue is almost always
that the cover cache (`_COVER_CACHE` in `<ASMR_STACK_ROOT>/bin/asmr-view`)
doesn't have an entry for that work.

This file documents the contract for resolving a work's cover from the
Neokikoeru SQLite DB, and the common bugs that produce a "missing"
result when the cover is actually on disk.

## TL;DR

- **Build the cache from the DB, not the filesystem.** The DB's
  `works.image_main` and `works.image_thumb` columns are the
  authoritative mapping from a work's RJ code to its cover file. The
  filename in the cover directory is **often a stale index** (a
  re-scan / re-index may rename the file to a wrong RJ code, but the
  DB still knows which work it belongs to).
- **Try both `<data_dir>/covers/...` and `<data_dir>/...` roots.**
  The DB stores paths like `doujin/RJ329000/RJ328016_img_main.jpg` —
  relative to `<data_dir>`, but the actual files live in
  `<data_dir>/covers/`. Try the `covers/` subdir first, fall back to
  the data dir.
- **Use the work's `id` (e.g. `RJ328016`) as the cache key, not the
  filename's RJ code.** They often differ. Building the cache from
  filesystem walks with the filename's RJ as the key will silently
  miss 30–50% of covers on a long-running library.

## Symptoms → root cause table

| Symptom | Root cause | Fix |
|---|---|---|
| `/api/cover/<n>?token=` returns 1.7 KB placeholder for some works, but `/Volumes/TOSHIBA/AMSR/covers/doujin/RJ*/<file>.jpg` exists | The cache was built by filesystem walk and key'd by the filename's RJ code (which is wrong for stale-indexed covers). The DB knows the right mapping. | Rebuild the cache from `SELECT id, image_main, image_thumb FROM works`. Use `id` as the key. See `build_cover_cache()` in `<ASMR_STACK_ROOT>/bin/asmr-view`. |
| All covers return placeholder (cache size = 0) | The DB path was joined to the wrong root — e.g. `NEOKIKOERU_DATA / image_main` instead of `NEOKIKOERU_DATA / "covers" / image_main`. | Add the `covers/` prefix in the path resolution. The `image_main` value is `doujin/RJ...` (not `covers/doujin/RJ...`). |
| 6-digit RJ works (`RJ439991`) show no cover but 8-digit works (`RJ01010222`) do | The numeric→RJ conversion padded to 8 digits: `numeric_to_rj(439991) = "RJ0439991"`, but the DB row is `RJ439991`. So `resolve_cover("RJ0439991")` returns nothing. | Use `resolve_rj(conn, n)` (in `<ASMR_STACK_ROOT>/lib/asmr_view_kikoeru.py`) which tries 6/8/raw forms against the DB. Apply it inside `_api_cover` and `_kikoeru_cover` before resolving the cover path. |
| `image_main` in DB points to a file that exists but the cache entry still isn't being used | The cache was populated before any of the fixes above were applied. The asmr-view daemon needs a restart. | `asmr-library view stop && asmr-library view start`. |

## How the fix works

`build_cover_cache()` in `<ASMR_STACK_ROOT>/bin/asmr-view` should:

```python
def build_cover_cache() -> None:
    _COVER_CACHE.clear()
    if not NEOKIKOERU_COVERS.is_dir():
        return
    db = get_db()
    rows = db.execute(
        "SELECT id, image_main, image_thumb FROM works "
        "WHERE image_main != '' OR image_thumb != ''"
    ).fetchall()
    for row in rows:
        work_rj = row["id"]                          # ← the WORK's RJ, not the file's
        kinds: dict[str, Path] = {}
        # Try both roots: <data>/covers/ and <data>/
        for root in (NEOKIKOERU_DATA / "covers", NEOKIKOERU_DATA):
            if row["image_main"]:
                p = root / row["image_main"]
                if p.is_file():
                    kinds["main"] = p
                    break
        for root in (NEOKIKOERU_DATA / "covers", NEOKIKOERU_DATA):
            if row["image_thumb"]:
                p = root / row["image_thumb"]
                if p.is_file():
                    kinds["sam" if "sam" in row["image_thumb"] else "thumb"] = p
                    break
        if kinds:
            _COVER_CACHE[work_rj] = kinds
```

The corresponding `_api_cover` and `_kikoeru_cover` handlers must:

1. Accept both numeric (`1010222`) and RJ (`RJ01010222`) input.
2. For numeric input, call `resolve_rj(conn, n)` to get the actual
   RJ code (handles 6-digit vs 8-digit).
3. Look up the cache by that RJ code.
4. Serve the file from `kinds["main"]` with `Content-Type: image/jpeg`.

## Verifying a complete cache

After fixing the cache and restarting asmr-view:

```sh
DB="$HOME/Library/Application Support/neokikoeru/neokikoeru.db"
PASS=0; FAIL=0; FAILED=""
for rj in $(sqlite3 "$DB" "SELECT id FROM works;"); do
  num=$(echo "$rj" | sed 's/^RJ0*//')
  # Real covers are >5 KB; the placeholder is 1.7 KB.
  size=$(curl -s -o /dev/null -w "%{size_download}" \
    "http://127.0.0.1:8890/api/cover/$num?token=")
  if [ "$size" -gt 5000 ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    FAILED="$FAILED $rj"
  fi
done
echo "All 97 covers: PASS=$PASS  FAIL=$FAIL"
# expected (after fix): PASS=97 FAIL=0
[ -n "$FAILED" ] && echo "Still missing:$FAILED"
```

You can also verify a specific cover is the real one (not a 1.7 KB
re-encoding of the placeholder):

```sh
curl -s "http://127.0.0.1:8890/api/cover/1010222?token=" -o /tmp/cover.jpg
file /tmp/cover.jpg        # → "JPEG image data, baseline, ... 560x420, ..."
wc -c /tmp/cover.jpg       # → 222980 (or similar large size)
```

## When 1 work is truly missing its cover

Some works simply don't have a cover on disk — the DLsite scrape
returned 0 covers, or the file was deleted, or the storage entry was
registered with the wrong `root_folder_path`. In that case:

1. `SELECT image_main FROM works WHERE id = 'RJ...'` — see what the DB
   thinks the cover is.
2. `ls <data_dir>/covers/doujin/RJ..._img_main.jpg` — see if it's on
   disk.
3. If neither has it, no fix in asmr-view can help — the user needs
   to re-run the DLsite scrape (`asmr-library build`) or manually
   place the cover file.

The 1.7 KB placeholder exists exactly for this case. The bug
described in this file is when the placeholder is served for covers
that ARE on disk.

## Original bug (2026-06-22)

Before the fix, `build_cover_cache()` did:

```python
# WRONG — keying by filename RJ, missing the covers/ prefix
for bucket in NEOKIKOERU_COVERS.iterdir():
    for f in bucket.iterdir():
        m = re.match(r"^(RJ\d+)_img_(main|thumb|sam)\.\w+$", f.name)
        if m:
            rj, kind = m.group(1), m.group(2).lower()
            _COVER_CACHE.setdefault(rj, {})[kind] = f
```

This produced a cache of size 96 (count of cover files on disk) with
keys like `RJ01048881` (the file's RJ) instead of `RJ01081641` (the
work's RJ). So `/api/cover/1010222` (for work `RJ01010222`) succeeded
for the 6-digit works that happened to be correctly named, and
returned the placeholder for the 28 works with 6-digit RJ codes where
the file was misnamed.

After the fix (DB-driven, work-id-keyed, both roots tried), the cache
is the same size (96–97 entries) but every entry points to the right
file for its work. `PASS=97 FAIL=0`.
