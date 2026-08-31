import { describe, it, expect, vi } from 'vitest';
import {
  AuthApiError,
  createRefreshTokenStore,
  createPkceStore,
  generatePkcePair,
  generateOAuth2State,
  buildOAuth2AuthorizeUrl,
  oauth2Callback,
  validateRegisterForm,
  validateLoginForm,
  fetchProviders,
  registerUser,
  loginUser,
  logoutUser,
  refreshAccessToken,
  getCurrentUser,
  requestPasswordReset,
  confirmPasswordReset,
  bootstrapSession,
} from '../src/auth-client.js';

function jsonResponse(body, { ok = true, status = ok ? 200 : 400 } = {}) {
  return { ok, status, json: async () => body };
}

function fakeStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
}

describe('createRefreshTokenStore', () => {
  it('saves, loads, and clears the refresh token', () => {
    const store = createRefreshTokenStore(fakeStorage());
    expect(store.load()).toBeNull();

    store.save('refresh-abc');
    expect(store.load()).toBe('refresh-abc');

    store.clear();
    expect(store.load()).toBeNull();
  });

  it('does not throw when storage is unavailable', () => {
    const store = createRefreshTokenStore(null);
    expect(() => store.save('x')).not.toThrow();
    expect(store.load()).toBeNull();
    expect(() => store.clear()).not.toThrow();
  });
});

describe('validateRegisterForm', () => {
  it('accepts a well-formed submission', () => {
    const result = validateRegisterForm({ email: 'a@example.com', password: 'Str0ngPass!', displayName: 'Alice' });
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual({});
  });

  it('flags a malformed email', () => {
    const result = validateRegisterForm({ email: 'not-an-email', password: 'Str0ngPass!', displayName: 'Alice' });
    expect(result.valid).toBe(false);
    expect(result.errors.email).toBeDefined();
  });

  it('flags a missing display name', () => {
    const result = validateRegisterForm({ email: 'a@example.com', password: 'Str0ngPass!', displayName: '' });
    expect(result.valid).toBe(false);
    expect(result.errors.displayName).toBeDefined();
  });

  it('flags a too-short password', () => {
    const result = validateRegisterForm({ email: 'a@example.com', password: 'short', displayName: 'Alice' });
    expect(result.valid).toBe(false);
    expect(result.errors.password).toBeDefined();
  });
});

describe('validateLoginForm', () => {
  it('accepts a well-formed submission', () => {
    const result = validateLoginForm({ emailOrUsername: 'alice', password: 'Str0ngPass!' });
    expect(result.valid).toBe(true);
  });

  it('flags missing fields', () => {
    const result = validateLoginForm({ emailOrUsername: '', password: '' });
    expect(result.valid).toBe(false);
    expect(result.errors.emailOrUsername).toBeDefined();
    expect(result.errors.password).toBeDefined();
  });
});

describe('registerUser', () => {
  it('posts the registration payload and returns the parsed body', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ id: 'u1', email: 'a@example.com' }));
    const result = await registerUser(fetchImpl, { email: 'a@example.com', password: 'Str0ngPass!', displayName: 'Alice' });

    expect(result.id).toBe('u1');
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/register');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({
      email: 'a@example.com', password: 'Str0ngPass!', displayName: 'Alice', username: undefined,
    });
  });

  it('throws an AuthApiError with the server error envelope on failure', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ error: 'EMAIL_TAKEN', message: 'This email is already registered.' }, { ok: false, status: 409 }),
    );

    await expect(registerUser(fetchImpl, { email: 'a@example.com', password: 'x', displayName: 'A' }))
      .rejects.toBeInstanceOf(AuthApiError);
    try {
      await registerUser(fetchImpl, { email: 'a@example.com', password: 'x', displayName: 'A' });
    } catch (err) {
      expect(err.code).toBe('EMAIL_TAKEN');
      expect(err.status).toBe(409);
    }
  });
});

describe('loginUser', () => {
  it('returns tokens and user on success', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ access_token: 'at', refresh_token: 'rt', expires_in: 1800, user: { id: 'u1' } }),
    );
    const result = await loginUser(fetchImpl, { emailOrUsername: 'a@example.com', password: 'Str0ngPass!' });
    expect(result.access_token).toBe('at');
  });

  it('throws on invalid credentials', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ error: 'INVALID_CREDENTIALS', message: 'Wrong password.' }, { ok: false, status: 401 }),
    );
    await expect(loginUser(fetchImpl, { emailOrUsername: 'a@example.com', password: 'wrong' }))
      .rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' });
  });
});

describe('logoutUser', () => {
  it('sends the bearer token', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'Logged out successfully' }));
    await logoutUser(fetchImpl, 'at-123');
    const [, options] = fetchImpl.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer at-123');
  });
});

describe('refreshAccessToken', () => {
  it('posts the refresh token and returns a new access token', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ access_token: 'new-at', expires_in: 1800 }));
    const result = await refreshAccessToken(fetchImpl, 'rt-123');
    expect(result.access_token).toBe('new-at');
  });
});

