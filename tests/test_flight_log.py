"""Tests for the live, user-friendly flight log."""

import csv
import os
import tempfile
import unittest
from datetime import datetime

from support import flight_log


class FlightLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        flight_log.record_laser_altitude(None, at=0.0)

    def _read(self):
        with open(os.path.join(self.tmp.name, flight_log.FLIGHT_LOG_FILENAME), newline="") as f:
            return list(csv.reader(f))

    def test_first_row_gets_friendly_header(self):
        flight_log.append_fix(
            self.tmp.name,
            1,
            datetime(2026, 9, 1, 10, 0, 0, 500000),
            datetime(2026, 9, 1, 10, 0, 1),
            25.7461234,
            "S",
            28.1881234,
            "E",
            1234.5,
            0.9,
            laser_altitude=None,
            use_latest_laser=False,
        )
        rows = self._read()
        self.assertEqual(rows[0], list(flight_log.FLIGHT_LOG_HEADER))
        self.assertEqual(
            rows[0],
            [
                "Fix Quality",
                "GPS Time",
                "GPS Timestamp",
                "System Time",
                "System Timestamp",
                "Latitude",
                "Longitude",
                "GPS Altitude",
                "Laser Altitude",
                "HDOP",
            ],
        )
        gps_time = datetime(2026, 9, 1, 10, 0, 0, 500000)
        system_time = datetime(2026, 9, 1, 10, 0, 1)
        self.assertEqual(
            rows[1],
            [
                "1",
                "2026-09-01 10:00:00.500",
                str(gps_time.timestamp()),
                "2026-09-01 10:00:01.000",
                str(system_time.timestamp()),
                "-25.7461234",
                "28.1881234",
                "1234.50",
                "",
                "0.90",
            ],
        )

    def test_header_written_only_once(self):
        for _ in range(2):
            flight_log.append_fix(
                self.tmp.name,
                1,
                datetime(2026, 9, 1),
                datetime(2026, 9, 1),
                1.0,
                "N",
                2.0,
                "E",
                0.0,
                1.0,
                use_latest_laser=False,
            )
        rows = self._read()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], list(flight_log.FLIGHT_LOG_HEADER))
        self.assertNotEqual(rows[1], list(flight_log.FLIGHT_LOG_HEADER))

    def test_hemispheres_become_signed_coordinates(self):
        self.assertEqual(flight_log.signed_coordinate(25.5, "S", "S"), -25.5)
        self.assertEqual(flight_log.signed_coordinate(25.5, "N", "S"), 25.5)
        self.assertEqual(flight_log.signed_coordinate(-25.5, "N", "S"), 25.5)
        self.assertEqual(flight_log.signed_coordinate(28.2, "W", "W"), -28.2)
        self.assertEqual(flight_log.signed_coordinate("28.2", "e", "W"), 28.2)

    def test_fresh_laser_last_return_is_joined(self):
        flight_log.record_laser_altitude(87.3, at=100.0)
        self.assertEqual(flight_log.latest_laser_altitude(now=101.5), 87.3)
        self.assertIsNone(flight_log.latest_laser_altitude(now=103.0))

    def test_lost_target_clears_laser_altitude(self):
        flight_log.record_laser_altitude(87.3, at=100.0)
        flight_log.record_laser_altitude(None, at=100.5)
        self.assertIsNone(flight_log.latest_laser_altitude(now=100.6))

    def test_append_uses_latest_laser_reading(self):
        flight_log.record_laser_altitude(52.25)
        flight_log.append_fix(
            self.tmp.name, 2, datetime(2026, 9, 1), datetime(2026, 9, 1), 1.0, "N", 2.0, "E", 300.0, 1.1
        )
        self.assertEqual(self._read()[1][8], "52.25")

    def test_missing_values_are_blank_not_errors(self):
        row = flight_log.format_row(
            None, datetime(2026, 9, 1), datetime(2026, 9, 1), 1.0, "N", 2.0, "E", None, "", None
        )
        self.assertEqual(row[0], "")
        self.assertEqual(row[7], "")
        self.assertEqual(row[8], "")
        self.assertEqual(row[9], "")


if __name__ == "__main__":
    unittest.main()
