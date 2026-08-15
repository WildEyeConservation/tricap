"""Regression checks for the standalone portal's load safeguards."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PORTAL_PATH = ROOT / "skyseeker-standalone" / "captive_portal.py"
SPEC = importlib.util.spec_from_file_location("skyseeker_captive_portal", PORTAL_PATH)
PORTAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTAL)


class PortalLoadSafeguardTests(unittest.TestCase):
    def test_server_accept_queue_handles_dashboard_bursts(self):
        self.assertGreaterEqual(PORTAL.PortalServer.request_queue_size, 128)
        self.assertTrue(PORTAL.PortalServer.daemon_threads)
        self.assertFalse(PORTAL.PortalServer.block_on_close)

    def test_periodic_dashboard_requests_are_single_flight(self):
        for key in (
            "home-status",
            "home-storage",
            "setup-sensors",
            "setup-stats",
            "setup-image-format",
            "backup-status",
            "verify-status",
            "netbird-status",
            "uplink-status",
        ):
            self.assertIn(f'"{key}"', PORTAL.HOME_JS + PORTAL.SETUP_JS)

    def test_high_frequency_polling_was_reduced(self):
        self.assertNotIn("setInterval(poll,1000)", PORTAL.HOME_JS)
        self.assertNotIn("setInterval(loadSensors,2000)", PORTAL.SETUP_JS)


if __name__ == "__main__":
    unittest.main()
