"""Focused tests for storage backup verification."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from support.backup import RsyncManager


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

    def test_sampled_verification_catches_corruption_in_an_interior_sample(self):
        block_size = 1024 * 1024
        file_size = 5 * block_size
        self._write_pair("capture/cam1.ARW", b"a" * file_size, b"a" * file_size)

        destination_path = self.destination / "capture/cam1.ARW"
        timestamp_ns = (self.source / "capture/cam1.ARW").stat().st_mtime_ns
        # With five blocks and four samples, the first interior sample starts at 2 MiB.
        with destination_path.open("r+b") as destination_file:
            destination_file.seek(2 * block_size + 100)
            destination_file.write(b"corrupt")
        os.utime(destination_path, ns=(timestamp_ns, timestamp_ns))

        result = self.manager.list_matched_files_sampled(str(self.source), str(self.destination), blocks=4, workers=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["checked"], 1)

    def test_sampled_verification_catches_first_and_last_block_corruption(self):
        block_size = 1024 * 1024
        file_size = 3 * block_size

        for name, offset in (("first.ARW", 100), ("last.ARW", file_size - 100)):
            with self.subTest(name=name):
                self._write_pair(name, b"a" * file_size, b"a" * file_size)
                source_path = self.source / name
                destination_path = self.destination / name
                timestamp_ns = source_path.stat().st_mtime_ns
                with destination_path.open("r+b") as destination_file:
                    destination_file.seek(offset)
                    destination_file.write(b"corrupt")
                os.utime(destination_path, ns=(timestamp_ns, timestamp_ns))

        result = self.manager.list_matched_files_sampled(str(self.source), str(self.destination), workers=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["checked"], 2)

    def test_same_size_file_with_different_mtime_is_not_matched(self):
        self._write_pair("capture/cam1.ARW", b"camera raw data", b"camera raw data")
        destination_path = self.destination / "capture/cam1.ARW"
        source_mtime_ns = (self.source / "capture/cam1.ARW").stat().st_mtime_ns
        different_mtime_ns = source_mtime_ns - 20_000_000
        os.utime(destination_path, ns=(different_mtime_ns, different_mtime_ns))

        result = self.manager.list_matched_files_sampled(str(self.source), str(self.destination), workers=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["checked"], 1)

    def test_source_file_missing_on_destination_is_never_matched(self):
        # Verification walks the destination, so a file that was never copied
        # cannot be matched and therefore cannot be deleted from the source.
        source_path = self.source / "capture/cam1.ARW"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"camera raw data")

        result = self.manager.list_matched_files_sampled(str(self.source), str(self.destination), workers=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["checked"], 0)
        self.assertTrue(source_path.is_file())

    def test_delete_matched_files_only_deletes_matches_and_prunes_empty_directories(self):
        (self.source / "lost+found").mkdir()
        self._write_pair("shared/delete.ARW", b"delete", b"delete")
        self._write_pair("shared/keep.ARW", b"keep", b"keep")
        self._write_pair("empty/branch/delete.ARW", b"delete", b"delete")

        result = self.manager.delete_matched_files(
            str(self.source),
            ["shared/delete.ARW", "empty/branch/delete.ARW"],
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted"], 2)
        self.assertFalse((self.source / "shared/delete.ARW").exists())
        self.assertTrue((self.source / "shared/keep.ARW").is_file())
        self.assertTrue((self.source / "shared").is_dir())
        self.assertFalse((self.source / "empty").exists())
        self.assertTrue((self.source / "lost+found").is_dir())
        self.assertTrue(self.source.is_dir())

    @patch("support.backup.time.sleep")
    @patch("support.backup.os.path.ismount", return_value=True)
    def test_backup_worker_failure_releases_claim_and_retries_unmount(self, _ismount, _sleep):
        source_file = self.source / "capture.ARW"
        source_file.write_bytes(b"camera raw data")
        claim_storage = Mock()
        release_storage = Mock()
        refresh_usage = Mock(side_effect=OSError("usage unavailable"))
        unmount = Mock(return_value=False)
        manager = RsyncManager(
            claim_storage=claim_storage,
            release_storage=release_storage,
            refresh_usage=refresh_usage,
            unmount=unmount,
        )

        with (
            patch.object(manager, "_prepare_backup", return_value=True),
            patch.object(manager, "_run_rsync_job", side_effect=RuntimeError("copy failed")),
            patch("support.backup.BACKUP_BENCHMARK_LOG", self.root / "benchmark.csv"),
        ):
            result = manager.start(str(self.source), str(self.destination))
            self.assertTrue(result["success"])
            thread = manager._thread
            assert thread is not None
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        claim_storage.assert_called_once_with("backup")
        release_storage.assert_called_once_with("backup")
        refresh_usage.assert_called_once_with()
        self.assertEqual(unmount.call_count, 5)
        self.assertFalse(manager.status()["running"])
        self.assertTrue(source_file.is_file())

    @patch("support.backup.time.sleep")
    @patch("support.backup.os.path.ismount", return_value=True)
    def test_unmount_callback_failure_still_releases_claim_and_stops_worker(self, _ismount, _sleep):
        source_file = self.source / "capture.ARW"
        source_file.write_bytes(b"camera raw data")
        claim_storage = Mock()
        release_storage = Mock()
        refresh_usage = Mock()
        unmount = Mock(side_effect=OSError("unmount failed"))
        manager = RsyncManager(
            claim_storage=claim_storage,
            release_storage=release_storage,
            refresh_usage=refresh_usage,
            unmount=unmount,
        )

        with (
            patch.object(manager, "_prepare_backup", return_value=True),
            patch.object(manager, "_run_rsync_job"),
            patch("support.backup.BACKUP_BENCHMARK_LOG", self.root / "benchmark.csv"),
        ):
            result = manager.start(str(self.source), str(self.destination))
            self.assertTrue(result["success"])
            thread = manager._thread
            assert thread is not None
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        claim_storage.assert_called_once_with("backup")
        release_storage.assert_called_once_with("backup")
        refresh_usage.assert_called_once_with()
        self.assertEqual(unmount.call_count, 5)
        self.assertFalse(manager.status()["running"])
        self.assertTrue(source_file.is_file())

    @patch("support.backup.os.path.ismount", return_value=False)
    def test_start_verify_and_delete_refuses_unmounted_destination(self, _ismount):
        result = self.manager.start_verify_and_delete(str(self.source), str(self.destination))

        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "destination_not_mounted")

    @patch("support.backup.os.path.ismount", return_value=True)
    def test_start_verify_and_delete_refuses_when_a_job_is_already_running(self, _ismount):
        self.manager._status.running = True

        result = self.manager.start_verify_and_delete(str(self.source), str(self.destination))

        self.assertFalse(result["success"])
        self.assertEqual(result["msg"], "Backup is running")

        self.manager._status.running = False
        self.manager._verify_status.running = True
        result = self.manager.start_verify_and_delete(str(self.source), str(self.destination))

        self.assertFalse(result["success"])
        self.assertEqual(result["msg"], "Verification is already running")

    @patch("support.backup.os.path.ismount", return_value=False)
    def test_start_refuses_unmounted_destination(self, _ismount):
        self.destination.rmdir()
        result = self.manager.start(str(self.source), str(self.destination))
        self.assertEqual(result["code"], "destination_not_mounted")
        self.assertFalse(result["success"])
        self.assertFalse(self.destination.exists())

    @patch("support.backup.time.sleep")
    def test_unmount_retries_are_bounded(self, sleep):
        unmount = Mock(return_value=False)
        manager = RsyncManager(unmount=unmount)
        self.assertFalse(manager._unmount_storage_with_retries())
        self.assertEqual(unmount.call_count, 5)
        self.assertEqual(sleep.call_count, 4)


if __name__ == "__main__":
    unittest.main()
