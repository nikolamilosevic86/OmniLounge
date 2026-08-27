import pytest

from server.game.url_safety import is_safe_external_url


class TestIsSafeExternalUrl:
    @pytest.mark.parametrize("url", [
        "https://api.openai.com/v1",
        "https://api.example.com/v1",
        "http://api.example.com:8080/v1",
    ])
    def test_accepts_ordinary_public_http_https_urls(self, url):
        assert is_safe_external_url(url) is True

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

