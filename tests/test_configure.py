"""Tests for the production SkySeeker configuration."""

import tempfile
import unittest
from pathlib import Path

from config import (
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)
from support.configure import TricapConfig, TricapConfigError


CONFIG_TEXT = """\
[Camera]
obsolete_camera_setting = value

[Altimeter]
measurement_timeout = 2
num_frames_to_avg = 2

[Misc]
image_capture_interval = 3
session_description = Test

[Web]
alti_required = retired-altimeter
cams_required = retired-camera
refresh_rate = 1000

[SMS]
timeout = 1
"""


class ConfigureTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "initial.cfg"
        self.config_path.write_text(CONFIG_TEXT, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_removes_retired_hardware_settings(self):
        config = TricapConfig(str(self.config_path))

        self.assertEqual(
            config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER),
            {SONY_IMAGE_FORMAT_CONFIG_KEY: SONY_IMAGE_FORMAT_CAMERA_SETTING},
        )
        web_settings = config.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
        self.assertEqual(web_settings, {"refresh_rate": "1000"})

    def test_saves_supported_sony_setting(self):
        config = TricapConfig(str(self.config_path))
        camera_settings = config.get_section_dict(
            TricapConfig.CAMERA_SECTION_HEADER
        )
        camera_settings[SONY_IMAGE_FORMAT_CONFIG_KEY] = "JPEG"
        config.set_section(camera_settings, TricapConfig.CAMERA_SECTION_HEADER)
        config.save_to_file()

        saved = TricapConfig(str(self.config_path))

        self.assertEqual(
            saved.get(
                SONY_IMAGE_FORMAT_CONFIG_KEY,
                TricapConfig.CAMERA_SECTION_HEADER,
            ),
            "JPEG",
        )

    def test_rejects_unknown_setting(self):
        config = TricapConfig(str(self.config_path))
        camera_settings = config.get_section_dict(
            TricapConfig.CAMERA_SECTION_HEADER
        )
        camera_settings["unknown"] = "value"

        with self.assertRaises(TricapConfigError):
            config.set_section(
                camera_settings,
                TricapConfig.CAMERA_SECTION_HEADER,
            )


if __name__ == "__main__":
    unittest.main()