describe('getCurrentUser', () => {
  it('sends the bearer token and returns the profile', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ id: 'u1', email: 'a@example.com' }));
    const result = await getCurrentUser(fetchImpl, 'at-123');
    expect(result.email).toBe('a@example.com');
    const [, options] = fetchImpl.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer at-123');
  });

  it('throws when the token is rejected', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ error: 'TOKEN_INVALID', message: 'Token invalid' }, { ok: false, status: 401 }),
    );
    await expect(getCurrentUser(fetchImpl, 'bad')).rejects.toMatchObject({ code: 'TOKEN_INVALID' });
  });
});

describe('fetchProviders', () => {
  it('returns the provider list', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ local_registration_enabled: true, local_login_enabled: true, oauth2_providers: [] }),
    );
    const result = await fetchProviders(fetchImpl);
    expect(result.local_registration_enabled).toBe(true);
  });
});

describe('password reset', () => {
  it('requests a reset link', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }));
    const result = await requestPasswordReset(fetchImpl, 'a@example.com');
    expect(result.message).toBe('ok');
  });

  it('confirms a reset with a token and new password', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ message: 'Password reset successful.' }));
    const result = await confirmPasswordReset(fetchImpl, { token: 'tok', newPassword: 'NewStr0ngPass!' });
    expect(result.message).toContain('reset');
  });
});

describe('PKCE helpers', () => {
  it('generates a verifier and a matching S256 challenge', async () => {
    const { verifier, challenge } = await generatePkcePair();
    expect(verifier.length).toBeGreaterThan(40);
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    const expected = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    expect(challenge).toBe(expected);
  });

  it('generates different pairs each time', async () => {
    const pair1 = await generatePkcePair();
    const pair2 = await generatePkcePair();
    expect(pair1.verifier).not.toBe(pair2.verifier);
  });

  it('generates a random state value', () => {
    expect(generateOAuth2State()).not.toBe(generateOAuth2State());
  });

  it('stores and clears the PKCE pair', () => {
    const store = createPkceStore(fakeStorage());
    expect(store.load()).toBeNull();
    store.save('state-1', 'verifier-1');
    expect(store.load()).toEqual({ state: 'state-1', verifier: 'verifier-1' });
    store.clear();
    expect(store.load()).toBeNull();
  });
});

describe('buildOAuth2AuthorizeUrl', () => {
  it('appends state and PKCE challenge params', () => {
    const url = buildOAuth2AuthorizeUrl('/api/auth/oauth2/authorize/azure', { state: 's1', challenge: 'c1' });
    expect(url).toContain('/api/auth/oauth2/authorize/azure?');
    expect(url).toContain('state=s1');
    expect(url).toContain('code_challenge=c1');
    expect(url).toContain('code_challenge_method=S256');
  });
});

describe('oauth2Callback', () => {
  it('posts the code, state, and verifier to the provider callback', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ access_token: 'at', refresh_token: 'rt', is_new_user: true, user: { id: 'u1' } }),
    );
    const result = await oauth2Callback(fetchImpl, 'azure', { code: 'c', state: 's', codeVerifier: 'v' });
    expect(result.access_token).toBe('at');
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/auth/oauth2/callback/azure');
    expect(JSON.parse(options.body)).toEqual({ code: 'c', state: 's', codeVerifier: 'v' });
  });

  it('throws an AuthApiError when the provider rejects the exchange', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ error: 'INVALID_CREDENTIALS', message: 'Provider authentication failed.' }, { ok: false, status: 401 }),
    );
    await expect(oauth2Callback(fetchImpl, 'azure', { code: 'c', state: 's', codeVerifier: 'v' }))
      .rejects.toBeInstanceOf(AuthApiError);
  });
});

describe('bootstrapSession', () => {
  it('returns null without calling fetch when there is no stored refresh token', async () => {
    const store = createRefreshTokenStore(fakeStorage());
    const fetchImpl = vi.fn();
    const result = await bootstrapSession(fetchImpl, store);
    expect(result).toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('exchanges a stored refresh token for an access token and profile', async () => {
    const store = createRefreshTokenStore(fakeStorage());
    store.save('rt-123');
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ access_token: 'new-at', expires_in: 1800 }))
      .mockResolvedValueOnce(jsonResponse({ id: 'u1', email: 'a@example.com', display_name: 'Alice' }));
    const result = await bootstrapSession(fetchImpl, store);
    expect(result).toEqual({ accessToken: 'new-at', expiresIn: 1800, user: { id: 'u1', email: 'a@example.com', display_name: 'Alice' } });
  });

  it('clears the stored refresh token and returns null when the refresh is rejected', async () => {
    const store = createRefreshTokenStore(fakeStorage());
    store.save('expired-rt');
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({ error: 'TOKEN_EXPIRED', message: 'Refresh token expired.' }, { ok: false, status: 401 }),
    );
    const result = await bootstrapSession(fetchImpl, store);
    expect(result).toBeNull();
    expect(store.load()).toBeNull();
  });

  it('clears the stored refresh token and returns null when the profile fetch fails', async () => {
    const store = createRefreshTokenStore(fakeStorage());
    store.save('rt-123');
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ access_token: 'new-at', expires_in: 1800 }))
      .mockResolvedValueOnce(jsonResponse({ error: 'TOKEN_INVALID', message: 'Token invalid' }, { ok: false, status: 401 }));
    const result = await bootstrapSession(fetchImpl, store);
    expect(result).toBeNull();
    expect(store.load()).toBeNull();
  });
});
