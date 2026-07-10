---
name: asmr-subtitle-batch
description: Fast ASMR subtitle workflow for Japanese audio works using MacWhisper persisted transcript rows and direct Codex batch translation. Use when generating Simplified Chinese .vtt sidecars for ASMR works, especially work folders with MP3/WAV duplicate tracks, works listed in ASMR-SUBTITLES CSVs, MacWhisper .vtt exports, or requests to preserve timings while improving subtitle generation speed.
---

# ASMR Subtitle Batch

Generate Simplified Chinese VTT sidecars quickly by separating deterministic media work from translation:

1. Transcribe each unique duplicate group once with MacWhisper `mw transcribe --persist`, preferring MP3 but falling back to M4A/FLAC/MP4/WAV when needed.
2. Read cue timings from MacWhisper SQLite (`session` + `transcriptline`).
3. Translate cue text directly in the current Codex session as a batch.
4. Render VTT and mirror it to duplicate audio files with the same stem.
5. Verify cue counts, naming, and leftover Japanese kana.

Do not use nested `codex exec` translation chunks for this workflow; it is slower and prone to reconnect failures.

## Fast Workflow

Use the helper script for extraction, writing, and verification:

```bash
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py inspect /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py transcribe-missing /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py dump /Volumes/TOSHIBA/AMSR/RJ01032464 --out /tmp/RJ01032464.cues.json
```

Translate the dumped `items` directly in the active Codex response, preserving each `id`. Save translations as:

```json
{
  "tracks": [
    {
      "stem": "track01",
      "items": [
        {"id": "cue-1", "text": "中文翻译"}
      ]
    }
  ]
}
```

Then apply and verify:

```bash
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py apply /Volumes/TOSHIBA/AMSR/RJ01032464 --translations /tmp/RJ01032464.zh.json
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py verify /Volumes/TOSHIBA/AMSR/RJ01032464
```

For large works, use the compact batch path to reduce translation overhead:

```bash
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py todo /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py pack /Volumes/TOSHIBA/AMSR/RJ01032464 --skip-missing --max-cues 700 --out /tmp/RJ01032464.pack.json
```

Translate each `texts` array directly in the active Codex response. Save only same-length `translations` arrays:

```json
{
  "schema": "asmr-simple-v1",
  "tracks": [
    {
      "source": "/path/to/track01.mp3",
      "translations": ["中文翻译1", "中文翻译2"]
    }
  ]
}
```

Then apply with built-in count and kana checks:

```bash
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py apply-simple /Volumes/TOSHIBA/AMSR/RJ01032464 --translations /tmp/RJ01032464.zh.json --dry-run
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py apply-simple /Volumes/TOSHIBA/AMSR/RJ01032464 --translations /tmp/RJ01032464.zh.json
```

## Large Work Loop

Use `todo` as the preflight and completion gate. Start with `todo`; if `pending_transcription` is nonzero, run `transcribe-missing` and then `todo` again. Treat the work as done only when `available_untranslated 0 pending_transcription 0`.

For large works, pack and apply in bounded chunks:

1. Create compact payloads with `pack --skip-missing --max-cues 500` to `--max-cues 700`. Use `--stem` or `--max-tracks` for the final small remainder.
2. When worker delegation is available and the payload is large, delegate only the translation JSON write. Keep `qa`, dry-run, apply, and verification in the main session.
3. Require translated JSON to preserve every `track.source` exactly and every `translations` array length exactly.
4. Run `qa`, then `apply-simple --dry-run`, then `apply-simple`. Do not skip the dry-run.
5. After the final chunk, run `verify`, `sweep`, and `todo`.

Final verification:

```bash
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py verify /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py sweep /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py todo /Volumes/TOSHIBA/AMSR/RJ01032464
python3 ~/.codex/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py audit /Volumes/TOSHIBA/AMSR/RJ01032464
```

## Rules

- Use MP3 as the transcription source when MP3/WAV duplicates exist; otherwise use the best available media source for that stem-duration group.
- A leading number is a track number only when it is one to three digits and is not the prefix of a longer number. Date-like names such as `2024年...` must never collapse into one group.
- For effect/difference variants, mirror only when their semantic content folder and normalized title agree after known variant suffixes are removed. A matching track number alone is never sufficient.
- For packaged variants such as `Track01_Title(SECut)` MP3/WAV plus `Track01_Title` MP4/video copies, group by the nearest character/content folder and the normalized stem with `(SECut)` removed; translate one canonical source and mirror to every variant stem.
- When work packages contain normal audio, `SECut` audio, and `ChapterNN`/video copies under the same character/content folder, group by that content folder plus the leading track/chapter number first. Do not let wrapper folders such as `01_mp3`, `02_SE Cut`, `wav`, or subtitle/video folders split the same logical track into duplicate work.
- Mirror the finished VTT to duplicate WAV/FLAC/M4A sidecars with the same stem.
- Name sidecars with original media stem plus `.vtt`: `track01.mp3` -> `track01.vtt`.
- Never create `track01.mp3.vtt` or `track01.zh-Hans.vtt`.
- Preserve MacWhisper cue timings exactly; replace cue payload text only.
- After writing, verify every media file has a sidecar, cue counts match MacWhisper rows, no bad names exist, and no leftover Hiragana/Katakana remains.
- Run `audit` after `verify`; it compares helper-generated VTT provenance with the media track and reports legacy cross-track mirroring without deleting anything.
- The canonical skill lives under `docs/skills/asmr-subtitle-batch`; synchronize it with `scripts/sync-skills.sh` rather than editing the installed copy directly.
