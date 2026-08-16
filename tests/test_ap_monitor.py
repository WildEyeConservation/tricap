"""Unit tests for the log-only AP health monitor (step 2 of the recovery plan)."""

from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-ap-monitor"
LOADER = SourceFileLoader("skyseeker_ap_monitor", str(MONITOR_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MONITOR = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MONITOR)


def result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class ApMonitorTests(unittest.TestCase):
    def test_finds_ap_interface_in_iw_output(self):
        out = "phy#0\n\tInterface wlx0\n\t\ttype AP\n"
        self.assertEqual(MONITOR.find_ap_interface(out), "wlx0")
        self.assertIsNone(MONITOR.find_ap_interface("Interface wlan0\n\ttype managed\n"))

    def test_control_socket_absent_is_reported_not_failed(self):
        # Until step 4 lands there is no control socket; that must read as
        # 'absent' (expected), never as an AP failure.
        with patch.object(MONITOR.os.path, "exists", return_value=False):
            self.assertEqual(MONITOR.hostapd_control_state("wlx0"), "absent")

    def test_snapshot_line_carries_freeze_diagnostics(self):
        import contextlib
        import io

        out = io.StringIO()
        with patch.object(MONITOR, "run", side_effect=lambda a, timeout=6: result(a, 1)), \
                contextlib.redirect_stdout(out):
            MONITOR.main()
        line = out.getvalue()
        for key in ("temp=", "load=", "mem_free=", "pcie_err="):
            self.assertIn(key, line)

    def test_main_always_exits_zero_and_never_acts(self):
        # Even with every probe failing, the monitor logs and exits 0 -
        # log-only means no restarts, no reboots, no non-zero exits.
        calls = []

        def failing_run(args, timeout=6):
            calls.append(args)
            return result(args, returncode=1)

        with patch.object(MONITOR, "run", side_effect=failing_run):
            self.assertEqual(MONITOR.main(), 0)

        for args in calls:
            joined = " ".join(args)
            self.assertNotIn("restart", joined)
            self.assertNotIn("reboot", joined)
            self.assertNotIn("stop", joined)

    def test_script_has_no_recovery_verbs(self):
        source = MONITOR_PATH.read_text(encoding="utf-8")
        for verb in ("systemctl restart", "systemctl reboot", "systemctl stop"):
            self.assertNotIn(verb, source)


if __name__ == "__main__":
    unittest.main()
