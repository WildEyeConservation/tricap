"""Focused tests for Sony capture and host-transfer format configuration."""

import unittest
from unittest.mock import Mock, patch

from sensors import sonySDK_cam


class SonyImageFormatTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.module = sonySDK_cam

    def setUp(self):
        self.camera = self.module.sonySDKcam.__new__(
            self.module.sonySDKcam
        )
        self.camera._cameraID = 2
        self.camera._sonyCamera = Mock()
        self.camera._sonyCamera.setCameraFileSaveType.return_value = True
        self.camera._sonyCamera.setPCFileSaveType.return_value = True

    def test_jpeg_sets_camera_and_pc_transfer_formats(self):
        self.camera.set_image_format("JPEG")

        self.camera._sonyCamera.setCameraFileSaveType.assert_called_once_with(
            1, 2
        )
        self.camera._sonyCamera.setPCFileSaveType.assert_called_once_with(1, 2)

    def test_raw_sets_camera_and_pc_transfer_formats(self):
        self.camera.set_image_format("RAW")

        self.camera._sonyCamera.setCameraFileSaveType.assert_called_once_with(
            2, 2
        )
        self.camera._sonyCamera.setPCFileSaveType.assert_called_once_with(2, 2)

    def test_default_preserves_camera_format_and_transfers_all_outputs(self):
        self.camera.set_image_format("Default")

        self.camera._sonyCamera.setCameraFileSaveType.assert_not_called()
        self.camera._sonyCamera.setPCFileSaveType.assert_called_once_with(0, 2)

    def test_read_only_pc_transfer_format_does_not_reject_camera(self):
        self.camera._sonyCamera.setPCFileSaveType.return_value = False

        with self.assertLogs(
                self.camera._logger.name, level="WARNING") as captured:
            self.camera.set_image_format("RAW")

        self.assertIn("not writable", "\n".join(captured.output))

    @patch("sensors.sonySDK_cam.subprocess.run")
    @patch("sensors.sonySDK_cam.os.path.ismount")
    @patch("sensors.sonySDK_cam.os.makedirs")
    def test_existing_transfer_tmpfs_is_not_mounted_again(
            self, makedirs_mock, ismount_mock, run_mock):
        ismount_mock.return_value = True

        self.camera._ensure_memory_fs("/transfer")

        makedirs_mock.assert_called_once_with("/transfer", exist_ok=True)
        run_mock.assert_not_called()

    @patch("sensors.sonySDK_cam.sleep")
    def test_camera_connection_retries_are_bounded(self, sleep_mock):
        self.camera.CONNECT_ATTEMPTS = 2
        self.camera.CONNECT_POLLS_PER_ATTEMPT = 2
        self.camera._sonyCamera.isConnected.return_value = False

        with self.assertRaisesRegex(RuntimeError, "connection timed out"):
            self.camera._connect_camera()

        self.assertEqual(self.camera._sonyCamera.connectCamera.call_count, 2)
        self.assertEqual(self.camera._sonyCamera.disconnect.call_count, 2)
        self.assertEqual(sleep_mock.call_count, 4)


if __name__ == "__main__":
    unittest.main()
