"""Phase K security review: SSRF protection for room-host-configured
generative-mode API base URLs (`server/game/story.py`).

Room hosts can configure a custom OpenAI-compatible `apiBaseUrl` for an AI
story character. That URL is later requested server-side (see
`_call_openai_compatible_endpoint` in `server/main.py`), so an
attacker-controlled room host could otherwise point the server at internal
network services or cloud metadata endpoints (SSRF, OWASP A10:2021).

This performs a best-effort, config-time check: only `http`/`https` schemes
are allowed, and known loopback/private/link-local/reserved IP literals are
rejected. Hostnames that are not IP literals cannot be fully validated
without a DNS lookup (a resolvable public hostname could still repoint to a
private address later — "DNS rebinding"); mitigating that fully would
require re-validating the resolved IP at request time, which is out of
scope for this check.
"""

import ipaddress
from urllib.parse import urlsplit

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def is_safe_external_url(url: str | None) -> bool:
    """Return True if `url` looks like a safe external http(s) address."""
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
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not an IP literal (e.g. a normal DNS hostname) — allow it; full
        # protection against DNS rebinding would require a request-time check.
        return True

    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )
