"""Regression checks for the standalone portal's polling behavior.

Guards the agreed pre-flight polling configuration (see
docs/stability-recovery-plan.md, step 1a): intervals, single-flight
guards, and the pause-while-capturing gates.
"""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PORTAL_PATH = ROOT / "skyseeker-standalone" / "captive_portal.py"
SPEC = importlib.util.spec_from_file_location("skyseeker_captive_portal", PORTAL_PATH)
PORTAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTAL)


class PortalServerTests(unittest.TestCase):
    def test_accept_queue_covers_worst_case_rejoin_burst(self):
        # 4 devices x ~10 simultaneous connections on rejoin, plus 10 buffer
        # (docs/stability-recovery-plan.md, step 1b).
        self.assertEqual(PORTAL.PortalServer.request_queue_size, 50)
        self.assertTrue(PORTAL.PortalServer.daemon_threads)
        self.assertFalse(PORTAL.PortalServer.block_on_close)


class PortalPollingTests(unittest.TestCase):
    def test_agreed_polling_intervals(self):
        self.assertIn("runPeriodic(connectionHeartbeat,5000)", PORTAL.COMMON_JS)
        self.assertIn("runPeriodic(poll,1000)", PORTAL.HOME_JS)
        self.assertIn("pollStorage(),15000)", PORTAL.HOME_JS)
        # Sensors poll doubles as the setup page's unlock check: 2 s normally,
        # 5 s while the page is locked out during capture/copy.
        self.assertIn("runPeriodic(loadSensors,()=>capturing?5000:2000)", PORTAL.SETUP_JS)

    def test_baseline_aggressive_timers_removed(self):
        for js, timer in (
            (PORTAL.COMMON_JS, "setInterval(connectionHeartbeat,1500)"),
            (PORTAL.HOME_JS, "setInterval(poll,1000)"),
            (PORTAL.HOME_JS, "setInterval(pollStorage,15000)"),
            (PORTAL.SETUP_JS, "setInterval(loadSensors,2000)"),
            (PORTAL.SETUP_JS, "setInterval(loadStats,15000)"),
            (PORTAL.SETUP_JS, "setInterval(loadImageFormat,15000)"),
            (PORTAL.SETUP_JS, "setInterval(uplinkStatus,10000)"),
        ):
            self.assertNotIn(timer, js)

    def test_every_poller_is_single_flight(self):
        for key in ("home-status", "home-storage"):
            self.assertIn(f'"{key}"', PORTAL.HOME_JS)
        for key in (
            "setup-status",
            "setup-stats",
            "setup-image-format",
            "setup-netbird",
            "setup-uplink",
            "backup-status",
            "verify-status",
        ):
            self.assertIn(f'"{key}"', PORTAL.SETUP_JS)

    def test_pollers_pause_while_capturing(self):
        # Home: the storage poll (whose estimate walks the NVMe) pauses while
        # recording so it never competes with the cameras for disk I/O.
        self.assertIn('latest&&latest.mode==="STARTED"?null:pollStorage()', PORTAL.HOME_JS)
        # Setup: everything except the unlock check pauses while locked out.
        for paused in (
            "capturing?null:loadStats()",
            "capturing?null:loadImageFormat()",
            'capturing?null:singleFlight("setup-netbird"',
            'capturing?null:singleFlight("setup-uplink"',
        ):
            self.assertIn(paused, PORTAL.SETUP_JS)


if __name__ == "__main__":
    unittest.main()


class PortalFlightLogTests(unittest.TestCase):
    def test_flight_log_download_is_the_file_written_on_the_drive(self):
        import os
        import tempfile
        from datetime import datetime
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            day = datetime.now().strftime("%Y_%m_%d")
            os.makedirs(os.path.join(tmp, day))
            body = "Fix Quality,GPS Time\n1,2026-09-01 10:00:00.000\n"
            with open(os.path.join(tmp, day, PORTAL.FLIGHT_LOG_FILENAME), "w") as f:
                f.write(body)
            with patch.object(PORTAL, "DATA_MOUNT", "/definitely/not/mounted"), \
                    patch.object(PORTAL, "DATA_FALLBACK", tmp):
                self.assertEqual(PORTAL.flight_log_for_today(), (day, body))

    def test_flight_log_missing_reports_none(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(PORTAL, "DATA_MOUNT", "/definitely/not/mounted"), \
                    patch.object(PORTAL, "DATA_FALLBACK", tmp):
                self.assertEqual(PORTAL.flight_log_for_today(), (None, None))
