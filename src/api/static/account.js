'use strict';
// Same-origin account UI. Session credentials are server-managed HttpOnly cookies.
(() => {
  if (window.museAccount) return;
  const root = '/api/v1/account';
  let snapshot = { configured: false, user: null, usage: null, live_available: false, auth_status: 'loading', auth_error: null };
  let accountEpoch = 0;
  let workspaceVersion = 0;
  let workspaceOwner = null;
  let mode = 'signin';
  let busy = false;
  let retryCount = 0;
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
  let signinTab;
  let signupTab;
  let googleButton;
  let divider;
  let recover;
  let refreshButton;
  let accountSignoutButton;
  let setupLink;
  let resend;
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
  const AUTH_PATHS = new Set(['/me', '/signin', '/signup', '/oauth', '/recover', '/resend', '/password', '/callback', '/signout']);
  async function request(path, method = 'GET', body, extraHeaders = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(root + path, {
        method, credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json', ...extraHeaders },
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
      if (error.name === 'AbortError') throw new Error('Muse took too long to answer. Your draft is still here.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  let inFlightRefresh = null;
  let lastEmittedKey = '';
  function snapshotKey(snap) {
    return JSON.stringify({
      configured: snap.configured,
      user: snap.user ? { id: snap.user.id, email: snap.user.email, email_verified: snap.user.email_verified } : null,
      usage: snap.usage || null,
      live_available: snap.live_available,
      auth_status: snap.auth_status,
      auth_error: snap.auth_error
    });
  }
  function emitChange() {
    renderAccount();
    const key = snapshotKey(snapshot);
    if (key === lastEmittedKey) return copy(snapshot);
    lastEmittedKey = key;
    const detail = copy(snapshot);
    window.dispatchEvent(new CustomEvent('muse:account-change', { detail }));
    window.dispatchEvent(new CustomEvent('account-change', { detail: copy(snapshot) }));
    return copy(snapshot);
  }
  function update(data) {
    const previous = snapshot.user?.id || null;
    const prevStatus = snapshot.auth_status;
    const user = data?.user && typeof data.user.id === 'string' ? {
      id: data.user.id, email: String(data.user.email || ''), email_verified: data.user.email_verified === true
    } : null;
    const nextStatus = user ? 'authenticated' : 'signed_out';
    snapshot = {
      configured: data?.configured === true,
      user,
      usage: data?.usage || null,
      live_available: data?.live_available === true,
      auth_status: nextStatus,
      auth_error: null
    };
    if (previous !== (user?.id || null) || prevStatus !== nextStatus) { accountEpoch += 1; workspaceVersion = 0; workspaceOwner = null; }
    return emitChange();
  }
  async function refresh() {
    if (inFlightRefresh) return inFlightRefresh;
    const run = (async () => {
      const epoch = accountEpoch;
      if (snapshot.auth_status === 'error' || snapshot.auth_status === 'expired') {
        snapshot = { ...snapshot, auth_status: 'loading', auth_error: null };
        emitChange();
      }
      try {
        const data = await request('/me');
        if (epoch !== accountEpoch) return copy(snapshot);
        return update(data);
      } catch (error) {
        if (epoch !== accountEpoch) return copy(snapshot);
        const expired = error?.status === 401;
        snapshot = {
          ...snapshot,
          user: expired ? null : snapshot.user,
          live_available: expired ? false : snapshot.live_available,
          auth_status: expired ? 'expired' : 'error',
          auth_error: error?.message || (expired ? 'Your session expired. Sign in again to continue.' : 'Could not verify your account right now.')
        };
        emitChange();
        throw error;
      }
    })();
    inFlightRefresh = run;
    try {
      return await run;
    } finally {
      if (inFlightRefresh === run) inFlightRefresh = null;
    }
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
  function setMode(next, text = '', isError = false, options = {}) {
    const previousMode = mode;
    mode = ['signin', 'signup', 'recover', 'resend', 'password', 'account'].includes(next) ? next : 'signin';
    if (!options.keepRetry && previousMode !== mode) retryCount = 0;
    const signedIn = mode === 'account';
    const passwordOnly = mode === 'password';
    const emailOnly = mode === 'recover' || mode === 'resend';
    const showGoogle = !signedIn && !passwordOnly && !emailOnly;
    title.textContent = { signin: 'Welcome back.', signup: 'Make it your studio.', recover: 'Reset your password.', resend: 'Confirm your email.', password: 'Choose a new password.', account: 'Your Muse account' }[mode];
    description.textContent = signedIn ? `${snapshot.user?.email || ''}${snapshot.user?.email_verified ? ' · email confirmed' : ' · confirm your email to generate'}` : mode === 'signup' ? 'Save your work and unlock 3 free Muse runs.' : mode === 'recover' ? 'We’ll send a password reset link if an account exists.' : mode === 'resend' ? 'We’ll send a new confirmation link if this email is waiting to be confirmed.' : passwordOnly ? 'Use at least 12 characters. Your draft stays here.' : 'Sign in to generate with Muse and save your work.';
    if (googleButton) googleButton.hidden = !showGoogle;
    if (divider) divider.hidden = !showGoogle;
    emailLabel.hidden = passwordOnly || signedIn;
    email.hidden = passwordOnly || signedIn;
    email.required = !passwordOnly && !signedIn;
    if (!options.preserveEmail && signedIn) email.value = '';
    passwordLabel.hidden = emailOnly || signedIn;
    password.hidden = emailOnly || signedIn;
    password.required = !emailOnly && !signedIn;
    password.autocomplete = mode === 'signin' ? 'current-password' : 'new-password';
    password.minLength = mode === 'signin' ? 1 : 12;
    password.value = '';
    submit.hidden = signedIn;
    submit.textContent = { signin: 'Sign in', signup: 'Create account', recover: 'Send reset link', resend: 'Send confirmation link', password: 'Update password' }[mode] || 'Continue';
    tabs.hidden = signedIn || passwordOnly;
    if (signinTab) {
      const signinActive = mode === 'signin' || mode === 'recover' || mode === 'resend';
      if (signinTab.classList?.toggle) signinTab.classList.toggle('ma-tab-active', signinActive);
      else signinTab.className = signinActive ? 'ma-tab-active' : '';
      signinTab.setAttribute('aria-pressed', String(signinActive));
    }
    if (signupTab) {
      const signupActive = mode === 'signup';
      if (signupTab.classList?.toggle) signupTab.classList.toggle('ma-tab-active', signupActive);
      else signupTab.className = signupActive ? 'ma-tab-active' : '';
      signupTab.setAttribute('aria-pressed', String(signupActive));
    }
    recover.textContent = 'Forgot password?';
    recover.hidden = !['signin', 'signup'].includes(mode);
    resend.hidden = mode !== 'signin';
    if (accountSignoutButton) accountSignoutButton.hidden = !signedIn;
    if (setupLink) setupLink.hidden = !signedIn;
    say(text || (signedIn ? quotaLabel.textContent : 'Saved examples remain available without an account.'), isError);
  }
  const track = (name, props) => { try { window.museTrack?.(name, props); } catch {} };
  function focusInitialField() {
    try {
      if (email && !email.hidden && !email.value.trim()) email.focus();
      else if (password && !password.hidden) password.focus();
      else if (accountSignoutButton && !accountSignoutButton.hidden) accountSignoutButton.focus();
      else if (refreshButton && !refreshButton.hidden) refreshButton.focus();
    } catch {}
  }
  function open(next = 'signin', text = '') {
    if (!dialog) mount();
    if (busy || !dialog) return;
    retryCount = 0;
    const alreadySignedIn = Boolean(snapshot.user);
    const targetMode = alreadySignedIn && ['signin', 'signup'].includes(next) ? 'account' : next;
    const resolvedText = alreadySignedIn && next === 'signup' && !text
      ? `You are already signed in as ${snapshot.user.email}. Sign out first to create or switch accounts.`
      : text;
    track('auth_dialog_opened', { mode: targetMode });
    setMode(targetMode, resolvedText);
    if (!dialog.open) dialog.showModal();
    focusInitialField();
    if (!snapshot.configured) say('Accounts are not available right now. Your saved demo and draft still work.', true);
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
    if (!snapshot.configured) { say('Accounts are not available right now. Please try again later.', true); return; }
    const selectedMode = mode;
    const emailValue = email.value.trim();
    const passwordValue = password.value;
    if (selectedMode !== 'password' && (!emailValue || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(emailValue))) {
      retryCount += 1;
      say(emailValue ? 'Enter a valid email address (for example, name@shop.com).' : 'Enter your email address first.', true);
      email.focus();
      return;
    }
    if (selectedMode === 'signin' && !passwordValue) {
      retryCount += 1;
      say('Enter your password to sign in, or choose Forgot password? below.', true);
      password.focus();
      return;
    }
    if (['signup', 'password'].includes(selectedMode) && passwordValue.length < 12) {
      retryCount += 1;
      say(`Use a password with at least 12 characters (${passwordValue.length}/12 entered). Your email stayed filled in.`, true);
      password.focus();
      return;
    }
    setBusy(true); say('One moment…');
    try {
      if (selectedMode === 'signin') {
        update(await request('/signin', 'POST', { email: emailValue, password: passwordValue }));
        retryCount = 0;
        track('signed_in');
        password.value = ''; dialog.close();
      } else if (selectedMode === 'signup') {
        const result = await request('/signup', 'POST', { email: emailValue, password: passwordValue });
        retryCount = 0;
        track('signup_submitted');
        if (result?.user) {
          update(result);
          track('signed_in');
          password.value = ''; dialog.close();
        } else {
          setMode('signin', result.message || 'Check your inbox to confirm your email, then sign in.', false, { preserveEmail: true });
        }
      } else if (selectedMode === 'resend') {
        const result = await request('/resend', 'POST', { email: emailValue });
        retryCount = 0;
        track('confirmation_resent');
        setMode('signin', result.message || 'If that email is waiting for confirmation, a new link is on its way.', false, { preserveEmail: true });
      } else if (selectedMode === 'recover') {
        const result = await request('/recover', 'POST', { email: emailValue });
        retryCount = 0;
        track('password_reset_requested');
        setMode('signin', result.message || 'If an account exists, a reset link is on its way.', false, { preserveEmail: true });
      } else if (selectedMode === 'password') {
        await request('/password', 'POST', { password: passwordValue });
        retryCount = 0;
        password.value = ''; await refresh(); setMode('account', 'Password updated. Your current draft is unchanged.');
      }
    } catch (error) {
      retryCount += 1;
      track('auth_failed', { mode: selectedMode, status: error.status || 0, attempt: retryCount });
      const rawMsg = error.message || 'Could not complete that request.';
      if (selectedMode === 'signup' && error.status === 409) {
        const retryHint = retryCount > 1
          ? ` (Attempt ${retryCount}: enter your password above to sign in, or click Forgot password? below.)`
          : '';
        setMode('signin', `${rawMsg}${retryHint}`, true, { preserveEmail: true, keepRetry: true });
        if (password && !password.hidden) password.focus();
      } else {
        const retryNote = retryCount > 1 && ['signin', 'signup'].includes(selectedMode)
          ? ` (Attempt ${retryCount}: check your details${selectedMode === 'signin' ? ' or choose Forgot password? below' : ''}.)`
          : '';
        say(`${rawMsg}${retryNote}`, true);
      }
    }
    finally { password.value = ''; setBusy(false); }
  }
  async function onGoogle() {
    if (busy) return;
    if (!snapshot.configured) { say('Accounts are not available right now. Please try again later.', true); return; }
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
    if (callbackError) { try { await refresh(); } catch {} open('signin', 'That link expired or was already used. Sign in, or use “Resend confirmation email” or “Forgot password?” for a new link.'); return true; }
    if (!access || !refreshToken) { try { await refresh(); } catch {} open('signin', 'That sign-in link is incomplete. Please sign in again.'); return true; }
    try {
      const landed = await request('/session', 'POST', { access_token: access, refresh_token: refreshToken });
      update(landed);
      if (recovery) open('password');
      else if (landed.password_reset_required) { track('email_confirmed'); open('password', 'Email confirmed. For your security, choose a new password for this account.'); }
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
    signinTab = node('button', { type: 'button' }, 'Sign in');
    signupTab = node('button', { type: 'button' }, 'Create account');
    signinTab.addEventListener('click', () => { if (!busy) { setMode('signin', '', false, { preserveEmail: true }); focusInitialField(); } });
    signupTab.addEventListener('click', () => { if (!busy) { setMode('signup', '', false, { preserveEmail: true }); focusInitialField(); } });
    tabs.append(signinTab, signupTab);
    googleButton = node('button', { type: 'button', class: 'ma-google' }, 'Continue with Google');
    googleButton.addEventListener('click', onGoogle);
    divider = node('p', { class: 'ma-divider' }, 'or use email');
    form = node('form', { novalidate: '' });
    emailLabel = node('label', { for: 'ma-email' }, 'Email'); email = node('input', { id: 'ma-email', type: 'email', autocomplete: 'email', maxlength: '254', required: '' });
    passwordLabel = node('label', { for: 'ma-password' }, 'Password'); password = node('input', { id: 'ma-password', type: 'password', autocomplete: 'current-password', maxlength: '128', required: '' });
    submit = node('button', { type: 'submit', class: 'ma-primary' }, 'Sign in');
    message = node('p', { class: 'ma-message', role: 'status', 'aria-live': 'polite' });
    recover = node('button', { type: 'button', class: 'ma-recover' }, 'Forgot password?'); recover.addEventListener('click', () => { if (!busy) { setMode('recover', '', false, { preserveEmail: true }); focusInitialField(); } });
    resend = node('button', { type: 'button', class: 'ma-resend' }, 'Resend confirmation email'); resend.addEventListener('click', () => { if (!busy) { setMode('resend', '', false, { preserveEmail: true }); focusInitialField(); } });
    form.append(emailLabel, email, passwordLabel, password, submit); form.addEventListener('submit', onSubmit);
    // Settings for the shop itself: what Muse knows about the business, editable any time (free).
    setupLink = node('a', { href: '/welcome?edit=1', class: 'ma-primary ma-setup-link', style: 'box-sizing:border-box;text-align:center;text-decoration:none', 'data-track': 'account_edit_setup', hidden: '' }, 'Edit shop setup');
    accountSignoutButton = node('button', { type: 'button', class: 'ma-secondary ma-dialog-signout', hidden: '' }, 'Sign out');
    accountSignoutButton.addEventListener('click', signout);
    refreshButton = node('button', { type: 'button', class: 'ma-refresh' }, 'Refresh account');
    refreshButton.addEventListener('click', async () => { if (busy) return; setBusy(true); try { await refresh(); setMode(snapshot.user ? 'account' : 'signin', 'Account refreshed.'); } catch (error) { say(error.message, true); } finally { setBusy(false); } });
    dialog.append(close, title, description, tabs, googleButton, divider, form, recover, resend, message, setupLink, accountSignoutButton, refreshButton);
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
    const previousEmail = snapshot.user?.email || '';
    accountEpoch += 1;
    workspaceVersion = 0;
    workspaceOwner = null;
    snapshot = {
      ...snapshot,
      user: null,
      live_available: false,
      auth_status: 'expired',
      auth_error: text || 'Your session ended. Sign in again to continue.'
    };
    emitChange();
    if (!dialog) mount();
    if (!dialog) return;
    track('session_expired');
    setMode('signin', text);
    if (previousEmail) email.value = previousEmail;
    if (!dialog.open) dialog.showModal();
  }
  // Every live Muse request, whichever page made it: refresh the run count afterwards (failed runs
  // and saved fallbacks are given back on the server), say when a saved result stood in for a new
  // one, and handle a session that ended before the run started.
  const nativeFetch = window.fetch?.bind(window);
  // Two scripts asking for the same thing at the same moment share one request. Each /api/v1 call
  // runs the server function once, so a duplicate on page load costs as much as the first. Only an
  // identical GET still in flight is shared (same URL, headers and account); nothing is kept once
  // the response arrives, and an account change starts fresh. A caller that aborts leaves on its
  // own; the request is cancelled when every caller has left. Only a request that started under a
  // second ago is joined, so a retry after a timeout never waits on a request that hangs.
  const inFlightGets = new Map();
  const JOIN_WINDOW_MS = 1000;
  function sharedGetKey(input, init) {
    if (typeof input !== 'string' && !(input instanceof URL)) return '';
    if (String(init?.method || 'GET').toUpperCase() !== 'GET' || init?.body != null) return '';
    if (init?.signal?.aborted) return '';
    let target;
    try { target = new URL(String(input), window.location.href); } catch { return ''; }
    if (target.origin !== window.location.origin || !target.pathname.startsWith('/api/v1/')) return '';
    let headers;
    try { headers = [...new Headers(init?.headers || {}).entries()].filter(([name]) => name !== 'content-type').sort(); } catch { return ''; }
    return JSON.stringify([accountEpoch, snapshot.user?.id || null, target.href, init?.credentials || 'same-origin', headers]);
  }
  function sharedGet(key, input, init) {
    let entry = inFlightGets.get(key);
    if (!entry || Date.now() - entry.startedAt > JOIN_WINDOW_MS) {
      const controller = new AbortController();
      const { signal: _callerSignal, ...rest } = init || {};
      entry = { waiters: 0, controller, startedAt: Date.now(), promise: nativeFetch(input, { ...rest, signal: controller.signal }) };
      inFlightGets.set(key, entry);
      const created = entry;
      const forget = () => { if (inFlightGets.get(key) === created) inFlightGets.delete(key); };
      created.promise.then(forget, forget);
    }
    const shared = entry;
    shared.waiters += 1;
    const signal = init?.signal;
    return new Promise((resolve, reject) => {
      let done = false;
      const leave = () => {
        if (done) return;
        done = true;
        reject(signal.reason ?? new DOMException('The operation was aborted.', 'AbortError'));
        shared.waiters -= 1;
        if (shared.waiters <= 0 && inFlightGets.get(key) === shared) {
          inFlightGets.delete(key);
          shared.controller.abort();
        }
      };
      signal?.addEventListener('abort', leave, { once: true });
      shared.promise.then((response) => {
        if (done) return;
        done = true;
        signal?.removeEventListener('abort', leave);
        try { resolve(response.clone()); } catch (error) { reject(error); }
      }, (error) => {
        if (done) return;
        done = true;
        signal?.removeEventListener('abort', leave);
        reject(error);
      });
    });
  }
  if (nativeFetch) {
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (!/[?&]live=(true|1)\b/.test(url)) {
        const key = sharedGetKey(input, init);
        return key ? sharedGet(key, input, init) : nativeFetch(input, init);
      }
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
    catch (error) {
      if (snapshot.auth_status === 'loading') {
        const expired = error?.status === 401;
        snapshot = {
          ...snapshot,
          auth_status: expired ? 'expired' : 'error',
          auth_error: error?.message || 'Could not verify your account right now.'
        };
      }
      emitChange();
    }
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
    ready: () => readyPromise, refresh, open, liveReady, getSnapshot: () => copy(snapshot), current: () => copy(snapshot.user), saveWorkspace, loadWorkspace, signout
  });
})();
