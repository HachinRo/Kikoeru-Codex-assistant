import tempfile
import unittest
from pathlib import Path

from load_script import load_script


ROOT = Path(__file__).resolve().parents[1]
BATCH = load_script(
    "macwhisper_batch_vtt_test",
    ROOT / "docs/skills/asmr-subtitle-batch/scripts/macwhisper_batch_vtt.py",
)


class SubtitleGroupingTests(unittest.TestCase):
    def test_semantic_folders_do_not_collapse(self):
        story = Path("/tmp/RJ01010222/(mp3)_ストーリー/01_いらっしゃいませ.mp3")
        ear = Path("/tmp/RJ01010222/(wav)_耳舐めマッサージ/01_右耳.wav")
        self.assertNotEqual(BATCH.group_key(story), BATCH.group_key(ear))

    def test_format_and_effect_wrappers_group(self):
        main = Path("/tmp/RJ01571688/mp3/01.SEあり/01.先輩です.mp3")
        variant = Path("/tmp/RJ01571688/wave/02.SEなし/01.先輩です_SEなし.wav")
        self.assertEqual(BATCH.group_key(main), BATCH.group_key(variant))

    def test_four_digit_year_is_not_track_number(self):
        dated = Path("/tmp/RJ01232781/mp3版/2024年01月05日配信分.mp3")
        self.assertIsNone(BATCH.track_identity(dated))

    def test_mp3_and_wav_content_folders_normalize(self):
        mp3 = Path("/tmp/RJ00000001/(mp3)_ストーリー/02_本編.mp3")
        wav = Path("/tmp/RJ00000001/(wav)_ストーリー/02_本編.wav")
        self.assertEqual(BATCH.group_key(mp3), BATCH.group_key(wav))

    def test_track_and_chapter_packaging_group_by_content_and_number(self):
        track = Path("/tmp/RJ00000001/01_内容/01_mp3/track01_本編.mp3")
        chapter = Path("/tmp/RJ00000001/01_内容/03_附字幕的音声动画/chapter01_简体中文.mp4")
        self.assertEqual(BATCH.group_key(track), BATCH.group_key(chapter))

    def test_reversed_prefix_is_same_track(self):
        normal = Path("/tmp/RJ00000001/mp3/02_本編.mp3")
        reversed_audio = Path("/tmp/RJ00000001/mp3/反転02_本編.mp3")
        self.assertEqual(BATCH.group_key(normal), BATCH.group_key(reversed_audio))

    def test_missing_and_empty_work_fail(self):
        with self.assertRaises(SystemExit):
            BATCH.require_work(Path("/tmp/definitely-not-an-asmr-work"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                BATCH.require_work(Path(tmp))


if __name__ == "__main__":
    unittest.main()
