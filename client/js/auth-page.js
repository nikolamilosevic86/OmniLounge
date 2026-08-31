import {
  AuthApiError,
  createRefreshTokenStore,
  createPkceStore,
  generatePkcePair,
  generateOAuth2State,
  buildOAuth2AuthorizeUrl,
  validateLoginForm,
  validateRegisterForm,
  fetchProviders,
  loginUser,
  registerUser,
} from '../../src/auth-client.js';

const refreshTokenStore = createRefreshTokenStore();
const pkceStore = createPkceStore();

const loginTabBtn = document.getElementById('login-tab-btn');
const registerTabBtn = document.getElementById('register-tab-btn');
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const authTitle = document.getElementById('auth-title');
const authBanner = document.getElementById('auth-banner');
const registrationToggle = document.getElementById('registration-toggle');
const loginToggle = document.getElementById('login-toggle');
const showRegisterBtn = document.getElementById('show-register-btn');
const showLoginBtn = document.getElementById('show-login-btn');
const oauth2ProvidersEl = document.getElementById('oauth2-providers');
const oauth2DividerEl = document.getElementById('oauth2-divider');
const guestLinkEl = document.getElementById('guest-link');

function showBanner(message, kind = 'error') {
  authBanner.textContent = message;
  authBanner.className = `auth-banner visible ${kind}`;
}

function clearBanner() {
  authBanner.textContent = '';
  authBanner.className = 'auth-banner';
}

function setFieldError(id, message) {
  const el = document.getElementById(id);
  if (el) el.textContent = message || '';
}

function clearFieldErrors(ids) {
  ids.forEach((id) => setFieldError(id, ''));
}

function showTab(tab) {
  const isLogin = tab === 'login';
  loginForm.hidden = !isLogin;
  registerForm.hidden = isLogin;
  loginTabBtn.classList.toggle('active', isLogin);
  registerTabBtn.classList.toggle('active', !isLogin);
  authTitle.textContent = isLogin ? 'Welcome back' : 'Create your account';
  clearBanner();
}

loginTabBtn.addEventListener('click', () => showTab('login'));
registerTabBtn.addEventListener('click', () => showTab('register'));
showRegisterBtn?.addEventListener('click', () => showTab('register'));
showLoginBtn?.addEventListener('click', () => showTab('login'));

function redirectToApp() {
  const params = new URLSearchParams(window.location.search);
  window.location.href = params.get('redirect') || '/';
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearBanner();
  clearFieldErrors(['login-email-error', 'login-password-error']);

  const emailOrUsername = document.getElementById('login-email-input').value.trim();
  const password = document.getElementById('login-password-input').value;

  const { valid, errors } = validateLoginForm({ emailOrUsername, password });
  if (!valid) {
    setFieldError('login-email-error', errors.emailOrUsername);
    setFieldError('login-password-error', errors.password);
    return;
  }

  const submitBtn = document.getElementById('login-submit-btn');
  submitBtn.disabled = true;
  try {
    const result = await loginUser(window.fetch.bind(window), { emailOrUsername, password });
    refreshTokenStore.save(result.refresh_token);
    redirectToApp();
  } catch (err) {
    showBanner(err instanceof AuthApiError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    submitBtn.disabled = false;
  }
});

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearBanner();
  clearFieldErrors(['register-name-error', 'register-email-error', 'register-password-error']);

  const displayName = document.getElementById('register-name-input').value.trim();
  const email = document.getElementById('register-email-input').value.trim();
  const password = document.getElementById('register-password-input').value;

  const { valid, errors } = validateRegisterForm({ email, password, displayName });
  if (!valid) {
    setFieldError('register-name-error', errors.displayName);
    setFieldError('register-email-error', errors.email);
    setFieldError('register-password-error', errors.password);
    return;
  }

  const submitBtn = document.getElementById('register-submit-btn');
  submitBtn.disabled = true;
  try {
    await registerUser(window.fetch.bind(window), { email, password, displayName });
    showTab('login');
    document.getElementById('login-email-input').value = email;
    showBanner('Account created. You can sign in now.', 'success');
  } catch (err) {
    showBanner(err instanceof AuthApiError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    submitBtn.disabled = false;
  }
});

async function initProviders() {
  try {
    const providers = await fetchProviders(window.fetch.bind(window));
    if (providers.local_registration_enabled) {
      registerTabBtn.hidden = false;
      registrationToggle.hidden = false;
      loginToggle.hidden = false;
    }
    // Defaults to allowed if the field is somehow missing, matching the
    // backend's own AUTH_ALLOW_GUEST_ACCESS default (fail open to the
    // existing anonymous-play experience, not fail closed).
    if (providers.allow_guest_access !== false && guestLinkEl) {
      guestLinkEl.hidden = false;
    }
    if (providers.oauth2_providers?.length) {
      oauth2DividerEl.hidden = false;
      oauth2ProvidersEl.hidden = false;
      for (const provider of providers.oauth2_providers) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'auth-provider-btn';
        btn.textContent = provider.label;
        btn.addEventListener('click', async () => {
          const { verifier, challenge } = await generatePkcePair();
          const state = generateOAuth2State();
          pkceStore.save(state, verifier);
          window.location.href = buildOAuth2AuthorizeUrl(provider.authorize_url, { state, challenge });
        });
        oauth2ProvidersEl.appendChild(btn);
      }
    }
  } catch {
    // The login form still works without provider metadata; failing quietly
    // here just means the registration tab/OAuth2 buttons stay hidden. The
    // guest link fails *open* instead (shown), matching the backend's own
    // AUTH_ALLOW_GUEST_ACCESS default -- a metadata fetch hiccup should
    // never be the reason a normally-anonymous game becomes unreachable.
    if (guestLinkEl) guestLinkEl.hidden = false;
  }
}

initProviders();
