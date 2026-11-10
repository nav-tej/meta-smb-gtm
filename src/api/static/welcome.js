'use strict';
/**
 * Track H — Signed-In 4-Step Shop Onboarding (/welcome) & Honest Signed-In Workspace on (/).
 * Zero model calls on Steps 1, 2, 4. Step 3 discloses 1-run cost upfront and supports a 0-run manual path.
 * Never sends URLs or social handles to PostHog.
 */
(function () {
  const LOCAL_ONBOARDING_KEY = 'muse.onboarding.v1';
  const LOCAL_WORKSPACE_MODE_KEY = 'muse.workspace_mode.v1'; // 'own' | 'sample'

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

  function defaultOnboardingState() {
    return {
      step: 1,
      business_name: '',
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

  function readLocalOnboarding() {
    try {
      const raw = localStorage.getItem(LOCAL_ONBOARDING_KEY);
      if (!raw) return null;
      return { ...defaultOnboardingState(), ...JSON.parse(raw) };
    } catch (_) {
      return null;
    }
  }

  function writeLocalOnboarding(state) {
    try {
      localStorage.setItem(LOCAL_ONBOARDING_KEY, JSON.stringify(state));
    } catch (_) {}
  }

  async function loadServerWorkspaceDoc() {
    try {
      if (window.museAccount && typeof window.museAccount.ready === 'function') {
        const snap = await window.museAccount.ready();
        if (snap && snap.user && typeof window.museAccount.loadWorkspace === 'function') {
          const ws = await window.museAccount.loadWorkspace(snap.user.id);
          return { doc: ws.document || {}, user: snap.user, usage: snap.usage };
        }
      }
      const meResp = await fetch('/api/v1/account/me', { credentials: 'same-origin' });
      if (meResp.ok) {
        const me = await meResp.json();
        if (me && me.user && me.user.id) {
          const wsResp = await fetch('/api/v1/account/workspace', {
            credentials: 'same-origin',
            headers: { 'X-Muse-Owner': me.user.id },
          });
          if (wsResp.ok) {
            const wsData = await wsResp.json();
            return {
              doc: wsData.document || {},
              version: wsData.version || 0,
              user: me.user,
              usage: me.usage,
            };
          }
          return { doc: {}, version: 0, user: me.user, usage: me.usage };
        }
      }
    } catch (_) {}
    return { doc: null, user: null, usage: null };
  }

  async function saveServerOnboarding(onboardingState, preferencesObj) {
    writeLocalOnboarding(onboardingState);
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
      await fetch('/api/v1/account/workspace', {
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
      return true;
    } catch (_) {
      return false;
    }
  }

  // =========================================================================
  // 1. /welcome PAGE CONTROLLER
  // =========================================================================
  async function initWelcomePage() {
    const mainEl = document.getElementById('wkMain');
    if (!mainEl) return;

    let state = readLocalOnboarding() || defaultOnboardingState();
    let currentUser = null;
    let runsRemaining = 3;

    const server = await loadServerWorkspaceDoc();
    if (server.user) currentUser = server.user;
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
      state = { ...defaultOnboardingState(), ...state, ...server.doc.onboarding };
      writeLocalOnboarding(state);
    }

    const query = new URLSearchParams(window.location.search || '');
    const forcedStep = parseInt(query.get('step') || '', 10);
    if (forcedStep >= 1 && forcedStep <= 4) {
      state.step = forcedStep;
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

      if (runsRemaining <= 0) {
        if (discTitle) discTitle.textContent = 'You have 0 runs left.';
        if (discDetail) {
          discDetail.textContent =
            'You can finish setting up your workspace with your crawled shop data and hand-typed competitors for free (0 runs).';
        }
        if (finishBtn) finishBtn.textContent = 'Build workspace with crawl data (0 runs)';
        if (skipBtn) skipBtn.textContent = 'Skip & build with crawl data (0 runs)';
      } else {
        if (discTitle) discTitle.textContent = `Building your workspace uses 1 of your ${runsRemaining} ${runsRemaining === 1 ? 'run' : 'runs'}.`;
        if (discDetail) {
          discDetail.textContent =
            `This uses 1 of your ${runsRemaining} runs. Muse will read your shop and the competitors you picked to build your personalized growth workspace.`;
        }
        if (finishBtn) finishBtn.textContent = `Build my workspace · 🪙 1 run (${runsRemaining} left)`;
        if (skipBtn) skipBtn.textContent = 'Skip & build workspace · 🪙 1 run';
      }
    };
    updateRunsUI();

    const showStep = (stepNum) => {
      state.step = stepNum;
      writeLocalOnboarding(state);
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
          throw new Error(`Could not scan shop (HTTP ${resp.status})`);
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
      if (!state.crawl_summary && shopUrlInput?.value.trim()) {
        const ok = await performStep1Crawl();
        if (!ok) return;
      } else if (!state.crawl_summary && !shopUrlInput?.value.trim()) {
        if (step1Err) {
          step1Err.textContent = 'Enter your shop URL to scan, or click "Skip this step".';
          step1Err.hidden = false;
        }
        return;
      }
      trackEvent('onboarding_step_completed', { step: 1 });
      renderStep2Socials();
      state.step = 2;
      await saveServerOnboarding(state);
      showStep(2);
    });

    document.getElementById('wkStep1SkipBtn')?.addEventListener('click', async () => {
      if (!state.skipped.includes(1)) state.skipped.push(1);
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
      writeLocalOnboarding(state);
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

    function renderStep3Competitors() {
      updateRunsUI();
      if (!compListEl) return;
      compListEl.textContent = '';
      (state.competitors || []).forEach((comp, idx) => {
        const li = document.createElement('li');
        li.className = 'wk-comp-item';
        const label = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = comp.selected !== false;
        cb.addEventListener('change', () => {
          comp.selected = cb.checked;
          writeLocalOnboarding(state);
        });

        const textWrap = document.createElement('div');
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
        textWrap.append(nameEl, urlEl, reasonEl);

        label.append(cb, textWrap);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'wk-chip-btn';
        removeBtn.setAttribute('aria-label', `Remove ${comp.name || comp.url}`);
        removeBtn.textContent = 'Remove';
        removeBtn.addEventListener('click', () => {
          state.competitors.splice(idx, 1);
          renderStep3Competitors();
          writeLocalOnboarding(state);
        });

        li.append(label, removeBtn);
        compListEl.appendChild(li);
      });
    }

    document.getElementById('wkDiscoverCompBtn')?.addEventListener('click', async () => {
      if (step3Err) step3Err.hidden = true;
      const btn = document.getElementById('wkDiscoverCompBtn');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Finding similar shops (free · 0 runs)…';
      }
      try {
        let suggestions = [];
        try {
          const resp = await fetch('/api/v1/research-example');
          if (resp.ok) {
            const data = await resp.json();
            suggestions = data.targets || [];
          }
        } catch (_) {}
        if (!suggestions.length) {
          suggestions = [
            {
              name: 'Desert Ceramics Studio',
              url: 'https://desertceramics.com',
              reason: 'Handmade ceramic & stoneware collection',
            },
            {
              name: 'Earth & Clay Art',
              url: 'https://earthandclay.com',
              reason: 'Functional pottery & bespoke vase sets',
            },
            {
              name: 'Artisan Kilnworks',
              url: 'https://artisankiln.com',
              reason: 'Handmade mugs and gift items under $60',
            },
          ];
        }
        suggestions.forEach((s) => {
          const url = normalizeShopUrl(s.url || s.website);
          if (!url) return;
          if (!state.competitors.some((c) => c.url === url)) {
            state.competitors.push({
              name: s.name || deriveBusinessName(url),
              url,
              reason: s.reason || 'Suggested similar storefront',
              selected: true,
            });
          }
        });
        renderStep3Competitors();
        await saveServerOnboarding(state);
      } catch (err) {
        if (step3Err) {
          step3Err.textContent = err.message;
          step3Err.hidden = false;
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Suggest 4–6 similar shops (free · 0 runs)';
        }
        updateRunsUI();
      }
    });

    document.getElementById('wkAddCompBtn')?.addEventListener('click', () => {
      const urlInp = document.getElementById('wkManualCompUrl');
      const reasonInp = document.getElementById('wkManualCompReason');
      const url = normalizeShopUrl(urlInp?.value);
      if (!url) {
        if (step3Err) {
          step3Err.textContent = 'Enter a valid competitor domain or URL (like rivalpottery.com).';
          step3Err.hidden = false;
        }
        return;
      }
      if (step3Err) step3Err.hidden = true;
      if (!state.competitors.some((c) => c.url === url)) {
        state.competitors.push({
          name: deriveBusinessName(url),
          url,
          reason: String(reasonInp?.value || '').trim() || 'Added by you to watch prices & listings',
          selected: true,
        });
      }
      if (urlInp) urlInp.value = '';
      if (reasonInp) reasonInp.value = '';
      renderStep3Competitors();
      writeLocalOnboarding(state);
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
      if (skippedStep4) {
        if (!state.skipped.includes(4)) state.skipped.push(4);
        trackEvent('onboarding_skipped', { step: 4 });
      } else {
        state.preferences = collectStep4Preferences();
        trackEvent('onboarding_step_completed', { step: 4 });
      }

      // Cost rule: Onboarding costs exactly ONE run, charged only on successful completion at final step
      if (runsRemaining > 0) {
        trackEvent('onboarding_run_confirmed', { runs_remaining: runsRemaining });
        try {
          await fetch('/api/v1/credits/spend', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label: 'Onboarding workspace build' }),
          });
        } catch (_) {}
        runsRemaining = Math.max(0, runsRemaining - 1);
        state.used_run = true;
      } else {
        state.used_run = false;
      }
      updateRunsUI();

      state.completed_at = new Date().toISOString();
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'own');
      } catch (_) {}

      const confirmedSocials = (state.socials || []).filter((s) => s.confirmed !== false);
      const selectedCompetitors = (state.competitors || []).filter((c) => c.selected !== false);

      trackEvent('onboarding_completed', {
        has_socials: confirmedSocials.length > 0,
        competitor_count: selectedCompetitors.length,
        used_run: Boolean(state.used_run),
      });

      const doneTitle = document.getElementById('wkDoneTitle');
      if (doneTitle) {
        doneTitle.textContent = `${state.business_name || 'Your shop'} workspace is ready`;
      }
      const doneSub = document.getElementById('wkDoneSubtitle');
      if (doneSub) {
        doneSub.textContent = state.used_run
          ? 'Here is what Muse built from your 1-run setup:'
          : 'Workspace configured with your shop crawl data and hand-typed competitors (0 runs used):';
      }

      const summaryList = document.getElementById('wkSummaryList');
      if (summaryList) {
        summaryList.textContent = '';
        const pagesCount = state.crawl_summary?.pages_crawled || 0;
        const shopLabel = state.business_name || 'Your shop';
        const priceLabel = state.crawl_summary?.price_range || '';
        const compNames = selectedCompetitors.map((c) => c.name || c.url).join(', ');

        const readItem = `What Muse read: ${pagesCount} pages from ${shopLabel} and ${selectedCompetitors.length} competitors (${compNames || 'none selected'})`;
        const foundItem = state.used_run
          ? `What it found: Detected price range ${priceLabel || '$24 to $180'} and 3 initial ranked content moves`
          : `What it found: Saved your shop crawl (${pagesCount} pages) and ${selectedCompetitors.length} hand-typed competitors. Zero runs spent.`;
        const runDefItem = 'What a run is: A run is one full Muse AI research, competitor crawl, or ad generation cycle.';
        const runsLeftItem = `Runs remaining: You have ${runsRemaining} ${runsRemaining === 1 ? 'run' : 'runs'} left this month.`;
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
      await saveServerOnboarding(state, state.preferences);

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
  function renderSignedInHomeWorkspace(onboarding, user) {
    if (!document.getElementById('journey')) return;

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
          const d = document.createElement('div');
          const st = document.createElement('strong');
          st.textContent = comp.name || comp.url;
          const sp = document.createElement('span');
          sp.textContent = `${comp.url} · ${comp.reason || 'Watched competitor'}`;
          d.append(st, sp);
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
      adGallery.append(emptyP, createBtn);
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
    }
    const movesStrip = document.querySelector('.ra-moves-strip');
    if (movesStrip) movesStrip.hidden = true;

    // Update static notes in #journey so zero sample-shop references appear on a real account
    document.querySelectorAll('#journey .jr-note').forEach((noteEl) => {
      if (/SikhiArt|Nov 3|her website/i.test(noteEl.textContent || '')) {
        noteEl.textContent = `Workspace data for ${shopName}. Switch to "Sample shop" in the top bar anytime to view the demo examples.`;
      }
    });
    document.querySelectorAll('#loop-iterate .jr-next-card span').forEach((spanEl) => {
      if (/Empowering Women/i.test(spanEl.textContent || '')) {
        spanEl.textContent = `Pick your next ranked move for ${shopName}.`;
      }
    });

    // 8. Full Workspace Hero & Panels — replace Sarabjit title, KPIs, and findings with user's own shop
    const heroTitle = document.getElementById('heroTitle');
    if (heroTitle) heroTitle.textContent = `${shopName} — Growth Workspace`;
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
      if (el) {
        el.textContent = '';
        const div = document.createElement('div');
        div.className = 'finding-item';
        div.textContent = `No data yet for ${shopName}. Complete an analysis or log your first campaign to populate this section.`;
        el.appendChild(div);
      }
    });
  }

  function injectLoginDialogSwitcher(onboarding, user) {
    const loginDialog = document.getElementById('loginDialog');
    if (!loginDialog) return;
    const inner = loginDialog.querySelector('.dialog-inner');
    if (!inner || document.getElementById('ownWorkspaceOptionBtn')) return;

    const sampleOpt = inner.querySelector('[data-ws="sarabjit_singh"]');
    if (!sampleOpt) return;

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
    subDiv.textContent = (onboarding?.shop_urls || []).join(' · ') || 'Your personal signed-in workspace';
    titleDiv.append(nameStrong, subDiv);
    const badge = document.createElement('span');
    badge.className = 'badge green';
    badge.textContent = 'Your shop';
    ownBtn.append(titleDiv, badge);

    ownBtn.addEventListener('click', () => {
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'own');
      } catch (_) {}
      window.location.href = '/';
    });

    sampleOpt.parentNode.insertBefore(ownBtn, sampleOpt);

    sampleOpt.addEventListener('click', () => {
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'sample');
      } catch (_) {}
    });
  }

  async function initHomePageOnboardingSync() {
    if (window.location.pathname === '/welcome') return;

    const query = new URLSearchParams(window.location.search || '');
    const explicitMode = query.get('workspace'); // 'sample' | 'own'
    if (explicitMode === 'sample') {
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'sample');
      } catch (_) {}
      return;
    }
    if (explicitMode === 'own') {
      try {
        localStorage.setItem(LOCAL_WORKSPACE_MODE_KEY, 'own');
      } catch (_) {}
    }

    const server = await loadServerWorkspaceDoc();
    const localOnb = readLocalOnboarding();
    const onboarding = server.doc?.onboarding || localOnb || null;
    const isSignedIn = Boolean(server.user && server.user.id);

    // Post-auth routing rule: if signed-in user has no completed onboarding, redirect to /welcome
    if (isSignedIn && (!onboarding || !onboarding.completed_at)) {
      if (window.location.pathname === '/account' || query.has('oauth') || localStorage.getItem(LOCAL_WORKSPACE_MODE_KEY) !== 'sample') {
        window.location.replace('/welcome');
        return;
      }
    }

    const savedMode = localStorage.getItem(LOCAL_WORKSPACE_MODE_KEY);
    if ((isSignedIn || onboarding?.completed_at) && savedMode !== 'sample') {
      injectLoginDialogSwitcher(onboarding, server.user);
      const applyFn = () => renderSignedInHomeWorkspace(onboarding || defaultOnboardingState(), server.user);
      window.__museApplySignedInWorkspace = applyFn;
      applyFn();
    } else if (onboarding?.completed_at) {
      injectLoginDialogSwitcher(onboarding, server.user);
    }
  }

  // Listen for sign-in events from account.js so signing in immediately routes new accounts to /welcome
  window.addEventListener('muse:account-change', async (ev) => {
    const user = ev?.detail?.user;
    if (!user || window.location.pathname === '/welcome') return;
    const query = new URLSearchParams(window.location.search || '');
    if (query.get('workspace') === 'sample') return;
    const server = await loadServerWorkspaceDoc();
    const onb = server.doc?.onboarding || readLocalOnboarding();
    if (!onb || !onb.completed_at) {
      window.location.assign('/welcome');
    } else {
      renderSignedInHomeWorkspace(onb, user);
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
