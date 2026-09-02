"""Restrict the web interface to private networks the rig is attached to."""

from __future__ import annotations

import ipaddress


def web_client_allowed(client_ip: str | None) -> bool:
    """Accept clients on any private network; reject public internet addresses.

    The rig is reached over its own access point, a direct Ethernet cable, a
    phone hotspot it has joined for internet, or the NetBird overlay. All of
    those hand out private or carrier-grade NAT addresses, and which subnet a
    hotspot uses is not ours to choose, so the rule is simply "not globally
    routable". Public addresses cannot reach the rig anyway because it always
    sits behind NAT; rejecting them here is belt and braces.
    """
    if not client_ip:
        return False

    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    if address.is_loopback:
        return True
    if address.version == 6:
        return address.is_link_local or address.is_private
    return not address.is_global
