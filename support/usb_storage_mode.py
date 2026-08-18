"""Temporarily disconnect non-storage USB devices during heavy disk work."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Iterable


_USB_DEVICE_NAME = re.compile(r"^\d+-\d+(?:\.\d+)*$")

# These devices must remain usable while the dashboard performs storage work.
# The mounted block-device ancestry is also preserved dynamically below.
ESSENTIAL_USB_IDS = {
    ("2357", "0108"),  # TP-Link RTL8192EU Wi-Fi adapter
    ("090c", "a38a"),  # ADATA SD810 mass-storage function
    # The cameras have their own power feeds.  Keep their SDK connections
    # intact because the native Sony disconnect path can terminate Tricap.
    ("054c", "0e90"),  # Sony ILX-LR1
}


class UsbStorageMode:
    """Deauthorize non-essential USB subtrees and later restore them."""

    def __init__(
        self,
        sysfs_root: Path | str = "/sys/bus/usb/devices",
        block_root: Path | str = "/sys/class/block",
        state_path: Path | str = "/run/tricap-usb-storage-mode.json",
        logger: logging.Logger | None = None,
    ) -> None:
        self.sysfs_root = Path(sysfs_root)
        self.block_root = Path(block_root)
        self.state_path = Path(state_path)
        self._logger = logger or logging.getLogger(__name__)
        self._targets: list[str] = []
        self._controls: dict[str, str] = {}

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="ascii").strip().lower()

    def _device_nodes(self) -> dict[str, Path]:
        nodes: dict[str, Path] = {}
        if not self.sysfs_root.exists():
            return nodes
        for path in self.sysfs_root.iterdir():
            if _USB_DEVICE_NAME.match(path.name) and (path / "idVendor").is_file():
                nodes[path.name] = path
        return nodes

    @staticmethod
    def _parent_name(name: str) -> str | None:
        if "." not in name:
            return None
        return name.rsplit(".", 1)[0]

    @classmethod
    def _with_ancestors(cls, names: Iterable[str], nodes: dict[str, Path]) -> set[str]:
        result = set(names)
        for name in tuple(result):
            parent = cls._parent_name(name)
            while parent:
                if parent in nodes:
                    result.add(parent)
                parent = cls._parent_name(parent)
        return result

    def _network_usb_nodes(self, nodes: dict[str, Path]) -> set[str]:
        preserved = set()
        for name, path in nodes.items():
            if any((path / "net").glob("*")):
                preserved.add(name)
        return preserved

    def _block_usb_nodes(self, external_device: str | None, nodes: dict[str, Path]) -> set[str]:
        if not external_device:
            return set()
        block_path = self.block_root / Path(external_device).name
        try:
            resolved = block_path.resolve(strict=True)
        except OSError:
            return set()
        parts = set(resolved.parts)
        return {name for name in nodes if name in parts}

    def _companion_nodes(self, names: set[str], nodes: dict[str, Path]) -> set[str]:
        """Preserve USB 2/USB 3 companions for the same controller and port."""
        preserved = set(names)
        signatures = set()
        for name in names:
            bus = name.split("-", 1)[0]
            serial_path = self.sysfs_root / ("usb" + bus) / "serial"
            devpath_path = nodes[name] / "devpath"
            if serial_path.is_file() and devpath_path.is_file():
                signatures.add((self._read(serial_path), self._read(devpath_path)))

        for name, path in nodes.items():
            bus = name.split("-", 1)[0]
            serial_path = self.sysfs_root / ("usb" + bus) / "serial"
            devpath_path = path / "devpath"
            if (serial_path.is_file() and devpath_path.is_file()
                    and (self._read(serial_path), self._read(devpath_path))
                    in signatures):
                preserved.add(name)
        return preserved

    def plan(self, external_device: str | None = None) -> list[str]:
        """Return the shallowest non-essential USB subtrees to disconnect."""
        nodes = self._device_nodes()
        essential = {
            name for name, path in nodes.items()
            if (self._read(path / "idVendor"), self._read(path / "idProduct"))
            in ESSENTIAL_USB_IDS
        }
        essential.update(self._network_usb_nodes(nodes))
        essential.update(self._block_usb_nodes(external_device, nodes))
        essential = self._with_ancestors(essential, nodes)
        essential = self._companion_nodes(essential, nodes)
        essential = self._with_ancestors(essential, nodes)

        nonessential = set(nodes) - essential
        targets = []
        for name in sorted(nonessential, key=lambda value: (value.count("."), value)):
            parent = self._parent_name(name)
            if parent not in nonessential:
                targets.append(name)
        return targets

    def quiesce(self, external_device: str | None = None) -> list[str]:
        """Deauthorize planned devices, persisting enough state for recovery."""
        if self._targets:
            return list(self._targets)

        targets = self.plan(external_device)
        controls = {}
        for name in targets:
            control = self.sysfs_root / name / "power" / "control"
            if control.is_file():
                controls[name] = self._read(control)
        state = {"targets": targets, "controls": controls}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        os.replace(temporary, self.state_path)

        changed: list[str] = []
        self._controls = controls
        try:
            for name in targets:
                device = self.sysfs_root / name
                control = device / "power" / "control"
                if control.is_file():
                    control.write_text("auto", encoding="ascii")
                (device / "authorized").write_text("0", encoding="ascii")
                changed.append(name)
                self._logger.info("USB storage mode disconnected %s", name)
        except Exception:
            self._targets = changed
            self.restore()
            raise

        self._targets = changed
        return list(changed)

    def restore(self) -> None:
        """Reauthorize devices disabled by this instance or a saved state."""
        targets = list(self._targets)
        controls = dict(self._controls)
        if not targets and self.state_path.is_file():
            try:
                state = json.loads(self.state_path.read_text())
                targets = list(state.get("targets") or [])
                controls = dict(state.get("controls") or {})
            except (OSError, ValueError, TypeError):
                self._logger.exception("Could not read USB storage-mode recovery state")

        for name in sorted(targets, key=lambda value: (value.count("."), value)):
            authorized = self.sysfs_root / name / "authorized"
            if not authorized.is_file():
                continue
            try:
                authorized.write_text("1", encoding="ascii")
                control = self.sysfs_root / name / "power" / "control"
                if control.is_file() and controls.get(name) in ("on", "auto"):
                    control.write_text(controls[name], encoding="ascii")
                self._logger.info("USB storage mode restored %s", name)
            except OSError:
                self._logger.exception("Could not restore USB device %s", name)

        self._targets = []
        self._controls = {}
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError:
            self._logger.exception("Could not remove USB storage-mode recovery state")


def recover_usb_storage_mode() -> None:
    """Restore devices left disabled if Tricap previously exited mid-job."""
    UsbStorageMode().restore()


__all__ = ["ESSENTIAL_USB_IDS", "UsbStorageMode", "recover_usb_storage_mode"]
