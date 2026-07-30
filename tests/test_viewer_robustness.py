import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from load_script import load_script


ROOT = Path(__file__).resolve().parents[1]
VIEWER = load_script("asmr_view_robustness_test", ROOT / "Web-UI/bin/asmr-view")
DASHBOARD = load_script(
    "asmr_dashboard_robustness_test",
    ROOT / "Web-UI/bin/asmr-dashboard",
)


class ViewerRobustnessTests(unittest.TestCase):
    def test_explicit_range_end_is_clamped_to_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "ten.bin"
            media.write_bytes(b"0123456789")
            handler = object.__new__(VIEWER.AsmrViewHandler)
            handler.headers = {"Range": "bytes=0-99"}
            handler.wfile = io.BytesIO()
            observed = {"status": None, "headers": []}
            handler.send_response = lambda status: observed.update(status=int(status))
            handler.send_header = lambda key, value: observed["headers"].append((key, value))
            handler.end_headers = lambda: None

            handler._serve_file_range(
                media,
                content_type="application/octet-stream",
            )

            headers = dict(observed["headers"])
            self.assertEqual(observed["status"], 206)
            self.assertEqual(headers["Content-Length"], "10")
            self.assertEqual(headers["Content-Range"], "bytes 0-9/10")
            self.assertEqual(handler.wfile.getvalue(), b"0123456789")

    def test_foreground_does_not_publish_pid_before_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "asmr-view.pid"
            args = SimpleNamespace(host="127.0.0.1", port=8890)
            with (
                mock.patch.object(VIEWER, "PID_PATH", pid_path),
                mock.patch.object(VIEWER, "build_cover_cache"),
                mock.patch.object(
                    VIEWER,
                    "ThreadingHTTPServer",
                    side_effect=OSError("address in use"),
                ),
            ):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = VIEWER.cmd_serve_foreground(args)

            self.assertEqual(result, 1)
            self.assertFalse(pid_path.exists())

    def test_stop_refuses_to_signal_non_viewer_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "asmr-view.pid"
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
            args = SimpleNamespace()
            with (
                mock.patch.object(VIEWER, "PID_PATH", pid_path),
                mock.patch.object(VIEWER, "_pid_is_alive", return_value=True),
                mock.patch.object(VIEWER, "_is_viewer_process", return_value=False),
                mock.patch.object(VIEWER.os, "kill") as kill,
            ):
                with redirect_stdout(io.StringIO()):
                    result = VIEWER.cmd_stop(args)

            self.assertEqual(result, 1)
            kill.assert_not_called()
            self.assertFalse(pid_path.exists())

    def test_start_returns_failure_when_child_exits_before_health(self):
        child = mock.Mock(pid=43210, returncode=1)
        child.poll.return_value = 1
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            args = SimpleNamespace(host="127.0.0.1", port=8890)
            with (
                mock.patch.object(VIEWER, "PID_PATH", base / "asmr-view.pid"),
                mock.patch.object(VIEWER, "START_LOCK_PATH", base / "start.lock"),
                mock.patch.object(VIEWER, "LOG_PATH", base / "asmr-view.log"),
                mock.patch.object(VIEWER.subprocess, "Popen", return_value=child),
                mock.patch.object(VIEWER.time, "sleep"),
            ):
                with redirect_stdout(io.StringIO()):
                    result = VIEWER.cmd_start(args)

            self.assertEqual(result, 1)


