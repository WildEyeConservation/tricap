"""Identify clients on physical networks directly attached to the rig."""

from __future__ import annotations

import ipaddress
import subprocess
import threading
import time


class DirectNetworkChecker:
    """Cache physical-interface IPv4 networks and test a client address."""

    def __init__(self, cache_seconds: float = 5.0):
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._expires = 0.0
        self._networks: tuple[ipaddress.IPv4Network, ...] = ()

    @staticmethod
    def _physical_interface(name: str) -> bool:
        return name.startswith(("wl", "eth", "en"))

    def _read_networks(self) -> tuple[ipaddress.IPv4Network, ...]:
        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", "up"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return ()
        networks = set()
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4 or not self._physical_interface(fields[1]):
                continue
            try:
                inet_index = fields.index("inet")
                networks.add(ipaddress.ip_network(fields[inet_index + 1], strict=False))
            except (ValueError, IndexError):
                continue
        return tuple(sorted(networks, key=str))

    def networks(self) -> tuple[ipaddress.IPv4Network, ...]:
        now = time.monotonic()
        with self._lock:
            if now >= self._expires:
                try:
                    self._networks = self._read_networks()
                except (OSError, subprocess.SubprocessError):
                    self._networks = ()
                self._expires = now + self.cache_seconds
            return self._networks

    def allows(self, client_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        if address.version != 4:
            return False
        return any(address in network for network in self.networks())


direct_network_checker = DirectNetworkChecker()


def directly_attached_client_allowed(client_ip: str) -> bool:
    return direct_network_checker.allows(client_ip)

