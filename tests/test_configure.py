"""Tests for the layered SkySeeker configuration."""

import configparser
import tempfile
import unittest
from pathlib import Path

from config import (
    DEFAULT_CONFIG_FP,
    SONY_IMAGE_FORMAT_CAMERA_SETTING,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)
from support.configure import TricapConfig, TricapConfigError

DEFAULTS_TEXT = """\
[Camera]
sony_image_format = Default   ; Default | RAW | JPEG

[Misc]
image_capture_interval = 3    ; float >= 0.5

[Ui]
status_poll_ms = 1000
sensors_poll_ms = 2000
sensors_poll_capturing_ms = 5000
background_poll_ms = 15000
uplink_poll_ms = 10000
netbird_poll_ms = 20000
backup_poll_ms = 2000
verify_poll_ms = 1000
heartbeat_ms = 5000
"""

LEGACY_OVERRIDES_TEXT = """\
[Camera]
sony_image_format = Camera setting
obsolete_camera_setting = value

[Altimeter]
measurement_timeout = 2
num_frames_to_avg = 2

[Misc]
image_capture_interval = 4
session_description = Test

[Web]
refresh_rate = 1000

[SMS]
timeout = 1
"""


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.defaults_path = root / "default.cfg"
        self.defaults_path.write_text(DEFAULTS_TEXT, encoding="utf-8")
        self.config_path = root / "initial.cfg"

    def tearDown(self):
        self.temp_dir.cleanup()

    def load(self):
        return TricapConfig(str(self.config_path), str(self.defaults_path))

    def saved(self):
        parser = configparser.ConfigParser()
        parser.read(self.config_path)
        return parser

    def test_overrides_layer_over_defaults(self):
        self.config_path.write_text("[Misc]\nimage_capture_interval = 4\n", encoding="utf-8")

        config = self.load()

        self.assertEqual(config.get("image_capture_interval", "Misc", "float"), 4.0)
        self.assertEqual(
            config.get_section_dict("Camera"),
            {SONY_IMAGE_FORMAT_CONFIG_KEY: SONY_IMAGE_FORMAT_CAMERA_SETTING},
        )

    def test_inline_comments_are_not_part_of_the_value(self):
        config = self.load()

        self.assertEqual(config.get(SONY_IMAGE_FORMAT_CONFIG_KEY, "Camera"), "Default")
        self.assertEqual(config.get("image_capture_interval", "Misc", "float"), 3.0)

    def test_missing_initial_cfg_runs_on_defaults_and_is_created_on_save(self):
        config = self.load()

        self.assertTrue(config.is_ready())
        config.save_to_file()

        self.assertEqual(dict(self.saved().items("Misc")), {"image_capture_interval": "3"})

    def test_retires_legacy_settings_from_overrides(self):
        self.config_path.write_text(LEGACY_OVERRIDES_TEXT, encoding="utf-8")

        config = self.load()
        self.assertEqual(
            config.get_section_dict("Camera"),
            {SONY_IMAGE_FORMAT_CONFIG_KEY: SONY_IMAGE_FORMAT_CAMERA_SETTING},
        )
        self.assertEqual(config.get("image_capture_interval", "Misc", "int"), 4)
        config.save_to_file()

        saved = self.saved()
        self.assertEqual(sorted(saved.sections()), ["Camera", "Misc"])
        self.assertEqual(
            dict(saved.items("Camera")),
            {SONY_IMAGE_FORMAT_CONFIG_KEY: SONY_IMAGE_FORMAT_CAMERA_SETTING},
        )
        self.assertEqual(dict(saved.items("Misc")), {"image_capture_interval": "4"})

    def test_save_keeps_the_rigs_other_overrides(self):
        self.config_path.write_text(
            "[Misc]\nimage_capture_interval = 2\n\n[Ui]\nstatus_poll_ms = 2000\n", encoding="utf-8"
        )
        config = self.load()
        camera_settings = config.get_section_dict("Camera")
        camera_settings[SONY_IMAGE_FORMAT_CONFIG_KEY] = "JPEG"
        config.set_section(camera_settings, "Camera")
        config.save_to_file()

        saved = self.saved()
        self.assertEqual(saved["Camera"][SONY_IMAGE_FORMAT_CONFIG_KEY], "JPEG")
        self.assertEqual(saved["Misc"]["image_capture_interval"], "2")
        self.assertEqual(saved["Ui"]["status_poll_ms"], "2000")
        self.assertEqual(self.load().get(SONY_IMAGE_FORMAT_CONFIG_KEY, "Camera"), "JPEG")

    def test_rejects_unknown_setting(self):
        config = self.load()
        camera_settings = config.get_section_dict("Camera")
        camera_settings["unknown"] = "value"

        with self.assertRaises(TricapConfigError):
            config.set_section(camera_settings, "Camera")

    def test_ui_settings_are_validated_integers(self):
        self.config_path.write_text("[Ui]\nstatus_poll_ms = 500\n", encoding="utf-8")

        settings = self.load().ui_settings()

        self.assertEqual(settings["status_poll_ms"], 500)
        self.assertEqual(settings["heartbeat_ms"], 5000)
        self.assertEqual(len(settings), len(TricapConfig.UI_MINIMUMS_MS))

    def test_ui_settings_below_minimum_are_refused(self):
        self.config_path.write_text("[Ui]\nstatus_poll_ms = 100\n", encoding="utf-8")

        with self.assertRaises(TricapConfigError):
            self.load().ui_settings()

    def test_shipped_default_cfg_is_complete(self):
        config = TricapConfig(str(self.config_path), DEFAULT_CONFIG_FP)

        self.assertEqual(config.get(SONY_IMAGE_FORMAT_CONFIG_KEY, "Camera"), "Default")
        self.assertGreaterEqual(float(config.get("image_capture_interval", "Misc", "float")), 0.5)
        self.assertEqual(
            config.ui_settings(),
            {
                "status_poll_ms": 1000,
                "sensors_poll_ms": 2000,
                "sensors_poll_capturing_ms": 5000,
                "background_poll_ms": 15000,
                "uplink_poll_ms": 10000,
                "netbird_poll_ms": 20000,
                "backup_poll_ms": 2000,
                "verify_poll_ms": 1000,
                "heartbeat_ms": 5000,
            },
        )


if __name__ == "__main__":
    unittest.main()
