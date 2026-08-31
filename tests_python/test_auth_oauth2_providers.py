"""Unit tests for server/auth/oauth2_providers.py: building the enabled
OAuth2 provider registry from environment variables (design doc §4.3, §4.4,
§5.2). A provider is considered "enabled" once its client_id (and, for
Azure/Cognito, its tenant/domain) env vars are set -- there is no separate
ENABLE_* flag, since supplying real credentials is itself the opt-in."""

from server.auth.oauth2_providers import load_configured_providers


class TestNoProvidersConfigured:
    def test_returns_an_empty_registry_when_no_env_vars_are_set(self, monkeypatch):
        for name in [
            "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_REDIRECT_URI",
            "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
            "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_REDIRECT_URI",
            "COGNITO_CLIENT_ID", "COGNITO_CLIENT_SECRET", "COGNITO_DOMAIN", "COGNITO_REGION",
            "COGNITO_USER_POOL_ID", "COGNITO_REDIRECT_URI",
        ]:
            monkeypatch.delenv(name, raising=False)
        providers = load_configured_providers(base_url="https://app.example.com")
        assert providers == {}


class TestAzureProvider:
    def test_enabled_when_client_id_and_tenant_id_are_set(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "az-client")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "az-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.delenv("AZURE_REDIRECT_URI", raising=False)
        providers = load_configured_providers(base_url="https://app.example.com")

        assert "azure" in providers
        provider = providers["azure"]
        assert provider.client_id == "az-client"
        assert provider.client_secret == "az-secret"
        assert provider.authorization_endpoint == "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/authorize"
        assert provider.token_endpoint == "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token"
        assert provider.jwks_uri == "https://login.microsoftonline.com/tenant-123/discovery/v2.0/keys"
        assert provider.issuer == "https://login.microsoftonline.com/tenant-123/v2.0"
        assert provider.redirect_uri == "https://app.example.com/auth-callback.html?provider=azure"
        assert provider.allowed_groups == []

    def test_parses_allowed_groups_from_a_comma_separated_env_var(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "az-client")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_ALLOWED_GROUPS", "group-a, group-b ,group-c")
        providers = load_configured_providers(base_url="https://app.example.com")
        assert providers["azure"].allowed_groups == ["group-a", "group-b", "group-c"]

    def test_disabled_when_tenant_id_is_missing(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "az-client")
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        providers = load_configured_providers(base_url="https://app.example.com")
        assert "azure" not in providers

    def test_redirect_uri_env_var_overrides_the_default(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "az-client")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_REDIRECT_URI", "https://custom.example.com/cb")
        providers = load_configured_providers(base_url="https://app.example.com")
        assert providers["azure"].redirect_uri == "https://custom.example.com/cb"


class TestGoogleProvider:
    def test_enabled_when_client_id_is_set(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "g-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "g-secret")
        providers = load_configured_providers(base_url="https://app.example.com")

        provider = providers["google"]
        assert provider.authorization_endpoint == "https://accounts.google.com/o/oauth2/v2/auth"
        assert provider.jwks_uri == "https://www.googleapis.com/oauth2/v3/certs"
        assert provider.issuer == "https://accounts.google.com"
        assert provider.redirect_uri == "https://app.example.com/auth-callback.html?provider=google"


class TestGithubProvider:
    def test_enabled_when_client_id_is_set_and_has_no_jwks(self, monkeypatch):
        monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-client")
        monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret")
        providers = load_configured_providers(base_url="https://app.example.com")

        provider = providers["github"]
        assert provider.provider_type == "github"
        assert provider.jwks_uri is None
        assert provider.issuer is None
        assert provider.authorization_endpoint == "https://github.com/login/oauth/authorize"


class TestCognitoProvider:
    def test_enabled_when_all_required_vars_are_set(self, monkeypatch):
        monkeypatch.setenv("COGNITO_CLIENT_ID", "c-client")
        monkeypatch.setenv("COGNITO_CLIENT_SECRET", "c-secret")
        monkeypatch.setenv("COGNITO_DOMAIN", "hobbo.auth.us-east-1.amazoncognito.com")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_abc123")
        providers = load_configured_providers(base_url="https://app.example.com")

        provider = providers["cognito"]
        assert provider.authorization_endpoint == "https://hobbo.auth.us-east-1.amazoncognito.com/oauth2/authorize"
        assert provider.jwks_uri == (
            "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123/.well-known/jwks.json"
        )
        assert provider.issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123"

    def test_disabled_when_user_pool_id_is_missing(self, monkeypatch):
        monkeypatch.setenv("COGNITO_CLIENT_ID", "c-client")
        monkeypatch.setenv("COGNITO_DOMAIN", "hobbo.auth.us-east-1.amazoncognito.com")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")
        monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
        providers = load_configured_providers(base_url="https://app.example.com")
        assert "cognito" not in providers
