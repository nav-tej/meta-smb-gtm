'use strict';
// Email digest sign-up on /digest. Shown only when the server can send email; double opt-in.
// Revision 4: Account required to subscribe; frequency and topic controls.
(() => {
  const $ = (id) => document.getElementById(id);
  const NOTICES = {
    confirmed: ['Your weekly digest is confirmed. The first email arrives next Monday.', ''],
    unsubscribed: ['You are unsubscribed. No more digest emails will be sent.', ''],
    'link-invalid': ['That email link is no longer valid. Sign up again below if you still want the digest.', 'warn'],
  };
  const params = new URLSearchParams(location.search);
  const result = params.get('email');
  const notice = NOTICES[result];
  if (notice) {
    const node = $('digestEmailNotice');
    if (node) {
      node.textContent = notice[0];
      node.className = `dg-status dg-email-notice ${notice[1]}`.trim();
      node.hidden = false;
      params.delete('email');
      try { history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '')); } catch {}
      try { window.museTrack?.('digest_email_link', { result }); } catch {}
    }
  }

  const section = $('digestSignup');
  const form = $('digestSignupForm');
  const status = $('digestSignupStatus');
  const gate = $('digestAccountGate');
  const info = $('digestAccountInfo');
  const signInBtn = $('digestSignInBtn');
  if (!section || !form) return;

  let currentUser = null;

  function updateAccountState(snap) {
    currentUser = snap?.user || null;
    if (!currentUser) {
      if (gate) gate.hidden = false;
      if (info) info.hidden = true;
      form.hidden = true;
    } else {
      if (gate) gate.hidden = true;
      if (info) info.hidden = false;
      form.hidden = false;

      const userEmailEl = $('digestUserEmail');
      const hiddenEmail = $('digestHiddenEmail');
      if (userEmailEl) userEmailEl.textContent = currentUser.email;
      if (hiddenEmail) hiddenEmail.value = currentUser.email;

      const remaining = Number.isFinite(snap?.usage?.remaining) ? snap.usage.remaining : 3;
      const runsNotice = $('digestRunsNotice');
      if (runsNotice) {
        if (remaining <= 0) {
          runsNotice.innerHTML = '0 runs remaining this month. <a href="/#pricing">Get more runs</a>. (Free weekly digest email)';
        } else if (remaining === 1) {
          runsNotice.innerHTML = '1 run remaining this month. <a href="/#pricing">Get more runs</a>. (Free weekly digest email)';
        } else {
          runsNotice.textContent = `${remaining} runs remaining this month. (Free weekly digest email)`;
        }
      }

      // Prefill competitor shop inputs from workspace if available
      try {
        const competitors = snap?.workspace?.competitors || snap?.workspace?.onboarding?.competitors || [];
        const shopInputs = form.querySelectorAll('input[name="shop"]');
        if (Array.isArray(competitors) && competitors.length > 0) {
          shopInputs.forEach((inp, idx) => {
            if (!inp.value.trim() && competitors[idx]) {
              const compUrl = typeof competitors[idx] === 'string' ? competitors[idx] : competitors[idx].url || '';
              if (compUrl) inp.value = compUrl;
            }
          });
        }
      } catch (_) {}
    }
  }

  if (signInBtn) {
    signInBtn.addEventListener('click', () => {
      try {
        window.museAccount?.open?.('signup', 'Sign in or create a free account to subscribe to your weekly competitor digest.');
      } catch (_) {}
    });
  }

  window.addEventListener('account-change', (e) => { updateAccountState(e.detail); syncDraftAccountState(e.detail); });
  window.addEventListener('muse:account-change', (e) => { updateAccountState(e.detail); syncDraftAccountState(e.detail); });

  fetch('/api/v1/digest/subscription', { credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : { available: false }))
    .then(async (data) => {
      const subNote = $('draftExistingSubNote');
      if (subNote) {
        subNote.textContent = data?.available === true
          ? 'Live email delivery is open below (separate from your draft settings). Active subscriptions are managed via confirmation and unsubscribe links.'
          : 'Live email delivery is not configured right now — you can still save draft schedule preferences and preview your personal digest below.';
      }
      try {
        const snap = await window.museAccount?.ready?.();
        updateAccountState(snap);
        syncDraftAccountState(snap);
      } catch {
        updateAccountState(null);
        syncDraftAccountState(null);
      }
      if (data?.available !== true && !location.search.includes('preview_digest')) return;
      section.hidden = false;
      try { window.museTrack?.('digest_prompt_shown', { surface: 'digest' }); } catch {}
    })
    .catch(() => {});

  const say = (text, error = false) => {
    if (!status) return;
    status.textContent = text;
    status.className = `dg-sub-status${error ? ' error' : ''}`;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!currentUser) {
      say('A free Muse account is required to subscribe.', true);
      try { window.museAccount?.open?.('signup'); } catch (_) {}
      return;
    }

    const email = (currentUser.email || '').trim();
    const competitors = [...form.querySelectorAll('input[name="shop"]')]
      .map((i) => i.value.trim())
      .filter(Boolean);

    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      say('Please ensure your account has a valid email address.', true);
      return;
    }
    if (!competitors.length) {
      say('Add at least one competitor shop link.', true);
      const firstShop = form.querySelector('input[name="shop"]');
      if (firstShop) firstShop.focus();
      return;
    }

    const frequency = form.frequency?.value || 'weekly';
    const topics = [...form.querySelectorAll('input[name="topic"]:checked')].map((i) => i.value);

    try {
      localStorage.setItem('muse.digest_preferences', JSON.stringify({ frequency, topics }));
    } catch (_) {}

    const button = form.querySelector('button[type="submit"]') || form.querySelector('button');
    if (button) button.disabled = true;
    say('Sending your confirmation email…');

    try {
      const response = await fetch('/api/v1/digest/subscribe', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, competitors }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'We could not sign you up right now. Try again later.');
      }
      say(data.message || 'Check your inbox to confirm.');
      try {
        window.museTrack?.('digest_subscribed', {
          surface: 'digest',
          frequency: frequency,
          topics: topics.join(','),
          shops: competitors.length,
        });
      } catch (_) {}
    } catch (error) {
      say(error.message, true);
    } finally {
      if (button) button.disabled = false;
    }
  });

  // ---------- Batch 2A: Personal Digest Draft Preferences & Preview ----------
  const draftSection = $('digestDraftSection');
  const draftGate = $('draftAccountGate');
  const draftForm = $('digestDraftForm');
  const draftSignInBtn = $('digestDraftSignInBtn');
  const draftCadenceEl = $('draftCadence');
  const draftAnchorWrap = $('draftAnchorDayWrap');
  const draftAnchorEl = $('draftAnchorDay');
  const draftTzEl = $('draftTimezone');
  const draftNextEl = $('draftNextSendDisplay');
  const draftSaveBtn = $('draftSaveBtn');
  const draftPreviewBtn = $('draftPreviewBtn');
  const draftStatusEl = $('draftSaveStatus');
  const previewBox = $('digestEmailPreviewBox');
  const previewSubject = $('previewSubject');
  const previewWindow = $('previewWindow');
  const previewFrame = $('digestPreviewFrame');
  const previewTextEl = $('digestPreviewText');
  const tabHtmlBtn = $('previewTabHtml');
  const tabTextBtn = $('previewTabText');

  let draftOwnerId = null;
  let draftVersion = null;
  let draftLoadedForOwner = null;
  let accountGen = 0;
  let previewReqSeq = 0;
  let loadController = null;
  let previewController = null;

  if (draftTzEl) {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected && ![...draftTzEl.options].some((o) => o.value === detected)) {
        const opt = document.createElement('option');
        opt.value = detected;
        opt.textContent = `${detected} (Device)`;
        draftTzEl.appendChild(opt);
      }
    } catch (_) {}
  }

  function sayDraft(text, error = false) {
    if (!draftStatusEl) return;
    draftStatusEl.textContent = text;
    draftStatusEl.className = `dg-sub-status${error ? ' error' : ''}`;
  }

  function toggleAnchorVisibility() {
    if (!draftAnchorWrap || !draftCadenceEl) return;
    draftAnchorWrap.hidden = draftCadenceEl.value !== 'monthly';
  }

  function readDraftPayload() {
    const shops = [...(draftForm?.querySelectorAll('input[name="draftShop"]') || [])]
      .map((i) => i.value.trim())
      .filter(Boolean)
      .slice(0, 3);
    const topics = [...(draftForm?.querySelectorAll('input[name="draftTopic"]:checked') || [])]
      .map((i) => i.value);
    const anchorRaw = draftAnchorEl?.value?.trim();
    const anchorDay = anchorRaw ? Number(anchorRaw) : null;
    return {
      cadence: draftCadenceEl?.value || 'weekly',
      topics,
      timezone: draftTzEl?.value || 'America/Los_Angeles',
      anchor_day: Number.isInteger(anchorDay) && anchorDay >= 1 && anchorDay <= 31 ? anchorDay : null,
      competitors: shops,
    };
  }

  function applyDraftToForm(data) {
    const prefs = data?.draft_preferences || {};
    if (draftCadenceEl && prefs.cadence) draftCadenceEl.value = prefs.cadence;
    toggleAnchorVisibility();
    if (draftAnchorEl) draftAnchorEl.value = prefs.anchor_day ? String(prefs.anchor_day) : '';
    if (draftTzEl && prefs.timezone) {
      if (![...draftTzEl.options].some((o) => o.value === prefs.timezone)) {
        const opt = document.createElement('option');
        opt.value = prefs.timezone;
        opt.textContent = prefs.timezone;
        draftTzEl.appendChild(opt);
      }
      draftTzEl.value = prefs.timezone;
    }
    const activeTopics = new Set(Array.isArray(prefs.topics) ? prefs.topics : []);
    draftForm?.querySelectorAll('input[name="draftTopic"]').forEach((box) => {
      box.checked = activeTopics.has(box.value);
    });
    const shopInputs = [...(draftForm?.querySelectorAll('input[name="draftShop"]') || [])];
    const savedShops = Array.isArray(prefs.competitors) ? prefs.competitors : [];
    shopInputs.forEach((inp, idx) => { inp.value = savedShops[idx] || ''; });
    if (draftNextEl && data?.next_send_display) draftNextEl.textContent = data.next_send_display;
  }

  function renderPreviewOutput(data) {
    if (!previewBox) return;
    previewBox.hidden = false;
    if (previewSubject) previewSubject.textContent = data.subject || 'Personal digest preview';
    if (previewWindow) previewWindow.textContent = data.next_send_display || '';
    if (draftNextEl && data.next_send_display) draftNextEl.textContent = data.next_send_display;
    if (previewFrame) previewFrame.srcdoc = data.html || '';
    if (previewTextEl) previewTextEl.textContent = data.text || '';
  }

  function isStaleAccount(genAtStart, ownerAtStart) {
    return genAtStart !== accountGen || ownerAtStart !== draftOwnerId;
  }

  function setDraftControlsDisabled(disabled) {
    const flag = Boolean(disabled);
    draftForm?.querySelectorAll('input, select, button').forEach((el) => {
      el.disabled = flag;
    });
    if (draftSaveBtn) draftSaveBtn.disabled = flag;
    if (draftPreviewBtn) draftPreviewBtn.disabled = flag;
  }

  function clearDraftUI() {
    draftVersion = null;
    draftLoadedForOwner = null;
    if (previewBox) previewBox.hidden = true;
    if (previewSubject) previewSubject.textContent = '';
    if (previewWindow) previewWindow.textContent = '';
    if (previewFrame) previewFrame.srcdoc = '';
    if (previewTextEl) previewTextEl.textContent = '';
    if (draftNextEl) draftNextEl.textContent = '';
    if (draftCadenceEl) draftCadenceEl.value = 'weekly';
    toggleAnchorVisibility();
    if (draftAnchorEl) draftAnchorEl.value = '';
    if (draftTzEl && draftTzEl.options.length > 0) {
      draftTzEl.value = draftTzEl.options[0].value;
    }
    draftForm?.querySelectorAll('input[name="draftTopic"]').forEach((box) => {
      box.checked = false;
    });
    draftForm?.querySelectorAll('input[name="draftShop"]').forEach((inp) => {
      inp.value = '';
    });
  }

  async function refreshPreview(genAtStart = accountGen) {
    if (!draftOwnerId || draftLoadedForOwner !== draftOwnerId || genAtStart !== accountGen) return;
    const ownerAtStart = draftOwnerId;
    const myPreviewSeq = ++previewReqSeq;
    if (previewController) previewController.abort();
    const controller = new AbortController();
    previewController = controller;
    const payload = { ...readDraftPayload(), expected_owner: ownerAtStart };
    if (draftPreviewBtn) draftPreviewBtn.disabled = true;
    try {
      const r = await fetch('/api/v1/digest/preview', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Muse-Owner': ownerAtStart },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (isStaleAccount(genAtStart, ownerAtStart) || draftLoadedForOwner !== ownerAtStart || myPreviewSeq !== previewReqSeq) return;
      const data = await r.json().catch(() => ({}));
      if (isStaleAccount(genAtStart, ownerAtStart) || draftLoadedForOwner !== ownerAtStart || myPreviewSeq !== previewReqSeq) return;
      if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load preview.');
      renderPreviewOutput(data);
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (isStaleAccount(genAtStart, ownerAtStart) || myPreviewSeq !== previewReqSeq) return;
      sayDraft(err.message, true);
    } finally {
      if (previewController === controller) previewController = null;
      if (
        !isStaleAccount(genAtStart, ownerAtStart)
        && draftLoadedForOwner === ownerAtStart
        && myPreviewSeq === previewReqSeq
        && draftPreviewBtn
      ) {
        draftPreviewBtn.disabled = false;
      }
    }
  }

  async function loadDraftAndPreview(ownerId, genAtStart) {
    if (loadController) loadController.abort();
    const controller = new AbortController();
    loadController = controller;
    sayDraft('Loading your draft digest settings…');
    try {
      const r = await fetch('/api/v1/digest/preferences', {
        credentials: 'same-origin',
        headers: { 'X-Muse-Owner': ownerId },
        signal: controller.signal,
      });
      if (isStaleAccount(genAtStart, ownerId)) return;
      const data = await r.json().catch(() => ({}));
      if (isStaleAccount(genAtStart, ownerId)) return;
      if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load draft preferences.');
      draftVersion = Number.isInteger(data.version) ? data.version : 0;
      draftLoadedForOwner = ownerId;
      applyDraftToForm(data);
      setDraftControlsDisabled(false);
      sayDraft('');
      await refreshPreview(genAtStart);
      if (isStaleAccount(genAtStart, ownerId)) return;
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (isStaleAccount(genAtStart, ownerId)) return;
      clearDraftUI();
      setDraftControlsDisabled(true);
      sayDraft(err.message, true);
    } finally {
      if (loadController === controller) loadController = null;
    }
  }

  function syncDraftAccountState(snap) {
    if (!draftSection) return;
    const user = snap?.user || null;
    const nextOwnerId = user?.id || null;
    if (!nextOwnerId) {
      if (draftOwnerId !== null || draftLoadedForOwner !== null) {
        accountGen++;
        previewReqSeq++;
      }
      draftOwnerId = null;
      if (loadController) { loadController.abort(); loadController = null; }
      if (previewController) { previewController.abort(); previewController = null; }
      clearDraftUI();
      setDraftControlsDisabled(true);
      sayDraft('');
      if (draftGate) draftGate.hidden = false;
      if (draftForm) draftForm.hidden = true;
      return;
    }
    if (nextOwnerId !== draftOwnerId) {
      accountGen++;
      previewReqSeq++;
      draftOwnerId = nextOwnerId;
      if (loadController) { loadController.abort(); loadController = null; }
      if (previewController) { previewController.abort(); previewController = null; }
      clearDraftUI();
      setDraftControlsDisabled(true);
      if (draftGate) draftGate.hidden = true;
      if (draftForm) draftForm.hidden = false;
      loadDraftAndPreview(nextOwnerId, accountGen);
      return;
    }
    if (draftGate) draftGate.hidden = true;
    if (draftForm) draftForm.hidden = false;
    if (draftLoadedForOwner !== nextOwnerId && !loadController) {
      setDraftControlsDisabled(true);
      loadDraftAndPreview(nextOwnerId, accountGen);
    }
  }

  if (draftSignInBtn) {
    draftSignInBtn.addEventListener('click', () => {
      try {
        window.museAccount?.open?.('signin', 'Sign in to save draft digest settings and preview your personal digest.');
      } catch (_) {}
    });
  }

  if (draftCadenceEl) {
    draftCadenceEl.addEventListener('change', () => {
      toggleAnchorVisibility();
      refreshPreview(accountGen);
    });
  }
  if (draftTzEl) draftTzEl.addEventListener('change', () => refreshPreview(accountGen));
  if (draftPreviewBtn) draftPreviewBtn.addEventListener('click', () => refreshPreview(accountGen));

  if (tabHtmlBtn && tabTextBtn && previewFrame && previewTextEl) {
    tabHtmlBtn.addEventListener('click', () => {
      tabHtmlBtn.classList.add('is-active');
      tabHtmlBtn.setAttribute('aria-selected', 'true');
      tabTextBtn.classList.remove('is-active');
      tabTextBtn.setAttribute('aria-selected', 'false');
      previewFrame.hidden = false;
      previewTextEl.hidden = true;
    });
    tabTextBtn.addEventListener('click', () => {
      tabTextBtn.classList.add('is-active');
      tabTextBtn.setAttribute('aria-selected', 'true');
      tabHtmlBtn.classList.remove('is-active');
      tabHtmlBtn.setAttribute('aria-selected', 'false');
      previewFrame.hidden = true;
      previewTextEl.hidden = false;
    });
  }

  if (draftForm) {
    draftForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!draftOwnerId || draftLoadedForOwner !== draftOwnerId || draftVersion === null) return;
      const genAtStart = accountGen;
      const ownerAtStart = draftOwnerId;
      const payload = {
        ...readDraftPayload(),
        expected_version: draftVersion,
        expected_owner: ownerAtStart,
      };
      if (draftSaveBtn) draftSaveBtn.disabled = true;
      sayDraft('Saving draft preferences to your workspace…');
      try {
        const r = await fetch('/api/v1/digest/preferences', {
          method: 'PUT',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Muse-Owner': ownerAtStart },
          body: JSON.stringify(payload),
        });
        if (isStaleAccount(genAtStart, ownerAtStart)) return;
        const data = await r.json().catch(() => ({}));
        if (isStaleAccount(genAtStart, ownerAtStart)) return;
        if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save draft preferences.');
        draftVersion = Number.isInteger(data.version) ? data.version : draftVersion;
        applyDraftToForm(data);
        sayDraft('Draft preferences saved to your workspace (no email subscription changed).');
        await refreshPreview(genAtStart);
        if (isStaleAccount(genAtStart, ownerAtStart)) return;
      } catch (err) {
        if (isStaleAccount(genAtStart, ownerAtStart)) return;
        sayDraft(err.message, true);
      } finally {
        if (!isStaleAccount(genAtStart, ownerAtStart) && draftLoadedForOwner === ownerAtStart && draftSaveBtn) {
          draftSaveBtn.disabled = false;
        }
      }
    });
  }
})();
