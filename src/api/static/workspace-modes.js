(() => {
  const SAMPLE_IDEAS = new Set([
    'idea-1-empowering-women',
    'idea-2-starter-prints',
    'idea-3-gift-ready',
    'idea-4-home-titles',
    'idea-5-painting-story',
    'etsy_ceramics',
    'gallery_print'
  ]);
  const SAMPLE_ARTWORKS = new Set([
    'ek_onkar',
    'ek_onkar_collector',
    'naam_japo',
    'naam_japo_restored',
    'kirat_karo',
    'kirat_karo_collector',
    'golden_temple',
    'diptych',
    'etsy_chai'
  ]);
  const ALLOWED_PLACEMENTS = new Set(['instagram_feed', 'instagram_story', 'facebook_feed']);
  const STORAGE_PREFIX = 'muse-editor-v1';

  let revision = 1;
  let lastKey = '';
  let lastOwner = null;
  let lastAuthStatus = null;
  const listeners = new Set();

  function cleanParam(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function isSampleIdea(idea) {
    const val = cleanParam(idea);
    if (!val || /^(own|shop|user):/i.test(val)) return false;
    return SAMPLE_IDEAS.has(val);
  }

  function isSampleArtwork(artwork) {
    const val = cleanParam(artwork);
    if (!val || /^(own|shop|user):/i.test(val)) return false;
    return SAMPLE_ARTWORKS.has(val);
  }

  function parseParams(searchOverride) {
    const rawSearch = typeof searchOverride === 'string'
      ? searchOverride
      : (typeof window !== 'undefined' && window.location ? window.location.search : '');
    const params = new URLSearchParams(rawSearch || '');
    const workspaceRaw = cleanParam(params.get('workspace')).toLowerCase();
    const workspace = workspaceRaw === 'sample' || workspaceRaw === 'own' ? workspaceRaw : '';
    const idea = cleanParam(params.get('idea'));
    const artwork = cleanParam(params.get('artwork'));
    const placementRaw = cleanParam(params.get('placement')).toLowerCase();
    const placement = ALLOWED_PLACEMENTS.has(placementRaw) ? placementRaw : '';
    return { workspace, idea, artwork, placement };
  }

  function readAccountSnapshot() {
    if (typeof window !== 'undefined' && window.museAccount && typeof window.museAccount.getSnapshot === 'function') {
      return window.museAccount.getSnapshot();
    }
    return {
      configured: false,
      user: null,
      usage: null,
      live_available: false,
      auth_status: 'signed_out',
      auth_error: null
    };
  }

  function computeState(snapshotOverride, searchOverride) {
    const snap = snapshotOverride || readAccountSnapshot();
    const params = parseParams(searchOverride);
    const explicitOwn = params.workspace === 'own';
    const requestedSample = !explicitOwn && (
      params.workspace === 'sample' ||
      isSampleIdea(params.idea) ||
      isSampleArtwork(params.artwork)
    );
    const authStatus = snap?.auth_status || (snap?.user ? 'authenticated' : 'signed_out');
    const ownerId = snap?.user && typeof snap.user.id === 'string' ? snap.user.id : null;

    let state = 'guest_entry';
    let mode = 'own';
    if (authStatus === 'loading') {
      state = 'loading';
      mode = 'loading';
    } else if (authStatus === 'error') {
      state = 'error';
      mode = 'error';
    } else if (authStatus === 'expired') {
      state = 'expired';
      mode = 'expired';
    } else if (ownerId) {
      state = requestedSample ? 'account_sample' : 'account_own';
      mode = requestedSample ? 'sample' : 'own';
    } else {
      state = requestedSample ? 'guest_sample' : 'guest_entry';
      mode = requestedSample ? 'sample' : 'own';
    }

    const stateKey = `${state}:${ownerId || ''}:${params.workspace}:${params.idea}:${params.artwork}:${params.placement}`;
    if (stateKey !== lastKey || ownerId !== lastOwner || authStatus !== lastAuthStatus) {
      revision += 1;
      lastKey = stateKey;
      lastOwner = ownerId;
      lastAuthStatus = authStatus;
    }

    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.dataset.museMode = state;
    }

    return Object.freeze({
      state,
      mode,
      isSample: state === 'account_sample' || state === 'guest_sample',
      isLoading: state === 'loading',
      isError: state === 'error',
      isExpired: state === 'expired',
      isAuthenticated: Boolean(ownerId) && (state === 'account_own' || state === 'account_sample'),
      isOwnWorkspace: state === 'account_own',
      ownerId,
      user: ownerId ? snap.user : null,
      authStatus,
      authError: snap?.auth_error || null,
      revision,
      requestedSample,
      sampleParams: requestedSample
        ? Object.freeze({
            workspace: 'sample',
            idea: isSampleIdea(params.idea) ? params.idea : '',
            artwork: isSampleArtwork(params.artwork) ? params.artwork : '',
            placement: params.placement
          })
        : Object.freeze({
            workspace: params.workspace,
            idea: '',
            artwork: '',
            placement: params.placement
          }),
      snapshot: snap || null
    });
  }

  function current() {
    return computeState();
  }

  async function resolve() {
    if (typeof window !== 'undefined' && window.museAccount && typeof window.museAccount.ready === 'function') {
      try {
        await window.museAccount.ready();
      } catch {
        // Account failures surface through snapshot.auth_status ('error' | 'expired').
      }
    }
    return computeState();
  }

  function isSampleMode(stateObj) {
    const s = stateObj || current();
    return Boolean(s && s.isSample);
  }

  function modeStorageKey(namespace, stateObj) {
    const ns = cleanParam(namespace) || 'studio';
    const s = stateObj || current();
    if (s.isSample) return `${STORAGE_PREFIX}:${ns}:sample`;
    if (s.ownerId) return `${STORAGE_PREFIX}:${ns}:account:${s.ownerId}`;
    return `${STORAGE_PREFIX}:${ns}:anon`;
  }

  function buildUrl(path, queryObj) {
    const base = path || (typeof window !== 'undefined' && window.location ? window.location.pathname : '/');
    const url = new URL(base, typeof window !== 'undefined' && window.location ? window.location.origin : 'https://muse.local');
    Object.entries(queryObj || {}).forEach(([k, v]) => {
      if (v) url.searchParams.set(k, String(v));
      else url.searchParams.delete(k);
    });
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function sampleHref(path, options = {}) {
    const query = { workspace: 'sample' };
    if (options.idea && isSampleIdea(options.idea)) query.idea = options.idea;
    if (options.artwork && isSampleArtwork(options.artwork)) query.artwork = options.artwork;
    if (options.placement && ALLOWED_PLACEMENTS.has(options.placement)) query.placement = options.placement;
    return buildUrl(path, query);
  }

  function ownHref(path) {
    return buildUrl(path, {});
  }

  function updateHistoryQuery(mutator) {
    if (typeof window === 'undefined' || !window.location || !window.history?.replaceState) return;
    const url = new URL(window.location.href);
    mutator(url.searchParams);
    try {
      window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    } catch {
      // Ignore history mutation errors in restricted sandboxes.
    }
  }

  // Cross-page links marked data-mode-link="/path" keep the visitor in the workspace
  // they are in (sample example vs. their own), so a sample draft never opens as "own".
  function syncModeLinks() {
    if (typeof document === 'undefined' || typeof document.querySelectorAll !== 'function') return;
    try {
      const sample = isSampleMode();
      document.querySelectorAll('a[data-mode-link]').forEach((link) => {
        const path = link.getAttribute('data-mode-link');
        if (!path || !/^\/(?!\/)/.test(path)) return;
        link.setAttribute('href', sample ? sampleHref(path) : ownHref(path));
      });
    } catch {
      // Links keep their static href when the DOM is unavailable.
    }
  }

  function notify() {
    const resolved = computeState();
    renderModeBanners();
    syncModeLinks();
    listeners.forEach((fn) => {
      try { fn(resolved); } catch {}
    });
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
      window.dispatchEvent(new CustomEvent('muse:mode-change', { detail: resolved }));
    }
    return resolved;
  }

  function enterSampleMode(options = {}) {
    updateHistoryQuery((params) => {
      params.set('workspace', 'sample');
      if (options.idea && isSampleIdea(options.idea)) params.set('idea', options.idea);
      else if (options.idea === null) params.delete('idea');
      if (options.artwork && isSampleArtwork(options.artwork)) params.set('artwork', options.artwork);
      else if (options.artwork === null) params.delete('artwork');
      if (options.placement && ALLOWED_PLACEMENTS.has(options.placement)) params.set('placement', options.placement);
    });
    return notify();
  }

  function goToOwnWorkspace(options = {}) {
    if (options.navigateTo && typeof window !== 'undefined' && window.location) {
      window.location.assign(ownHref(options.navigateTo));
      return current();
    }
    updateHistoryQuery((params) => {
      params.delete('workspace');
      params.delete('idea');
      params.delete('artwork');
      params.delete('placement');
    });
    return notify();
  }

  function bindAsyncGuard() {
    const start = current();
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const isCurrent = () => {
      const now = current();
      if (now.isLoading || now.isError || now.isExpired) return false;
      return (
        now.revision === start.revision &&
        now.ownerId === start.ownerId &&
        now.isSample === start.isSample &&
        now.state === start.state
      );
    };
    return Object.freeze({
      revision: start.revision,
      ownerId: start.ownerId,
      isSample: start.isSample,
      state: start.state,
      signal: controller ? controller.signal : undefined,
      abort: () => { try { controller?.abort(); } catch {} },
      isCurrent
    });
  }

  function ensureBannerElement() {
    if (typeof document === 'undefined' || !document.body) return null;
    let banner = document.getElementById('museModeBanner');
    if (banner) return banner;
    banner = document.createElement('div');
    banner.id = 'museModeBanner';
    banner.className = 'muse-mode-banner';
    banner.hidden = true;
    const host = document.getElementById('museModeBannerHost');
    if (host) {
      host.appendChild(banner);
      return banner;
    }
    const anchor = document.querySelector('main, .shell, .app-shell, .ms-main');
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(banner, anchor);
    } else {
      const header = document.querySelector('header');
      if (header && header.parentNode) header.parentNode.insertBefore(banner, header.nextSibling);
      else document.body.insertBefore(banner, document.body.firstChild);
    }
    return banner;
  }

  function buildButton(label, action, variant) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `muse-mode-btn ${variant || 'secondary'}`;
    btn.setAttribute('data-muse-action', action);
    btn.textContent = label;
    btn.addEventListener('click', async () => {
      if (action === 'retry-auth') {
        btn.disabled = true;
        try { await window.museAccount?.refresh?.(); } catch {}
        finally { btn.disabled = false; notify(); }
      } else if (action === 'signin') {
        window.museAccount?.open?.('signin', 'Sign in to load your workspace and keep your edits safe.');
      } else if (action === 'signup') {
        window.museAccount?.open?.('signup', 'Create an account to save your own shop workspace.');
      } else if (action === 'back-to-own') {
        goToOwnWorkspace();
      }
    });
    return btn;
  }

  function renderModeBanners(customHost) {
    if (typeof document === 'undefined') return null;
    const banner = customHost || ensureBannerElement();
    if (!banner) return null;
    const s = computeState();
    banner.dataset.modeState = s.state;
    banner.textContent = '';

    if (s.state === 'account_own' || s.state === 'guest_entry') {
      banner.hidden = true;
      banner.removeAttribute('role');
      return banner;
    }

    banner.hidden = false;
    banner.setAttribute('role', s.isError || s.isExpired ? 'alert' : 'status');

    const inner = document.createElement('div');
    inner.className = 'muse-mode-banner-inner';
    const textWrap = document.createElement('div');
    textWrap.className = 'muse-mode-banner-copy';
    const badge = document.createElement('span');
    badge.className = 'muse-mode-badge';
    const msg = document.createElement('span');
    msg.className = 'muse-mode-text';
    const actions = document.createElement('div');
    actions.className = 'muse-mode-banner-actions';

    if (s.state === 'loading') {
      banner.className = 'muse-mode-banner is-loading';
      badge.textContent = 'Checking account';
      msg.textContent = 'Loading your workspace status…';
    } else if (s.state === 'error') {
      banner.className = 'muse-mode-banner is-error';
      badge.textContent = 'Account check unavailable';
      msg.textContent = `${s.authError || 'Could not verify your account right now.'} Sample data is kept separate and your device edits stay safe.`;
      actions.appendChild(buildButton('Retry account check', 'retry-auth', 'primary'));
      actions.appendChild(buildButton('Sign in', 'signin', 'secondary'));
    } else if (s.state === 'expired') {
      banner.className = 'muse-mode-banner is-expired';
      badge.textContent = 'Session expired';
      msg.textContent = 'Your session ended. Sign in again to open your workspace; your unsaved device edits are safe.';
      actions.appendChild(buildButton('Sign in again', 'signin', 'primary'));
      actions.appendChild(buildButton('Retry', 'retry-auth', 'secondary'));
    } else if (s.state === 'account_sample') {
      banner.className = 'muse-mode-banner is-sample';
      badge.textContent = 'Sample shop';
      msg.textContent = 'Viewing the Art of Sarabjit Singh example. Changes here stay separate from your own shop.';
      actions.appendChild(buildButton('Back to my workspace', 'back-to-own', 'primary'));
    } else if (s.state === 'guest_sample') {
      banner.className = 'muse-mode-banner is-sample';
      badge.textContent = 'Sample shop example';
      msg.textContent = 'Exploring the Art of Sarabjit Singh example. Set up your own shop or sign in anytime.';
      actions.appendChild(buildButton('Set up your own shop', 'back-to-own', 'secondary'));
      if (s.snapshot?.configured) actions.appendChild(buildButton('Sign in', 'signin', 'primary'));
    }

    textWrap.appendChild(badge);
    textWrap.appendChild(msg);
    inner.appendChild(textWrap);
    if (actions.childNodes.length) inner.appendChild(actions);
    banner.appendChild(inner);
    return banner;
  }

  function subscribe(fn) {
    if (typeof fn !== 'function') return () => {};
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('muse:account-change', () => { notify(); });
    window.addEventListener('popstate', () => { notify(); });
    if (typeof document !== 'undefined') {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => { renderModeBanners(); syncModeLinks(); });
      } else {
        renderModeBanners();
        syncModeLinks();
      }
    }
  }

  window.museModes = Object.freeze({
    resolve,
    current,
    isSampleMode,
    modeStorageKey,
    getSampleParams: parseParams,
    isSampleIdea,
    isSampleArtwork,
    enterSampleMode,
    goToOwnWorkspace,
    sampleHref,
    ownHref,
    bindAsyncGuard,
    renderModeBanners,
    subscribe
  });
})();
