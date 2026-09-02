"""Focused tests for the production GRF-500 altimeter."""

import threading
import unittest
from unittest.mock import Mock, patch

import serial

from config import ALTIMETER_STATE
from sensors.grf500_altimeter import Grf500Altimeter


class Grf500AltimeterTests(unittest.TestCase):

    @patch.object(Grf500Altimeter, "_configure")
    @patch.object(Grf500Altimeter, "_get_correct_port_name", return_value="/dev/grf500")
    @patch("sensors.grf500_altimeter.serial.Serial")
    def test_opens_port_with_lwnx_serial_settings(
            self, serial_mock, _port_mock, _configure_mock):
        altimeter = Grf500Altimeter()

        self.assertFalse(hasattr(altimeter, "config"))
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

    @patch.object(Grf500Altimeter, "_configure")
    @patch.object(Grf500Altimeter, "_get_correct_port_name", return_value="/dev/grf500")
    @patch("sensors.grf500_altimeter.serial.Serial")
    def test_serial_exception_ends_read_with_error_and_unavailable(
            self, _serial_mock, _port_mock, _configure_mock):
        altimeter = Grf500Altimeter()
        altimeter.state = ALTIMETER_STATE.MEASURING
        altimeter._measurement = 12.3
        altimeter.first_return = 12.1
        altimeter.last_return = 12.3
        altimeter._txn = Mock(side_effect=serial.SerialException("USB unplugged"))

        altimeter._read(threading.Event())

        self.assertEqual(altimeter.state, ALTIMETER_STATE.ERROR)
        self.assertFalse(altimeter.available)
        self.assertIsNone(altimeter.measurement)
        self.assertIsNone(altimeter.first_return)
        self.assertIsNone(altimeter.last_return)
        self.assertEqual(altimeter.get_error(), "USB unplugged")


if __name__ == "__main__":
    unittest.main()
