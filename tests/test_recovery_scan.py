"""Tests for the onboard-radio rescue hotspot scan."""

import importlib.util
import subprocess
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-recovery-scan"
LOADER = SourceFileLoader("skyseeker_recovery_scan", str(SCAN_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
SCAN = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(SCAN)


def result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class RecoveryScanTests(unittest.TestCase):
    def test_visibility_check_requests_a_fresh_rescue_scan(self):
        calls = []

        def commands(args, timeout=15):
            calls.append(args)
            if "list" in args:
                return result(args, stdout=f"{SCAN.SSID}\n")
            return result(args)

        with patch.object(SCAN, "run", side_effect=commands):
            self.assertTrue(SCAN.rescue_visible("wlan0"))
        self.assertEqual(
            calls[0],
            [SCAN.NMCLI, "device", "wifi", "rescan", "ifname", "wlan0", "ssid", SCAN.SSID],
        )

    def test_active_uplink_is_never_interrupted(self):
        with (
            patch.object(SCAN, "onboard_interface", return_value="wlan0"),
            patch.object(SCAN, "active_connection", return_value="field-uplink"),
            patch.object(SCAN, "profile_exists") as profile,
            patch.object(SCAN, "rescue_visible") as visible,
            patch.object(SCAN, "run") as run_mock,
        ):
            self.assertEqual(SCAN.main(), 0)
        profile.assert_not_called()
        visible.assert_not_called()
        run_mock.assert_not_called()

    def test_disconnected_radio_scans_and_joins_rescue_hotspot(self):
        calls = []

        def commands(args, timeout=15):
            calls.append(args)
            return result(args)

        with (
            patch.object(SCAN, "onboard_interface", return_value="wlan0"),
            patch.object(SCAN, "active_connection", return_value=None),
            patch.object(SCAN, "profile_exists", return_value=True),
            patch.object(SCAN, "rescue_visible", return_value=True),
            patch.object(SCAN, "run", side_effect=commands),
        ):
            self.assertEqual(SCAN.main(), 0)

        self.assertIn(
            [SCAN.NMCLI, "--wait", "30", "connection", "up", SCAN.PROFILE, "ifname", "wlan0"],
            calls,
        )

    def test_joining_rescue_profile_does_not_manage_netbird(self):
        calls = []

        def commands(args, timeout=15):
            calls.append(args)
            if "--active" in args:
                return result(args)
            if args[-2:] == ["connection", "show"]:
                return result(args, stdout=f"{SCAN.PROFILE}\n")
            if "list" in args:
                return result(args, stdout=f"{SCAN.SSID}\n")
            return result(args)

        with (
            patch.object(SCAN, "onboard_interface", return_value="wlan0"),
            patch.object(SCAN, "run", side_effect=commands),
        ):
            self.assertEqual(SCAN.main(), 0)

        self.assertIn("up", calls[-1])
        self.assertIn(SCAN.PROFILE, calls[-1])
        self.assertTrue(all("netbird" not in " ".join(command).lower() for command in calls))

    def test_failed_connect_logs_and_performs_no_followup_command(self):
        calls = []

        def commands(args, timeout=15):
            calls.append(args)
            return result(args, returncode=10, stderr="connection failed")

        with (
            patch.object(SCAN, "onboard_interface", return_value="wlan0"),
            patch.object(SCAN, "active_connection", return_value=None),
            patch.object(SCAN, "profile_exists", return_value=True),
            patch.object(SCAN, "rescue_visible", return_value=True),
            patch.object(SCAN, "run", side_effect=commands),
            patch.object(SCAN, "log") as log,
        ):
            self.assertEqual(SCAN.main(), 0)

        self.assertTrue(log.called)
        self.assertEqual(len(calls), 1)
        self.assertIn("up", calls[0])


if __name__ == "__main__":
    unittest.main()
