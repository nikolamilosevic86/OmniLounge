"""Phase K security review: SSRF protection for room-host-configured
generative-mode API base URLs (`server/game/story.py`).

Room hosts can configure a custom OpenAI-compatible `apiBaseUrl` for an AI
story character. That URL is later requested server-side (see
`_call_openai_compatible_endpoint` in `server/main.py`), so an
attacker-controlled room host could otherwise point the server at internal
network services or cloud metadata endpoints (SSRF, OWASP A10:2021).

This performs a best-effort check: only `http`/`https` schemes are allowed,
and known loopback/private/link-local/reserved IP literals are rejected.
Hostnames that are not IP literals are additionally RESOLVED and every
address they resolve to is checked, so an attacker cannot simply point a
public DNS name at `169.254.169.254` or `127.0.0.1`. Names in internal-only
namespaces (`.internal`, `.local`, ...) are rejected outright, since inside
a cloud VPC those resolve to real internal hosts.

Residual risk: DNS rebinding -- a name that resolves publicly (or not at
all) here could return a private address on the later, separate
request-time lookup. Closing that requires pinning the validated IP and
connecting to it directly, which is out of scope for a config-time check.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}

# Names that never legitimately identify a public API endpoint but do
# resolve (or are intercepted) inside common cloud environments.
_BLOCKED_HOSTNAME_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".localdomain",
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Note: Python already reports IPv4-mapped and 6to4 forms such as
    # `::ffff:127.0.0.1` as private, so no unwrapping is needed here.
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _resolves_to_blocked_address(hostname: str, resolver) -> bool:
    """True if `hostname` demonstrably resolves to a non-public address.

    Lookup failures fail OPEN. That sounds backwards, but the attack being
    closed here is "point a public-looking domain at 169.254.169.254", which
    requires the name to resolve. A name that does not resolve cannot reach
    anything, so the later HTTP request simply fails -- rejecting it would
    only break legitimate placeholder/offline/split-horizon configurations
    without removing any reachable target.
    """
    try:
        infos = resolver(hostname, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return False

    addresses = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            addresses.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue

    return any(_is_blocked_ip(ip) for ip in addresses)


def is_safe_external_url(url: str | None, resolver=socket.getaddrinfo) -> bool:
    """Return True if `url` looks like a safe external http(s) address.

    `resolver` matches the `socket.getaddrinfo` signature and exists so
    tests can inject a deterministic, offline stub.
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parts = urlsplit(url)
    except ValueError:
        return False

    if parts.scheme not in ("http", "https"):
        return False

    try:
        hostname = parts.hostname
    except ValueError:
        return False
    if not hostname:
        return False

    normalized = hostname.lower().rstrip(".")
    if normalized in _BLOCKED_HOSTNAMES:
        return False
    if normalized.endswith(_BLOCKED_HOSTNAME_SUFFIXES):
        return False

    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        # Not an IP literal -- resolve it and check every returned address.
        return not _resolves_to_blocked_address(normalized, resolver)

    return not _is_blocked_ip(ip)
