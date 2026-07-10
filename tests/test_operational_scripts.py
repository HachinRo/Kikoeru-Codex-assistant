import json
import os
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

    def test_neo_config_redacts_secrets_by_default(self):
        script = ROOT / "Web-UI/bin/neokikoeru-serve"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = base / "state"
            state.mkdir()
            (state / "serve-config.json").write_text(
                json.dumps({"admin_user": "admin", "admin_password": "secret-pass", "token": "secret-jwt"}),
                encoding="utf-8",
            )
            env = {**os.environ, "HOME": str(base / "home"), "ASMR_STATE_ROOT": str(state)}
            result = subprocess.run([str(script), "config"], env=env, text=True, capture_output=True, check=True)
            self.assertNotIn("secret-pass", result.stdout)
            self.assertNotIn("secret-jwt", result.stdout)
            self.assertEqual(result.stdout.count("[redacted]"), 2)

    def test_cover_workflow_uses_local_reindex(self):
        script = (ROOT / "Web-UI/bin/asmr-fix-covers-workflow").read_text(encoding="utf-8")
        self.assertIn('"${LIB_BIN}" reindex', script)
        self.assertNotIn('POST "${VIEW_URL}/api/admin/reindex"', script)


if __name__ == "__main__":
    unittest.main()
