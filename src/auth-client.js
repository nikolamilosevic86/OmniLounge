const REFRESH_TOKEN_STORAGE_KEY = 'hobboverse-refresh-token';
const PKCE_STORAGE_KEY = 'hobboverse-oauth2-pkce';

/** Thrown for any non-2xx auth API response; carries the server's error
 * envelope (design doc §7.1.x: { error, message, details }). */
export class AuthApiError extends Error {
  constructor(body, status) {
    super(body?.message || 'Request failed');
    this.code = body?.error || 'UNKNOWN';
    this.details = body?.details || {};
    this.status = status;
  }
}

function base64UrlEncode(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** RFC 7636 S256 PKCE pair: a high-entropy verifier and its SHA-256
 * challenge. State/verifier are the frontend's responsibility (design doc
 * §7.1.6/§7.1.7) -- the backend never sees or stores the verifier until the
 * callback request hands it over for the provider itself to check. */
export async function generatePkcePair() {
  const verifierBytes = new Uint8Array(64);
  crypto.getRandomValues(verifierBytes);
  const verifier = base64UrlEncode(verifierBytes);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = base64UrlEncode(new Uint8Array(digest));
  return { verifier, challenge };
}

export function generateOAuth2State() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

/** Persists {state, verifier} across the redirect to the provider and back
 * (design doc §19.6 token-storage notes apply to the verifier too). */
export function createPkceStore(storage = defaultSessionStorage()) {
  return {
    save(state, verifier) {
      try {
        storage?.setItem(PKCE_STORAGE_KEY, JSON.stringify({ state, verifier }));
      } catch {
        // Nothing to do if storage is unavailable.
      }
    },
    load() {
      try {
        const raw = storage?.getItem(PKCE_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
      } catch {
        return null;
      }
    },
    clear() {
      try {
        storage?.removeItem(PKCE_STORAGE_KEY);
      } catch {
        // Nothing to do if storage is unavailable.
      }
    },
  };
}

/** Refresh tokens live in sessionStorage (design doc §19.6), never
 * localStorage. `storage` is injectable so this stays testable under
 * vitest's plain "node" environment, which has no sessionStorage global. */
export function createRefreshTokenStore(storage = defaultSessionStorage()) {
  return {
    save(token) {
      try {
        storage?.setItem(REFRESH_TOKEN_STORAGE_KEY, token);
      } catch {
        // Storage can be unavailable (private browsing, quota) -- losing the
        // refresh token just means an earlier re-login, not a crash.
      }
    },
    load() {
      try {
        return storage?.getItem(REFRESH_TOKEN_STORAGE_KEY) ?? null;
      } catch {
        return null;
      }
    },
    clear() {
      try {
        storage?.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      } catch {
        // Nothing to do if storage is unavailable.
      }
    },
  };
}

function defaultSessionStorage() {
  return typeof sessionStorage !== 'undefined' ? sessionStorage : null;
}

/** Loose client-side checks only, for fast UX feedback -- the backend's
 * password policy (server/auth/passwords.py) is the actual source of truth
 * and is re-validated on every request regardless of what this returns. */
export function validateRegisterForm({ email, password, displayName }) {
  const errors = {};
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Enter a valid email address.';
  }
  if (!displayName || displayName.trim().length === 0) {
    errors.displayName = 'Display name is required.';
  }
  if (!password || password.length < 8) {
    errors.password = 'Password must be at least 8 characters.';
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateLoginForm({ emailOrUsername, password }) {
  const errors = {};
  if (!emailOrUsername || emailOrUsername.trim().length === 0) {
    errors.emailOrUsername = 'Email or username is required.';
  }
  if (!password) {
    errors.password = 'Password is required.';
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

async function parseJsonBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function postJson(fetchImpl, path, payload, headers = {}) {
  const response = await fetchImpl(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(payload),
  });
  const body = await parseJsonBody(response);
  if (!response.ok) {
    throw new AuthApiError(body, response.status);
  }
  return body;
}

export async function fetchProviders(fetchImpl) {
  const response = await fetchImpl('/api/auth/providers');
  const body = await parseJsonBody(response);
  if (!response.ok) {
    throw new AuthApiError(body, response.status);
  }
  return body;
}

export async function registerUser(fetchImpl, { email, password, displayName, username }) {
  return postJson(fetchImpl, '/api/auth/register', { email, password, displayName, username });
}

export async function loginUser(fetchImpl, { emailOrUsername, password }) {
  return postJson(fetchImpl, '/api/auth/login', { emailOrUsername, password });
}

export async function logoutUser(fetchImpl, accessToken) {
  return postJson(fetchImpl, '/api/auth/logout', {}, { Authorization: `Bearer ${accessToken}` });
}

export async function refreshAccessToken(fetchImpl, refreshToken) {
  return postJson(fetchImpl, '/api/auth/refresh', { refreshToken });
}

export function buildOAuth2AuthorizeUrl(authorizeUrl, { state, challenge }) {
  const url = new URL(authorizeUrl, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
  url.searchParams.set('state', state);
  url.searchParams.set('code_challenge', challenge);
  url.searchParams.set('code_challenge_method', 'S256');
  return url.toString();
}

export async function oauth2Callback(fetchImpl, provider, { code, state, codeVerifier }) {
  return postJson(fetchImpl, `/api/auth/oauth2/callback/${encodeURIComponent(provider)}`, { code, state, codeVerifier });
}

export async function getCurrentUser(fetchImpl, accessToken) {
  const response = await fetchImpl('/api/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const body = await parseJsonBody(response);
  if (!response.ok) {
    throw new AuthApiError(body, response.status);
  }
  return body;
}

export async function requestPasswordReset(fetchImpl, email) {
  return postJson(fetchImpl, '/api/auth/password-reset/request', { email });
}

export async function confirmPasswordReset(fetchImpl, { token, newPassword }) {
  return postJson(fetchImpl, '/api/auth/password-reset/confirm', { token, newPassword });
}

/** Restores a session from a previously stored refresh token, e.g. on page
 * load -- so a returning logged-in player doesn't have to sign in again
 * every time they open the game. Returns null (and clears the stored
 * refresh token, so future loads don't keep retrying a dead one) if there
 * is no refresh token, or if it's no longer valid. */
export async function bootstrapSession(fetchImpl, refreshTokenStore) {
  const refreshToken = refreshTokenStore.load();
  if (!refreshToken) return null;
  try {
    const { access_token: accessToken, expires_in: expiresIn } = await refreshAccessToken(fetchImpl, refreshToken);
    const user = await getCurrentUser(fetchImpl, accessToken);
    return { accessToken, expiresIn, user };
  } catch {
    refreshTokenStore.clear();
    return null;
  }
}
