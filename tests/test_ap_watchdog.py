"""Unit tests for the restart-only AP watchdog (step 5 of the recovery plan)."""

from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-ap-watchdog"
LOADER = SourceFileLoader("skyseeker_ap_watchdog", str(WATCHDOG_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
WATCHDOG = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(WATCHDOG)


def result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def healthy_commands(args, timeout=6):
    if args[:3] == [WATCHDOG.SYSTEMCTL, "is-active", "--quiet"]:
        return result(args)
    if args == [WATCHDOG.IW, "dev"]:
        return result(args, stdout="Interface wlx0\n\ttype AP\n")
    if args[:5] == [WATCHDOG.IP, "-o", "link", "show", "dev"]:
        return result(args, stdout="3: wlx0: <BROADCAST,UP,LOWER_UP> state UP\n")
    if args[-1] == "ping":
        return result(args, stdout="PONG\n")
    if args[-1] == "status":
        return result(args, stdout="state=ENABLED\nssid=skyseeker\n")
    return result(args, returncode=1, stderr="unexpected command")


class ApWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        patches = [
            patch.object(WATCHDOG, "STATE_PATH", root / "state"),
            patch.object(WATCHDOG, "DISABLE_PATH", root / "disabled"),
            patch.object(WATCHDOG, "RESTART_SETTLE_SECONDS", 0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_full_health_check_reaches_hostapd_and_dnsmasq(self):
        with patch.object(WATCHDOG, "run", side_effect=healthy_commands):
            healthy, detail, services = WATCHDOG.ap_health()
        self.assertTrue(healthy)
        self.assertEqual(services, [])
        self.assertIn("wlx0", detail)

    def test_dead_dnsmasq_targets_dnsmasq_not_hostapd(self):
        def commands(args, timeout=6):
            if args == [WATCHDOG.SYSTEMCTL, "is-active", "--quiet", "dnsmasq.service"]:
                return result(args, returncode=3)
            return healthy_commands(args, timeout)

        with patch.object(WATCHDOG, "run", side_effect=commands):
            healthy, detail, services = WATCHDOG.ap_health()
        self.assertFalse(healthy)
        self.assertEqual(services, ["dnsmasq.service"])
        self.assertIn("DHCP", detail)

    def test_third_failure_restarts_the_failed_service(self):
        WATCHDOG.save_state({"failures": 2, "last_restart": 0.0})
        restarts = []

        def commands(args, timeout=6):
            if args[:2] == [WATCHDOG.SYSTEMCTL, "restart"]:
                restarts.append(args[2])
                return result(args)
            return result(args, returncode=1)

        with patch.object(WATCHDOG, "run", side_effect=commands):
            self.assertEqual(WATCHDOG.main(), 0)
        self.assertEqual(restarts, ["hostapd.service"] )
        self.assertEqual(WATCHDOG.load_state()["failures"], 0)

    def test_cooldown_suppresses_repeat_restarts(self):
        WATCHDOG.save_state({"failures": 5, "last_restart": time.time() - 30})
        with patch.object(WATCHDOG, "run", side_effect=lambda a, timeout=6: result(a, 1)) as run_mock:
            self.assertEqual(WATCHDOG.main(), 0)
        for call in run_mock.call_args_list:
            self.assertNotEqual(call.args[0][:2], [WATCHDOG.SYSTEMCTL, "restart"])

    def test_disable_marker_suppresses_checks(self):
        WATCHDOG.DISABLE_PATH.touch()
        with patch.object(WATCHDOG, "ap_health") as health_mock:
            self.assertEqual(WATCHDOG.main(), 0)
        health_mock.assert_not_called()

    def test_no_reboot_path_exists(self):
        source = WATCHDOG_PATH.read_text(encoding="utf-8")
        for verb in ("reboot", "poweroff", "shutdown"):
            self.assertNotIn(f'"{verb}"', source)
            self.assertNotIn(f"systemctl {verb}", source)


if __name__ == "__main__":
    unittest.main()
