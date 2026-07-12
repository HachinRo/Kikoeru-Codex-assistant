import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from load_script import load_script


ROOT = Path(__file__).resolve().parents[1]


class OperationalScriptTests(unittest.TestCase):
    def test_all_dashboard_mutations_require_admin(self):
        viewer = load_script("asmr_view_test", ROOT / "Web-UI/bin/asmr-view")
        expected = {
            "download", "retry", "fill", "fix-covers", "reindex", "subs-search",
            "fix-content", "subs-dry-run", "subs-fetch",
        }
        self.assertEqual(viewer.PROTECTED_DASHBOARD_ACTIONS, expected)
        self.assertEqual(viewer.ADMIN_DEFAULT_PASSWORD, "")

    def test_worker_status_checks_indexed_files(self):
        worker = ROOT / "Web-UI/bin/asmr-library-worker"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = base / "library"
            staging = base / "staging"
            state = base / "state"
            work = library / "RJ00000001"
            for path in (work, staging, state):
                path.mkdir(parents=True, exist_ok=True)
            env = {
                **os.environ,
                "ASMR_TEST_MODE": "1",
                "ASMR_VOLUME_ROOT": str(base),
                "ASMR_LIBRARY_ROOT": str(library),
                "ASMR_STAGING_ROOT": str(staging),
                "ASMR_STATE_ROOT": str(state),
                "NEOKIKOERU_DB": str(base / "missing.db"),
            }
            result = subprocess.run([str(worker), "status", "RJ00000001"], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("UNKNOWN", result.stdout)

            media = work / "track.mp3"
            media.write_bytes(b"audio")
            db_path = base / "neo.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE files(path TEXT, size INTEGER, work_id TEXT, is_folder INTEGER)")
                db.execute("INSERT INTO files VALUES(?, ?, ?, 0)", ("/RJ00000001/track.mp3", 5, "RJ00000001"))
            env["NEOKIKOERU_DB"] = str(db_path)
            result = subprocess.run([str(worker), "status", "RJ00000001"], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("COMPLETE", result.stdout)

    def test_cover_workflow_uses_local_reindex(self):
        script = (ROOT / "Web-UI/bin/asmr-fix-covers-workflow").read_text(encoding="utf-8")
        self.assertIn('"${LIB_BIN}" reindex', script)
        self.assertNotIn('POST "${VIEW_URL}/api/admin/reindex"', script)

    def test_reindex_uses_native_scanner_without_maintenance_port(self):
        script = (ROOT / "Web-UI/bin/asmr-library").read_text(encoding="utf-8")
        match = re.search(r"run_reindex\(\) \{(?P<body>.*?)\n\}", script, re.S)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn('bin/asmr-native-scan', body)
        self.assertNotIn('neokikoeru-serve', body)
        self.assertNotIn('storage scan', body)

        build = re.search(r"run_build\(\) \{(?P<body>.*?)\n\}", script, re.S)
        self.assertIsNotNone(build)
        self.assertIn('bin/asmr-native-scan', build.group("body"))
        self.assertIn('--rebuild-content', build.group("body"))

    def test_active_stack_has_no_separate_worker_dependency(self):
        active = [
            ROOT / "Web-UI/bin/asmr-library",
            ROOT / "Web-UI/bin/asmr-view",
            ROOT / "Web-UI/bin/asmr-neo",
            ROOT / "Web-UI/bin/asmr-dashboard",
            ROOT / "Web-UI/bin/media-stack-health",
            ROOT / "scripts/status.sh",
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in active)
        self.assertNotIn("8889", text)
        self.assertNotIn("neokikoeru-serve", text)
        self.assertNotIn("/api/v1", text)


if __name__ == "__main__":
    unittest.main()
