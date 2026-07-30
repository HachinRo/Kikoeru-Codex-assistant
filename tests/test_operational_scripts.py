import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

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
            with closing(sqlite3.connect(db_path)) as db:
                db.execute("CREATE TABLE files(path TEXT, size INTEGER, work_id TEXT, is_folder INTEGER)")
                db.execute("INSERT INTO files VALUES(?, ?, ?, 0)", ("/RJ00000001/track.mp3", 5, "RJ00000001"))
                db.commit()
            env["NEOKIKOERU_DB"] = str(db_path)
            result = subprocess.run([str(worker), "status", "RJ00000001"], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("COMPLETE", result.stdout)

    def test_worker_rejects_zero_exit_when_downloader_reports_failure(self):
        worker = ROOT / "Web-UI/bin/asmr-library-worker"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = base / "library"
            staging = base / "staging"
            state = base / "state"
            config = state / ".asmroner-data" / "config.toml"
            fake_downloader = base / "fake-asmroner"
            for path in (library, staging, config.parent):
                path.mkdir(parents=True, exist_ok=True)
            config.write_text("", encoding="utf-8")
            fake_downloader.write_text(
                "#!/bin/sh\n"
                "mkdir -p \"$4/RJ00000002-test\"\n"
                "printf audio >\"$4/RJ00000002-test/track.mp3\"\n"
                "printf '❌ 下载文件 track.mp3 失败\\n'\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_downloader.chmod(0o755)
            env = {
                **os.environ,
                "ASMR_TEST_MODE": "1",
                "ASMR_VOLUME_ROOT": str(base),
                "ASMR_LIBRARY_ROOT": str(library),
                "ASMR_STAGING_ROOT": str(staging),
                "ASMR_STATE_ROOT": str(state),
                "ASMRONER_BIN": str(fake_downloader),
            }
            result = subprocess.run(
                [str(worker), "download", "RJ00000002"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("reported failed files despite exit status 0", result.stderr)
            self.assertFalse((library / "RJ00000002").exists())
            self.assertTrue((staging / "RJ00000002.partial").is_dir())

    def test_worker_retry_ignores_failure_from_previous_log_attempt(self):
        worker = ROOT / "Web-UI/bin/asmr-library-worker"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = base / "library"
            staging = base / "staging"
            state = base / "state"
            config = state / ".asmroner-data" / "config.toml"
            payload = staging / "RJ00000005.partial" / "RJ00000005-test"
            log_path = state / "logs" / "RJ00000005.log"
            fake_downloader = base / "fake-asmroner"
            for path in (library, payload, config.parent, log_path.parent):
                path.mkdir(parents=True, exist_ok=True)
            config.write_text("", encoding="utf-8")
            log_path.write_text("❌ 下载文件 old.mp3 失败\n", encoding="utf-8")
            (payload / "track.mp3").write_bytes(b"audio")
            fake_downloader.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_downloader.chmod(0o755)
            env = {
                **os.environ,
                "ASMR_TEST_MODE": "1",
                "ASMR_VOLUME_ROOT": str(base),
                "ASMR_LIBRARY_ROOT": str(library),
                "ASMR_STAGING_ROOT": str(staging),
                "ASMR_STATE_ROOT": str(state),
                "ASMRONER_BIN": str(fake_downloader),
            }
            result = subprocess.run(
                [str(worker), "retry", "RJ00000005"],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("COMPLETE", result.stdout)
            self.assertTrue((library / "RJ00000005" / "track.mp3").is_file())

    def test_dashboard_progress_uses_catalog_total_for_existing_work(self):
        dashboard = load_script("asmr_dashboard_progress_test", ROOT / "Web-UI/bin/asmr-dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = base / "library"
            staging = base / "staging"
            work = library / "RJ00000003"
            work.mkdir(parents=True)
            staging.mkdir()
            (work / "one.mp3").write_bytes(b"one")
            (work / "two.mp3").write_bytes(b"two")
            info = {
                "folder_exists": True,
                "db_work": {"name": "Partial work"},
                "db_files": [
                    {"path": "/RJ00000003/one.mp3", "is_folder": 0},
                    {"path": "/RJ00000003/two.mp3", "is_folder": 0},
                ],
                "audio_files": 2,
                "subtitle_files": 0,
            }
            with (
                mock.patch.object(dashboard, "LIBRARY_ROOT", library),
                mock.patch.object(dashboard, "STAGING_ROOT", staging),
                mock.patch.object(dashboard, "work_info", return_value=info),
                mock.patch.object(dashboard, "_expected_file_count_from_tracks_api", return_value=4),
            ):
                progress = dashboard._work_progress("RJ00000003", status="running")
            self.assertEqual(progress["downloaded_files"], 2)
            self.assertEqual(progress["expected_files"], 4)
            self.assertEqual(progress["expected_source"], "tracks-api")
            self.assertEqual(progress["missing_file_count"], 2)
            self.assertEqual(progress["percent"], 50)

    def test_dashboard_progress_includes_active_fill_payload(self):
        dashboard = load_script("asmr_dashboard_fill_progress_test", ROOT / "Web-UI/bin/asmr-dashboard")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            library = base / "library"
            staging = base / "staging"
            work = library / "RJ00000004"
            fill_payload = staging / "RJ00000004.fill" / "RJ00000004-test"
            work.mkdir(parents=True)
            fill_payload.mkdir(parents=True)
            (work / "one.mp3").write_bytes(b"one")
            (fill_payload / "one.mp3").write_bytes(b"one")
            (fill_payload / "two.mp3").write_bytes(b"two")
            info = {
                "folder_exists": True,
                "db_work": {"name": "Filling work"},
                "db_files": [],
                "audio_files": 1,
                "subtitle_files": 0,
            }
            with (
                mock.patch.object(dashboard, "LIBRARY_ROOT", library),
                mock.patch.object(dashboard, "STAGING_ROOT", staging),
                mock.patch.object(dashboard, "work_info", return_value=info),
                mock.patch.object(dashboard, "_expected_file_count_from_tracks_api", return_value=2),
            ):
                progress = dashboard._work_progress("RJ00000004", status="running")
            self.assertEqual(progress["downloaded_files"], 2)
            self.assertEqual(progress["expected_files"], 2)
            self.assertEqual(progress["stage_files"], 2)
            self.assertEqual(progress["percent"], 99)

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
