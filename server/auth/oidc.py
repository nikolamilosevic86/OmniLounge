"""OIDC id_token verification via a provider's JWKS endpoint (design doc
§4.3 Azure Entra ID, §4.4 Google/Cognito, §10.3 OAuth2 security).

The id_token's signature is always verified against the issuing provider's
published public key (fetched fresh from `jwks_uri`) before any claim is
trusted -- an unverified id_token is exactly as dangerous as an unverified
password, since it asserts "this is who the user is".
"""

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

# Only RS256 is accepted. This also forbids the classic "alg=none" /
# algorithm-confusion attack, where a token claims no signature (or an HMAC
# signature checked against the public RSA key bytes) and PyJWT would
# otherwise accept it if asked to verify against "whatever alg the token
# says" instead of a fixed allowlist.
_ALLOWED_ALGORITHMS = ["RS256"]


class IdTokenVerificationError(Exception):
    """The id_token is malformed, expired, or fails signature/claim checks."""


class JwksUnavailableError(IdTokenVerificationError):
    """The provider's JWKS endpoint couldn't be reached (network/DNS/timeout
    failure, or a non-2xx response) -- distinct from a genuinely invalid
    token so callers can report a 503 (transient, retry-worthy) rather than
    a 401 (the token/credentials themselves were rejected)."""


async def _fetch_jwks(jwks_uri: str, http_client: httpx.AsyncClient) -> dict:
    response = await http_client.get(jwks_uri)
    response.raise_for_status()
    return response.json()


def _find_jwk(jwks: dict, kid: str) -> dict:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise IdTokenVerificationError(f"no matching signing key for kid={kid!r}")


async def verify_id_token(
    id_token: str, *, jwks_uri: str, audience: str, issuer: str, http_client: httpx.AsyncClient,
) -> dict:
    """Fetches the provider's JWKS, verifies the id_token's RS256 signature
    against the matching key, and validates `exp`/`aud`/`iss`. Returns the
    decoded claims on success; raises IdTokenVerificationError otherwise."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise IdTokenVerificationError(f"malformed id_token: {exc}") from exc

    if header.get("alg") not in _ALLOWED_ALGORITHMS:
        raise IdTokenVerificationError(f"unsupported id_token algorithm: {header.get('alg')!r}")

    kid = header.get("kid")
    if not kid:
        raise IdTokenVerificationError("id_token header is missing 'kid'")

    try:
        jwks = await _fetch_jwks(jwks_uri, http_client)
    except httpx.HTTPError as exc:
        raise JwksUnavailableError(f"failed to fetch signing keys: {exc}") from exc

    jwk = _find_jwk(jwks, kid)
    try:
        public_key = RSAAlgorithm.from_jwk(jwk)
    except (ValueError, TypeError) as exc:
        raise IdTokenVerificationError(f"invalid signing key: {exc}") from exc

    try:
        return jwt.decode(
            id_token, key=public_key, algorithms=_ALLOWED_ALGORITHMS, audience=audience, issuer=issuer,
        )
    except jwt.PyJWTError as exc:
        raise IdTokenVerificationError(str(exc)) from exc
