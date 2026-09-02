"""Tests for SkySeeker diagnostics and bounded AP recovery."""

import contextlib
from importlib.machinery import SourceFileLoader
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HEALTH_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-health"
LOADER = SourceFileLoader("skyseeker_health", str(HEALTH_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
HEALTH = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(HEALTH)


def result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def healthy_status():
    return {
        "hostapd": "active",
        "dnsmasq": "active",
        "interface": "wlx0",
        "driver": "8192eu",
        "link_up": True,
        "control": "ENABLED",
        "stations": 1,
        "weakest_signal": -62,
    }


class NetworkHealthTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        patches = [
            patch.object(HEALTH, "STATE_PATH", root / "state"),
            patch.object(HEALTH, "DISABLE_PATH", root / "disabled"),
            patch.object(HEALTH, "RESTART_SETTLE_SECONDS", 0),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_finds_only_an_ap_interface(self):
        output = "Interface wlan0\n\ttype managed\nInterface wlx0\n\ttype AP\n"
        self.assertEqual(HEALTH.find_ap_interface(output), "wlx0")
        self.assertIsNone(
            HEALTH.find_ap_interface("Interface wlan0\n\ttype managed\n")
        )

    def test_station_stats_reports_count_and_weakest_signal(self):
        dump = (
            "Station 24:b2:b9:c9:1e:cf (on wlx0)\n\tsignal: -70 dBm\n"
            "Station aa:bb:cc:dd:ee:ff (on wlx0)\n\tsignal: -52 dBm\n"
        )
        with patch.object(HEALTH, "run", return_value=result([], stdout=dump)):
            self.assertEqual(HEALTH.station_stats("wlx0"), (2, -70))

    def test_snapshot_contains_device_and_network_diagnostics(self):
        with (
            patch.object(HEALTH, "unit_state", side_effect=["active", "active"]),
            patch.object(HEALTH, "pcie_error_count", return_value=2),
            patch.object(HEALTH, "cpu_temp_c", return_value=54),
            patch.object(HEALTH, "load_1min", return_value="0.32"),
            patch.object(HEALTH, "mem_available_mb", return_value=812),
            patch.object(HEALTH.os.path, "ismount", return_value=True),
        ):
            snapshot = HEALTH.snapshot(healthy_status())

        self.assertEqual(snapshot["ap"], "ok")
        self.assertEqual(snapshot["tricap"], "active")
        self.assertEqual(snapshot["netbird"], "active")
        self.assertEqual(snapshot["storage"], "mounted")
        self.assertEqual(snapshot["pcie_errors"], 2)

    def test_manual_diagnostics_never_restarts_services(self):
        with (
            patch.object(HEALTH, "ap_status", return_value=healthy_status()),
            patch.object(HEALTH, "print_snapshot"),
            patch.object(HEALTH, "run") as run_mock,
        ):
            self.assertEqual(HEALTH.main([]), 0)
        run_mock.assert_not_called()

    def test_dead_dnsmasq_targets_only_dnsmasq(self):
        status = healthy_status()
        status["dnsmasq"] = "inactive"
        healthy, detail, services = HEALTH.ap_health(status)
        self.assertFalse(healthy)
        self.assertEqual(services, ["dnsmasq.service"])
        self.assertIn("DHCP", detail)

    def test_third_failure_restarts_failed_service(self):
        HEALTH.save_state({"failures": 2, "last_restart": 0.0})
        status = healthy_status()
        status["hostapd"] = "inactive"
        restarts = []

        def commands(args, timeout=6):
            if args[:2] == [HEALTH.SYSTEMCTL, "restart"]:
                restarts.append(args[2])
                return result(args)
            return result(args)

        with (
            patch.object(HEALTH, "run", side_effect=commands),
            patch.object(HEALTH, "ap_status", return_value=healthy_status()),
        ):
            self.assertEqual(HEALTH.recover(status), 0)
        self.assertEqual(restarts, ["hostapd.service"])
        self.assertEqual(HEALTH.load_state()["failures"], 0)

    def test_cooldown_suppresses_repeat_restarts(self):
        HEALTH.save_state({"failures": 5, "last_restart": time.time() - 30})
        status = healthy_status()
        status["hostapd"] = "inactive"
        with patch.object(HEALTH, "run") as run_mock:
            self.assertEqual(HEALTH.recover(status), 0)
        run_mock.assert_not_called()

    def test_restart_budget_suppresses_further_restarts(self):
        HEALTH.save_state({"failures": 0, "last_restart": 0.0,
                           "restarts_since_recovery": HEALTH.MAX_RESTARTS_BEFORE_BACKOFF})
        status = healthy_status()
        status["hostapd"] = "inactive"
        with (
            patch.object(HEALTH, "run") as run_mock,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(HEALTH.recover(status), 0)
        run_mock.assert_not_called()
        self.assertIn("recovery paused", output.getvalue())

    def test_healthy_check_resets_restart_budget(self):
        HEALTH.save_state({"failures": 4, "last_restart": 123.0, "restarts_since_recovery": 3})

        self.assertEqual(HEALTH.recover(healthy_status()), 0)

        state = HEALTH.load_state()
        self.assertEqual(state["failures"], 0)
        self.assertEqual(state["restarts_since_recovery"], 0)
        self.assertEqual(state["last_restart"], 123.0)

    def test_disable_marker_suppresses_recovery(self):
        HEALTH.DISABLE_PATH.touch()
        with patch.object(HEALTH, "run") as run_mock:
            self.assertEqual(HEALTH.recover(healthy_status()), 0)
        run_mock.assert_not_called()

    def test_automatic_recovery_has_no_power_cycle_path(self):
        source = HEALTH_PATH.read_text(encoding="utf-8")
        for command in ("reboot", "poweroff", "shutdown"):
            self.assertNotIn(command, source)

    def test_failed_snapshot_is_still_printable(self):
        status = healthy_status()
        status["interface"] = None
        with (
            patch.object(HEALTH, "snapshot", return_value={"ap": "failed"}),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            HEALTH.print_snapshot(status)
        self.assertIn("ap=failed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
