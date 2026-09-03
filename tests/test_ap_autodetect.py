"""Tests for the USB AP adapter auto-detect script, run against a fake root."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "services" / "usr-local" / "sbin" / "skyseeker-ap-autodetect.sh"
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "bash is required to run the autodetect script")
class ApAutodetectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "etc" / "default").mkdir(parents=True)
        self.env_file = self.root / "etc" / "default" / "skyseeker-standalone"

    def add_interface(self, name, driver=None, wireless=True):
        iface = self.root / "sys" / "class" / "net" / name
        iface.mkdir(parents=True)
        if wireless:
            (iface / "wireless").mkdir()
        if driver:
            # sysfs names the bound driver in device/uevent; mirror that.
            (iface / "device").mkdir()
            (iface / "device" / "uevent").write_text(f"DRIVER={driver}\nMODALIAS=x\n")

    def pin(self, name):
        self.env_file.write_text(f"AP_IFACE={name}\nSUBNET_IP=192.168.50.1\n")

    def run_script(self):
        return subprocess.run(
            [BASH, str(SCRIPT), str(self.root)],
            capture_output=True, text=True, timeout=30, check=False,
        )

    def test_dongle_from_any_driver_is_chosen_over_the_onboard_radio(self):
        self.add_interface("wlan0", "brcmfmac")
        self.add_interface("wlan1", "mt7921u")
        self.add_interface("eth0", "bcmgenet", wireless=False)
        self.pin("wlx0")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AP adapter is wlan1 (driver mt7921u)", result.stdout)
        self.assertIn("AP_IFACE=wlan1", self.env_file.read_text())

    def test_only_the_onboard_radio_leaves_configs_alone(self):
        self.add_interface("wlan0", "brcmfmac")
        self.pin("wlx0")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no USB AP adapter found", result.stdout)
        self.assertIn("AP_IFACE=wlx0", self.env_file.read_text())

    def test_pinned_name_wins_when_several_dongles_are_present(self):
        self.add_interface("wlan0", "brcmfmac")
        self.add_interface("wlan1", "8192eu")
        self.add_interface("wlan2", "rtl88x2bu")
        self.pin("wlan2")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("several USB radios present (wlan1); using wlan2", result.stdout)
        self.assertNotIn("rewriting", result.stdout)
        self.assertIn("AP_IFACE=wlan2", self.env_file.read_text())

    def test_first_dongle_by_name_when_pin_is_stale(self):
        self.add_interface("wlan0", "brcmfmac")
        self.add_interface("wlan2", "8192eu")
        self.add_interface("wlan1", "rtl88x2bu")
        self.pin("wlx0")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AP_IFACE=wlan1", self.env_file.read_text())

    def test_matching_pin_rewrites_nothing(self):
        self.add_interface("wlan0", "brcmfmac")
        self.add_interface("wlan1", "8192eu")
        self.pin("wlan1")
        before = self.env_file.read_text()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("rewriting", result.stdout)
        self.assertEqual(self.env_file.read_text(), before)

    def test_stale_pin_is_rewritten_in_every_config(self):
        self.add_interface("wlan0", "brcmfmac")
        self.add_interface("wlan1", "8192eu")
        self.pin("wlx0")
        hostapd = self.root / "etc" / "hostapd" / "hostapd-skyseeker.conf"
        hostapd.parent.mkdir(parents=True)
        hostapd.write_text("interface=wlx0\n")
        dnsmasq = self.root / "etc" / "dnsmasq.d" / "skyseeker.conf"
        dnsmasq.parent.mkdir(parents=True)
        dnsmasq.write_text("interface=wlx0\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AP_IFACE=wlan1", self.env_file.read_text())
        self.assertIn("interface=wlan1", hostapd.read_text())
        self.assertIn("ctrl_interface=/run/hostapd", hostapd.read_text())
        self.assertEqual(dnsmasq.read_text(), "interface=wlan1\n")


if __name__ == "__main__":
    unittest.main()
