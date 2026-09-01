"""Focused tests for u-blox GPS status processing."""

import unittest
from datetime import datetime, time, timezone
from types import SimpleNamespace

from serial_comms.SerialProcess import SerialProcess


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

    def test_completed_gsv_cycle_updates_satellite_and_snr_status(self):
        self.gps.process_gsv(SimpleNamespace(
            talker="GP",
            numMsg="1",
            msgNum="1",
            numSV="3",
            signalID="0",
            cno_01="10",
            cno_02="20",
            cno_03="30",
            cno_04="",
        ))

        self.assertEqual(self.gps.total_visible, 3)
        self.assertEqual(self.gps.visible_by_talker, {"GP": 3})
        self.assertEqual(self.gps.snr_min, 10)
        self.assertEqual(self.gps.snr_avg, 20.0)
        self.assertEqual(self.gps.snr_max, 30)


if __name__ == "__main__":
    unittest.main()
