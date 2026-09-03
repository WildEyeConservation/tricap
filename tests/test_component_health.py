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

        health = component_health(manager, gps, altimeter, storage_mounted=True)

        self.assertFalse(health["cameras"]["connected"])
        self.assertEqual(health["cameras"]["count"], 0)
        self.assertTrue(health["cameras"]["message"])
        self.assertEqual(
            health["cameras"]["error"],
            "Sony SDK reported zero cameras",
        )
        self.assertFalse(health["gps"]["connected"])
        self.assertFalse(health["gps"]["fix"])
        self.assertFalse(health["altimeter"]["connected"])
        self.assertTrue(health["altimeter"]["message"])
        self.assertTrue(health["storage"]["connected"])
        self.assertEqual(
            set(health),
            {"cameras", "gps", "altimeter", "storage"},
        )

    def test_altimeter_error_reports_lost_communication(self):
        manager = Mock()
        manager.get_cameras_as_list.return_value = []
        gps = Mock(isConnected=False)
        gps.hasGps.return_value = False
        altimeter = SimpleNamespace(
            available=False,
            state=SimpleNamespace(name="ERROR"),
        )

        health = component_health(manager, gps, altimeter, storage_mounted=True)

        self.assertFalse(health["altimeter"]["connected"])
        self.assertIn("lost communication", health["altimeter"]["message"])


if __name__ == "__main__":
    unittest.main()
