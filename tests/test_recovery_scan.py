"""Tests for the onboard-radio rescue hotspot scan."""

from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-recovery-scan"
LOADER = SourceFileLoader("skyseeker_recovery_scan", str(SCAN_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
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
            [SCAN.NMCLI, "device", "wifi", "rescan", "ifname", "wlan0",
             "ssid", SCAN.SSID],
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
            [SCAN.NMCLI, "--wait", "30", "connection", "up", SCAN.PROFILE,
             "ifname", "wlan0"],
            calls,
        )

    def test_scan_does_not_manage_netbird(self):
        source = SCAN_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("netbird up", source)
        self.assertNotIn("netbird down", source)
        self.assertNotIn("systemctl restart netbird", source)


if __name__ == "__main__":
    unittest.main()
