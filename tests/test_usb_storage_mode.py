"""Tests for storage-only USB device selection and recovery."""

import tempfile
import unittest
from pathlib import Path

from support.usb_storage_mode import UsbStorageMode


class UsbStorageModeTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.usb = root / "usb"
        self.block = root / "block"
        self.state = root / "run" / "state.json"
        self.usb.mkdir()
        self.block.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def device(self, name, vendor, product, network=False):
        path = self.usb / name
        (path / "power").mkdir(parents=True)
        (path / "idVendor").write_text(vendor)
        (path / "idProduct").write_text(product)
        (path / "authorized").write_text("1")
        (path / "power" / "control").write_text("on")
        (path / "devpath").write_text(name.split("-", 1)[1])
        if network:
            (path / "net" / "wlan0").mkdir(parents=True)
        return path

    def root_bus(self, bus, serial):
        path = self.usb / ("usb" + str(bus))
        path.mkdir()
        (path / "serial").write_text(serial)

    def mode(self):
        return UsbStorageMode(self.usb, self.block, self.state)

    def test_preserves_wifi_and_sd810_components(self):
        self.root_bus(7, "xhci-controller")
        self.root_bus(8, "xhci-controller")
        self.device("1-1", "2357", "0108", network=True)
        self.device("7-1", "8564", "4100")
        self.device("8-1", "8564", "4100")
        self.device("8-1.2", "090c", "a38a")
        self.device("6-1", "054c", "0e90")
        self.device("2-1", "1546", "01a8")

        self.assertEqual(self.mode().plan(), ["2-1"])

    def test_preserves_sony_camera_but_disconnects_other_sensor(self):
        self.device("6-1", "054c", "0e90")
        self.device("4-1", "1546", "01a9")

        self.assertEqual(self.mode().plan(), ["4-1"])

    def test_disconnects_only_root_of_nonessential_hub_subtree(self):
        self.device("3-1", "1234", "0001")
        self.device("3-1.1", "054c", "1111")
        self.device("3-1.2", "abcd", "2222")

        self.assertEqual(self.mode().plan(), ["3-1"])

    def test_quiesce_and_restore_authorization(self):
        gps = self.device("2-1", "1546", "01a8")
        mode = self.mode()

        self.assertEqual(mode.quiesce(), ["2-1"])
        self.assertEqual((gps / "authorized").read_text(), "0")
        self.assertEqual((gps / "power" / "control").read_text(), "auto")
        self.assertTrue(self.state.is_file())

        mode.restore()
        self.assertEqual((gps / "authorized").read_text(), "1")
        self.assertEqual((gps / "power" / "control").read_text(), "on")
        self.assertFalse(self.state.exists())

    def test_new_instance_recovers_saved_state(self):
        gps = self.device("2-1", "1546", "01a8")
        self.mode().quiesce()

        self.mode().restore()

        self.assertEqual((gps / "authorized").read_text(), "1")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
