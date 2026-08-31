"""Focused tests for storage backup verification."""

import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
