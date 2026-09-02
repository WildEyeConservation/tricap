"""Tests for the Sony-only production camera manager."""

import time
import unittest
from threading import Lock
from unittest.mock import ANY, Mock, call, patch

from sensors.cam_manager import TriCapCamsManager
from config import CAM_MANAGER_STATES, CAMERA_STATES


class SonyCameraManagerTests(unittest.TestCase):

    @patch.object(TriCapCamsManager, "mount_disk", return_value=True)
    @patch("sensors.cam_manager.subprocess.run")
    @patch("sensors.cam_manager.SonyCamera")
    @patch("sensors.cam_manager.discover_sony_cameras")
    def test_initialises_every_discovered_sony_camera(
            self, discover_mock, camera_mock, _run_mock, _mount_mock):
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
    def test_returns_to_stopped_once_capture_threads_finish(
            self, discover_mock, camera_mock, _run_mock, _mount_mock):
        discover_mock.return_value = (Mock(), 1)
        camera = Mock(serial_num="one", state=CAMERA_STATES.CAPTURING)
        camera_mock.return_value = camera

        manager = TriCapCamsManager(
            {"image_capture_interval": "3"},
            {"sony_image_format": "Default"},
            Lock(),
        )

        # The mocked capture target returns immediately, so the manager must
        # reset itself without any external periodic caller.
        manager.start_capturing()

        deadline = time.monotonic() + 2
        while manager.state != CAM_MANAGER_STATES.STOPPED and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(manager.state, CAM_MANAGER_STATES.STOPPED)
        self.assertEqual(camera.state, CAMERA_STATES.INITIALISED)
        camera.reset_session_counters.assert_called_once_with()
        camera.capture_and_copy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
