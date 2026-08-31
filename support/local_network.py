"""Restrict the web interface to SkySeeker-managed networks."""

from __future__ import annotations

import ipaddress


AP_NETWORK = ipaddress.ip_network("192.168.50.0/24")
WIRED_MAINTENANCE_NETWORK = ipaddress.ip_network("192.168.51.0/24")
NETBIRD_NETWORK = ipaddress.ip_network("100.64.0.0/10")
ALLOWED_CLIENT_NETWORKS = (
    AP_NETWORK,
    WIRED_MAINTENANCE_NETWORK,
    NETBIRD_NETWORK,
)


def web_client_allowed(client_ip: str | None) -> bool:
    if not client_ip:
        return False

    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    if address.is_loopback:
        return True
    return address.version == 4 and any(
        address in network for network in ALLOWED_CLIENT_NETWORKS
    )
