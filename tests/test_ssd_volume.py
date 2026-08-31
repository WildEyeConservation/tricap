import unittest

from support.ssd_volume import Volume, pick_volume


def usb_disk(children, serial="S123"):
    return {"path": "/dev/sda", "type": "disk", "tran": "usb", "fstype": None, "size": "1000",
            "serial": serial, "children": children}


def part(path, fstype="exfat", size="900", uuid="1234-ABCD", partuuid="p-1"):
    return {"path": path, "type": "part", "fstype": fstype, "size": size, "uuid": uuid, "partuuid": partuuid}


class PickVolumeTest(unittest.TestCase):
    def test_uses_filesystem_uuid_as_identity(self):
        self.assertEqual(pick_volume([usb_disk([part("/dev/sda1")])]), Volume("/dev/sda1", "1234-ABCD"))

    def test_prefers_largest_filesystem_over_leading_efi_partition(self):
        disk = usb_disk([part("/dev/sda1", fstype="vfat", size="200", uuid="EFI-0001"),
                         part("/dev/sda2", size="900", uuid="DATA-0002")])
        self.assertEqual(pick_volume([disk]).path, "/dev/sda2")

    def test_identity_fallback_chain(self):
        self.assertEqual(pick_volume([usb_disk([part("/dev/sda1", uuid=None)])]).id, "p-1")
        self.assertEqual(pick_volume([usb_disk([part("/dev/sda1", uuid=None, partuuid=None)])]).id, "S123")
        self.assertEqual(pick_volume([usb_disk([part("/dev/sda1", uuid=None, partuuid=None)], serial=None)]).id, "/dev/sda1")

    def test_disk_without_partition_table(self):
        disk = {"path": "/dev/sda", "type": "disk", "tran": "usb", "fstype": "exfat", "size": "1000",
                "uuid": "RAW-0001", "serial": "S1"}
        self.assertEqual(pick_volume([disk]), Volume("/dev/sda", "RAW-0001"))

    def test_ignores_non_usb_and_unformatted(self):
        nvme = {"path": "/dev/nvme0n1", "type": "disk", "tran": "nvme", "fstype": None,
                "children": [part("/dev/nvme0n1p1", fstype="ext4")]}
        blank = usb_disk([part("/dev/sdb1", fstype=None)])
        self.assertIsNone(pick_volume([nvme, blank]))
        self.assertIsNone(pick_volume([]))

    def test_sizes_may_be_numbers_or_missing(self):
        disk = usb_disk([part("/dev/sda1", size=200, uuid="A"), part("/dev/sda2", size=None, uuid="B")])
        self.assertEqual(pick_volume([disk]).id, "A")
