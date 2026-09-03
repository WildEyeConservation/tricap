"""Tests for the Sony-only production camera manager."""

import tempfile
import threading
import unittest
from pathlib import Path
from threading import Lock
from unittest.mock import ANY, Mock, call, patch

from config import CAM_MANAGER_STATES, CAMERA_STATES
from sensors.cam_manager import TriCapCamsManager


class SonyCameraManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.marker = Path(self.temp_dir.name) / "capture-active"
        marker_patch = patch("sensors.cam_manager.CAPTURE_ACTIVE_MARKER", str(self.marker))
        marker_patch.start()
        self.addCleanup(marker_patch.stop)
        self.real_thread = threading.Thread
        self.created_threads = []

    def _record_thread(self, *args, **kwargs):
        thread = self.real_thread(*args, **kwargs)
        self.created_threads.append(thread)
        return thread

    def _join_created_threads(self):
        for thread in self.created_threads:
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive(), "manager thread did not exit")

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_initialises_every_discovered_sony_camera(self, discover_mock, camera_mock, _run_mock, _mount_mock):
        sdk = Mock()
        discover_mock.return_value = (sdk, 2)
        camera_mock.side_effect = [Mock(serial_num="one"), Mock(serial_num="two")]

        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )

        self.assertEqual(manager.get_num_cams(), 2)
        self.assertEqual(
            [item.args[1] for item in camera_mock.call_args_list],
            [1, 2],
        )
        self.assertEqual(
            camera_mock.call_args_list,
            [
                call(sdk, 1, ANY, "Default"),
                call(sdk, 2, ANY, "Default"),
            ],
        )

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_returns_to_stopped_once_capture_threads_finish(self, discover_mock, camera_mock, _run_mock, _mount_mock):
        discover_mock.return_value = (Mock(), 1)
        capture_started = threading.Event()
        release_capture = threading.Event()

        def capture_target(*_args):
            capture_started.set()
            release_capture.wait()

        camera = Mock(serial_num="one", state=CAMERA_STATES.CAPTURING)
        camera.capture_and_copy.side_effect = capture_target
        camera_mock.return_value = camera
        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )

        with patch("sensors.cam_manager.threading.Thread", side_effect=self._record_thread):
            capture_started_ok = manager.start_capturing()
            capture_target_started = capture_started.wait(timeout=1)
            state_while_capturing = manager.state
            marker_while_capturing = self.marker.exists()
            release_capture.set()
            self._join_created_threads()

        self.assertTrue(capture_started_ok)
        self.assertTrue(capture_target_started)
        self.assertEqual(state_while_capturing, CAM_MANAGER_STATES.STARTED)
        self.assertTrue(marker_while_capturing)
        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)
        self.assertFalse(self.marker.exists())
        self.assertEqual(camera.state, CAMERA_STATES.INITIALISED)
        camera.reset_session_counters.assert_called_once_with()
        camera.capture_and_copy.assert_called_once()

    @patch.object(TriCapCamsManager, "mount_disk", return_value=False)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_refuses_to_capture_when_internal_storage_does_not_mount(
        self, discover_mock, camera_mock, _run_mock, _mount_mock
    ):
        discover_mock.return_value = (Mock(), 1)
        camera = Mock(serial_num="one")
        camera_mock.return_value = camera
        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )
        manager.altimeter = Mock()

        self.assertFalse(manager.start_capturing())

        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)
        camera.capture_and_copy.assert_not_called()
        manager.altimeter.start_measuring.assert_not_called()
        self.assertFalse(self.marker.exists())

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_stop_capturing_signals_threads_and_manager_resets_when_they_exit(
        self, discover_mock, camera_mock, _run_mock, _mount_mock
    ):
        discover_mock.return_value = (Mock(), 1)
        capture_started = threading.Event()
        stop_seen = threading.Event()
        release_capture = threading.Event()

        def capture_target(
            _mount_point,
            _interval,
            _init_start,
            _session_start,
            _serial_number,
            stop_capture,
            _count_lock,
            _index,
            _capture_done,
            _sync_lock,
        ):
            capture_started.set()
            stop_capture.wait()
            stop_seen.set()
            release_capture.wait()

        camera = Mock(serial_num="one", state=CAMERA_STATES.CAPTURING)
        camera.capture_and_copy.side_effect = capture_target
        camera_mock.return_value = camera
        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )

        with patch("sensors.cam_manager.threading.Thread", side_effect=self._record_thread):
            capture_started_ok = manager.start_capturing()
            capture_target_started = capture_started.wait(timeout=1)
            # stop_capturing only signals; the finaliser thread resets the
            # manager once the capture threads have actually exited.
            manager.stop_capturing()
            stop_was_seen = stop_seen.wait(timeout=1)
            state_before_threads_exit = manager.state
            release_capture.set()
            self._join_created_threads()

        self.assertTrue(capture_started_ok)
        self.assertTrue(capture_target_started)
        self.assertTrue(stop_was_seen)
        self.assertEqual(state_before_threads_exit, CAM_MANAGER_STATES.STARTED)
        self.assertTrue(manager._stop_capture.is_set())
        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)
        self.assertFalse(self.marker.exists())
        camera.release.assert_not_called()
        self.assertEqual(manager._external_storage_jobs, set())

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_shutdown_during_capture_is_bounded_and_releases_resources(
        self, discover_mock, camera_mock, _run_mock, _mount_mock
    ):
        discover_mock.return_value = (Mock(), 1)
        capture_started = threading.Event()
        release_capture = threading.Event()

        def capture_target(*_args):
            capture_started.set()
            release_capture.wait()

        camera = Mock(serial_num="one", state=CAMERA_STATES.CAPTURING)
        camera.capture_and_copy.side_effect = capture_target
        camera_mock.return_value = camera
        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )
        manager.altimeter = Mock()

        with patch("sensors.cam_manager.threading.Thread", side_effect=self._record_thread):
            capture_started_ok = manager.start_capturing()
            capture_target_started = capture_started.wait(timeout=1)
            marker_while_capturing = self.marker.exists()
            with patch("sensors.cam_manager.time.monotonic", side_effect=[100.0, 126.0]):
                shutdown_thread = self.real_thread(target=manager.shutdown)
                shutdown_thread.start()
                shutdown_thread.join(timeout=1)
            shutdown_returned = not shutdown_thread.is_alive()
            marker_cleared = not self.marker.exists()
            release_capture.set()
            shutdown_thread.join(timeout=1)
            shutdown_finished = not shutdown_thread.is_alive()
            self._join_created_threads()

        self.assertTrue(capture_started_ok)
        self.assertTrue(capture_target_started)
        self.assertTrue(marker_while_capturing)
        self.assertTrue(shutdown_finished)
        self.assertTrue(shutdown_returned)
        self.assertTrue(manager._stop_capture.is_set())
        self.assertTrue(marker_cleared)
        manager.altimeter.stop_measuring.assert_called_once_with()
        camera.release.assert_called_once_with()
        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_shutdown_when_idle_clears_stale_marker_and_releases_cameras(
        self, discover_mock, camera_mock, _run_mock, _mount_mock
    ):
        discover_mock.return_value = (Mock(), 2)
        cameras = [
            Mock(serial_num="one", state=CAMERA_STATES.INITIALISED),
            Mock(serial_num="two", state=CAMERA_STATES.INITIALISED),
        ]
        camera_mock.side_effect = cameras
        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )
        self.marker.write_text("stale", encoding="utf-8")

        manager.shutdown()

        self.assertFalse(self.marker.exists())
        for camera in cameras:
            camera.release.assert_called_once_with()
        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)

    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.os.path.ismount", return_value=True)
    def test_unmount_refuses_while_external_storage_is_claimed(self, _ismount, run):
        manager = TriCapCamsManager.__new__(TriCapCamsManager)
        manager._external_jobs_lock = threading.Lock()
        manager._external_storage_jobs = set()
        manager.claim_external_storage("backup")

        self.assertFalse(manager.unmount_disk())
        run.assert_not_called()

        manager.release_external_storage("backup")
        self.assertTrue(manager.unmount_disk())
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
