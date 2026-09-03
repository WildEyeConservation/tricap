"""Tests for retrying Sony USB discovery during application startup."""

import unittest
from unittest.mock import Mock, patch

from sensors.sony_discovery import discover_sony_cameras


class SonyDiscoveryTests(unittest.TestCase):
    @patch("sensors.sony_discovery.time.sleep")
    def test_retries_zero_camera_snapshots_with_fresh_sdk_instances(self, sleep_mock):
        empty_one = Mock()
        empty_one.getNumCameras.return_value = 0
        empty_two = Mock()
        empty_two.getNumCameras.return_value = 0
        ready_one = Mock()
        ready_one.getNumCameras.return_value = 3
        ready_two = Mock()
        ready_two.getNumCameras.return_value = 3
        factory = Mock(side_effect=[empty_one, empty_two, ready_one, ready_two])

        sdk, count = discover_sony_cameras(factory, attempts=4, interval=0.25, stable_results=2)

        self.assertIs(sdk, ready_two)
        self.assertEqual(count, 3)
        self.assertEqual(factory.call_count, 4)
        self.assertEqual(sleep_mock.call_count, 3)

    @patch("sensors.sony_discovery.time.sleep")
    def test_retries_transient_sdk_errors(self, sleep_mock):
        ready_one = Mock()
        ready_one.getNumCameras.return_value = 2
        ready_two = Mock()
        ready_two.getNumCameras.return_value = 2
        factory = Mock(side_effect=[OSError("USB not ready"), ready_one, ready_two])

        sdk, count = discover_sony_cameras(factory, attempts=3, interval=0, stable_results=2)

        self.assertIs(sdk, ready_two)
        self.assertEqual(count, 2)
        self.assertEqual(sleep_mock.call_count, 2)

    @patch("sensors.sony_discovery.time.sleep")
    def test_raises_after_all_attempts_are_empty(self, sleep_mock):
        empty = Mock()
        empty.getNumCameras.return_value = 0

        with self.assertRaisesRegex(RuntimeError, "No Sony cameras"):
            discover_sony_cameras(lambda: empty, attempts=3, interval=0)

        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
