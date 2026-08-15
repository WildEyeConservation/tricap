"""Unit tests for the Wi-Fi AP liveness monitor."""

from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-ap-watchdog"
LOADER = SourceFileLoader("skyseeker_ap_watchdog", str(WATCHDOG_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
WATCHDOG = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(WATCHDOG)


def result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class ApWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.state_path = root / "state"
        self.disable_path = root / "disabled"
        self.state_patch = patch.object(WATCHDOG, "STATE_PATH", self.state_path)
        self.disable_patch = patch.object(WATCHDOG, "DISABLE_PATH", self.disable_path)
        self.settle_patch = patch.object(WATCHDOG, "RESTART_SETTLE_SECONDS", 0)
        self.state_patch.start()
        self.disable_patch.start()
        self.settle_patch.start()

    def tearDown(self):
        self.settle_patch.stop()
        self.disable_patch.stop()
        self.state_patch.stop()
        self.tempdir.cleanup()

    def test_full_health_check_reaches_hostapd_control_socket(self):
        def command(args, timeout=6):
            if args[:3] == [WATCHDOG.SYSTEMCTL, "is-active", "--quiet"]:
                return result(args)
            if args == [WATCHDOG.IW, "dev"]:
                return result(args, stdout="Interface wlx0\n\ttype AP\n")
            if args[:5] == [WATCHDOG.IP, "-o", "link", "show", "dev"]:
                return result(args, stdout="3: wlx0: <BROADCAST,UP,LOWER_UP> state UP\n")
            if args == [WATCHDOG.IW, "dev", "wlx0", "info"]:
                return result(args, stdout="Interface wlx0\n\ttype AP\n\twiphy 0\n")
            if args[-1] == "ping":
                return result(args, stdout="PONG\n")
            if args[-1] == "status":
                return result(args, stdout="state=ENABLED\nssid=skyseeker\n")
            return result(args, returncode=1, stderr="unexpected command")

        with patch.object(WATCHDOG, "run", side_effect=command):
            self.assertEqual(WATCHDOG.ap_health(), (True, "AP wlx0 is responsive"))

    def test_third_failure_restarts_hostapd_and_clears_state_after_recovery(self):
        WATCHDOG.save_state({"failures": 2, "restarted": False})
        with patch.object(
            WATCHDOG,
            "ap_health",
            side_effect=[(False, "control ping failed"), (True, "AP wlx0 is responsive")],
        ), patch.object(WATCHDOG, "run", return_value=result([])) as run_mock:
            self.assertEqual(WATCHDOG.main(), 0)

        run_mock.assert_called_once_with(
            [WATCHDOG.SYSTEMCTL, "restart", "hostapd.service"], timeout=15
        )
        self.assertFalse(self.state_path.exists())

    def test_failed_check_after_restart_requests_reboot(self):
        WATCHDOG.save_state({"failures": 3, "restarted": True})
        with patch.object(
            WATCHDOG, "ap_health", return_value=(False, "driver timed out")
        ), patch.object(WATCHDOG, "run", return_value=result([])) as run_mock:
            self.assertEqual(WATCHDOG.main(), 0)

        run_mock.assert_has_calls([call([WATCHDOG.SYSTEMCTL, "reboot"], timeout=15)])

    def test_disable_marker_suppresses_checks(self):
        self.disable_path.touch()
        with patch.object(WATCHDOG, "ap_health") as health_mock:
            self.assertEqual(WATCHDOG.main(), 0)
        health_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
