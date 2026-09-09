from __future__ import annotations

import ipaddress


_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::1/128"),
)


def is_lan_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Accept only explicit private/link-local/loopback networks, not reserved IPs."""
    if address.is_unspecified or address.is_multicast:
        return False
    return any(address in network for network in _LAN_NETWORKS if address.version == network.version)
