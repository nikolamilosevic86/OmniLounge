import { createPkceStore, createRefreshTokenStore, oauth2Callback } from '../../src/auth-client.js';

const statusEl = document.getElementById('callback-status');
const bannerEl = document.getElementById('callback-banner');

function showError(message) {
  statusEl.textContent = 'Sign-in failed';
  bannerEl.textContent = message;
  bannerEl.className = 'auth-banner visible error';
}

async function run() {
  const params = new URLSearchParams(window.location.search);
  const provider = params.get('provider');
  const code = params.get('code');
  const returnedState = params.get('state');

  if (!provider || !code || !returnedState) {
    showError('Missing provider response. Please try signing in again.');
    return;
  }

  const pkceStore = createPkceStore();
  const saved = pkceStore.load();
  pkceStore.clear();

  // The saved `state` must match what we generated before redirecting away,
  // or this response didn't originate from the login attempt this tab made.
  if (!saved || saved.state !== returnedState) {
    showError('This sign-in link is no longer valid. Please try again.');
    return;
  }

  try {
    const result = await oauth2Callback(window.fetch.bind(window), provider, {
      code, state: returnedState, codeVerifier: saved.verifier,
    });
    createRefreshTokenStore().save(result.refresh_token);
    window.location.href = '/';
  } catch (err) {
    showError(err.message || 'Sign-in failed. Please try again.');
  }
}

run();
