"""Destination validation for scheduled HTTP requests."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from backend.core.config import settings

__all__ = [
    "UnsafeDestinationError",
    "build_pinned_request",
    "validate_destination",
    "validate_destination_async",
]


class UnsafeDestinationError(ValueError):
    """The requested destination is not permitted."""


def _normalized_host(host: str) -> str:
    return host.rstrip(".").lower()


def _host_is_allowed(host: str) -> bool:
    normalized = _normalized_host(host)
    for configured in settings.SCHEDULER_ALLOWED_HOSTS:
        pattern = _normalized_host(str(configured))
        if pattern.startswith("*."):
            suffix = pattern[1:]
            if normalized.endswith(suffix) and normalized != suffix[1:]:
                return True
        elif normalized == pattern:
            return True
    return False


def _allowed_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for value in settings.SCHEDULER_ALLOWED_CIDRS:
        try:
            networks.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError as exc:
            raise UnsafeDestinationError("Scheduler CIDR allowlist is invalid") from exc
    return tuple(networks)


def _is_allowed_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if any(address in network for network in _allowed_networks()):
        return True
    if address.is_global:
        return True
    if not settings.SCHEDULER_ALLOW_PRIVATE_NETWORKS:
        return False
    return address.is_private and not (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    )


def validate_destination(url: str) -> tuple[str, ...] | None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UnsafeDestinationError("Destination URL is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise UnsafeDestinationError("Only absolute HTTP(S) destinations are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeDestinationError("Destination credentials are not allowed")
    if parsed.fragment:
        raise UnsafeDestinationError("Destination fragments are not allowed")

    host = _normalized_host(hostname)
    if _host_is_allowed(host):
        return

    resolved: set[ipaddress.IPv4Address | ipaddress.IPv6Address]
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            port = port or (443 if parsed.scheme.lower() == "https" else 80)
            addresses = socket.getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
            resolved = {ipaddress.ip_address(item[4][0]) for item in addresses}
        except (OSError, TypeError, ValueError) as exc:
            raise UnsafeDestinationError("Destination host could not be resolved") from exc
        if not resolved:
            raise UnsafeDestinationError("Destination host could not be resolved")
    else:
        resolved = {literal}

    if not all(_is_allowed_address(address) for address in resolved):
        raise UnsafeDestinationError("Destination resolves to a disallowed network")
    return tuple(sorted(str(address) for address in resolved))


def build_pinned_request(
    url: str, address: str | None
) -> tuple[str, dict[str, str], dict[str, str]]:
    if address is None:
        return url, {}, {}
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeDestinationError("Destination URL is invalid")
    try:
        port = parsed.port
        ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeDestinationError("Destination address is invalid") from exc

    literal = f"[{address}]" if ":" in address else address
    netloc = literal if port is None else f"{literal}:{port}"
    request_url = urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )
    try:
        host = hostname.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError as exc:
        raise UnsafeDestinationError("Destination host is invalid") from exc
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority = f"{authority}:{port}"
    extensions = {"sni_hostname": host} if parsed.scheme.lower() == "https" else {}
    return request_url, {"Host": authority}, extensions


async def validate_destination_async(url: str) -> tuple[str, ...] | None:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(validate_destination, url),
            timeout=settings.SCHEDULER_DNS_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise UnsafeDestinationError("Destination host could not be resolved") from exc
