"""Tests for coordinated system-clock validation and application."""

import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, call, patch

from support.system_clock import (
    ClockSync,
    disable_ntp,
    set_system_time,
    set_system_timezone,
    timezone_name_for_offset,
    validate_phone_time,
)


class SystemClockTests(unittest.TestCase):

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

    @patch("support.system_clock.time.time",
           side_effect=[1785484799.0, 1785484800.125])
    @patch("support.system_clock.subprocess.run")
    def test_sets_system_clock_and_rtc(self, run_mock, _time_mock):
        result = set_system_time(1785484800.123)

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

    @patch("support.system_clock.time.time",
           side_effect=[1785484799.0, 1785484800.125])
    @patch("support.system_clock.subprocess.run")
    def test_rtc_failure_does_not_fail_system_sync(
            self, run_mock, _time_mock):
        run_mock.side_effect = [
            None,
            subprocess.CalledProcessError(1, ["hwclock"]),
        ]

        result = set_system_time(1785484800.123)

        self.assertFalse(result["rtcSynced"])

    def test_browser_offsets_map_to_posix_etc_zones(self):
        self.assertEqual(timezone_name_for_offset(-120), "Etc/GMT-2")   # UTC+2
        self.assertEqual(timezone_name_for_offset(300), "Etc/GMT+5")    # UTC-5
        self.assertEqual(timezone_name_for_offset(0), "Etc/UTC")
        self.assertIsNone(timezone_name_for_offset(-330))               # UTC+5:30
        self.assertIsNone(timezone_name_for_offset(None))

    @patch("support.system_clock.subprocess.run")
    def test_sets_system_timezone_for_whole_hour_offsets(self, run_mock):
        self.assertEqual(set_system_timezone(-120), "Etc/GMT-2")

        run_mock.assert_called_once_with(
            ["timedatectl", "set-timezone", "Etc/GMT-2"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("support.system_clock.subprocess.run")
    def test_unrepresentable_or_failed_timezone_is_skipped(self, run_mock):
        self.assertIsNone(set_system_timezone(-330))
        run_mock.assert_not_called()

        run_mock.side_effect = subprocess.CalledProcessError(1, ["timedatectl"])
        self.assertIsNone(set_system_timezone(-120))

    @patch("support.system_clock.subprocess.run")
    def test_disable_ntp_failure_is_nonfatal(self, run_mock):
        run_mock.side_effect = subprocess.CalledProcessError(
            1, ["timedatectl", "set-ntp", "false"])

        self.assertFalse(disable_ntp())

        run_mock.assert_called_once_with(
            ["timedatectl", "set-ntp", "false"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("support.system_clock.set_system_timezone",
           return_value="Etc/GMT-2")
    @patch("support.system_clock.set_system_time")
    def test_phone_after_gps_only_sets_timezone(
            self, set_time_mock, set_timezone_mock):
        set_time_mock.return_value = {
            "previousEpochMs": 1,
            "deviceEpochMs": 2,
            "adjustmentMs": 1,
            "rtcSynced": True,
        }
        clock = ClockSync()
        clock.sync_from_gps(datetime(2026, 9, 2, tzinfo=timezone.utc))
        set_time_mock.reset_mock()

        result = clock.sync_from_phone(1785484800123, -120)

        set_time_mock.assert_not_called()
        set_timezone_mock.assert_called_once_with(-120)
        self.assertEqual(result["source"], "gps")
        self.assertFalse(result["timeApplied"])
        self.assertEqual(result["adjustmentMs"], 0)
        self.assertEqual(result["timezone"], "Etc/GMT-2")

    @patch("support.system_clock.set_system_time")
    def test_gps_sync_sets_time_and_marks_source(self, set_time_mock):
        set_time_mock.return_value = {
            "previousEpochMs": 1,
            "deviceEpochMs": 2,
            "adjustmentMs": 1,
            "rtcSynced": True,
        }
        on_synced = Mock(return_value=(2, ["camera three failed"]))
        clock = ClockSync(on_synced=on_synced)
        gps_time = datetime(
            2026, 9, 2, 12, 30, 15, 500000, tzinfo=timezone.utc)

        result = clock.sync_from_gps(gps_time)

        set_time_mock.assert_called_once_with(gps_time.timestamp())
        on_synced.assert_called_once_with("gps")
        self.assertEqual(clock.source, "gps")
        self.assertEqual(result["source"], "gps")
        self.assertTrue(result["timeApplied"])
        self.assertEqual(result["camerasSynced"], 2)
        self.assertEqual(result["cameraErrors"], ["camera three failed"])


if __name__ == "__main__":
    unittest.main()
