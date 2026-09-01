"""Tests for phone-supplied clock validation and application."""

import subprocess
import unittest
from unittest.mock import call, patch

from support.phone_time import (
    set_system_time_from_phone,
    set_system_timezone_from_phone,
    timezone_name_for_offset,
    validate_phone_time,
)


class PhoneTimeTests(unittest.TestCase):

    def test_validates_epoch_and_timezone_offset(self):
        epoch_ms, timezone_offset = validate_phone_time({
            "epochMs": 1785484800123,
            "timezoneOffsetMinutes": -120,
        })

        self.assertEqual(epoch_ms, 1785484800123)
        self.assertEqual(timezone_offset, -120)

    def test_rejects_missing_or_implausible_epoch(self):
        for payload in ({}, {"epochMs": "1785484800123"},
                        {"epochMs": 0}, {"epochMs": float("nan")}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_phone_time(payload)

    @patch("support.phone_time.time.time",
           side_effect=[1785484799.0, 1785484800.125])
    @patch("support.phone_time.subprocess.run")
    def test_sets_system_clock_and_rtc(self, run_mock, _time_mock):
        result = set_system_time_from_phone(1785484800123)

        self.assertEqual(run_mock.call_args_list, [
            call(
                ["date", "--set", "@1785484800.123"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ),
            call(
                ["hwclock", "--systohc", "--utc"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ),
        ])
        self.assertEqual(result["previousEpochMs"], 1785484799000)
        self.assertEqual(result["deviceEpochMs"], 1785484800125)
        self.assertEqual(result["adjustmentMs"], 1123)
        self.assertTrue(result["rtcSynced"])

    @patch("support.phone_time.time.time",
           side_effect=[1785484799.0, 1785484800.125])
    @patch("support.phone_time.subprocess.run")
    def test_rtc_failure_does_not_fail_system_sync(
            self, run_mock, _time_mock):
        run_mock.side_effect = [
            None,
            subprocess.CalledProcessError(1, ["hwclock"]),
        ]

        result = set_system_time_from_phone(1785484800123)

        self.assertFalse(result["rtcSynced"])

    def test_browser_offsets_map_to_posix_etc_zones(self):
        self.assertEqual(timezone_name_for_offset(-120), "Etc/GMT-2")   # UTC+2
        self.assertEqual(timezone_name_for_offset(300), "Etc/GMT+5")    # UTC-5
        self.assertEqual(timezone_name_for_offset(0), "Etc/UTC")
        self.assertIsNone(timezone_name_for_offset(-330))               # UTC+5:30
        self.assertIsNone(timezone_name_for_offset(None))

    @patch("support.phone_time.subprocess.run")
    def test_sets_system_timezone_for_whole_hour_offsets(self, run_mock):
        self.assertEqual(set_system_timezone_from_phone(-120), "Etc/GMT-2")

        run_mock.assert_called_once_with(
            ["timedatectl", "set-timezone", "Etc/GMT-2"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("support.phone_time.subprocess.run")
    def test_unrepresentable_or_failed_timezone_is_skipped(self, run_mock):
        self.assertIsNone(set_system_timezone_from_phone(-330))
        run_mock.assert_not_called()

        run_mock.side_effect = subprocess.CalledProcessError(1, ["timedatectl"])
        self.assertIsNone(set_system_timezone_from_phone(-120))


if __name__ == "__main__":
    unittest.main()
