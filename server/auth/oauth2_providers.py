"""Builds the enabled OAuth2/OIDC provider registry from environment
variables (design doc §4.3 Azure Entra ID, §4.4 Cognito/Google/GitHub,
§5.2). A provider is "enabled" simply by having its client_id (and, for
Azure/Cognito, its tenant/domain) configured -- there is no separate
AUTH_ENABLE_OAUTH2 flag to keep in sync, since supplying real credentials
already is the opt-in.
"""

import os

from server.auth.oauth2 import OAuth2ProviderSettings


def _redirect_uri(env_var: str, provider_name: str, base_url: str) -> str:
    # This app has no client-side router, so the callback "page" is a real
    # static file (client/auth-callback.html) reading ?provider= from the
    # query string -- not a path segment as a router-based SPA would use.
    return os.getenv(env_var) or f"{base_url}/auth-callback.html?provider={provider_name}"


def _load_azure(base_url: str) -> OAuth2ProviderSettings | None:
    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    if not client_id or not tenant_id:
        return None
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    allowed_groups_raw = os.getenv("AZURE_ALLOWED_GROUPS", "")
    return OAuth2ProviderSettings(
        name="azure", provider_type="azure", client_id=client_id,
        client_secret=os.getenv("AZURE_CLIENT_SECRET", ""),
        redirect_uri=_redirect_uri("AZURE_REDIRECT_URI", "azure", base_url),
        authorization_endpoint=f"{authority}/oauth2/v2.0/authorize",
        token_endpoint=f"{authority}/oauth2/v2.0/token",
        jwks_uri=f"{authority}/discovery/v2.0/keys",
        issuer=f"{authority}/v2.0",
        scopes=["openid", "profile", "email"],
        allowed_groups=[g.strip() for g in allowed_groups_raw.split(",") if g.strip()],
        label="Sign in with Microsoft",
    )


def _load_google(base_url: str) -> OAuth2ProviderSettings | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return None
    return OAuth2ProviderSettings(
        name="google", provider_type="google", client_id=client_id,
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        redirect_uri=_redirect_uri("GOOGLE_REDIRECT_URI", "google", base_url),
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        issuer="https://accounts.google.com",
        scopes=["openid", "email", "profile"],
        label="Sign in with Google",
    )


def _load_github(base_url: str) -> OAuth2ProviderSettings | None:
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        return None
    return OAuth2ProviderSettings(
        name="github", provider_type="github", client_id=client_id,
        client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
        redirect_uri=_redirect_uri("GITHUB_REDIRECT_URI", "github", base_url),
        authorization_endpoint="https://github.com/login/oauth/authorize",
        token_endpoint="https://github.com/login/oauth/access_token",
        jwks_uri=None,
        issuer=None,
        scopes=["read:user", "user:email"],
        label="Sign in with GitHub",
    )


def _load_cognito(base_url: str) -> OAuth2ProviderSettings | None:
    client_id = os.getenv("COGNITO_CLIENT_ID")
    domain = os.getenv("COGNITO_DOMAIN")
    region = os.getenv("COGNITO_REGION")
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    if not client_id or not domain or not region or not user_pool_id:
        return None
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    return OAuth2ProviderSettings(
        name="cognito", provider_type="cognito", client_id=client_id,
        client_secret=os.getenv("COGNITO_CLIENT_SECRET", ""),
        redirect_uri=_redirect_uri("COGNITO_REDIRECT_URI", "cognito", base_url),
        authorization_endpoint=f"https://{domain}/oauth2/authorize",
        token_endpoint=f"https://{domain}/oauth2/token",
        jwks_uri=f"{issuer}/.well-known/jwks.json",
        issuer=issuer,
        scopes=["openid", "email", "profile"],
        label="Sign in with Amazon Cognito",
    )


def load_configured_providers(*, base_url: str) -> dict[str, OAuth2ProviderSettings]:
    providers = {}
    for loader in (_load_azure, _load_google, _load_github, _load_cognito):
        provider = loader(base_url)
        if provider is not None:
            providers[provider.name] = provider
    return providers
