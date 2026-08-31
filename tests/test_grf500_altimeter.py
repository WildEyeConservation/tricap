"""Focused tests for the production GRF-500 altimeter."""

import unittest
from unittest.mock import Mock, patch

from sensors.grf500_altimeter import Grf500Altimeter


class Grf500AltimeterTests(unittest.TestCase):

    @patch.object(Grf500Altimeter, "_configure")
    @patch.object(Grf500Altimeter, "_get_correct_port_name", return_value="/dev/grf500")
    @patch("sensors.grf500_altimeter.serial.Serial")
    def test_settings_are_independent(
            self, serial_mock, _port_mock, _configure_mock):
        settings = {
            "measurement_timeout": "2",
            "num_frames_to_avg": "4",
        }

        altimeter = Grf500Altimeter(settings)
        altimeter.config.measurement_timeout = 7

        self.assertEqual(settings["measurement_timeout"], "7")
        self.assertEqual(settings["num_frames_to_avg"], "4")
        serial_mock.assert_called_once_with(
            port="/dev/grf500",
            baudrate=115200,
            timeout=0.2,
            write_timeout=1.0,
        )

    def test_frame_round_trip_validates_crc(self):
        altimeter = Grf500Altimeter.__new__(Grf500Altimeter)
        frame = altimeter._build(44, data=b"distance")
        buffer = bytearray(frame)

        packets = altimeter._extract(buffer)

        self.assertEqual(packets, [(44, b"distance", True)])
        self.assertEqual(buffer, bytearray())

    def test_distance_conversion_handles_lost_signal(self):
        self.assertEqual(Grf500Altimeter._distance_metres(22), 2.2)
        self.assertIsNone(Grf500Altimeter._distance_metres(-10))
        self.assertIsNone(Grf500Altimeter._distance_metres(-1))


if __name__ == "__main__":
    unittest.main()
