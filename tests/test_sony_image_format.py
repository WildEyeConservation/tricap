"""Focused tests for Sony capture and host-transfer format configuration."""

import unittest
from unittest.mock import Mock, patch

from sensors import sonySDK_cam


class FormatCamera:
    def __init__(self):
        self.camera_format = "existing"
        self.pc_format = "existing"
        self.camera_write_succeeds = True
        self.pc_write_succeeds = True

    def setCameraFileSaveType(self, image_format, camera_id):
        if self.camera_write_succeeds:
            self.camera_format = image_format
        return self.camera_write_succeeds

    def setPCFileSaveType(self, image_format, camera_id):
        if self.pc_write_succeeds:
            self.pc_format = image_format
        return self.pc_write_succeeds


class SonyImageFormatTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.module = sonySDK_cam

    def setUp(self):
        self.camera = self.module.sonySDKcam.__new__(
            self.module.sonySDKcam
        )
        self.camera._cameraID = 2
        self.sdk = FormatCamera()
        self.camera._sonyCamera = self.sdk

    def test_jpeg_sets_camera_and_pc_transfer_formats(self):
        outcome = self.camera.set_image_format("JPEG")

        self.assertIsNone(outcome)
        self.assertEqual(self.sdk.camera_format, 1)
        self.assertEqual(self.sdk.pc_format, 1)

    def test_raw_sets_camera_and_pc_transfer_formats(self):
        outcome = self.camera.set_image_format("RAW")

        self.assertIsNone(outcome)
        self.assertEqual(self.sdk.camera_format, 2)
        self.assertEqual(self.sdk.pc_format, 2)

    def test_default_preserves_camera_format_and_transfers_all_outputs(self):
        outcome = self.camera.set_image_format("Default")

        self.assertIsNone(outcome)
        self.assertEqual(self.sdk.camera_format, "existing")
        self.assertEqual(self.sdk.pc_format, 0)

    def test_read_only_pc_transfer_format_does_not_reject_camera(self):
        self.sdk.pc_write_succeeds = False

        outcome = self.camera.set_image_format("RAW")

        self.assertIsNone(outcome)
        self.assertEqual(self.sdk.camera_format, 2)
        self.assertEqual(self.sdk.pc_format, "existing")

    def test_failed_camera_format_write_preserves_existing_formats(self):
        self.sdk.camera_write_succeeds = False

        with self.assertRaises(RuntimeError):
            self.camera.set_image_format("RAW")

        self.assertEqual(self.sdk.camera_format, "existing")
        self.assertEqual(self.sdk.pc_format, "existing")

    @patch("sensors.sonySDK_cam.sleep")
    def test_camera_connection_retries_are_bounded(self, sleep_mock):
        self.camera.CONNECT_ATTEMPTS = 2
        self.camera.CONNECT_POLLS_PER_ATTEMPT = 2
        sdk = Mock()
        sdk.isConnected.return_value = False
        self.camera._sonyCamera = sdk

        with self.assertRaisesRegex(RuntimeError, "connection timed out"):
            self.camera._connect_camera()

        self.assertEqual(sdk.connectCamera.call_count, 2)
        self.assertEqual(sdk.disconnect.call_count, 2)
        self.assertEqual(sleep_mock.call_count, 4)


if __name__ == "__main__":
    unittest.main()
