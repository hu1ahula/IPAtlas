from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
    summarize_address_range,
)


IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


def parse_ip(value: str) -> IPAddress:
    return ip_address(value.strip())


def parse_network(value: str) -> IPNetwork:
    return ip_network(value.strip(), strict=False)


def parse_ip_range(start_ip: str, end_ip: str) -> tuple[IPAddress, IPAddress]:
    start = parse_ip(start_ip)
    end = parse_ip(end_ip)
    if start.version != end.version:
        raise ValueError("IP range endpoints must use the same IP version")
    if int(start) > int(end):
        raise ValueError("range start_ip must be less than or equal to end_ip")
    return start, end


def range_to_networks(start_ip: str, end_ip: str) -> list[IPNetwork]:
    start, end = parse_ip_range(start_ip, end_ip)
    return list(summarize_address_range(start, end))


def ip_classification(ip: IPAddress) -> dict[str, bool | int | str]:
    return {
        "ip": str(ip),
        "ip_version": ip.version,
        "is_private": ip.is_private,
        "is_global": ip.is_global,
        "is_loopback": ip.is_loopback,
        "is_multicast": ip.is_multicast,
        "is_reserved": ip.is_reserved,
        "is_link_local": ip.is_link_local,
    }

