'use strict';
/**
 * Track H — Signed-In 4-Step Shop Onboarding (/welcome) & Honest Signed-In Workspace on (/).
 * Zero model calls on Steps 1, 2, 4. Step 3 discloses 1-run cost upfront and supports a 0-run manual path.
 * Never sends URLs or social handles to PostHog.
 */
(function () {
  const LOCAL_ONBOARDING_KEY = 'muse.onboarding.v1';
  // A guest asked to create an account (for competitor suggestions here, or to analyze a shop
  // they added on home) leaves a short-lived note. After sign-in the setup wizard adopts it, so
  // their setup so far and the shops they added come with them.
  const SIGNUP_HANDOFF_KEY = 'muse.signup_handoff.v1';
  const SIGNUP_HANDOFF_MAX_AGE_MS = 2 * 60 * 60 * 1000;
  function saveSignupHandoff(extra) {
    try {
      const prev = JSON.parse(localStorage.getItem(SIGNUP_HANDOFF_KEY) || 'null') || {};
      const competitors = Array.isArray(prev.competitors) ? prev.competitors : [];
      localStorage.setItem(SIGNUP_HANDOFF_KEY, JSON.stringify({ ...prev, ...extra, competitors, at: Date.now() }));
    } catch (_) {}
  }
  function takeSignupHandoff() {
    try {
      const raw = localStorage.getItem(SIGNUP_HANDOFF_KEY);
      localStorage.removeItem(SIGNUP_HANDOFF_KEY);
      const handoff = raw ? JSON.parse(raw) : null;
      if (!handoff || !(Date.now() - Number(handoff.at) < SIGNUP_HANDOFF_MAX_AGE_MS)) return null;
      return handoff;
    } catch (_) {
      return null;
    }
  }
  const LOCAL_WORKSPACE_MODE_KEY = 'muse.workspace_mode.v1'; // 'own' | 'sample'
  let homeSyncEpoch = 0;
  // True once this page has shown a signed-out visitor: a sign-in after that is a fresh one.
  let homeSawSignedOut = false;
  let lastRenderedUserId = null;
  let cleanHomeState = null;

  function trackEvent(eventName, props = {}) {
    try {
      if (typeof window.museTrack === 'function') {
        window.museTrack(eventName, props);
      } else if (window.museAnalytics && typeof window.museAnalytics.track === 'function') {
        window.museAnalytics.track(eventName, props);
      } else if (window.posthog && typeof window.posthog.capture === 'function') {
        window.posthog.capture(eventName, props);
      }
    } catch (_) {
      /* analytics must never block onboarding */
    }
  }

  function normalizeShopUrl(raw) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) return '';
    const withProto = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed.replace(/^\/+/, '')}`;
    try {
      const parsed = new URL(withProto);
      if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname.includes('.')) {
        return '';
      }
      return parsed.toString();
    } catch (_) {
      return '';
    }
  }

  function deriveBusinessName(urlStr, explicitName) {
    const cleanExplicit = String(explicitName || '').trim();
    if (cleanExplicit) return cleanExplicit.slice(0, 140);
    try {
      const host = new URL(urlStr).hostname.replace(/^www\./i, '');
      const base = host.split('.')[0] || 'My Shop';
      return base
        .split(/[-_]+/)
        .filter(Boolean)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
    } catch (_) {
      return 'My Shop';
    }
  }

  function extractSocialHandlesFromCrawl(crawlData) {
    const found = [];
    const seen = new Set();
    const addHandle = (platform, rawUrlOrHandle) => {
      const clean = String(rawUrlOrHandle || '').trim();
      if (!clean) return;
      let handle = clean;
      let url = clean;
      try {
        if (/^https?:\/\//i.test(clean)) {
          const u = new URL(clean);
          const parts = u.pathname.split('/').filter(Boolean);
          if (parts.length > 0) {
            handle = '@' + parts[0].replace(/^@/, '');
          }
        } else if (!clean.startsWith('@')) {
          handle = '@' + clean;
        }
      } catch (_) {}
      const key = `${platform.toLowerCase()}:${handle.toLowerCase()}`;
      if (seen.has(key)) return;
      seen.add(key);
      found.push({
        platform: platform.toLowerCase(),
        handle,
        url: /^https?:\/\//i.test(url) ? url : `https://${platform.toLowerCase()}.com/${handle.replace(/^@/, '')}`,
        confirmed: true,
        source: 'crawl',
      });
    };

    if (!crawlData || typeof crawlData !== 'object') return found;

    // 1. Explicit suggested_socials or socials returned by backend (Session 2 pure extractor)
    const backendSocials = crawlData.suggested_socials || crawlData.socials || [];
    if (Array.isArray(backendSocials)) {
      backendSocials.forEach((item) => {
        if (item && typeof item === 'object' && item.platform && (item.handle || item.url)) {
          addHandle(item.platform, item.handle || item.url);
        } else if (typeof item === 'string') {
          detectPlatformFromUrl(item, addHandle);
        }
      });
    }

    // 2. Inspect crawled channels and discovered items ONLY (never invent handles)
    const urlsToInspect = [];
    (crawlData.channels || []).forEach((ch) => {
      if (ch && ch.url) urlsToInspect.push(ch.url);
    });
    (crawlData.discovered_catalog_items || []).forEach((it) => {
      if (it && it.url) urlsToInspect.push(it.url);
    });
    urlsToInspect.forEach((u) => detectPlatformFromUrl(u, addHandle));
    return found;
  }

  function detectPlatformFromUrl(rawUrl, addFn) {
    try {
      const u = new URL(String(rawUrl));
      const host = u.hostname.toLowerCase();
      if (host.includes('instagram.com')) addFn('instagram', rawUrl);
      else if (host.includes('facebook.com')) addFn('facebook', rawUrl);
      else if (host.includes('pinterest.com')) addFn('pinterest', rawUrl);
      else if (host.includes('tiktok.com')) addFn('tiktok', rawUrl);
    } catch (_) {}
  }

  function computePriceRangeLabel(priceHints) {
    if (!Array.isArray(priceHints) || !priceHints.length) return '';
    const nums = [];
    priceHints.forEach((hint) => {
      const matches = String(hint).match(/\d+(?:,\d{3})*(?:\.\d+)?/g);
      if (matches) {
        matches.forEach((m) => {
          const val = parseFloat(m.replace(/,/g, ''));
          if (Number.isFinite(val) && val > 0) nums.push(val);
        });
      }
    });
    if (!nums.length) return priceHints.slice(0, 3).join(', ');
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const fmt = (n) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);
    return min === max ? fmt(min) : `${fmt(min)} to ${fmt(max)}`;
  }

  // What the business offers, guessed from the scanned pages. The seller confirms or changes it
  // in step 1, and their own choice always wins over a later scan.
  const OFFER_LABELS = { products: 'Products', services: 'Services', both: 'Both' };
  function guessBusinessType(items, priceRange) {
    const list = Array.isArray(items) ? items : [];
    const productPages = list.filter((i) => ['products', 'listings'].includes(i?.bucket)).length;
    const text = list.map((i) => `${i?.url || ''} ${i?.title || ''}`).join(' ').toLowerCase();
    const serviceHits = (text.match(/\b(services?|consult\w*|case[-\s]stud\w*|advisory|agency|engagements?|work[-\s]with[-\s]us|book[-\s]a[-\s]call|our[-\s]clients|solutions?|retainers?)\b/g) || []).length;
    if (productPages >= 3 && serviceHits >= 3) return 'both';
    if (productPages >= 3 || (productPages >= 1 && priceRange)) return 'products';
    if (serviceHits >= 1) return 'services';
    return null;
  }

  function defaultOnboardingState() {
    return {
      step: 1,
      business_name: '',
      business_type: null,
      shop_urls: [],
      crawl_summary: null,
      socials: [],
      competitors: [],
      preferences: null,
      preferences_version: 1,
      completed_at: null,
      skipped: [],
      used_run: false,
    };
  }

  function localKeyForUser(user) {
    return user && user.id ? `muse_onboarding_${user.id}` : 'muse_onboarding_anon';
  }

  function readLocalOnboarding(user) {
    try {
      const key = localKeyForUser(user);
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      return { ...defaultOnboardingState(), ...JSON.parse(raw) };
    } catch (_) {
      return null;
    }
  }

  function writeLocalOnboarding(state, user) {
    try {
      const key = localKeyForUser(user);
      localStorage.setItem(key, JSON.stringify(state));
    } catch (_) {}
  }

  async function loadServerWorkspaceDoc() {
    try {
      if (window.museModes && typeof window.museModes.resolve === 'function') {
        await window.museModes.resolve();
      } else if (window.museAccount && typeof window.museAccount.ready === 'function') {
        await window.museAccount.ready();
      }
      if (window.museAccount && typeof window.museAccount.getSnapshot === 'function') {
        const snap = window.museAccount.getSnapshot();
        const authStatus = snap?.auth_status || (snap?.user ? 'authenticated' : 'signed_out');
        if (authStatus === 'error' || authStatus === 'expired' || authStatus === 'loading') {
          return {
            doc: null,
            version: 0,
            user: null,
            usage: null,
            authStatus,
            authError: snap?.auth_error || null,
          };
        }
        if (snap && !snap.user) {
          return { doc: null, version: 0, user: null, usage: snap.usage || null, authStatus: 'signed_out', authError: null };
        }
        if (snap && snap.user && typeof window.museAccount.loadWorkspace === 'function') {
          const ws = await window.museAccount.loadWorkspace(snap.user.id);
          return {
            doc: ws.document || {},
            version: ws.version || 0,
            user: snap.user,
            usage: snap.usage,
            authStatus: 'authenticated',
            authError: null,
          };
        }
      }
      const meResp = await fetch('/api/v1/account/me', {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (!meResp.ok) {
        return {
          doc: null,
          version: 0,
          user: null,
          usage: null,
          authStatus: meResp.status === 401 ? 'expired' : 'error',
          authError: meResp.status === 401 ? 'Your session expired. Sign in again.' : 'Could not verify your account right now.',
        };
      }
      const me = await meResp.json();
      if (me && me.user && me.user.id) {
        const wsResp = await fetch('/api/v1/account/workspace', {
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { 'X-Muse-Owner': me.user.id },
        });
        if (wsResp.ok) {
          const wsData = await wsResp.json();
          return {
            doc: wsData.document || {},
            version: wsData.version || 0,
            user: me.user,
            usage: me.usage,
            authStatus: 'authenticated',
            authError: null,
          };
        }
        return { doc: {}, version: 0, user: me.user, usage: me.usage, authStatus: 'authenticated', authError: null };
      }
      return { doc: null, version: 0, user: null, usage: me?.usage || null, authStatus: 'signed_out', authError: null };
    } catch (err) {
      return {
        doc: null,
        version: 0,
        user: null,
        usage: null,
        authStatus: 'error',
        authError: err?.message || 'Could not verify your account right now.',
      };
    }
  }

  async function saveServerOnboarding(onboardingState, preferencesObj, userObj) {
    const user = userObj || (window.museAccount?.getSnapshot?.()?.user || null);
    writeLocalOnboarding(onboardingState, user);
    try {
      if (window.museAccount && typeof window.museAccount.getSnapshot === 'function') {
        const snap = window.museAccount.getSnapshot();
        if (snap && snap.user && typeof window.museAccount.loadWorkspace === 'function') {
          let currentDoc = {};
          try {
            const loaded = await window.museAccount.loadWorkspace(snap.user.id);
            currentDoc = loaded.document || {};
          } catch (_) {}
          const nextDoc = {
            ...currentDoc,
            onboarding: onboardingState,
            ...(preferencesObj ? { preferences: preferencesObj } : {}),
          };
          await window.museAccount.saveWorkspace(nextDoc, snap.user.id);
          return true;
        }
      }
      const meResp = await fetch('/api/v1/account/me', { credentials: 'same-origin' });
      if (!meResp.ok) return false;
      const me = await meResp.json();
      if (!me?.user?.id) return false;
      const getResp = await fetch('/api/v1/account/workspace', {
        credentials: 'same-origin',
        headers: { 'X-Muse-Owner': me.user.id },
      });
      const current = getResp.ok ? await getResp.json() : { document: {}, version: 0 };
      const nextDoc = {
        ...(current.document || {}),
        onboarding: onboardingState,
        ...(preferencesObj ? { preferences: preferencesObj } : {}),
      };
      const putResp = await fetch('/api/v1/account/workspace', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Muse-Owner': me.user.id,
        },
        body: JSON.stringify({
          document: nextDoc,
          expected_version: current.version || 0,
          expected_owner: me.user.id,
        }),
      });
      if (!putResp.ok) {
        const errJson = await putResp.json().catch(() => ({}));
        throw new Error(errJson.detail || errJson.message || 'Your setup could not be saved to your account. Try again.');
      }
      return true;
    } catch (err) {
      throw err;
    }
  }

  // =========================================================================
  // 1. /welcome PAGE CONTROLLER
  // =========================================================================
  async function initWelcomePage() {
    const mainEl = document.getElementById('wkMain');
    if (!mainEl) return;

    let currentUser = null;
    let runsRemaining = 3;

    const server = await loadServerWorkspaceDoc();
    if (server.authStatus === 'error' || server.authStatus === 'expired') {
      let errNote = document.getElementById('wkAuthStatusError');
      if (!errNote) {
        errNote = document.createElement('div');
        errNote.id = 'wkAuthStatusError';
        errNote.setAttribute('role', 'alert');
        errNote.style.cssText = 'margin:16px 0;padding:14px 16px;border-radius:10px;background:#fbe8df;color:#6c281b;border:1px solid #e2b8a8;';
        mainEl.prepend(errNote);
      }
      errNote.textContent = server.authError || 'Could not verify your account status right now. Retry or sign in above; your saved work on this device stays safe.';
      const onRecovered = (modeState) => {
        if (modeState && !modeState.isLoading && !modeState.isError && !modeState.isExpired) {
          window.location.reload();
        }
      };
      window.museModes?.subscribe?.(onRecovered);
      return;
    }
    if (server.user) currentUser = server.user;
    let state = readLocalOnboarding(currentUser) || defaultOnboardingState();
    window.museModes?.subscribe?.((modeState) => {
      if (!modeState || modeState.isLoading) return;
      const nextUid = modeState.ownerId || null;
      const curUid = currentUser?.id || null;
      if (nextUid !== curUid) {
        window.location.reload();
      }
    });
    if (server.usage && typeof server.usage.remaining === 'number') {
      runsRemaining = Math.max(0, server.usage.remaining);
    } else {
      try {
        const credResp = await fetch('/api/v1/credits', { credentials: 'same-origin' });
        if (credResp.ok) {
          const cred = await credResp.json();
          if (typeof cred.balance === 'number') runsRemaining = Math.max(0, cred.balance);
        }
      } catch (_) {}
    }

    if (server.doc && server.doc.onboarding && typeof server.doc.onboarding === 'object') {
      state = { ...defaultOnboardingState(), ...server.doc.onboarding };
      writeLocalOnboarding(state, currentUser);
    }

    // Signed in just now from one of those prompts, on this device: adopt the note.
    if (currentUser && !state.completed_at) {
      const handoff = takeSignupHandoff();
      if (handoff) {
        if (handoff.from === 'wizard' && !(server.doc && server.doc.onboarding)) {
          const guestState = readLocalOnboarding(null);
          if (guestState) state = { ...guestState };
          try { localStorage.removeItem(localKeyForUser(null)); } catch (_) {}
        }
        state.competitors = Array.isArray(state.competitors) ? state.competitors : [];
        (handoff.competitors || []).forEach((raw) => {
          const url = normalizeShopUrl(raw);
          if (url && !state.competitors.some((c) => c.url === url)) {
            state.competitors.push({ name: deriveBusinessName(url), url, role: 'similar_audience', rationale: '', reason: 'Added before you signed in', selected: true });
          }
        });
        if (handoff.step >= 1 && handoff.step <= 4) state.step = handoff.step;
        writeLocalOnboarding(state, currentUser);
        trackEvent('signup_handoff_adopted', { from: handoff.from || 'unknown' });
      }
    }

    const query = new URLSearchParams(window.location.search || '');
    const forcedStep = parseInt(query.get('step') || '', 10);
    if (forcedStep >= 1 && forcedStep <= 4) {
      state.step = forcedStep;
    }
    // A seller who finished setup and comes back is editing it: their answers load into each
    // step and the last step saves the changes (free) instead of building a new workspace.
    const editing = Boolean(currentUser && state.completed_at);
    if (editing && !(forcedStep >= 1 && forcedStep <= 4)) state.step = 1;
    if (editing) {
      let banner = document.getElementById('wkEditBanner');
      if (!banner) {
        banner = document.createElement('div');
        banner.id = 'wkEditBanner';
        banner.className = 'wk-edit-banner';
        banner.setAttribute('role', 'status');
        mainEl.prepend(banner);
      }
      banner.textContent = '';
      const strong = document.createElement('strong');
      strong.textContent = `Editing the setup for ${state.business_name || 'your shop'}.`;
      const text = document.createElement('span');
      text.textContent = ' Change any step, then press “Save changes” on step 4. Saving uses no runs.';
      const back = document.createElement('a');
      back.href = '/';
      back.textContent = 'Back to my workspace';
      banner.append(strong, text, ' ', back);
    }

    trackEvent('onboarding_started', {});

    const runsPill = document.getElementById('wkRunsPill');
    const updateRunsUI = () => {
      if (runsPill) {
        runsPill.textContent = `${runsRemaining} ${runsRemaining === 1 ? 'run' : 'runs'} left`;
      }
      const discTitle = document.getElementById('wkRunDisclosureTitle');
      const discDetail = document.getElementById('wkRunDisclosureDetail');
      const finishBtn = document.getElementById('wkStep4FinishBtn');
      const skipBtn = document.getElementById('wkStep4SkipBtn');

      if (discTitle) discTitle.textContent = editing ? 'Saving your changes is free (0 runs used).' : 'Building your workspace is free (0 runs used).';
      if (discDetail) {
        discDetail.textContent =
          `This uses 0 runs. All ${runsRemaining} ${runsRemaining === 1 ? 'run' : 'runs'} are kept for your ad generations and live research.`;
      }
      if (finishBtn) finishBtn.textContent = editing ? 'Save changes (free · 0 runs)' : 'Build my workspace (free · 0 runs)';
      if (skipBtn) skipBtn.textContent = editing ? 'Keep these answers & save →' : 'Skip & build workspace (0 runs) →';
    };
    updateRunsUI();

    const showStep = (stepNum) => {
      state.step = stepNum;
      writeLocalOnboarding(state, currentUser);
      [1, 2, 3, 4].forEach((n) => {
        const sec = document.getElementById(`wkStep${n}`);
        if (sec) sec.hidden = n !== stepNum;
        const ind = document.querySelector(`[data-step-ind="${n}"]`);
        if (ind) {
          ind.classList.toggle('is-active', n === stepNum);
          ind.classList.toggle('is-done', n < stepNum);
        }
      });
      const doneSec = document.getElementById('wkStepDone');
      if (doneSec) doneSec.hidden = stepNum !== 5;
    };

    // Hydrate Step 1 fields
    const shopUrlInput = document.getElementById('wkShopUrl');
    const bizNameInput = document.getElementById('wkBusinessName');
    const moreUrlsInput = document.getElementById('wkMoreShopUrls');
    const proofBox = document.getElementById('wkShopProof');
    const step1Err = document.getElementById('wkStep1Error');

    if (state.shop_urls.length > 0 && shopUrlInput) {
      shopUrlInput.value = state.shop_urls[0];
      if (state.shop_urls.length > 1 && moreUrlsInput) {
        moreUrlsInput.value = state.shop_urls.slice(1).join(', ');
      }
    }
    if (state.business_name && bizNameInput) {
      bizNameInput.value = state.business_name;
    }

    const offerInputs = Array.from(document.querySelectorAll('input[name="wkOffer"]'));
    const offerHint = document.getElementById('wkOfferHint');
    const offerHintDefault = offerHint ? offerHint.textContent : '';
    let offerChosen = Boolean(state.business_type);
    const setOffer = (value) => { offerInputs.forEach((i) => { i.checked = i.value === value; }); };
    const selectedOffer = () => offerInputs.find((i) => i.checked)?.value || 'products';
    if (state.business_type) setOffer(state.business_type);
    offerInputs.forEach((input) => input.addEventListener('change', () => {
      if (!input.checked) return;
      offerChosen = true;
      state.business_type = input.value;
      if (offerHint) offerHint.textContent = offerHintDefault;
      writeLocalOnboarding(state, currentUser);
    }));
    // Step 1 also records the name the seller typed and what they offer, scanned again or not.
    const keepStep1Answers = () => {
      const typedName = String(bizNameInput?.value || '').trim();
      if (typedName) state.business_name = typedName.slice(0, 140);
      if (offerInputs.length) state.business_type = selectedOffer();
    };

    const renderCrawlProof = (summary) => {
      if (!proofBox || !summary) return;
      proofBox.hidden = false;
      proofBox.textContent = '';
      const strong = document.createElement('strong');
      const count = summary.products_count || summary.pages_crawled || 0;
      const priceText = summary.price_range
        ? `, prices ${summary.price_range}`
        : ' (no public prices listed on crawled pages)';
      strong.textContent = `✓ Found ${count} ${count === 1 ? 'product/page' : 'products/pages'} on ${summary.business_name}${priceText}`;
      proofBox.appendChild(strong);
      if (Array.isArray(summary.sample_titles) && summary.sample_titles.length > 0) {
        const sub = document.createElement('div');
        sub.style.marginTop = '4px';
        sub.style.fontSize = '0.8rem';
        sub.textContent = `Sample items: ${summary.sample_titles.slice(0, 4).join(' · ')}`;
        proofBox.appendChild(sub);
      }
    };

    if (state.crawl_summary) {
      renderCrawlProof(state.crawl_summary);
    }

    async function performStep1Crawl() {
      if (step1Err) step1Err.hidden = true;
      const primaryUrl = normalizeShopUrl(shopUrlInput.value);
      if (!primaryUrl) {
        if (step1Err) {
          step1Err.textContent = 'Enter a valid domain or shop URL (for example: mountainpottery.com).';
          step1Err.hidden = false;
        }
        return false;
      }
      const extraUrls = String(moreUrlsInput?.value || '')
        .split(',')
        .map((s) => normalizeShopUrl(s))
        .filter(Boolean);
      const bizName = deriveBusinessName(primaryUrl, bizNameInput?.value);
      if (bizNameInput && !bizNameInput.value.trim()) {
        bizNameInput.value = bizName;
      }

      const scanBtn = document.getElementById('wkScanShopBtn');
      if (scanBtn) {
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning your shop pages…';
      }
      try {
        const resp = await fetch('/api/v1/ingest-storefront', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            business_name: bizName,
            website_url: primaryUrl,
            marketplace_urls: extraUrls,
            social_urls: [],
            max_urls_per_source: 25,
          }),
        });
        if (!resp.ok) {
          throw new Error('Muse could not read that website. Check the address or skip this step.');
        }
        const data = await resp.json();
        const items = Array.isArray(data.discovered_catalog_items) ? data.discovered_catalog_items : [];
        const pagesCrawled = Number(data.total_pages_crawled) || items.length;
        const priceRange = data.price_range || computePriceRangeLabel(data.detected_price_hints || []);
        const summary = {
          business_name: data.business_name || bizName,
          primary_url: primaryUrl,
          pages_crawled: pagesCrawled,
          products_count: items.length || pagesCrawled,
          price_range: priceRange,
          sample_titles: items.map((i) => i.title).filter(Boolean).slice(0, 6),
          channels: data.channels || [],
        };
        state.business_name = summary.business_name;
        state.shop_urls = [primaryUrl, ...extraUrls];
        state.crawl_summary = summary;
        if (!offerChosen) {
          const guess = guessBusinessType(items, priceRange);
          if (guess) {
            setOffer(guess);
            state.business_type = guess;
            if (offerHint) offerHint.textContent = `Muse guessed “${OFFER_LABELS[guess]}” from your website. Change it if that is not right.`;
          }
        }

        // Extract social handles strictly from crawled pages
        const extractedSocials = extractSocialHandlesFromCrawl(data);
        if (extractedSocials.length > 0) {
          const existingKeys = new Set(state.socials.map((s) => `${s.platform}:${s.handle.toLowerCase()}`));
          extractedSocials.forEach((s) => {
            const k = `${s.platform}:${s.handle.toLowerCase()}`;
            if (!existingKeys.has(k)) state.socials.push(s);
          });
        }
        renderCrawlProof(summary);
        await saveServerOnboarding(state);
        if (typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
          window.dispatchEvent(
            new CustomEvent('muse:scan-complete', {
              detail: { summary, data, businessName: summary.business_name, primaryUrl, extraUrls },
            })
          );
        }
        return true;
      } catch (err) {
        if (step1Err) {
          step1Err.textContent = err.message || 'Could not scan that shop URL. Check the address or skip this step.';
          step1Err.hidden = false;
        }
        return false;
      } finally {
        if (scanBtn) {
          scanBtn.disabled = false;
          scanBtn.textContent = 'Scan my shop (free · 0 runs)';
        }
      }
    }

    document.getElementById('wkScanShopBtn')?.addEventListener('click', performStep1Crawl);

    document.getElementById('wkStep1NextBtn')?.addEventListener('click', async () => {
      const typedUrl = normalizeShopUrl(shopUrlInput?.value || '');
      const websiteChanged = Boolean(typedUrl && state.crawl_summary && typedUrl !== (state.shop_urls || [])[0]);
      if (websiteChanged) {
        const ok = await performStep1Crawl();
        if (!ok) return;
      } else if (!state.crawl_summary && shopUrlInput?.value.trim()) {
        const ok = await performStep1Crawl();
        if (!ok) return;
      } else if (!state.crawl_summary && !shopUrlInput?.value.trim()) {
        if (step1Err) {
          step1Err.textContent = 'Enter your shop URL to scan, or click "Skip this step".';
          step1Err.hidden = false;
        }
        return;
      }
      keepStep1Answers();
      trackEvent('onboarding_step_completed', { step: 1 });
      renderStep2Socials();
      state.step = 2;
      await saveServerOnboarding(state);
      showStep(2);
    });

    document.getElementById('wkStep1SkipBtn')?.addEventListener('click', async () => {
      if (!state.skipped.includes(1)) state.skipped.push(1);
      keepStep1Answers();
      trackEvent('onboarding_skipped', { step: 1 });
      renderStep2Socials();
      state.step = 2;
      await saveServerOnboarding(state);
      showStep(2);
    });

    // =========================================================================
    // STEP 2: YOUR SOCIALS
    // =========================================================================
    const socialChipsEl = document.getElementById('wkSocialChips');
    const socialEmptyEl = document.getElementById('wkSocialEmptyNotice');

    function renderStep2Socials() {
      if (!socialChipsEl) return;
      socialChipsEl.textContent = '';
      if (!state.socials || state.socials.length === 0) {
        if (socialEmptyEl) socialEmptyEl.hidden = false;
        return;
      }
      if (socialEmptyEl) socialEmptyEl.hidden = true;
      state.socials.forEach((soc, idx) => {
        const chip = document.createElement('div');
        chip.className = 'wk-social-chip' + (soc.confirmed ? ' is-confirmed' : '');
        const label = document.createElement('span');
        const capPlat = soc.platform.charAt(0).toUpperCase() + soc.platform.slice(1);
        label.textContent = `${capPlat}: ${soc.handle}${soc.source === 'crawl' ? ' (found on your site)' : ''}`;
        chip.appendChild(label);

        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = 'wk-chip-btn' + (soc.confirmed ? ' primary' : '');
        confirmBtn.textContent = soc.confirmed ? '✓ Confirmed' : 'Confirm';
        confirmBtn.addEventListener('click', () => {
          soc.confirmed = !soc.confirmed;
          renderStep2Socials();
        });

        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'wk-chip-btn';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => {
          const platEl = document.getElementById('wkSocialPlatform');
          const inpEl = document.getElementById('wkSocialHandleInput');
          if (platEl) platEl.value = soc.platform;
          if (inpEl) {
            inpEl.value = soc.handle;
            inpEl.focus();
          }
          state.socials.splice(idx, 1);
          renderStep2Socials();
        });

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'wk-chip-btn';
        removeBtn.setAttribute('aria-label', `Remove ${soc.handle}`);
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', () => {
          state.socials.splice(idx, 1);
          renderStep2Socials();
        });

        chip.append(confirmBtn, editBtn, removeBtn);
        socialChipsEl.appendChild(chip);
      });
    }

    document.getElementById('wkAddSocialBtn')?.addEventListener('click', () => {
      const plat = document.getElementById('wkSocialPlatform')?.value || 'instagram';
      const inp = document.getElementById('wkSocialHandleInput');
      const raw = String(inp?.value || '').trim();
      const errEl = document.getElementById('wkStep2Error');
      if (!raw) {
        if (errEl) {
          errEl.textContent = 'Enter a handle (like @myshop) or profile link.';
          errEl.hidden = false;
        }
        return;
      }
      if (errEl) errEl.hidden = true;
      let handle = raw;
      if (/^https?:\/\//i.test(raw)) {
        try {
          const parts = new URL(raw).pathname.split('/').filter(Boolean);
          if (parts.length) handle = '@' + parts[0].replace(/^@/, '');
        } catch (_) {}
      } else if (!handle.startsWith('@')) {
        handle = '@' + handle;
      }
      state.socials.push({
        platform: plat,
        handle,
        url: /^https?:\/\//i.test(raw) ? raw : `https://${plat}.com/${handle.replace(/^@/, '')}`,
        confirmed: true,
        source: 'manual',
      });
      if (inp) inp.value = '';
      renderStep2Socials();
      writeLocalOnboarding(state, currentUser);
    });

    document.getElementById('wkStep2BackBtn')?.addEventListener('click', () => showStep(1));
    document.getElementById('wkStep2SkipBtn')?.addEventListener('click', async () => {
      if (!state.skipped.includes(2)) state.skipped.push(2);
      trackEvent('onboarding_skipped', { step: 2 });
      renderStep3Competitors();
      state.step = 3;
      await saveServerOnboarding(state);
      showStep(3);
    });
    document.getElementById('wkStep2NextBtn')?.addEventListener('click', async () => {
      trackEvent('onboarding_step_completed', { step: 2 });
      renderStep3Competitors();
      state.step = 3;
      await saveServerOnboarding(state);
      showStep(3);
    });

    // =========================================================================
    // STEP 3: YOUR COMPETITORS
    // =========================================================================
    const compListEl = document.getElementById('wkCompList');
    const step3Err = document.getElementById('wkStep3Error');

    const compRoleOptions = [
      { value: 'similar_audience', label: 'Similar audience' },
      { value: 'price_reference', label: 'Price reference' },
      { value: 'inspiration', label: 'Creative inspiration' },
    ];

    function renderStep3Competitors() {
      updateRunsUI();
      if (!compListEl) return;
      compListEl.textContent = '';
      (state.competitors || []).forEach((comp, idx) => {
        if (!comp.role || !compRoleOptions.some((o) => o.value === comp.role)) {
          comp.role = 'similar_audience';
        }
        if (typeof comp.rationale !== 'string') {
          comp.rationale = comp.reason || '';
        }
        const li = document.createElement('li');
        li.className = 'wk-comp-item sm-wk-comp-item';
        const label = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = comp.selected !== false;
        cb.addEventListener('change', () => {
          comp.selected = cb.checked;
          writeLocalOnboarding(state, currentUser);
        });

        const textWrap = document.createElement('div');
        textWrap.style.flex = '1';
        textWrap.style.minWidth = '0';
        const nameEl = document.createElement('strong');
        nameEl.textContent = comp.name || comp.url;
        const urlEl = document.createElement('div');
        urlEl.style.fontSize = '0.78rem';
        urlEl.style.color = 'var(--wk-muted)';
        urlEl.textContent = comp.url;
        const reasonEl = document.createElement('div');
        reasonEl.style.fontSize = '0.82rem';
        reasonEl.style.marginTop = '2px';
        reasonEl.textContent = comp.reason || 'Watched competitor store';

        const metaRow = document.createElement('div');
        metaRow.className = 'sm-comp-role-wrap';

        const roleLabel = document.createElement('label');
        roleLabel.className = 'sm-field-inline';
        roleLabel.textContent = 'Why watch: ';
        const roleSelect = document.createElement('select');
        roleSelect.className = 'wk-select sm-comp-role';
        roleSelect.setAttribute('aria-label', `Role for ${comp.name || comp.url}`);
        compRoleOptions.forEach((opt) => {
          const o = document.createElement('option');
          o.value = opt.value;
          o.textContent = opt.label;
          if (opt.value === comp.role) o.selected = true;
          roleSelect.appendChild(o);
        });
        roleSelect.addEventListener('change', () => {
          comp.role = roleSelect.value;
          writeLocalOnboarding(state, currentUser);
        });
        roleLabel.appendChild(roleSelect);

        const rationaleInput = document.createElement('input');
        rationaleInput.type = 'text';
        rationaleInput.className = 'wk-input sm-comp-rationale';
        rationaleInput.placeholder = 'Note why (e.g. gift packaging, $35 entry print)';
        rationaleInput.maxLength = 200;
        rationaleInput.value = comp.rationale || comp.reason || '';
        rationaleInput.setAttribute('aria-label', `Rationale for ${comp.name || comp.url}`);
        rationaleInput.addEventListener('change', () => {
          comp.rationale = rationaleInput.value.trim();
          comp.reason = comp.rationale || comp.reason || '';
          reasonEl.textContent = comp.reason || 'Watched competitor store';
          writeLocalOnboarding(state, currentUser);
        });

        metaRow.append(roleLabel, rationaleInput);
        textWrap.append(nameEl, urlEl, reasonEl, metaRow);

        label.append(cb, textWrap);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'wk-chip-btn';
        removeBtn.setAttribute('aria-label', `Remove ${comp.name || comp.url}`);
        removeBtn.textContent = 'Remove';
        removeBtn.addEventListener('click', () => {
          state.competitors.splice(idx, 1);
          renderStep3Competitors();
          writeLocalOnboarding(state, currentUser);
        });

        li.append(label, removeBtn);
        compListEl.appendChild(li);
      });
    }

    // Suggestions: Muse reads the seller's own shop website (1 live run) and the results arrive
    // unticked, so the seller picks. A guest is asked to create a free account first.
    const suggestBtnLabel = 'Suggest similar shops (1 run)';
    const suggestNote = document.getElementById('wkSuggestNote');
    const showSuggestNote = (text) => {
      if (!suggestNote) return;
      suggestNote.textContent = text || '';
      suggestNote.hidden = !text;
    };
    if (!currentUser) showSuggestNote('Suggestions need a free account. It comes with 3 runs, and your setup so far comes with you.');
    document.getElementById('wkDiscoverCompBtn')?.addEventListener('click', async () => {
      if (step3Err) step3Err.hidden = true;
      if (!currentUser) {
        writeLocalOnboarding(state, null);
        saveSignupHandoff({ from: 'wizard', step: 3 });
        trackEvent('signup_prompted', { surface: 'onboarding_suggest_competitors' });
        window.museAccount?.open?.('signup', 'Create a free account and Muse will suggest shops like yours. You get 3 free runs, and suggestions use 1. Your setup so far comes with you.');
        return;
      }
      const shopUrl = (state.shop_urls || []).find(Boolean);
      if (!shopUrl) {
        if (step3Err) {
          step3Err.textContent = 'Add your shop website in step 1 first, so Muse knows what you sell.';
          step3Err.hidden = false;
        }
        return;
      }
      const btn = document.getElementById('wkDiscoverCompBtn');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Reading your shop and finding similar ones…';
      }
      try {
        const resp = await fetch('/api/v1/research-targets?live=true', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ website: shopUrl }),
        });
        let data = {};
        try { data = await resp.json(); } catch (_) {}
        if (!resp.ok) {
          const detail = typeof data.detail === 'string' && !/<html|traceback/i.test(data.detail) ? data.detail : '';
          if (resp.status === 401) throw new Error('Your session ended, so no run was used. Sign in again to get suggestions.');
          throw new Error(detail || 'Muse could not suggest shops right now, so no run was used. Add competitors by hand below.');
        }
        let added = 0;
        (data.targets || []).forEach((target) => {
          const url = normalizeShopUrl(target.url);
          if (!url || state.competitors.some((c) => c.url === url)) return;
          state.competitors.push({
            name: target.name || deriveBusinessName(url),
            url,
            role: 'similar_audience',
            rationale: target.reason || '',
            reason: target.reason || 'Suggested by Muse from your website',
            selected: false,
            suggested: true,
          });
          added += 1;
        });
        renderStep3Competitors();
        writeLocalOnboarding(state, currentUser);
        await saveServerOnboarding(state);
        showSuggestNote(added
          ? `Muse suggested ${added} ${added === 1 ? 'shop' : 'shops'} from your website. They are unverified, so tick the ones you want to watch.`
          : 'Muse found no new shops to suggest. Add competitors by hand below.');
        trackEvent('onboarding_competitors_suggested', { count: added });
      } catch (err) {
        if (step3Err) {
          step3Err.textContent = err.message;
          step3Err.hidden = false;
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = suggestBtnLabel;
        }
        try {
          const snap = await window.museAccount?.refresh?.();
          if (snap?.usage && typeof snap.usage.remaining === 'number') runsRemaining = Math.max(0, snap.usage.remaining);
        } catch (_) {}
        updateRunsUI();
      }
    });

    document.getElementById('wkAddCompBtn')?.addEventListener('click', () => {
      const urlInp = document.getElementById('wkManualCompUrl');
      const reasonInp = document.getElementById('wkManualCompReason');
      const roleInp = document.getElementById('wkManualCompRole');
      const url = normalizeShopUrl(urlInp?.value);
      if (!url) {
        if (step3Err) {
          step3Err.textContent = 'Enter a valid competitor domain or URL (like rivalpottery.com).';
          step3Err.hidden = false;
        }
        return;
      }
      if (step3Err) step3Err.hidden = true;
      const reasonText = String(reasonInp?.value || '').trim() || 'Added by you to watch prices & listings';
      if (!state.competitors.some((c) => c.url === url)) {
        state.competitors.push({
          name: deriveBusinessName(url),
          url,
          role: roleInp?.value || 'similar_audience',
          rationale: reasonText,
          reason: reasonText,
          selected: true,
        });
      }
      if (urlInp) urlInp.value = '';
      if (reasonInp) reasonInp.value = '';
      renderStep3Competitors();
      writeLocalOnboarding(state, currentUser);
    });

    document.getElementById('wkStep3BackBtn')?.addEventListener('click', () => showStep(2));
    document.getElementById('wkStep3SkipBtn')?.addEventListener('click', async () => {
      if (!state.skipped.includes(3)) state.skipped.push(3);
      trackEvent('onboarding_skipped', { step: 3 });
      updateRunsUI();
      state.step = 4;
      await saveServerOnboarding(state);
      showStep(4);
    });
    document.getElementById('wkStep3NextBtn')?.addEventListener('click', async () => {
      trackEvent('onboarding_step_completed', { step: 3 });
      updateRunsUI();
      state.step = 4;
      await saveServerOnboarding(state);
      showStep(4);
    });

    // =========================================================================
    // STEP 4: HOW YOU WORK & WORKSPACE COMPLETION
    // =========================================================================
    // Saved step 4 answers go back into the form, so editing setup never resets them to defaults.
    function hydrateStep4(prefs) {
      if (!prefs || typeof prefs !== 'object') return;
      const setVal = (id, value) => {
        const el = document.getElementById(id);
        if (el && value !== undefined && value !== null && value !== '') el.value = String(value);
      };
      setVal('wkPrefExperience', prefs.experience);
      const access = prefs.access || {};
      if (typeof access.can_change_prices === 'boolean') setVal('wkPrefPriceControl', access.can_change_prices ? 'yes' : 'no');
      setVal('wkPrefMinutes', access.minutes_per_week);
      setVal('wkPrefBudget', access.ads_budget_band);
      if (Array.isArray(access.channels)) {
        document.querySelectorAll('#wkPrefChannels input[type="checkbox"]').forEach((el) => {
          el.checked = access.channels.includes(el.value);
        });
      }
      const taste = prefs.taste || {};
      setVal('wkPrefTone', taste.tone);
      setVal('wkPrefAvoid', taste.subjects_to_avoid);
      setVal('wkPrefFocus', prefs.research_focus);
    }
    if (editing) hydrateStep4(state.preferences);

    function collectStep4Preferences() {
      const channels = [...document.querySelectorAll('#wkPrefChannels input[type="checkbox"]:checked')].map((el) => el.value);
      return {
        experience: document.getElementById('wkPrefExperience')?.value || 'some',
        access: {
          channels,
          can_change_prices: (document.getElementById('wkPrefPriceControl')?.value || 'yes') === 'yes',
          minutes_per_week: parseInt(document.getElementById('wkPrefMinutes')?.value || '30', 10),
          ads_budget_band: document.getElementById('wkPrefBudget')?.value || 'none',
        },
        taste: {
          tone: document.getElementById('wkPrefTone')?.value || 'warm_story',
          subjects_to_avoid: String(document.getElementById('wkPrefAvoid')?.value || '').trim().slice(0, 160),
        },
        research_focus: String(document.getElementById('wkPrefFocus')?.value || '').trim().slice(0, 300),
        watch: {
          competitor_urls: (state.competitors || []).filter((c) => c.selected !== false).map((c) => c.url),
        },
        version: 1,
      };
    }

    async function completeOnboarding(skippedStep4) {
      if (skippedStep4 && editing) {
        // Editing: keep the saved step 4 answers as they are.
      } else if (skippedStep4) {
        if (!state.skipped.includes(4)) state.skipped.push(4);
        trackEvent('onboarding_skipped', { step: 4 });
      } else {
        state.preferences = collectStep4Preferences();
        trackEvent('onboarding_step_completed', { step: 4 });
      }

      const finishBtn = document.getElementById('wkStep4FinishBtn');
      const skipBtn = document.getElementById('wkStep4SkipBtn');
      const errEl = document.getElementById('wkStep4Error');
      if (errEl) errEl.hidden = true;
      if (finishBtn) finishBtn.disabled = true;
      if (skipBtn) skipBtn.disabled = true;

      if (runsRemaining > 0) {
        trackEvent('onboarding_run_confirmed', { runs_remaining: runsRemaining });
      }

      let buildResult = null;
      try {
        const payload = {
          business_name: state.business_name,
          business_type: state.business_type || null,
          shop_urls: state.shop_urls,
          socials: state.socials,
          competitors: state.competitors,
          preferences: state.preferences,
          skipped: state.skipped,
          crawl_summary: state.crawl_summary,
          edit: editing,
          step: 5,
        };

        const headers = { 'Content-Type': 'application/json' };
        if (currentUser?.id) {
          headers['X-Muse-Owner'] = currentUser.id;
        }

        const resp = await fetch('/api/v1/onboarding/build', {
          method: 'POST',
          credentials: 'same-origin',
          headers,
          body: JSON.stringify(payload),
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || errData.message || 'Could not complete onboarding. Please try again.');
        }

        buildResult = await resp.json();
      } catch (err) {
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent = err.message || 'Could not complete onboarding.';
        }
        if (finishBtn) finishBtn.disabled = false;
        if (skipBtn) skipBtn.disabled = false;
        return;
      }

      state.completed_at = buildResult.completed_at || new Date().toISOString();
      state.used_run = Boolean(buildResult.used_run);
      if (typeof buildResult.runs_remaining === 'number') {
        runsRemaining = buildResult.runs_remaining;
      } else if (buildResult.charged) {
        runsRemaining = Math.max(0, runsRemaining - 1);
      }
      updateRunsUI();

      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'own');
      } catch (_) {}
      writeLocalOnboarding(state, currentUser);

      const confirmedSocials = (state.socials || []).filter((s) => s.confirmed !== false);
      const selectedCompetitors = (state.competitors || []).filter((c) => c.selected !== false);

      trackEvent(editing ? 'onboarding_edited' : 'onboarding_completed', {
        has_socials: confirmedSocials.length > 0,
        competitor_count: selectedCompetitors.length,
        used_run: Boolean(state.used_run),
      });

      const doneTitle = document.getElementById('wkDoneTitle');
      if (doneTitle) {
        doneTitle.textContent = editing
          ? `Changes saved for ${state.business_name || 'your shop'}`
          : `${state.business_name || 'Your shop'} workspace is ready`;
      }
      const doneSub = document.getElementById('wkDoneSubtitle');
      if (doneSub) {
        doneSub.textContent = editing
          ? 'Muse uses your updated setup from now on (0 runs used):'
          : 'Your workspace is set up with what Muse found on your website and the shops you watch (0 runs used):';
      }
      if (editing) document.getElementById('wkEditBanner')?.remove();

      const summaryList = document.getElementById('wkSummaryList');
      if (summaryList) {
        summaryList.textContent = '';
        const pagesCount = state.crawl_summary?.pages_crawled || 0;
        const shopLabel = state.business_name || 'Your shop';
        const priceLabel = state.crawl_summary?.price_range || '';
        const compNames = selectedCompetitors.map((c) => c.name || c.url).join(', ');

        const readItem = `What Muse read: ${pagesCount} pages from ${shopLabel} and ${selectedCompetitors.length} competitors (${compNames || 'none selected'})`;
        const extraMem = typeof window.museSellerMemory?.getOnboardingMemoryEntries === 'function'
          ? window.museSellerMemory.getOnboardingMemoryEntries()
          : [];
        const foundItem = `What it found: ${priceLabel ? `Detected price range ${priceLabel}` : 'No public prices detected yet'} and saved your shop crawl (${pagesCount} pages), ${selectedCompetitors.length} competitors, and ${extraMem.length} profile item(s). Zero runs spent.`;
        const runDefItem = 'What a run is: A run is one full Muse AI research, competitor crawl, or ad generation cycle.';
        const runsLeftItem = `Runs remaining: You have ${runsRemaining} ${runsRemaining === 1 ? 'run' : 'runs'} left this month for your ad generations and live research.`;
        const cachedItem = 'What is cached: Your shop crawl, competitor watchlist, and setup results are cached so reopening your workspace costs 0 runs.';
        const socialsItem = `Confirmed socials: ${confirmedSocials.length ? confirmedSocials.map((s) => `${s.platform} (${s.handle})`).join(', ') : 'None added yet'}`;

        [readItem, foundItem, runDefItem, runsLeftItem, cachedItem, socialsItem].forEach((txt) => {
          const li = document.createElement('li');
          li.textContent = `✓ ${txt}`;
          summaryList.appendChild(li);
        });
      }

      const emailInp = document.getElementById('wkDigestEmail');
      if (emailInp && currentUser?.email && !emailInp.value) {
        emailInp.value = currentUser.email;
      }
      const watchDesc = document.getElementById('wkDigestWatchDesc');
      if (watchDesc && selectedCompetitors.length > 0) {
        watchDesc.textContent = `We’ll watch ${selectedCompetitors.map((c) => c.name || c.url).join(', ')} and send one ready-to-post idea every Monday.`;
      }

      showStep(5);
      trackEvent('onboarding_explainer_viewed', {
        used_run: Boolean(state.used_run),
        runs_left: runsRemaining,
      });
    }

    document.getElementById('wkStep4BackBtn')?.addEventListener('click', () => showStep(3));
    document.getElementById('wkStep4SkipBtn')?.addEventListener('click', () => completeOnboarding(true));
    document.getElementById('wkStep4FinishBtn')?.addEventListener('click', () => completeOnboarding(false));

    document.getElementById('wkDigestSubscribeBtn')?.addEventListener('click', async () => {
      const emailVal = String(document.getElementById('wkDigestEmail')?.value || '').trim();
      const statusEl = document.getElementById('wkDigestStatus');
      if (!emailVal || !emailVal.includes('@')) {
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = 'Enter a valid email address.';
        }
        return;
      }
      try {
        const resp = await fetch('/api/v1/digest/subscribe', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: emailVal }),
        });
        const data = await resp.json().catch(() => ({}));
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = data.message || '✓ Check your inbox to confirm your Monday digest subscription.';
        }
        trackEvent('digest_subscribed', { trigger: 'onboarding_complete' });
      } catch (_) {
        if (statusEl) {
          statusEl.hidden = false;
          statusEl.textContent = 'Saved your digest preference.';
        }
      }
    });

    // Initial step render on load
    renderStep2Socials();
    renderStep3Competitors();
    showStep(state.step >= 1 && state.step <= 4 ? state.step : 1);
  }

  // =========================================================================
  // 2. HOME PAGE (/) SIGNED-IN WORKSPACE & HONEST EMPTY STATES
  // =========================================================================
  function captureCleanHomeState() {
    if (cleanHomeState || !document.getElementById('journey')) return;
    const textTargets = [];
    [
      '#activeWorkspaceKicker', '.workspace-kicker', '#activeWorkspaceLabel', '#activeAvatar',
      '.jr-eyebrow', '#actionablePlaybookTitle', '#heroTitle', '#heroCategory', '#heroDesc',
      '#kpiArtworks', '#kpiPriceGap', '#kpiRoas', '#compDomainBadge', '#compSummaryText',
    ].forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) textTargets.push([el, el.textContent]);
    });
    const hiddenTargets = ['#loggedOutHero', '.hero-bridge', '.ra-moves-strip']
      .map((sel) => document.querySelector(sel))
      .filter(Boolean)
      .map((el) => [el, Boolean(el.hidden)]);
    const childTargets = [];
    [
      '.monitoring-title', '.monitoring-right', '#loop-research .jr-card.c1',
      '#loop-research .jr-watch', '#sellerList', '#adGallery',
      '#loop-improve ol.jr-recos', '#channelStrip',
    ].forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) childTargets.push([el, Array.from(el.childNodes)]);
    });
    document.querySelectorAll('.jr-stats > div, #loop-research .jr-card.c2').forEach((el) => {
      childTargets.push([el, Array.from(el.childNodes)]);
    });
    ['findingsContainer', 'insightsContainer', 'diagnosticsContainer', 'metaAdsContainer', 'reallocationsContainer', 'audiencesContainer'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) childTargets.push([el, Array.from(el.childNodes)]);
    });
    const steerInput = document.getElementById('jrSteerInput');
    const compInput = document.getElementById('compUrlInput');
    cleanHomeState = {
      textTargets,
      hiddenTargets,
      childTargets,
      // #competitorSnapshotsNote is worded per visitor by index.html (refreshVisitorCopy).
      jrNotes: Array.from(document.querySelectorAll('#journey .jr-note:not(#competitorSnapshotsNote)')).map((el) => [el, el.textContent]),
      nextSpans: Array.from(document.querySelectorAll('#loop-iterate .jr-next-card span')).map((el) => [el, el.textContent]),
      steerPlaceholder: steerInput ? [steerInput, steerInput.placeholder] : null,
      compInput: compInput ? [compInput, compInput.value, compInput.placeholder] : null,
      chips: Array.from(document.querySelectorAll('.jr-chip-btn')).map((el) => [el, el.textContent, el.getAttribute('data-directive')]),
      refineChips: Array.from(document.querySelectorAll('.ms-refine-chips button')).map((el) => [el, el.textContent, el.getAttribute('data-refine')]),
    };
  }

  function resetSignedOutHomeWorkspace({ preserveMode = false } = {}) {
    document.getElementById('ownWorkspaceOptionBtn')?.remove();
    window.__museApplySignedInWorkspace = null;
    lastRenderedUserId = null;
    if (!preserveMode) {
      try {
        if (localStorage.getItem(LOCAL_WORKSPACE_MODE_KEY) === 'own') {
          localStorage.removeItem(LOCAL_WORKSPACE_MODE_KEY);
        }
      } catch (_) {}
    }
    if (cleanHomeState) {
      cleanHomeState.textTargets.forEach(([el, text]) => { if (el) el.textContent = text; });
      cleanHomeState.hiddenTargets.forEach(([el, hidden]) => { if (el) el.hidden = hidden; });
      cleanHomeState.childTargets.forEach(([el, nodes]) => { if (el) el.replaceChildren(...nodes); });
      cleanHomeState.jrNotes.forEach(([el, text]) => { if (el) el.textContent = text; });
      cleanHomeState.nextSpans.forEach(([el, text]) => { if (el) el.textContent = text; });
      if (cleanHomeState.steerPlaceholder) {
        const [el, placeholder] = cleanHomeState.steerPlaceholder;
        if (el) el.placeholder = placeholder;
      }
      if (cleanHomeState.compInput) {
        const [el, value, placeholder] = cleanHomeState.compInput;
        if (el) { el.value = value; el.placeholder = placeholder; }
      }
      cleanHomeState.chips.forEach(([el, text, directive]) => {
        if (!el) return;
        el.textContent = text;
        if (directive === null) el.removeAttribute('data-directive');
        else el.setAttribute('data-directive', directive);
      });
      cleanHomeState.refineChips.forEach(([el, text, refine]) => {
        if (!el) return;
        el.textContent = text;
        if (refine === null) el.removeAttribute('data-refine');
        else el.setAttribute('data-refine', refine);
      });
    } else if (document.getElementById('journey')) {
      const loggedOutHero = document.getElementById('loggedOutHero');
      if (loggedOutHero) loggedOutHero.hidden = false;
      const heroBridge = document.querySelector('.hero-bridge');
      if (heroBridge) heroBridge.hidden = false;
      const movesStrip = document.querySelector('.ra-moves-strip');
      if (movesStrip) movesStrip.hidden = false;
    }
    try {
      window.dispatchEvent(new CustomEvent('muse:workspace-reset'));
    } catch (_) {}
  }

  function renderSignedInHomeWorkspace(onboarding, user) {
    if (!document.getElementById('journey')) return;
    captureCleanHomeState();
    lastRenderedUserId = user?.id || null;

    const shopName = onboarding?.business_name || (user?.email ? `${user.email.split('@')[0]}’s Shop` : 'Your Shop');
    const summary = onboarding?.crawl_summary || null;
    const socials = (onboarding?.socials || []).filter((s) => s.confirmed !== false);
    const competitors = (onboarding?.competitors || []).filter((c) => c.selected !== false);
    const priceRange = summary?.price_range || '';
    const pagesCrawled = summary?.pages_crawled || 0;

    // 1. Topbar workspace label & kicker
    const kickerEl = document.getElementById('activeWorkspaceKicker') || document.querySelector('.workspace-kicker');
    if (kickerEl) kickerEl.textContent = 'Your shop';
    const labelEl = document.getElementById('activeWorkspaceLabel');
    if (labelEl) labelEl.textContent = shopName;
    const avatarEl = document.getElementById('activeAvatar');
    if (avatarEl) {
      const initials = shopName
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w.charAt(0).toUpperCase())
        .join('');
      avatarEl.textContent = initials || 'YS';
    }

    // Hide logged-out marketing hero for signed-in users viewing their own workspace
    const loggedOutHero = document.getElementById('loggedOutHero');
    if (loggedOutHero) loggedOutHero.hidden = true;
    const heroBridge = document.querySelector('.hero-bridge');
    if (heroBridge) heroBridge.hidden = true;

    // 2. Monitoring / Watchlist top bar — zero Sarabjit data
    const monTitle = document.querySelector('.monitoring-title');
    if (monTitle) {
      monTitle.textContent = '';
      const strong = document.createElement('strong');
      if (competitors.length > 0) {
        strong.textContent = `Watching ${competitors.length} ${competitors.length === 1 ? 'competitor' : 'competitors'}`;
        const details = document.createElement('span');
        details.className = 'monitoring-details';
        details.textContent = ` · ${competitors.map((c) => c.name || c.url).join(', ')}`;
        monTitle.append(strong, details);
      } else {
        strong.textContent = 'Watching 0 competitors';
        const addLink = document.createElement('a');
        addLink.href = '/welcome?step=3';
        addLink.style.marginLeft = '8px';
        addLink.style.color = '#a6f4c5';
        addLink.textContent = 'Choose competitors →';
        monTitle.append(strong, addLink);
      }
    }
    const monRight = document.querySelector('.monitoring-right');
    if (monRight) {
      monRight.textContent = '';
      const pill1 = document.createElement('span');
      pill1.className = 'monitoring-pill';
      pill1.textContent = `${pagesCrawled} shop ${pagesCrawled === 1 ? 'page' : 'pages'} scanned`;
      const pill2 = document.createElement('a');
      pill2.className = 'monitoring-pill';
      pill2.href = '/?workspace=sample';
      pill2.style.color = '#fff';
      pill2.style.textDecoration = 'underline';
      pill2.textContent = 'Switch to Sample shop';
      monRight.append(pill1, pill2);
    }

    // 3. Growth loop hero stats — honest counts from user's workspace only
    const eyebrow = document.querySelector('.jr-eyebrow');
    if (eyebrow) eyebrow.textContent = `${shopName} · your growth workspace`;
    const statsBoxes = document.querySelectorAll('.jr-stats > div');
    if (statsBoxes.length >= 4) {
      statsBoxes[0].innerHTML = '';
      const s0Strong = document.createElement('strong');
      s0Strong.textContent = String(pagesCrawled);
      const s0Span = document.createElement('span');
      s0Span.textContent = 'your shop pages scanned [live]';
      statsBoxes[0].append(s0Strong, s0Span);

      statsBoxes[1].innerHTML = '';
      const s1Strong = document.createElement('strong');
      s1Strong.textContent = String(competitors.length);
      const s1Span = document.createElement('span');
      s1Span.textContent = 'competitors on your watchlist [live]';
      statsBoxes[1].append(s1Strong, s1Span);

      statsBoxes[2].innerHTML = '';
      const s2Strong = document.createElement('strong');
      s2Strong.textContent = String(socials.length);
      const s2Span = document.createElement('span');
      s2Span.textContent = 'confirmed social channels [live]';
      statsBoxes[2].append(s2Strong, s2Span);

      statsBoxes[3].innerHTML = '';
      const s3Strong = document.createElement('strong');
      s3Strong.textContent = priceRange || '—';
      const s3Span = document.createElement('span');
      s3Span.textContent = 'detected shop price range [live]';
      statsBoxes[3].append(s3Strong, s3Span);
    }

    // 4. Research Stage Card 1: Your business
    const bizCard = document.querySelector('#loop-research .jr-card.c1');
    if (bizCard) {
      bizCard.textContent = '';
      const h = document.createElement('header');
      const h3 = document.createElement('h3');
      h3.textContent = 'Your business';
      h.appendChild(h3);
      bizCard.appendChild(h);

      if (!onboarding?.shop_urls?.length) {
        const p = document.createElement('p');
        p.className = 'jr-note';
        p.textContent = 'No shop URL connected yet. Scan your website or marketplace shop to load your catalog and prices.';
        const a = document.createElement('a');
        a.className = 'jr-action';
        a.href = '/welcome?step=1';
        a.textContent = 'Add your shop URL →';
        bizCard.append(p, a);
      } else {
        const bizRow = document.createElement('div');
        bizRow.className = 'jr-biz';
        const av = document.createElement('span');
        av.className = 'jr-avatar';
        av.textContent = avatarEl ? avatarEl.textContent : 'YS';
        const info = document.createElement('div');
        const st = document.createElement('strong');
        st.textContent = shopName;
        const sp = document.createElement('span');
        sp.textContent = `${onboarding.shop_urls[0]}${priceRange ? ` · Prices ${priceRange}` : ''}`;
        info.append(st, sp);
        bizRow.append(av, info);
        bizCard.appendChild(bizRow);

        const sellsLabel = document.createElement('p');
        sellsLabel.className = 'jr-label';
        sellsLabel.textContent = 'Shop pages';
        const sellsPills = document.createElement('div');
        sellsPills.className = 'jr-pills';
        onboarding.shop_urls.forEach((u) => {
          const pill = document.createElement('span');
          pill.className = 'jr-pill star';
          try {
            pill.textContent = new URL(u).hostname.replace(/^www\./, '');
          } catch (_) {
            pill.textContent = u;
          }
          sellsPills.appendChild(pill);
        });
        bizCard.append(sellsLabel, sellsPills);

        const socLabel = document.createElement('p');
        socLabel.className = 'jr-label';
        socLabel.textContent = 'Confirmed socials';
        bizCard.appendChild(socLabel);
        if (socials.length > 0) {
          const socPills = document.createElement('div');
          socPills.className = 'jr-pills';
          socials.forEach((s) => {
            const pill = document.createElement('span');
            pill.className = 'jr-pill';
            pill.textContent = `${s.platform}: ${s.handle}`;
            socPills.appendChild(pill);
          });
          bizCard.appendChild(socPills);
        } else {
          const emptySoc = document.createElement('a');
          emptySoc.className = 'jr-action';
          emptySoc.href = '/welcome?step=2';
          emptySoc.textContent = 'Confirm your social handles →';
          bizCard.appendChild(emptySoc);
        }
      }
    }

    // 5. Research Stage Card 2: Competitor watchlist
    const sellerListEl = document.getElementById('sellerList');
    const watchPara = document.querySelector('#loop-research .jr-watch');
    if (watchPara) {
      watchPara.textContent = competitors.length
        ? `${competitors.length} ${competitors.length === 1 ? 'competitor' : 'competitors'} on your watchlist`
        : 'No competitors selected yet';
    }
    if (sellerListEl) {
      sellerListEl.textContent = '';
      if (competitors.length === 0) {
        const li = document.createElement('li');
        li.className = 'jr-seller';
        const d = document.createElement('div');
        const st = document.createElement('strong');
        st.textContent = 'Your competitor watchlist is empty';
        const sp = document.createElement('span');
        sp.textContent = 'Add 1 to 6 similar sellers to compare prices and catalog gaps.';
        d.append(st, sp);
        const a = document.createElement('a');
        a.className = 'jr-mini primary';
        a.href = '/welcome?step=3';
        a.textContent = 'Add competitors →';
        li.append(d, a);
        sellerListEl.appendChild(li);
      } else {
        competitors.forEach((comp) => {
          const li = document.createElement('li');
          li.className = 'jr-seller';
          // Analysis reads this, not the row's first link (that is the Meta Ad Library link).
          li.dataset.url = competitorUrl(comp.url);
          const d = document.createElement('div');
          const st = document.createElement('strong');
          st.textContent = comp.name || comp.url;
          const sp = document.createElement('span');
          sp.textContent = `${comp.url} · ${comp.reason || 'Watched competitor'}`;
          const adLink = document.createElement('a');
          adLink.className = 'jr-meta-ad-link';
          adLink.target = '_blank';
          adLink.rel = 'noopener noreferrer';
          const query = comp.name || comp.url;
          adLink.href = `https://www.facebook.com/ads/library/?active_status=active&AdCandidate=&q=${encodeURIComponent(query)}&search_type=keyword_unordered&media_type=all`;
          adLink.textContent = 'See their ads on Meta ↗';
          d.append(st, sp, adLink);
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'jr-mini primary js-live-brief';
          btn.textContent = 'Analyze seller →';
          li.append(d, btn);
          sellerListEl.appendChild(li);
        });
      }
    }

    // 6. Research Stage Card 3: Price comparison chart (honest user price range, no Sarabjit prices)
    const priceCards = document.querySelectorAll('#loop-research .jr-card.c2');
    const priceCard = priceCards.length > 1 ? priceCards[1] : null;
    if (priceCard) {
      priceCard.textContent = '';
      const h = document.createElement('header');
      const h3 = document.createElement('h3');
      h3.textContent = 'Your price positioning';
      h.appendChild(h3);
      priceCard.appendChild(h);

      if (priceRange) {
        const p = document.createElement('p');
        p.style.fontWeight = '700';
        p.style.fontSize = '1.05rem';
        p.textContent = `Your detected price range: ${priceRange} [live]`;
        const sub = document.createElement('p');
        sub.className = 'jr-note';
        sub.textContent = `Extracted from ${pagesCrawled} crawled pages on ${shopName}. Run a live analysis on a watched competitor to plot their price bar beside yours.`;
        priceCard.append(p, sub);
      } else {
        const p = document.createElement('p');
        p.className = 'jr-note';
        p.textContent = 'No public product prices detected yet. Scan your product pages so Muse can compare your price range against competitors.';
        const a = document.createElement('a');
        a.className = 'jr-action';
        a.href = '/welcome?step=1';
        a.textContent = 'Scan shop prices →';
        priceCard.append(p, a);
      }
    }

    // 7. Create Stage (#loop-create) & Improve Stage (#loop-improve) — zero Sarabjit data
    const adGallery = document.getElementById('adGallery');
    if (adGallery) {
      adGallery.textContent = '';
      const emptyP = document.createElement('p');
      emptyP.className = 'jr-note';
      emptyP.textContent = `No saved ads generated for ${shopName} yet. Pick an item from your catalog to create your first post.`;
      const createBtn = document.createElement('a');
      createBtn.className = 'jr-action';
      createBtn.href = '/create';
      createBtn.textContent = 'Create your first post →';
      const firstAdBtn = document.createElement('a');
      firstAdBtn.className = 'jr-action';
      firstAdBtn.href = window.museModes?.ownHref ? window.museModes.ownHref('/first-ad') : '/first-ad';
      firstAdBtn.textContent = 'Prepare your first ad →';
      adGallery.append(emptyP, createBtn, firstAdBtn);
    }

    const recosList = document.querySelector('#loop-improve ol.jr-recos');
    if (recosList) {
      recosList.textContent = '';
      const li = document.createElement('li');
      const badge = document.createElement('span');
      badge.className = 'jr-impact high';
      badge.textContent = 'Next move for your shop';
      const title = document.createElement('strong');
      const desc = document.createElement('p');
      const link = document.createElement('a');
      if (competitors.length > 0) {
        title.textContent = `Run your first competitor brief on ${competitors[0].name || competitors[0].url}`;
        desc.textContent = `Compare ${shopName}${priceRange ? ` (${priceRange})` : ''} against ${competitors[0].name || competitors[0].url} to unlock ranked recommendations.`;
        link.href = '#loop-research';
        link.textContent = 'Analyze watched competitor →';
      } else {
        title.textContent = 'Add a competitor to unlock ranked ideas';
        desc.textContent = 'Tell Muse which shops sell similar products so it can rank your highest-impact moves.';
        link.href = '/welcome?step=3';
        link.textContent = 'Choose competitors →';
      }
      li.append(badge, title, desc, link);
      recosList.appendChild(li);

      const adLi = document.createElement('li');
      const adBadge = document.createElement('span');
      adBadge.className = 'jr-impact medium';
      adBadge.textContent = 'First ad preparation';
      const adTitle = document.createElement('strong');
      adTitle.textContent = 'No ad running yet? Prepare your first ad';
      const adDesc = document.createElement('p');
      adDesc.textContent = 'Choose an outcome, review your wording, audience, and budget, and export a manual Ads Manager checklist. Nothing is published automatically.';
      const adLink = document.createElement('a');
      adLink.href = window.museModes?.ownHref ? window.museModes.ownHref('/first-ad') : '/first-ad';
      adLink.textContent = 'Prepare your first ad →';
      adLi.append(adBadge, adTitle, adDesc, adLink);
      recosList.appendChild(adLi);
    }
    const movesStrip = document.querySelector('.ra-moves-strip');
    if (movesStrip) movesStrip.hidden = true;

    // Update static notes in #journey so zero sample-shop references appear on a real account
    document.querySelectorAll('#journey .jr-note:not(#competitorSnapshotsNote)').forEach((noteEl) => {
      if (/SikhiArt|Nov 3|her website/i.test(noteEl.textContent || '')) {
        noteEl.textContent = `Workspace data for ${shopName}. Switch to "Sample shop" in the top bar anytime to view the demo examples.`;
      }
    });
    document.querySelectorAll('#loop-iterate .jr-next-card span').forEach((spanEl) => {
      if (/Empowering Women/i.test(spanEl.textContent || '')) {
        spanEl.textContent = `Pick your next ranked move for ${shopName}.`;
      }
    });

    // Update steer input and chips to derive from user's shop & competitors
    const steerInput = document.getElementById('jrSteerInput');
    if (steerInput) {
      steerInput.placeholder = competitors[0]
        ? `e.g. Look at why ${competitors[0].name || competitors[0].url} prices start higher`
        : 'e.g. Look at competitor prices or find gift ideas under $50';
    }
    document.querySelectorAll('.jr-chip-btn').forEach((chip) => {
      if (/SikhiArt/i.test(chip.textContent || '')) {
        const compName = competitors[0]?.name || competitors[0]?.url || 'competitors';
        chip.textContent = `Why ${compName} entry`;
        chip.setAttribute('data-directive', `Look at why ${compName} starts at higher prices`);
      }
    });
    document.querySelectorAll('.ms-refine-chips button').forEach((btn) => {
      if (/Women/i.test(btn.textContent || '')) {
        btn.textContent = 'Featured series';
        btn.setAttribute('data-refine', 'Focus on my featured series');
      }
    });
    const compInput = document.getElementById('compUrlInput');
    if (compInput) {
      compInput.value = competitors[0]?.url || '';
      compInput.placeholder = competitors[0]?.url || 'https://competitor-shop.com';
    }
    const playbookTitle = document.getElementById('actionablePlaybookTitle');
    if (playbookTitle) playbookTitle.textContent = `Actionable Playbook for ${shopName}`;

    // 8. Full Workspace Hero & Panels — replace Sarabjit title, KPIs, and findings with user's own shop
    const heroTitle = document.getElementById('heroTitle');
    if (heroTitle) heroTitle.textContent = `${shopName} · Growth workspace`;
    const heroCat = document.getElementById('heroCategory');
    if (heroCat) heroCat.textContent = 'Signed-in Seller Workspace';
    const heroDesc = document.getElementById('heroDesc');
    if (heroDesc) {
      heroDesc.textContent = onboarding?.shop_urls?.length
        ? `Connected storefront: ${onboarding.shop_urls.join(', ')}. Switch to "Sample shop" in the top right anytime to view the sample demo.`
        : 'Finish shop setup to populate your storefront channels, prices, and competitors.';
    }
    const channelStrip = document.getElementById('channelStrip');
    if (channelStrip) {
      channelStrip.textContent = '';
      (onboarding?.shop_urls || []).forEach((u) => {
        const a = document.createElement('a');
        a.className = 'channel-chip ok';
        a.href = u;
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = `✓ ${u}`;
        channelStrip.appendChild(a);
      });
      socials.forEach((s) => {
        const a = document.createElement('a');
        a.className = 'channel-chip social';
        a.href = s.url || '#';
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = `${s.platform}: ${s.handle}`;
        channelStrip.appendChild(a);
      });
    }
    const kpiArtworks = document.getElementById('kpiArtworks');
    if (kpiArtworks) kpiArtworks.textContent = `${pagesCrawled} Pages`;
    const kpiPriceGap = document.getElementById('kpiPriceGap');
    if (kpiPriceGap) kpiPriceGap.textContent = priceRange || 'Add prices';
    const kpiRoas = document.getElementById('kpiRoas');
    if (kpiRoas) kpiRoas.textContent = 'Log 1 result';

    const compDomainBadge = document.getElementById('compDomainBadge');
    if (compDomainBadge) {
      compDomainBadge.textContent = competitors[0]?.name || competitors[0]?.url || 'No competitor selected';
    }
    const compSummaryText = document.getElementById('compSummaryText');
    if (compSummaryText) {
      compSummaryText.textContent = competitors.length
        ? `Ready to analyze ${competitors.map((c) => c.name || c.url).join(', ')}. Click "Analyze seller" to generate your first brief.`
        : 'No competitor brief loaded yet. Add a competitor in onboarding to compare catalogs and prices.';
    }
    ['findingsContainer', 'insightsContainer', 'diagnosticsContainer', 'metaAdsContainer', 'reallocationsContainer', 'audiencesContainer'].forEach((id) => {
      const el = document.getElementById(id);
      // The dashboard's competitor ad check may already have filled this card for this seller.
      if (el && user?.id && el.dataset.ownSignalsOwner === user.id) return;
      if (el) {
        el.textContent = '';
        const div = document.createElement('div');
        div.className = 'finding-item';
        if (id === 'metaAdsContainer') {
          const compNames = competitors.map((c) => c.name || c.url);
          const firstComp = compNames[0] || 'competitors';
          const pubUrl = `https://www.facebook.com/ads/library/?active_status=active&AdCandidate=&q=${encodeURIComponent(firstComp)}&search_type=keyword_unordered&media_type=all`;
          div.innerHTML = `
            <div style="font-size:0.85rem;color:var(--text-muted);">Competitor ads have not been checked yet.</div>
            <div style="margin-top:6px;"><a class="jr-meta-ad-link" href="${safeUrl(pubUrl)}" target="_blank" rel="noopener noreferrer">Search public Meta Ad Library for ${esc(firstComp)} ↗</a></div>
          `;
        } else {
          div.textContent = `No data yet for ${shopName}. Complete an analysis or log your first campaign to populate this section.`;
        }
        el.appendChild(div);
      }
    });
  }

  function injectLoginDialogSwitcher(onboarding, user) {
    const loginDialog = document.getElementById('loginDialog');
    if (!loginDialog) return;
    const inner = loginDialog.querySelector('.dialog-inner');
    if (!inner) return;
    document.getElementById('ownWorkspaceOptionBtn')?.remove();

    const sampleOpt = inner.querySelector('[data-ws="sarabjit_singh"]');
    if (!sampleOpt) return;

    // Until setup is finished there is no workspace of their own to open: point to the wizard.
    const setupDone = Boolean(onboarding?.completed_at);
    const ownBtn = document.createElement('button');
    ownBtn.type = 'button';
    ownBtn.id = 'ownWorkspaceOptionBtn';
    ownBtn.className = 'workspace-option';
    const titleDiv = document.createElement('div');
    const nameStrong = document.createElement('div');
    nameStrong.style.fontWeight = '700';
    nameStrong.style.fontSize = '0.95rem';
    nameStrong.textContent = `🏪 ${onboarding?.business_name || (user?.email ? `${user.email.split('@')[0]}’s Shop` : 'Your Shop')}`;
    const subDiv = document.createElement('div');
    subDiv.style.fontSize = '0.8rem';
    subDiv.style.color = 'var(--text-muted)';
    subDiv.style.marginTop = '0.2rem';
    subDiv.textContent = setupDone
      ? ((onboarding?.shop_urls || []).join(' · ') || 'Your personal signed-in workspace')
      : 'Finish setup to open your own workspace.';
    titleDiv.append(nameStrong, subDiv);
    const badge = document.createElement('span');
    badge.className = 'badge green';
    badge.textContent = setupDone ? 'Your shop' : 'Finish setup';
    ownBtn.append(titleDiv, badge);

    ownBtn.addEventListener('click', () => {
      if (!setupDone) {
        window.location.href = '/welcome';
        return;
      }
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'own');
      } catch (_) {}
      window.location.href = '/';
    });

    sampleOpt.parentNode.insertBefore(ownBtn, sampleOpt);

    if (!sampleOpt.dataset.wsBound) {
      sampleOpt.dataset.wsBound = '1';
      sampleOpt.addEventListener('click', () => {
        try {
          localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'sample');
        } catch (_) {}
      });
    }
  }

  // Signed in, setup not finished, viewing the demo: #setupHero says what to do next and replaces
  // the logged-out hero. Any other state hides it; restoreLoggedOut puts the logged-out hero back
  // where it belongs (guests and the sample view).
  const competitorUrl = (url) => (/^https?:\/\//i.test(url || '') ? url : `https://${url}`);

  // A seller who just finished setup gets one card that says what to do first: analyze a
  // competitor (their first personal result, 1 run) or make today's post (free).
  function syncFirstMoveCard(show, onboarding, user, doc) {
    const card = document.getElementById('firstMoveCard');
    if (!card) return;
    const hideKey = user?.id ? `muse.firstmove.hidden.v1:${user.id}` : '';
    let hiddenByUser = false;
    try { hiddenByUser = Boolean(hideKey && localStorage.getItem(hideKey)); } catch (_) {}
    if (!show || hiddenByUser) {
      // Clear it too: a hidden card must not keep another account's shop names in the page.
      card.textContent = '';
      card.hidden = true;
      return;
    }
    const first = (onboarding?.competitors || []).find((c) => c && c.url && c.selected !== false) || null;
    const firstUrl = first ? competitorUrl(first.url) : '';
    const name = first ? (first.name || first.url) : '';
    const analyzed = Boolean(first && (doc?.briefs || {})[firstUrl]);
    const usage = window.museAccount?.getSnapshot?.()?.usage;
    const runsLeft = usage && Number.isFinite(usage.remaining) ? Math.max(0, usage.remaining) : null;
    const make = (tag, cls, text) => {
      const node = document.createElement(tag);
      if (cls) node.className = cls;
      if (text) node.textContent = text;
      return node;
    };
    card.textContent = '';
    const hide = make('button', 'first-move-hide', 'Hide');
    hide.type = 'button';
    hide.addEventListener('click', () => {
      try { if (hideKey) localStorage.setItem(hideKey, '1'); } catch (_) {}
      card.textContent = '';
      card.hidden = true;
    });
    const title = make('h2', '', 'Your shop is set up. Get your first result.');
    title.id = 'firstMoveTitle';
    const actions = make('div', 'first-move-actions');

    const compOption = make('div', 'first-move-option');
    const compBtn = make('button', 'first-move-btn primary');
    compBtn.type = 'button';
    compBtn.id = 'firstMoveCompetitorBtn';
    if (!first) {
      compOption.append(make('strong', '', 'Add a competitor to compare with'),
        make('span', '', 'Muse compares their prices and listings with yours.'));
      compBtn.textContent = 'Add a competitor';
      compBtn.addEventListener('click', () => {
        const input = document.getElementById('addCompetitorInput');
        input?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        input?.focus?.();
      });
    } else if (analyzed) {
      compOption.append(make('strong', '', `See what Muse found about ${name}`),
        make('span', '', 'Your analysis is saved. Viewing it is free.'));
      compBtn.textContent = 'View analysis';
    } else {
      compOption.append(make('strong', '', `Analyze ${name}`),
        make('span', '', `Muse compares their prices and listings with yours. Uses 1 run${runsLeft === null ? '' : ` (you have ${runsLeft} left)`}.`));
      compBtn.textContent = `Analyze ${name} · 1 run`;
    }
    if (first) {
      compBtn.addEventListener('click', () => {
        const row = Array.from(document.querySelectorAll('#sellerList li.jr-seller')).find((li) => li.dataset.url === firstUrl);
        const rowBtn = row?.querySelector('.js-live-brief');
        row?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        if (rowBtn && !rowBtn.disabled) rowBtn.click();
      });
    }
    compOption.append(compBtn);

    const postOption = make('div', 'first-move-option');
    const postLink = make('a', 'first-move-btn', "Open today's studio");
    postLink.href = window.museModes?.ownHref ? window.museModes.ownHref('/today') : '/today';
    postOption.append(make('strong', '', "Make today's post"),
      make('span', '', 'Muse drafts a post from one of your listings. Free.'), postLink);

    actions.append(compOption, postOption);
    card.append(make('p', 'first-move-eyebrow', 'Start here'), title, actions, hide);
    card.hidden = false;
  }

  let setupHeroHidLoggedOut = [];
  function syncSetupHero(show, restoreLoggedOut) {
    const setupHero = document.getElementById('setupHero');
    if (!setupHero) return;
    // The logged-out hero and its "Free demo below ... no account needed" line.
    const guestOnly = [document.getElementById('loggedOutHero'), document.querySelector('.hero-bridge')].filter(Boolean);
    if (show) {
      guestOnly.forEach((el) => {
        if (el.hidden) return;
        el.hidden = true;
        setupHeroHidLoggedOut.push(el);
      });
      const usage = window.museAccount?.getSnapshot?.()?.usage;
      const runs = document.getElementById('setupHeroRuns');
      if (runs) {
        runs.textContent = usage && Number.isFinite(usage.remaining) && Number.isFinite(usage.limit)
          ? `${Math.max(0, usage.remaining)} of ${usage.limit} runs left · research and ad drafts on your products`
          : 'Research and ad drafts on your products';
      }
    } else if (setupHeroHidLoggedOut.length) {
      if (restoreLoggedOut) setupHeroHidLoggedOut.forEach((el) => { el.hidden = false; });
      setupHeroHidLoggedOut = [];
    }
    setupHero.hidden = !show;
  }

  async function applyHomeModeState(modeStateOverride = null) {
    if (window.location.pathname === '/welcome') return;
    if (!document.getElementById('journey')) return;
    const seq = ++homeSyncEpoch;
    const query = new URLSearchParams(window.location.search || '');
    let modeState = modeStateOverride || window.museModes?.current?.() || {
      state: query.get('workspace') === 'sample' ? 'guest_sample' : 'guest_entry',
      isSample: query.get('workspace') === 'sample',
      isAuthenticated: false,
      isLoading: false,
      isError: false,
      isExpired: false,
      ownerId: null,
    };

    try { localStorage.removeItem(LOCAL_WORKSPACE_MODE_KEY); } catch (_) {}

    if (modeState.isLoading) return;
    if (modeState.isError || modeState.isExpired) {
      const rd = document.getElementById('returningDashboard');
      if (rd) rd.hidden = true;
      const sf = document.getElementById('sampleAdFormatsGallery');
      if (sf) sf.hidden = true;
      window.museModes?.renderModeBanners?.();
      return;
    }

    const sf = document.getElementById('sampleAdFormatsGallery');
    if (sf) sf.hidden = modeState.state === 'account_own';

    if (!modeState.isAuthenticated) {
      homeSawSignedOut = true;
      window.museModes?.setSetupPending?.(null);
      syncSetupHero(false, true);
      syncFirstMoveCard(false);
      if (lastRenderedUserId || document.getElementById('ownWorkspaceOptionBtn')) {
        resetSignedOutHomeWorkspace({ preserveMode: modeState.isSample });
      }
      window.museModes?.renderModeBanners?.();
      return;
    }

    const guard = window.museModes?.bindAsyncGuard ? window.museModes.bindAsyncGuard() : { isCurrent: () => true };
    const server = await loadServerWorkspaceDoc();
    if (seq !== homeSyncEpoch || !guard.isCurrent()) return;
    if (server.authStatus === 'error' || server.authStatus === 'expired' || server.authStatus === 'loading') {
      const rd = document.getElementById('returningDashboard');
      if (rd) rd.hidden = true;
      const sf2 = document.getElementById('sampleAdFormatsGallery');
      if (sf2) sf2.hidden = true;
      window.museModes?.renderModeBanners?.();
      return;
    }
    const snap = window.museAccount?.getSnapshot?.();
    if (snap && (snap.user?.id || null) !== (server.user?.id || null)) return;

    const isSignedIn = Boolean(server.user && server.user.id);
    const onboarding = isSignedIn ? (server.doc?.onboarding || null) : null;

    const setupPending = isSignedIn && !(onboarding && onboarding.completed_at);

    // Setup not finished. Arriving from sign-in (the /account landing, an OAuth return, or a
    // sign-in on this page) still goes to the wizard. A seller who comes back to the dashboard
    // without finishing sees the sample shop as an explicit demo, with a nudge to finish setup.
    if (setupPending) {
      const fromSignIn = window.location.pathname === '/account' || query.has('oauth');
      const canShowDemo = typeof window.museModes?.enterSampleMode === 'function';
      if (fromSignIn || (!modeState.isSample && (homeSawSignedOut || !canShowDemo))) {
        window.location.replace('/welcome');
        return;
      }
      if (!modeState.isSample) {
        // The mode subscriber would repeat this pass for the switch we are about to make.
        lastHandledHomeModeKey = `account_sample:${server.user.id}:1`;
        modeState = window.museModes.enterSampleMode();
        if (!modeState?.isSample) {
          window.location.replace('/welcome');
          return;
        }
        if (sf) sf.hidden = false;
      }
    }
    window.museModes?.setSetupPending?.(setupPending ? server.user.id : null);

    if (modeState.isSample) {
      if (lastRenderedUserId || document.getElementById('ownWorkspaceOptionBtn')) {
        resetSignedOutHomeWorkspace({ preserveMode: true });
      }
      if (isSignedIn) {
        injectLoginDialogSwitcher(onboarding, server.user);
        const wsBar = document.getElementById('workspaceBar');
        const wsLabel = document.getElementById('activeWorkspaceLabel');
        if (wsBar) wsBar.hidden = false;
        if (wsLabel) wsLabel.textContent = 'Art of Sarabjit Singh · Sample shop';
      }
      window.museModes?.renderModeBanners?.();
    } else if (isSignedIn) {
      if (lastRenderedUserId && lastRenderedUserId !== server.user.id) {
        resetSignedOutHomeWorkspace({ preserveMode: true });
      }
      injectLoginDialogSwitcher(onboarding, server.user);
      const applyFn = () => renderSignedInHomeWorkspace(onboarding || defaultOnboardingState(), server.user);
      window.__museApplySignedInWorkspace = applyFn;
      applyFn();
    }
    syncSetupHero(Boolean(setupPending && modeState.isSample), Boolean(modeState.isSample));
    syncFirstMoveCard(Boolean(isSignedIn && !setupPending && !modeState.isSample), onboarding, server.user, server.doc);
  }

  let homeModeSubscribed = false;
  let lastHandledHomeModeKey = '';
  function ensureHomeModeSubscription() {
    if (homeModeSubscribed || !window.museModes?.subscribe) return;
    homeModeSubscribed = true;
    window.museModes.subscribe(async (modeState) => {
      if (window.location.pathname === '/welcome') return;
      if (!document.getElementById('journey')) return;
      const modeKey = `${modeState?.state || ''}:${modeState?.ownerId || ''}:${modeState?.isSample ? '1' : '0'}`;
      if (modeKey && modeKey === lastHandledHomeModeKey) return;
      lastHandledHomeModeKey = modeKey;
      await applyHomeModeState(modeState);
    });
  }

  async function initHomePageOnboardingSync() {
    if (window.location.pathname === '/welcome') return;
    if (!document.getElementById('journey')) return;
    if (window.museModes?.resolve) {
      const resolved = await window.museModes.resolve();
      const modeKey = `${resolved?.state || ''}:${resolved?.ownerId || ''}:${resolved?.isSample ? '1' : '0'}`;
      lastHandledHomeModeKey = modeKey;
      await applyHomeModeState(resolved);
      ensureHomeModeSubscription();
      return;
    }
    await applyHomeModeState();
  }

  // Listen for sign-in / sign-out events from account.js so signed-out views reset immediately
  window.addEventListener('muse:account-change', async (ev) => {
    if (window.location.pathname === '/welcome') return;
    if (window.museModes?.subscribe) {
      ensureHomeModeSubscription();
      return;
    }
    const seq = ++homeSyncEpoch;
    const user = ev?.detail?.user || null;
    if (!user) {
      resetSignedOutHomeWorkspace();
      return;
    }
    const query = new URLSearchParams(window.location.search || '');
    if (query.get('workspace') === 'sample') return;
    const server = await loadServerWorkspaceDoc();
    if (seq !== homeSyncEpoch) return;
    const snap = window.museAccount?.getSnapshot?.();
    if (snap && snap.user?.id !== user.id) return;
    // Authoritative check on server document: no cross-account local leak
    const onb = server.doc?.onboarding || null;
    if (!onb || !onb.completed_at) {
      window.location.assign('/welcome');
    } else {
      injectLoginDialogSwitcher(onb, user);
      renderSignedInHomeWorkspace(onb, user);
    }
  });

  window.addEventListener('pageshow', (event) => {
    if (window.location.pathname === '/welcome') return;
    if (!document.getElementById('journey')) return;
    if (event.persisted) {
      if (lastRenderedUserId || document.getElementById('ownWorkspaceOptionBtn')) {
        resetSignedOutHomeWorkspace({ preserveMode: true });
      }
      window.museAccount?.refresh?.();
      initHomePageOnboardingSync();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initWelcomePage();
      initHomePageOnboardingSync();
    });
  } else {
    initWelcomePage();
    initHomePageOnboardingSync();
  }
})();
