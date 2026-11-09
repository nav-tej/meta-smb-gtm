'use strict';
// Same-origin account UI. Session credentials are server-managed HttpOnly cookies.
(() => {
  if (window.museAccount) return;
  const root = '/api/v1/account';
  let snapshot = { configured: false, user: null, usage: null, live_available: false };
  let accountEpoch = 0;
  let workspaceVersion = 0;
  let workspaceOwner = null;
  let mode = 'signin';
  let busy = false;
  let dialog;
  let form;
  let title;
  let description;
  let email;
  let password;
  let passwordLabel;
  let emailLabel;
  let submit;
  let message;
  let tabs;
  let googleButton;
  let divider;
  let recover;
  let accountButton;
  let signupButton;
  let signoutButton;
  let quotaLabel;
  const copy = value => JSON.parse(JSON.stringify(value));
  const node = (tag, attrs = {}, text = '') => {
    const element = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs)) element.setAttribute(name, value);
    element.textContent = text;
    return element;
  };
  function say(text, error = false) {
    if (!message) return;
    message.textContent = text;
    message.className = error ? 'ma-message ma-error' : 'ma-message';
  }
  const AUTH_PATHS = new Set(['/me', '/signin', '/signup', '/oauth', '/recover', '/password', '/callback', '/signout']);
  async function request(path, method = 'GET', body, extraHeaders = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(root + path, {
        method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...extraHeaders },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal
      });
      let data = {};
      try { data = await response.json(); } catch { /* A gateway may return HTML. */ }
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : data.detail?.message;
        const error = new Error(detail || (response.status === 429 ? 'Your current allowance is used. Try again when it resets.' : response.status === 409 ? 'A newer draft is saved. Load it before saving again.' : 'We could not complete that request. Your draft is still here.'));
        error.status = response.status;
        if (response.status === 401 && snapshot.user && !AUTH_PATHS.has(path)) sessionEnded('Your session ended, so this was not saved to your account. Sign in again; your draft is still on this device.');
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The account server took too long. Your draft is still here.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function update(data) {
    const previous = snapshot.user?.id || null;
    const user = data?.user && typeof data.user.id === 'string' ? {
      id: data.user.id, email: String(data.user.email || ''), email_verified: data.user.email_verified === true
    } : null;
    snapshot = { configured: data?.configured === true, user, usage: data?.usage || null, live_available: data?.live_available === true };
    if (previous !== (user?.id || null)) { accountEpoch += 1; workspaceVersion = 0; workspaceOwner = null; }
    renderAccount();
    const detail = copy(snapshot);
    window.dispatchEvent(new CustomEvent('muse:account-change', { detail }));
    window.dispatchEvent(new CustomEvent('account-change', { detail: copy(snapshot) }));
    return copy(snapshot);
  }
  async function refresh() {
    const epoch = accountEpoch;
    const data = await request('/me');
    if (epoch !== accountEpoch) return copy(snapshot);
    return update(data);
  }
  function renderAccount() {
    if (!accountButton) return;
    const user = snapshot.user;
    accountButton.hidden = !snapshot.configured;
    // Signed out: a clear "Create free account" button; run counts only show once signed in.
    signupButton.hidden = !snapshot.configured || !!user;
    quotaLabel.hidden = !snapshot.configured || !user;
    accountButton.textContent = user ? 'Your account' : 'Sign in';
    accountButton.setAttribute('aria-label', user ? `Account for ${user.email}` : 'Sign in or create an account');
    signoutButton.hidden = !user;
    if (!user) quotaLabel.textContent = '';
    else if (!user.email_verified) quotaLabel.textContent = 'Confirm your email to generate';
    else if (snapshot.usage && snapshot.usage.plan === 'unlimited' && snapshot.live_available) quotaLabel.textContent = 'Unlimited runs';
    else if (snapshot.usage && Number.isFinite(snapshot.usage.remaining)) quotaLabel.textContent = `${Math.max(0, snapshot.usage.remaining)} of ${snapshot.usage.limit} runs left`;
    else quotaLabel.textContent = snapshot.live_available ? 'Muse generation available' : 'Live generation unavailable';
  }
  function setBusy(value) {
    busy = value;
    if (!form) return;
    form.querySelectorAll('button, input').forEach(element => { element.disabled = value; });
    submit.setAttribute('aria-busy', String(value));
    if (googleButton) { googleButton.disabled = value; googleButton.setAttribute('aria-busy', String(value)); }
    if (signoutButton) signoutButton.disabled = value;
  }
  function setMode(next, text = '') {
    mode = ['signin', 'signup', 'recover', 'password', 'account'].includes(next) ? next : 'signin';
    const signedIn = mode === 'account';
    const passwordOnly = mode === 'password';
    const showGoogle = !signedIn && !passwordOnly && mode !== 'recover';
    title.textContent = { signin: 'Welcome back.', signup: 'Make it your studio.', recover: 'Reset your password.', password: 'Choose a new password.', account: 'Your Muse account' }[mode];
    description.textContent = signedIn ? `${snapshot.user?.email || ''}${snapshot.user?.email_verified ? ' · email confirmed' : ' · confirm your email to generate'}` : mode === 'signup' ? 'Save your work and unlock 3 free Muse runs.' : mode === 'recover' ? 'We’ll send a password reset link if an account exists.' : passwordOnly ? 'Use at least 12 characters. Your draft stays here.' : 'Sign in to generate with Muse and save your work.';
    if (googleButton) googleButton.hidden = !showGoogle;
    if (divider) divider.hidden = !showGoogle;
    emailLabel.hidden = passwordOnly || signedIn;
    email.hidden = passwordOnly || signedIn;
    email.required = !passwordOnly && !signedIn;
    passwordLabel.hidden = mode === 'recover' || signedIn;
    password.hidden = mode === 'recover' || signedIn;
    password.required = mode !== 'recover' && !signedIn;
    password.autocomplete = mode === 'signin' ? 'current-password' : 'new-password';
    password.minLength = mode === 'signin' ? 1 : 12;
    password.value = '';
    submit.hidden = signedIn;
    submit.textContent = { signin: 'Sign in', signup: 'Create account', recover: 'Send reset link', password: 'Update password' }[mode] || 'Continue';
    tabs.hidden = signedIn || passwordOnly;
    recover.hidden = mode !== 'signin';
    say(text || (signedIn ? quotaLabel.textContent : 'Saved examples remain available without an account.'));
  }
  const track = (name, props) => { try { window.museTrack?.(name, props); } catch {} };
  function open(next = 'signin', text = '') {
    if (!dialog) mount();
    if (busy || !dialog) return;
    track('auth_dialog_opened', { mode: snapshot.user && next === 'signin' ? 'account' : next });
    setMode(snapshot.user && next === 'signin' ? 'account' : next, text);
    if (!dialog.open) dialog.showModal();
    if (!snapshot.configured) say('Account setup is unavailable on this server. Your saved demo and draft still work.', true);
  }
  function liveReady() {
    if (!snapshot.user) { open('signup', 'Create an account or sign in to make a new Muse generation. Your current draft stays here.'); return false; }
    if (!snapshot.user.email_verified) { open('account', 'Confirm your email using the signup link, then refresh your account.'); return false; }
    if (!snapshot.live_available || (snapshot.usage && snapshot.usage.remaining !== null && snapshot.usage.remaining <= 0)) {
      const usedUp = snapshot.usage && snapshot.usage.remaining !== null && snapshot.usage.remaining <= 0;
      if (usedUp) { try { window.museTrack?.('runs_exhausted', { plan: snapshot.usage.plan }); } catch {} }
      if (usedUp && window.museShell?.openPricing) window.museShell.openPricing();
      else open('account', usedUp ? (snapshot.usage.plan === 'trial' ? 'Your three free runs are used. Pick a plan for 20 runs a month; saved drafts and downloads stay available.' : 'Your runs for this period are used. They reset monthly; saved drafts and downloads stay available.') : 'Live generation is temporarily unavailable. Your saved drafts and downloads still work.');
      return false;
    }
    return true;
  }
  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    if (!snapshot.configured) { say('Account setup is unavailable on this server. Please try again later.', true); return; }
    const selectedMode = mode;
    const emailValue = email.value.trim();
    const passwordValue = password.value;
    if (selectedMode !== 'password' && !emailValue) { email.focus(); return; }
    if (['signup', 'password'].includes(selectedMode) && passwordValue.length < 12) { say('Use a password with at least 12 characters.', true); password.focus(); return; }
    setBusy(true); say('One moment…');
    try {
      if (selectedMode === 'signin') {
        update(await request('/signin', 'POST', { email: emailValue, password: passwordValue }));
        track('signed_in');
        password.value = ''; dialog.close();
      } else if (selectedMode === 'signup') {
        const result = await request('/signup', 'POST', { email: emailValue, password: passwordValue });
        track('signup_submitted');
        if (result?.user) {
          update(result);
          track('signed_in');
          password.value = ''; dialog.close();
        } else {
          setMode('signin', result.message || 'Check your inbox to confirm your email, then sign in.');
        }
      } else if (selectedMode === 'recover') {
        const result = await request('/recover', 'POST', { email: emailValue });
        track('password_reset_requested');
        setMode('signin', result.message || 'If an account exists, a reset link is on its way.');
      } else if (selectedMode === 'password') {
        await request('/password', 'POST', { password: passwordValue });
        password.value = ''; await refresh(); setMode('account', 'Password updated. Your current draft is unchanged.');
      }
    } catch (error) { track('auth_failed', { mode: selectedMode, status: error.status || 0 }); say(error.message, true); }
    finally { password.value = ''; setBusy(false); }
  }
  async function onGoogle() {
    if (busy) return;
    if (!snapshot.configured) { say('Account setup is unavailable on this server. Please try again later.', true); return; }
    setBusy(true); say('Redirecting to Google…');
    try {
      track('oauth_started', { provider: 'google', mode });
      const result = await request('/oauth', 'POST', { provider: 'google', next: window.location?.pathname || '/account' });
      if (result?.url) {
        if (typeof window.location?.assign === 'function') window.location.assign(result.url);
        else if (window.location) window.location.href = result.url;
        return;
      }
      say('Google sign-in is unavailable right now. Use your email and password below.', true);
    } catch (error) {
      track('auth_failed', { mode: 'google', status: error.status || 0 });
      say(error.message, true);
    } finally { setBusy(false); }
  }
  async function signout() {
    if (busy) return;
    setBusy(true);
    try {
      await request('/signout', 'POST', {});
      update({ configured: snapshot.configured, user: null, usage: null, live_available: false });
      if (dialog?.open) dialog.close();
    } catch (error) { setBusy(false); open('account'); say(error.message, true); }
    finally { setBusy(false); }
  }
  function requireAccount(expectedOwner) {
    if (!snapshot.user) { open('signup', 'Sign in to save or load your own workspace. Your draft stays here.'); throw new Error('Sign in to access your saved workspace.'); }
    if (expectedOwner !== undefined && expectedOwner !== snapshot.user.id) {
      const error = new Error('The account changed. Load the workspace again.');
      error.status = 409;
      throw error;
    }
    return { owner: snapshot.user.id, epoch: accountEpoch };
  }
  function stillOwner(start, responseOwner) {
    return start.epoch === accountEpoch && start.owner === snapshot.user?.id && (responseOwner === undefined || responseOwner === start.owner);
  }
  async function loadWorkspace(expectedOwner) {
    const start = requireAccount(expectedOwner);
    const data = await request('/workspace', 'GET', undefined, { 'X-Muse-Owner': start.owner });
    if (!stillOwner(start, data?.owner_id)) {
      const error = new Error('The account changed. Load the workspace again.');
      error.status = 409;
      throw error;
    }
    workspaceVersion = Number.isSafeInteger(data.version) ? data.version : 0;
    workspaceOwner = start.owner;
    return copy(data);
  }
  async function saveWorkspace(documentValue, expectedOwner) {
    const start = requireAccount(expectedOwner);
    if (workspaceOwner !== null && workspaceOwner !== start.owner) {
      const error = new Error('The account changed while saving. Reload your workspace.');
      error.status = 409;
      throw error;
    }
    const encoded = JSON.stringify(documentValue);
    if (!encoded || encoded.length > 3000000) throw new Error('This draft is too large to save. Download the image separately.');
    if (/"(?:key|access_token|refresh_token|service_role_key|service_key|unlockKey|unlock_key|demo_key|authorization)"\s*:/i.test(encoded)) throw new Error('Save draft content only, without account or presenter keys.');
    const data = await request('/workspace', 'PUT', { document: JSON.parse(encoded), expected_version: workspaceVersion, expected_owner: start.owner }, { 'X-Muse-Owner': start.owner });
    if (!stillOwner(start, data?.owner_id)) {
      const error = new Error('The account changed while saving. Reload your workspace.');
      error.status = 409;
      throw error;
    }
    workspaceVersion = Number.isSafeInteger(data.version) ? data.version : workspaceVersion;
    workspaceOwner = start.owner;
    return copy(data);
  }
  async function callback() {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const access = hash.get('access_token');
    const refreshToken = hash.get('refresh_token');
    const recovery = hash.get('type') === 'recovery';
    const providerToken = hash.get('provider_token');
    const callbackError = hash.get('error_description') || hash.get('error');
    const query = new URLSearchParams(window.location.search || '');
    const oauthProvider = query.get('oauth');
    const oauthError = query.get('oauth_error');
    if (oauthProvider || oauthError) {
      query.delete('oauth'); query.delete('oauth_error');
      try { history.replaceState(null, '', window.location.pathname + (query.size ? `?${query}` : '') + window.location.hash); } catch {}
      try { await refresh(); } catch {}
      if (oauthError) { open('signin', oauthError); return true; }
      track('signed_in', { provider: oauthProvider });
      open('account', 'Signed in with Google. Your account is ready.');
      return true;
    }
    if (!access && !refreshToken && !callbackError) return false;
    // Remove credentials from the visible URL before any network transmission.
    history.replaceState(null, '', window.location.pathname + window.location.search);
    if (callbackError) { try { await refresh(); } catch {} open('signin', 'That sign-in link expired or could not be used. Sign in or request a new password reset link.'); return true; }
    if (!access || !refreshToken) { try { await refresh(); } catch {} open('signin', 'That sign-in link is incomplete. Please sign in again.'); return true; }
    try {
      update(await request('/session', 'POST', { access_token: access, refresh_token: refreshToken }));
      if (recovery) open('password');
      else if (providerToken) { track('signed_in', { provider: 'google' }); open('account', 'Signed in with Google. Your account is ready.'); }
      else { track('email_confirmed'); open('account', 'Email confirmed. Your account is ready.'); }
    } catch { try { await refresh(); } catch {} open('signin', 'We could not complete that sign-in link. Please sign in again.'); }
    return true;
  }
  function mount() {
    if (dialog || !document.body) return;
    const container = node('div', { class: 'ma-account-controls' });
    accountButton = node('button', { type: 'button', class: 'ma-account-button' }, 'Sign in');
    quotaLabel = node('span', { class: 'ma-quota', 'aria-live': 'polite', hidden: '' }, '');
    signupButton = node('button', { type: 'button', class: 'ma-signup-button', 'data-track': 'header_signup', hidden: '' }, 'Create free account');
    signoutButton = node('button', { type: 'button', class: 'ma-signout', hidden: '' }, 'Sign out');
    container.append(quotaLabel, accountButton, signupButton, signoutButton);
    const header = document.querySelector('header.topbar') || document.querySelector('body > header');
    (header || document.body).append(container);
    accountButton.addEventListener('click', () => open()); signupButton.addEventListener('click', () => open('signup')); signoutButton.addEventListener('click', signout);
    dialog = node('dialog', { class: 'ma-dialog', 'aria-labelledby': 'ma-title' });
    const close = node('button', { type: 'button', class: 'ma-close', 'aria-label': 'Close account dialog' }, '×');
    close.addEventListener('click', () => { if (!busy) { password.value = ''; dialog.close(); } });
    title = node('h2', { id: 'ma-title' }, 'Welcome back.');
    description = node('p', { class: 'ma-description' });
    tabs = node('div', { class: 'ma-tabs' });
    const signinTab = node('button', { type: 'button' }, 'Sign in');
    const signupTab = node('button', { type: 'button' }, 'Create account');
    signinTab.addEventListener('click', () => { if (!busy) setMode('signin'); }); signupTab.addEventListener('click', () => { if (!busy) setMode('signup'); }); tabs.append(signinTab, signupTab);
    googleButton = node('button', { type: 'button', class: 'ma-google' }, 'Continue with Google');
    googleButton.addEventListener('click', onGoogle);
    divider = node('p', { class: 'ma-divider' }, 'or use email');
    form = node('form');
    emailLabel = node('label', { for: 'ma-email' }, 'Email'); email = node('input', { id: 'ma-email', type: 'email', autocomplete: 'email', maxlength: '254', required: '' });
    passwordLabel = node('label', { for: 'ma-password' }, 'Password'); password = node('input', { id: 'ma-password', type: 'password', autocomplete: 'current-password', maxlength: '128', required: '' });
    submit = node('button', { type: 'submit', class: 'ma-primary' }, 'Sign in');
    message = node('p', { class: 'ma-message', role: 'status', 'aria-live': 'polite' });
    recover = node('button', { type: 'button', class: 'ma-recover' }, 'Forgot password?'); recover.addEventListener('click', () => { if (!busy) setMode('recover'); });
    form.append(emailLabel, email, passwordLabel, password, submit); form.addEventListener('submit', onSubmit);
    const refreshButton = node('button', { type: 'button', class: 'ma-refresh' }, 'Refresh account');
    refreshButton.addEventListener('click', async () => { if (busy) return; setBusy(true); try { await refresh(); setMode(snapshot.user ? 'account' : 'signin', 'Account refreshed.'); } catch (error) { say(error.message, true); } finally { setBusy(false); } });
    dialog.append(close, title, description, tabs, googleButton, divider, form, recover, message, refreshButton);
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const focusables = [...dialog.querySelectorAll('button:not([hidden]):not([disabled]), input:not([hidden]):not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(el => !el.closest('[hidden]'));
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    });
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); else password.value = ''; });
    document.body.append(dialog); renderAccount();
  }
  // A sign-in that lapsed while the tab was open: show it once, keep the draft, ask to sign in.
  let endedNotice = 0;
  // The account snapshot is left alone, so signing back into the same account keeps the
  // editors' draft in place (a different account goes through the normal switch protection).
  function sessionEnded(text) {
    if (Date.now() - endedNotice < 5000 || busy) return;
    endedNotice = Date.now();
    if (!dialog) mount();
    if (!dialog) return;
    track('session_expired');
    setMode('signin', text);
    if (snapshot.user?.email) email.value = snapshot.user.email;
    if (!dialog.open) dialog.showModal();
  }
  // Every live Muse request, whichever page made it: refresh the run count afterwards (failed runs
  // and saved fallbacks are given back on the server), say when a saved result stood in for a new
  // one, and handle a session that ended before the run started.
  const nativeFetch = window.fetch?.bind(window);
  if (nativeFetch) {
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (!/[?&]live=(true|1)\b/.test(url)) return nativeFetch(input, init);
      const response = await nativeFetch(input, init);
      try {
        if (snapshot.configured) {
          if (response.status === 401 && snapshot.user) sessionEnded('Your session ended before Muse started, so no run was used. Sign in again; your draft is still here.');
          else if (response.headers.get('X-Muse-Fallback')) window.museShell?.toast?.('Live Muse was unavailable, so saved results are shown. No run was used.', 'warn');
          else if (!response.ok && response.status >= 500) window.museShell?.toast?.('Muse could not finish this run, so it was not counted. Your work is still here.', 'warn');
          if (snapshot.user) setTimeout(() => { refresh().catch(() => {}); }, 1500);
        }
      } catch { /* observing never breaks the request */ }
      return response;
    };
  }
  mount();
  const readyPromise = (async () => {
    try { if (!await callback()) await refresh(); }
    catch { renderAccount(); }
    return copy(snapshot);
  })();
  // Back from Stripe Checkout (/account?billing=success|cancelled). The redirect itself grants
  // nothing: the plan appears once Stripe's verified webhook is recorded, so wait for it here.
  const note = (text, kind = '') => { try { window.museShell?.toast?.(text, kind); } catch {} };
  async function checkoutReturn() {
    const params = new URLSearchParams(location.search);
    const result = params.get('billing');
    if (result !== 'success' && result !== 'cancelled') return;
    params.delete('billing');
    try { history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '') + location.hash); } catch {}
    if (result === 'cancelled') { note('Checkout cancelled. Nothing was charged.'); return; }
    note('Payment received. Activating your plan…');
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, attempt ? 3000 : 500));
      try { await refresh(); } catch { continue; }
      const plan = snapshot.usage?.plan;
      if (plan && plan !== 'trial') {
        note(`Your ${plan[0].toUpperCase()}${plan.slice(1)} plan is active: ${snapshot.usage.remaining ?? 'unlimited'} runs available.`);
        track('plan_activated', { plan });
        return;
      }
      if (!snapshot.user) break;
    }
    if (!dialog) mount();
    if (!snapshot.user) { open('signin', 'Payment received. Sign in with the account you used at checkout to see your plan.'); return; }
    track('plan_activation_slow');
    open('account', 'Your payment went through, but activation is taking longer than usual. Refresh this page in a minute. If your plan still shows the trial, email help@nplusalpha.com; you will not be charged twice.');
  }
  readyPromise.then(checkoutReturn).catch(() => {});
  window.museAccount = Object.freeze({
    ready: () => readyPromise, refresh, open, liveReady, getSnapshot: () => copy(snapshot), saveWorkspace, loadWorkspace, signout
  });
})();