class DashboardJobRobustnessTests(unittest.TestCase):
    def setUp(self):
        with DASHBOARD.actions_lock:
            self.original_actions = dict(DASHBOARD.actions)
            DASHBOARD.actions.clear()
            DASHBOARD.running_processes.clear()
            DASHBOARD.cancelled_actions.clear()

    def tearDown(self):
        DASHBOARD.cancel_running_actions("test cleanup")
        with DASHBOARD.actions_lock:
            DASHBOARD.actions.clear()
            DASHBOARD.actions.update(self.original_actions)
            DASHBOARD.running_processes.clear()
            DASHBOARD.cancelled_actions.clear()

    def test_capture_retains_only_bounded_tail(self):
        result = DASHBOARD.run_capture(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('a' * 50000 + 'TAIL')",
            ],
            timeout=5,
        )

        self.assertTrue(result["ok"], result)
        self.assertLessEqual(
            len(result["output"].encode("utf-8")),
            DASHBOARD.MAX_ACTION_OUTPUT_BYTES,
        )
        self.assertTrue(result["output"].endswith("TAIL"))

    def test_capture_timeout_terminates_process_group(self):
        started = time.monotonic()
        result = DASHBOARD.run_capture(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.05,
        )

        self.assertEqual(result["exit_code"], 124)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertLess(time.monotonic() - started, 5)

    def test_loaded_running_action_is_marked_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            actions_path = Path(tmp) / "actions.json"
            with mock.patch.object(DASHBOARD, "ACTIONS_PATH", actions_path):
                with DASHBOARD.actions_lock:
                    DASHBOARD.actions["abc123"] = {
                        "id": "abc123",
                        "name": "reindex",
                        "argv": ["reindex"],
                        "status": "running",
                        "started_at": 1,
                        "finished_at": None,
                        "exit_code": None,
                        "output": "",
                        "pid": 123,
                    }
                    DASHBOARD._persist_actions_locked()
                    DASHBOARD.actions.clear()

                DASHBOARD._load_actions()

                record = DASHBOARD.actions["abc123"]
                self.assertEqual(record["status"], "interrupted")
                self.assertEqual(record["exit_code"], 130)
                self.assertNotIn("pid", record)
                persisted = json.loads(actions_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted["actions"][0]["status"],
                    "interrupted",
                )
                self.assertNotIn("pid", persisted["actions"][0])

    def test_queue_rejects_overlapping_action(self):
        with DASHBOARD.actions_lock:
            DASHBOARD.actions["running"] = {
                "id": "running",
                "name": "reindex",
                "argv": ["reindex"],
                "status": "running",
                "started_at": 1,
                "finished_at": None,
                "exit_code": None,
                "output": "",
            }

        with self.assertRaises(DASHBOARD.ActionConflictError) as caught:
            DASHBOARD.queue_action("download", ["download", "RJ00000001"])

        self.assertEqual(caught.exception.record["id"], "running")

    def test_completed_action_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with (
                mock.patch.object(DASHBOARD, "ACTIONS_PATH", base / "actions.json"),
                mock.patch.object(DASHBOARD, "SUMMARY_CACHE", base / "summary.json"),
                mock.patch.object(DASHBOARD, "action_progress", return_value={}),
            ):
                queued = DASHBOARD.queue_action(
                    "test",
                    [sys.executable, "-c", "print('complete')"],
                    timeout=5,
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with DASHBOARD.actions_lock:
                        status = DASHBOARD.actions[queued["id"]]["status"]
                    if status != "running":
                        break
                    time.sleep(0.01)

                self.assertEqual(status, "done")
                payload = json.loads(
                    DASHBOARD.ACTIONS_PATH.read_text(encoding="utf-8")
                )
                persisted = {
                    record["id"]: record
                    for record in payload["actions"]
                }
                self.assertEqual(persisted[queued["id"]]["status"], "done")
                self.assertIn("complete", persisted[queued["id"]]["output"])

    def test_pruning_bounds_completed_action_history(self):
        with DASHBOARD.actions_lock:
            for index in range(DASHBOARD.MAX_ACTION_RECORDS + 5):
                action_id = f"done-{index}"
                DASHBOARD.actions[action_id] = {
                    "id": action_id,
                    "name": "test",
                    "argv": [],
                    "status": "done",
                    "started_at": index,
                    "finished_at": index,
                    "exit_code": 0,
                    "output": "",
                }
            DASHBOARD._prune_actions_locked()

            self.assertEqual(
                len(DASHBOARD.actions),
                DASHBOARD.MAX_ACTION_RECORDS,
            )
            self.assertNotIn("done-0", DASHBOARD.actions)
            self.assertIn(
                f"done-{DASHBOARD.MAX_ACTION_RECORDS + 4}",
                DASHBOARD.actions,
            )


if __name__ == "__main__":
    unittest.main()
