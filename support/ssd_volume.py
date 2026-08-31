"""Locate the external USB volume and give it a stable identity."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

LSBLK_CMD = ["lsblk", "--json", "--paths", "--bytes", "--output",
             "NAME,PATH,TYPE,FSTYPE,TRAN,SIZE,UUID,PARTUUID,SERIAL"]
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Volume:
    path: str  # what mount(8) needs, e.g. /dev/sda1
    id: str    # filesystem UUID; falls back to PARTUUID, disk serial, then path


def pick_volume(blockdevices: list[dict]) -> Volume | None:
    """Largest filesystem on a USB disk, so a leading EFI/boot partition is skipped."""
    best: tuple[dict, dict] | None = None
    for disk in blockdevices:
        if disk.get("tran") != "usb":
            continue
        for part in disk.get("children") or [disk]:
            if part.get("type") not in ("disk", "part") or not part.get("fstype") or not part.get("path"):
                continue
            if best is None or _size(part) > _size(best[0]):
                best = (part, disk)
    if best is None:
        return None
    part, disk = best
    vol_id = part.get("uuid") or part.get("partuuid") or disk.get("serial") or part["path"]
    return Volume(part["path"], vol_id)


def find_volume() -> Volume | None:
    try:
        out = subprocess.check_output(LSBLK_CMD, text=True)
        return pick_volume(json.loads(out).get("blockdevices", []))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        _logger.warning("Failed to discover external SSD: %s", exc)
        return None


def _size(dev: dict) -> int:
    try:
        return int(dev.get("size") or 0)
    except (TypeError, ValueError):
        return 0
