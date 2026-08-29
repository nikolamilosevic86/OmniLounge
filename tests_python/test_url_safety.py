import socket

import pytest

from server.game.url_safety import is_safe_external_url


def _resolver_returning(*ips):
    """Build a `socket.getaddrinfo`-shaped stub so hostname tests never
    touch real DNS (deterministic and offline-safe)."""
    def resolver(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))
            for ip in ips
        ]
    return resolver


def _failing_resolver(host, port, *args, **kwargs):
    raise socket.gaierror("name or service not known")


_PUBLIC = _resolver_returning("93.184.216.34")


class TestIsSafeExternalUrl:
    @pytest.mark.parametrize("url", [
        "https://api.openai.com/v1",
        "https://api.example.com/v1",
        "http://api.example.com:8080/v1",
    ])
    def test_accepts_ordinary_public_http_https_urls(self, url):
        assert is_safe_external_url(url, resolver=_PUBLIC) is True

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/v1",
        "http://localhost/v1",
        "http://localhost.localdomain/v1",
        "http://[::1]/v1",
        "http://10.0.0.5/v1",
        "http://172.16.0.5/v1",
        "http://192.168.1.5/v1",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/v1",
    ])
    def test_rejects_loopback_private_and_link_local_addresses(self, url):
        assert is_safe_external_url(url) is False

    @pytest.mark.parametrize("url", [
        "ftp://example.com/v1",
        "file:///etc/passwd",
        "gopher://example.com",
        "",
        None,
        "not-a-url",
    ])
    def test_rejects_non_http_schemes_and_malformed_input(self, url):
        assert is_safe_external_url(url) is False

    @pytest.mark.parametrize("url", [
        "http:///v1",
        "http://",
        "http:///path?query=1",
    ])
    def test_rejects_urls_with_no_hostname(self, url):
        assert is_safe_external_url(url) is False

    def test_rejects_malformed_ipv6_bracket_literal(self):
        # An unterminated/invalid IPv6 bracket makes urlsplit itself raise
        # ValueError -- this must be treated as unsafe, not crash the caller.
        assert is_safe_external_url("http://[::1") is False


class TestHostnameResolutionSsrfGuard:
    """A public-looking DNS name is the obvious way around an IP-literal
    blocklist: the attacker just points their own domain at an internal
    address. These cover that bypass."""

    @pytest.mark.parametrize("internal_ip", [
        "169.254.169.254",  # cloud instance metadata
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.5",
        "172.16.0.5",
    ])
    def test_rejects_public_hostname_resolving_to_internal_address(self, internal_ip):
        resolver = _resolver_returning(internal_ip)
        assert is_safe_external_url("https://evil.example.com/v1", resolver=resolver) is False

    def test_rejects_when_any_resolved_address_is_internal(self):
        # A multi-record name must be rejected if *any* answer is internal,
        # otherwise the attacker just adds one public A record as cover.
        resolver = _resolver_returning("93.184.216.34", "169.254.169.254")
        assert is_safe_external_url("https://evil.example.com/v1", resolver=resolver) is False

    def test_allows_unresolvable_hostname_fail_open(self):
        # Deliberate: a name that does not resolve cannot reach any internal
        # service, so rejecting it would only break legitimate placeholder
        # and offline configurations. See the module docstring.
        assert is_safe_external_url("https://nope.invalid/v1", resolver=_failing_resolver) is True

    def test_allows_hostname_with_no_resolved_addresses(self):
        assert is_safe_external_url("https://empty.example.com/v1", resolver=_resolver_returning()) is True

    @pytest.mark.parametrize("url", [
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://db.internal/v1",
        "http://printer.local/v1",
        "http://foo.localhost/v1",
        "http://box.localdomain/v1",
    ])
    def test_rejects_internal_only_hostname_suffixes_without_dns(self, url):
        # These must be rejected on the name alone -- inside a cloud VPC they
        # resolve to real internal hosts, so we cannot rely on the lookup.
        assert is_safe_external_url(url, resolver=_PUBLIC) is False

    def test_rejects_trailing_dot_localhost(self):
        # "localhost." is a fully-qualified form of the same name and must
        # not slip past the exact-match blocklist.
        assert is_safe_external_url("http://localhost./v1", resolver=_PUBLIC) is False

    def test_rejects_uppercase_localhost(self):
        assert is_safe_external_url("http://LOCALHOST/v1", resolver=_PUBLIC) is False

    def test_accepts_public_hostname_resolving_to_public_address(self):
        assert is_safe_external_url("https://api.openai.com/v1", resolver=_PUBLIC) is True

    def test_uses_real_resolver_by_default(self):
        # The default must be the live resolver, otherwise the production
        # call sites would silently skip the DNS check entirely. Asserted on
        # the signature so the test needs no network.
        import inspect
        default = inspect.signature(is_safe_external_url).parameters["resolver"].default
        assert default is socket.getaddrinfo

    def test_blocklisted_suffix_check_runs_before_any_lookup(self):
        def exploding_resolver(*args, **kwargs):
            raise AssertionError("resolver must not be called for blocked names")

        assert is_safe_external_url(
            "http://metadata.google.internal/", resolver=exploding_resolver
        ) is False

