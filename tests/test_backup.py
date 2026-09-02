"""Focused tests for storage backup verification."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sensors.cam_manager import TriCapCamsManager
from support.backup import BackupStatus, RsyncManager


class BackupTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.source.mkdir()
        self.destination.mkdir()
        self.manager = RsyncManager()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_pair(self, name: str, source: bytes, destination: bytes) -> None:
        source_path = self.source / name
        destination_path = self.destination / name
        source_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(source)
        destination_path.write_bytes(destination)
        timestamp_ns = source_path.stat().st_mtime_ns
        os.utime(destination_path, ns=(timestamp_ns, timestamp_ns))

    def test_camera_raw_file_is_verified_like_every_other_file(self):
        self._write_pair("capture/cam1.ARW", b"camera raw data", b"camera raw data")

        result = self.manager.list_matched_files_sampled(
            str(self.source),
            str(self.destination),
            workers=1,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], ["capture/cam1.ARW"])

    def test_changed_camera_raw_file_is_not_safe_to_delete(self):
        self._write_pair("capture/cam1.ARW", b"camera raw data", b"camera bad data")

        result = self.manager.list_matched_files_sampled(
            str(self.source),
            str(self.destination),
            workers=1,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["checked"], 1)

    def test_backup_status_only_exposes_copy_and_verification_state(self):
        status = BackupStatus().__dict__

        self.assertEqual(
            set(status),
            {
                "running", "phase", "message", "started_at", "finished_at",
                "total_files", "total_bytes", "files_done", "bytes_copied", "current_file",
                "verify_mode", "verified", "verify_missing", "verify_changed",
                "verify_extra", "verify_samples", "dst_files", "dst_bytes",
                "ready_to_delete", "planned_bytes", "planned_files",
                "elapsed_seconds", "copy_seconds", "throughput_mib_s",
            },
        )

    def test_unmount_callback_is_optional(self):
        calls = []
        manager = RsyncManager(unmount=lambda: calls.append(True) or True)

        self.assertTrue(manager._unmount_storage())
        self.assertEqual(calls, [True])

    def test_refresh_usage_callback_is_optional_and_failure_tolerant(self):
        self.manager._refresh_storage_usage()

        calls = []
        manager = RsyncManager(refresh_usage=lambda: calls.append(True))
        manager._refresh_storage_usage()
        self.assertEqual(calls, [True])

        def explode():
            raise OSError("drive gone")
        RsyncManager(refresh_usage=explode)._refresh_storage_usage()
        self.assertTrue(RsyncManager()._unmount_storage())

    def test_prune_keeps_root_and_lost_and_found(self):
        (self.source / "lost+found").mkdir()
        (self.source / "2026_09_01" / "cam").mkdir(parents=True)

        self.manager.delete_matched_files(str(self.source), [])

        self.assertTrue((self.source / "lost+found").is_dir())
        self.assertTrue(self.source.is_dir())
        self.assertFalse((self.source / "2026_09_01").exists())

    @patch("support.backup.os.path.ismount", return_value=False)
    def test_start_refuses_unmounted_destination(self, _ismount):
        self.destination.rmdir()
        result = self.manager.start(str(self.source), str(self.destination))
        self.assertEqual(result["code"], "destination_not_mounted")
        self.assertFalse(result["success"])
        self.assertFalse(self.destination.exists())

    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.os.path.ismount", return_value=True)
    def test_unmount_refuses_while_external_storage_is_claimed(
        self, _ismount, run
    ):
        manager = TriCapCamsManager.__new__(TriCapCamsManager)
        manager._external_jobs_lock = threading.Lock()
        manager._external_storage_jobs = set()
        manager.claim_external_storage("backup")
        self.assertFalse(manager.unmount_disk())
        run.assert_not_called()

        manager.release_external_storage("backup")
        self.assertTrue(manager.unmount_disk())
        run.assert_called_once()

    @patch("support.backup.time.sleep")
    def test_unmount_retries_are_bounded(self, sleep):
        unmount = Mock(return_value=False)
        manager = RsyncManager(unmount=unmount)
        self.assertFalse(manager._unmount_storage_with_retries())
        self.assertEqual(unmount.call_count, 5)
        self.assertEqual(sleep.call_count, 4)


if __name__ == "__main__":
    unittest.main()
