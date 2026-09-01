"""Focused tests for u-blox GPS status processing."""

import unittest
from types import SimpleNamespace

from serial_comms.SerialProcess import SerialProcess


class UbloxGpsTests(unittest.TestCase):

    def setUp(self):
        self.gps = SerialProcess()

    def test_valid_pdop_updates_latest_status(self):
        self.gps.process_gsa(SimpleNamespace(PDOP="1.25"))

        self.assertEqual(self.gps.pdop, 1.25)
        self.assertIsNotNone(self.gps.pdopLastUpdate)

    def test_timezone_comes_from_configuration(self):
        gps = SerialProcess(timezone="Africa/Johannesburg")

        self.assertEqual(gps._tz.zone, "Africa/Johannesburg")
        self.assertEqual(self.gps._tz.zone, "UTC")

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
