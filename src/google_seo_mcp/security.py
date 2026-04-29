"""Security primitives shared across the MCP.

Two responsibilities:

1. SSRF guard — reject URLs that resolve to non-public IPs (RFC1918,
   loopback, link-local, cloud metadata endpoints). Required because every
   ``fetch_*`` helper in this MCP accepts a URL string passed from an LLM
   that might be operating on prompt-injected input.
2. Untrusted-content wrapper — outputs that contain HTML, JSON-LD, OG
   tags or meta from third-party origins are tagged so the LLM knows not
   to follow instructions embedded in them.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlparse

# Hosts the LLM should never be able to reach via fetch_*.
# Cloud metadata services + AWS/GCP/Azure IMDS literal IPs.
_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "instance-data.ec2.internal",
})

# RFC1918 / loopback / link-local / multicast / reserved ranges
_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + AWS/GCP IMDS
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # unique local
    ipaddress.ip_network("fe80::/10"),       # link-local IPv6
]


class SSRFBlocked(RuntimeError):
    """Raised when a fetch target resolves to a non-public address."""


def assert_url_is_public(url: str) -> None:
    """Reject URLs that resolve to private / loopback / metadata hosts.

    Honors ``GOOGLE_SEO_ALLOW_PRIVATE_FETCH=true`` for legitimate test
    setups against staging on a private network. Default is BLOCK.
    """
    if os.getenv("GOOGLE_SEO_ALLOW_PRIVATE_FETCH") == "true":
        return

    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise SSRFBlocked(f"Refusing non-HTTP scheme: {p.scheme!r}")

    host = (p.hostname or "").lower()
    if not host:
        raise SSRFBlocked(f"URL has no hostname: {url!r}")
    if host in _BLOCKED_HOSTNAMES:
        raise SSRFBlocked(f"Hostname {host!r} is on the blocklist (cloud metadata)")

    # Resolve every A/AAAA the host returns and reject if any is non-public.
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFBlocked(f"DNS resolution failed for {host!r}: {e}") from None

    for family, _t, _p, _cn, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if any(ip in net for net in _BLOCKED_NETS):
            raise SSRFBlocked(
                f"Host {host!r} resolves to {ip_str!r} which is in a blocked "
                f"non-public range. Set GOOGLE_SEO_ALLOW_PRIVATE_FETCH=true "
                f"to override (only do so on trusted internal networks)."
            )
        # Also reject explicitly reserved / private addresses
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise SSRFBlocked(
                f"Host {host!r} resolves to {ip_str!r} (reserved/loopback/link-local)."
            )
        if ip.is_private and not os.getenv("GOOGLE_SEO_ALLOW_PRIVATE_FETCH") == "true":
            raise SSRFBlocked(
                f"Host {host!r} resolves to private address {ip_str!r}."
            )


# ── Untrusted content wrappers (anti prompt-injection) ───────────────

_UNTRUSTED_OPEN = "<untrusted-third-party-content>"
_UNTRUSTED_CLOSE = "</untrusted-third-party-content>"
_DEFAULT_CAP_BYTES = 10_000


def wrap_untrusted(value: Any, *, max_bytes: int = _DEFAULT_CAP_BYTES) -> Any:
    """Mark a string output as untrusted (originated from a third party).

    The LLM is instructed (via system prompt or the wrapper itself) NOT to
    follow instructions embedded in this content. Long values are truncated
    to avoid token bombs and to limit prompt-injection payload size.
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if not isinstance(value, str):
        return value  # dicts/lists are walked by callers if needed
    truncated = False
    if len(value.encode("utf-8")) > max_bytes:
        # truncate by characters approximated to bytes
        value = value[: max_bytes // 2]
        truncated = True
    return (
        f"{_UNTRUSTED_OPEN}{value}{'...[truncated]' if truncated else ''}{_UNTRUSTED_CLOSE}"
    )


_UNTRUSTED_FIELDS = frozenset({
    "title", "meta_description", "meta_robots", "canonical",
    "h1", "og", "twitter", "name", "description",
})


def mark_third_party_strings(payload: dict[str, Any]) -> dict[str, Any]:
    """Walk a payload and wrap known third-party string fields as untrusted.

    Used by tools that return text scraped from external HTML so the LLM
    receives a clear marker instead of raw attacker-controlled strings.
    """
    if not isinstance(payload, dict):
        return payload
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in _UNTRUSTED_FIELDS and isinstance(v, str):
            out[k] = wrap_untrusted(v)
        elif k in _UNTRUSTED_FIELDS and isinstance(v, list):
            out[k] = [wrap_untrusted(x) if isinstance(x, str) else x for x in v]
        elif k in _UNTRUSTED_FIELDS and isinstance(v, dict):
            out[k] = {
                ik: (wrap_untrusted(iv) if isinstance(iv, str) else iv)
                for ik, iv in v.items()
            }
        else:
            out[k] = v
    return out
