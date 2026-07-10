# Subtitle grouping audit — 2026-07-11

Scope: all 116 `RJ*` works under the live ASMR media root.

## Result

- The old helper grouped every one-to-three digit prefix globally. It could
  collapse unrelated folders and interpreted the first three digits of a
  four-digit year as a track number.
- The corrected helper keys numbered tracks by semantic content folder,
  normalized title, and track number. Format, SE-cut, subtitle-video, and
  reversed-audio wrappers are normalized without merging unrelated content.
- Missing or empty work paths now fail instead of returning a false success.
- Helper-generated VTTs now support a provenance audit against MacWhisper.

## Live-library audit

- 34 high-confidence cross-date mismatches were found in `RJ01232781`: sidecars
  for distinct 2024 recordings all referenced one February 24 transcript.
- Those 34 VTTs were moved, not deleted, to the ignored local quarantine at
  `local/quarantine/subtitle-grouping-20260711/`. The two sidecars belonging to
  the source recording remain active.
- 61 title-mismatch candidates remain across `RJ240318`, `RJ356598`,
  `RJ376778`, and `RJ383035`. They are retained because effect, channel, and
  arrangement variants can legitimately share dialogue despite different
  filenames. The corrected grouping will not mirror these automatically in
  future batches.
- Machine-readable per-work reports are retained under the ignored
  `local/audits/subtitle-grouping-20260711-v3/` directory.

No audio, video, image, or database content was changed.
