import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from load_script import load_script


ROOT = Path(__file__).resolve().parents[1]
SERVE_INDEX = load_script("serve_index_test", ROOT / "Web-UI/lib/serve_index.py")


class ServeIndexTests(unittest.TestCase):
    def make_work(self, source: Path, rj: str, filename: str = "track.mp3") -> Path:
        work = source / rj
        work.mkdir(parents=True)
        media = work / filename
        media.write_bytes(b"audio")
        return media

    def test_successful_build_replaces_old_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            media = self.make_work(source, "RJ00000001")
            index = root / "serve-index"
            index.mkdir()
            (index / "old-marker").write_text("old", encoding="utf-8")

            result = SERVE_INDEX.build_index(source, index)

            self.assertEqual(result, (1, 0, 1))
            link = index / "RJ00000001" / "track.mp3"
            self.assertTrue(link.is_symlink())
            self.assertEqual(Path(os.readlink(link)), media)
            self.assertFalse((index / "old-marker").exists())
            self.assertEqual(list(root.glob(".serve-index.*-*")), [])

    def test_build_failure_preserves_old_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            self.make_work(source, "RJ00000001")
            index = root / "serve-index"
            index.mkdir()
            marker = index / "old-marker"
            marker.write_text("old", encoding="utf-8")

            with mock.patch.object(SERVE_INDEX.os, "symlink", side_effect=OSError("injected")):
                with self.assertRaisesRegex(OSError, "injected"):
                    SERVE_INDEX.build_index(source, index)

            self.assertEqual(marker.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(root.glob(".serve-index.*-*")), [])

    def test_failed_install_restores_old_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            self.make_work(source, "RJ00000001")
            index = root / "serve-index"
            index.mkdir()
            marker = index / "old-marker"
            marker.write_text("old", encoding="utf-8")
            real_replace = SERVE_INDEX.os.replace
            calls = 0

            def fail_second_replace(src, dst):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected install failure")
                return real_replace(src, dst)

            with mock.patch.object(SERVE_INDEX.os, "replace", side_effect=fail_second_replace):
                with self.assertRaisesRegex(OSError, "injected install failure"):
                    SERVE_INDEX.build_index(source, index)

            self.assertEqual(marker.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(root.glob(".serve-index.*-*")), [])


if __name__ == "__main__":
    unittest.main()
