"""Focused tests for u-blox GPS status processing."""

import csv
import os
import tempfile
import unittest
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from serial_comms.SerialProcess import SerialProcess
from support import flight_log


class UbloxGpsTests(unittest.TestCase):
    def setUp(self):
        self.gps = SerialProcess()

    def test_valid_pdop_updates_latest_status(self):
        self.gps.process_gsa(SimpleNamespace(PDOP="1.25"))

        self.assertEqual(self.gps.pdop, 1.25)
        self.assertIsNotNone(self.gps.pdopLastUpdate)

    def test_gga_time_is_dated_in_utc_and_survives_midnight(self):
        noon = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        stamped = SerialProcess.gps_datetime(time(12, 30, 15, 500000), noon)
        self.assertEqual(stamped, datetime(2026, 9, 1, 12, 30, 15, 500000, tzinfo=timezone.utc))
        self.assertEqual(stamped.timestamp(), 1788265815.5)  # 2026-09-01T12:30:15.5Z

        just_after_midnight = datetime(2026, 9, 2, 0, 0, 5, tzinfo=timezone.utc)
        fix_before_midnight = SerialProcess.gps_datetime(time(23, 59, 58), just_after_midnight)
        self.assertEqual(fix_before_midnight.date().isoformat(), "2026-09-01")

        just_before_midnight = datetime(2026, 9, 1, 23, 59, 58, tzinfo=timezone.utc)
        fix_after_midnight = SerialProcess.gps_datetime(time(0, 0, 5), just_before_midnight)
        self.assertEqual(fix_after_midnight.date().isoformat(), "2026-09-02")

    def test_save_rmc_calls_first_fix_with_aware_utc_datetime(self):
        on_first_fix = Mock()
        gps = SerialProcess(on_first_fix=on_first_fix)
        msg = SimpleNamespace(
            date=datetime(2026, 9, 2).date(),
            time=time(12, 30, 15, 500000),
            lat="1234.5678",
            lon="01234.5678",
        )

        gps.saveRmc(msg)

        on_first_fix.assert_called_once_with(datetime(2026, 9, 2, 12, 30, 15, 500000, tzinfo=timezone.utc))
        self.assertTrue(gps._firstGps)

    def test_save_rmc_marks_first_fix_without_callback(self):
        msg = SimpleNamespace(
            date=datetime(2026, 9, 2).date(),
            time=time(12, 30, 15),
            lat="1234.5678",
            lon="01234.5678",
        )

        self.gps.saveRmc(msg)

        self.assertTrue(self.gps._firstGps)

    def test_completed_gsv_cycle_updates_satellite_and_snr_status(self):
        self.gps.process_gsv(
            SimpleNamespace(
                talker="GP",
                numMsg="1",
                msgNum="1",
                numSV="3",
                signalID="0",
                cno_01="10",
                cno_02="20",
                cno_03="30",
                cno_04="",
            )
        )

        self.assertEqual(self.gps.total_visible, 3)
        self.assertEqual(self.gps.visible_by_talker, {"GP": 3})
        self.assertEqual(self.gps.snr_min, 10)
        self.assertEqual(self.gps.snr_avg, 20.0)
        self.assertEqual(self.gps.snr_max, 30)

    def test_save_gga_writes_one_formatted_line_to_fallback_directory(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 9, 2, 12, 0, 0)
                return value.replace(tzinfo=tz) if tz is not None else value

        msg = SimpleNamespace(
            time=time(12, 30, 15),
            lat="1234.5678",
            NS="S",
            lon="01234.5678",
            EW="E",
            alt=100.0,
            HDOP="0.9",
            sep="30.0",
            quality=1,
        )
        self.gps._firstGps = True

        with (
            tempfile.TemporaryDirectory() as fallback_dir,
            patch("serial_comms.SerialProcess.os.path.ismount", return_value=False),
            patch("serial_comms.SerialProcess.FALLBACK_TELEMETRY_DIR", fallback_dir),
            patch("serial_comms.SerialProcess.datetime", FixedDateTime),
        ):
            self.gps.saveGga(msg)

            gps_file = os.path.join(fallback_dir, "2026_09_02", "gpsData.csv")
            with open(gps_file) as f:
                lines = f.readlines()
            with open(os.path.join(fallback_dir, "2026_09_02", "flightData.csv"), newline="") as f:
                rows = list(csv.reader(f))

        gps_epoch = datetime(2026, 9, 2, 12, 30, 15, tzinfo=timezone.utc).timestamp()
        pi_epoch = datetime(2026, 9, 2, 12, 0, 0).timestamp()
        self.assertEqual(lines, [f"1,{gps_epoch},{pi_epoch},1234.5678,S,01234.5678,E,100.0,0.9,30.0\n"])
        self.assertEqual(rows[0], list(flight_log.FLIGHT_LOG_HEADER))
        self.assertEqual(rows[1][5:7], ["-1234.5678000", "1234.5678000"])


if __name__ == "__main__":
    unittest.main()
