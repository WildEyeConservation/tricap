"""Focused tests for Sony capture and host-transfer format configuration."""

import importlib
import sys
import types
import unittest
from unittest.mock import Mock


def _import_sony_camera_module():
    """Import the camera handler without requiring the on-device native SDK."""
    for module_name in (
            "exiftool", "numpy", "rawpy", "scipy", "scipy.interpolate",
            "PIL", "PIL.Image", "sonySDKWrapper"):
        if module_name not in sys.modules:
            sys.modules[module_name] = types.ModuleType(module_name)

    sys.modules["exiftool"].ExifToolHelper = object
    sys.modules["scipy"].interpolate = sys.modules["scipy.interpolate"]
    sys.modules["PIL"].Image = sys.modules["PIL.Image"]
    return importlib.import_module("sensors.sonySDK_cam")


class SonyImageFormatTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.module = _import_sony_camera_module()

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

    def test_pc_transfer_failure_is_not_silently_ignored(self):
        self.camera._sonyCamera.setPCFileSaveType.return_value = False

        with self.assertRaisesRegex(RuntimeError, "PC transfer format"):
            self.camera.set_image_format("RAW")


if __name__ == "__main__":
    unittest.main()
