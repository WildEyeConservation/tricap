"""Tests for phone-supplied clock validation and application."""

import subprocess
import unittest
from unittest.mock import call, patch

from support.phone_time import (
    set_system_time_from_phone,
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


if __name__ == "__main__":
    unittest.main()
