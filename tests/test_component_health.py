"""Tests for operator-facing optional-component health messages."""

import unittest
from unittest.mock import Mock

from support.component_health import component_health


class ComponentHealthTests(unittest.TestCase):

    def test_camera_startup_error_is_visible_while_retrying(self):
        manager = Mock()
        manager.get_cameras_as_list.return_value = []
        manager.camera_startup_error = "Sony SDK reported zero cameras"
        gps = Mock(isConnected=False)
        gps.hasGps.return_value = False
        altimeter = Mock(available=False, configured_type='altimeter')
        imu = Mock(_BerryIMUversion=99)

        health = component_health(
            manager, gps, altimeter, imu, storage_mounted=True
        )

        self.assertFalse(health['cameras']['connected'])
        self.assertIn('automatic discovery is retrying',
                      health['cameras']['message'])
        self.assertEqual(
            health['cameras']['error'],
            "Sony SDK reported zero cameras",
        )


if __name__ == "__main__":
    unittest.main()
