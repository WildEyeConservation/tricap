"""Tests for operator-facing optional-component health messages."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from support.component_health import component_health


class ComponentHealthTests(unittest.TestCase):

    def test_camera_startup_error_explains_storage_remains_available(self):
        manager = Mock()
        manager.get_cameras_as_list.return_value = []
        manager.camera_startup_error = "Sony SDK reported zero cameras"
        gps = Mock(isConnected=False)
        gps.hasGps.return_value = False
        altimeter = Mock(available=False)

        health = component_health(
            manager, gps, altimeter, storage_mounted=True
        )

        self.assertFalse(health['cameras']['connected'])
        self.assertIn('Storage operations remain available',
                      health['cameras']['message'])
        self.assertIn('Restart Tricap after reconnecting cameras',
                      health['cameras']['message'])
        self.assertEqual(
            health['cameras']['error'],
            "Sony SDK reported zero cameras",
        )
        self.assertIn('GRF-500', health['altimeter']['message'])
        self.assertEqual(
            set(health),
            {'cameras', 'gps', 'altimeter', 'storage'},
        )

    def test_altimeter_error_reports_lost_communication(self):
        manager = Mock()
        manager.get_cameras_as_list.return_value = []
        gps = Mock(isConnected=False)
        gps.hasGps.return_value = False
        altimeter = SimpleNamespace(
            available=False,
            state=SimpleNamespace(name='ERROR'),
        )

        health = component_health(
            manager, gps, altimeter, storage_mounted=True
        )

        self.assertFalse(health['altimeter']['connected'])
        self.assertEqual(
            health['altimeter']['message'],
            'GRF-500 altimeter lost communication. '
            'Reconnect it; it is retried when capture starts.',
        )


if __name__ == "__main__":
    unittest.main()
