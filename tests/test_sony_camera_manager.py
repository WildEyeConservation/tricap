"""Tests for the Sony-only production camera manager."""

import unittest
from threading import Lock
from unittest.mock import ANY, Mock, call, patch

from sensors.cam_manager import TriCapCamsManager
from config import SONY_TEMPFS_MOUNT_POINT


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
            [item.args[2] for item in camera_mock.call_args_list],
            [1, 2],
        )
        self.assertEqual(
            camera_mock.call_args_list,
            [
                call(SONY_TEMPFS_MOUNT_POINT, sdk, 1, ANY, "Default"),
                call(SONY_TEMPFS_MOUNT_POINT, sdk, 2, ANY, "Default"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
