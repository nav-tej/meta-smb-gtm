/* Seller Memory & Scan-to-Recommendation UI (PRD Section 12, Batch 1) */
(function () {
  'use strict';

  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.__museSellerMemoryInit) return;
  window.__museSellerMemoryInit = true;

  const ROLE_LABELS = {
    similar_audience: 'Similar audience',
    price_reference: 'Price reference',
    inspiration: 'Creative inspiration',
  };

  const KIND_LABELS = {
    observation: 'Observed fact',
    interpretation: 'Interpretation · unconfirmed',
    preference: 'Saved preference',
    goal: 'Seller goal',
  };

  const SOURCE_LABELS = {
    shop_scan: 'Shop scan',
    user_input: 'Typed by you',
    voice_transcript: 'Voice note',
    voice_demo_fixture: 'Sample voice note (demo)',
    onboarding_questions: 'Setup answers',
    feedback_suggestion: 'From your feedback',
    sample_snapshot: 'Sample shop',
  };

  const BANNED_SAMPLE_TERMS = ['sarabjit', 'sikhiart', 'sikh heroines', 'art of sarabjit'];

  const state = {
    ownerId: null,
    authenticated: false,
    version: 0,
    businessName: '',
    businessType: null,
    preferences: {},
    voiceProfile: {},
    memoryEntries: [],
    competitorEntries: [],
    suggestedUpdates: [],
    dismissSignals: [],
    contentSources: {},
    youtubeHandle: '',
    draftOverride: null,
    scope: 'draft', // 'draft' | 'shop_default'
    draftId: 'default',
    recommendResult: null,
    previousTopId: null,
    onboardingEntries: [],
    onboardingScanDiff: [],
    onboardingScanWarnings: [],
    onboardingScanUrl: '',
    onboardingScanDate: '',
    conflictPending: null,
    serverBaseline: null,
    loadedForOwner: '__init__',
    activeGeneration: 0,
    recSeq: 0,
    scanSeq: 0,
    interpretSeq: 0,
  };

  function cloneDeep(val, fallback = null) {
    try {
      return val === undefined ? fallback : JSON.parse(JSON.stringify(val));
    } catch (_) {
      return fallback;
    }
  }

  function safeHttpUrl(raw) {
    if (!raw || typeof raw !== 'string') return '';
    const trimmed = raw.trim();
    if (!trimmed) return '';
    try {
      const parsed = new URL(trimmed);
      if (
        (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
        !parsed.username &&
        !parsed.password
      ) {
        return parsed.href;
      }
    } catch (_) {}
    return '';
  }

  // --- Safe DOM & Storage Helpers ---
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') node.className = String(v);
      else if (k === 'hidden') node.hidden = Boolean(v);
      else if (k === 'disabled') node.disabled = Boolean(v);
      else if (k === 'checked') node.checked = Boolean(v);
      else if (k === 'value') node.value = String(v);
      else node.setAttribute(k, String(v));
    });
    children.flat().forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      if (typeof child === 'string' || typeof child === 'number') {
        node.appendChild(document.createTextNode(String(child)));
      } else {
        node.appendChild(child);
      }
    });
    return node;
  }

  function safeParse(raw, fallback) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function currentOwnerId() {
    const snap = window.museAccount?.getSnapshot?.();
    const uid = snap?.user?.id || null;
    return uid ? String(uid) : null;
  }

  function ownerNamespace(owner = currentOwnerId()) {
    return owner || 'guest';
  }

  function currentWorkspaceMode() {
    return isSampleMode() ? 'sample' : 'own';
  }

  function urlDraftParam() {
    try {
      const fromUrl = new URLSearchParams(location.search).get('draft');
      if (fromUrl && fromUrl.trim()) return fromUrl.trim().slice(0, 64);
    } catch (_) {}
    return '';
  }

  function currentDraftId() {
    return state.draftId || urlDraftParam() || 'default';
  }

  function draftStorageKey(
    ns = ownerNamespace(),
    mode = currentWorkspaceMode(),
    draftId = currentDraftId()
  ) {
    return `muse.sm.draft.${encodeURIComponent(ns)}.${mode}.${encodeURIComponent(draftId)}`;
  }

  function handoffStorageKey(handoffId, ns = ownerNamespace()) {
    return `muse.sm.handoff.${encodeURIComponent(ns)}.${encodeURIComponent(handoffId)}`;
  }

  function pendingOnboardingKey(ns = ownerNamespace()) {
    return `muse.sm.pending_onb.${encodeURIComponent(ns)}`;
  }

  function guestSampleKey() {
    return 'muse.sm.guest_sample.v1';
  }

  function isCurrentRequestContext(gen, expectedUid, expectedSample) {
    return (
      gen === state.activeGeneration &&
      currentOwnerId() === expectedUid &&
      isSampleMode() === expectedSample
    );
  }

  function stateTagForCurrent() {
    return `${currentOwnerId() || 'guest'}:${isSampleMode() ? 'sample' : 'own'}`;
  }

  function isSampleMode() {
    if (window.museModes?.isSampleMode) return window.museModes.isSampleMode();
    if (new URLSearchParams(location.search).get('workspace') === 'sample') return true;
    const uid = currentOwnerId();
    if (uid) return false;
    try {
      const onbRaw = localStorage.getItem('muse.onboarding.v1');
      const onb = safeParse(onbRaw, null);
      if (onb && onb.completed_at && onb.business_name) return false;
    } catch (_) {}
    return true;
  }

  function authHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const uid = currentOwnerId();
    if (uid) headers['X-Muse-Owner'] = uid;
    return headers;
  }

  async function apiJson(url, options = {}) {
    const resp = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      data = { detail: text };
    }
    return { ok: resp.ok, status: resp.status, data };
  }

  function resetInMemoryState() {
    state.activeGeneration += 1;
    state.recSeq += 1;
    state.scanSeq += 1;
    state.interpretSeq += 1;
    state.version = 0;
    state.businessName = '';
    state.businessType = null;
    state.preferences = {};
    state.voiceProfile = {};
    state.memoryEntries = [];
    state.competitorEntries = [];
    state.suggestedUpdates = [];
    state.dismissSignals = [];
    state.contentSources = {};
    state.youtubeHandle = '';
    state.draftOverride = null;
    state.recommendResult = null;
    state.previousTopId = null;
    state.conflictPending = null;
    state.serverBaseline = null;
  }

  function clearPrivateMemoryUI() {
    resetInMemoryState();
    state.onboardingEntries = [];
    state.onboardingScanDiff = [];
    state.onboardingScanWarnings = [];
    state.onboardingScanUrl = '';
    state.onboardingScanDate = '';
    const memBackdrop = document.getElementById('smMemoryModalBackdrop');
    if (memBackdrop) {
      memBackdrop.hidden = true;
      const body = document.getElementById('smMemoryModalBody');
      if (body) body.textContent = '';
    }
    const conflictBackdrop = document.getElementById('smConflictModalBackdrop');
    if (conflictBackdrop) {
      conflictBackdrop.hidden = true;
      conflictBackdrop.textContent = '';
    }
    [
      'smContextPanel',
      'smWhatChangedBanner',
      'smMissingInfoBanner',
      'smTopMovePreview',
      'smStudioContextBar',
      'smOnboardingScanReview',
    ].forEach((id) => {
      const node = document.getElementById(id);
      if (node) {
        node.textContent = '';
        node.hidden = true;
      }
    });
    document.querySelectorAll('#loop-improve ol.jr-recos li[data-sm-reco-id]').forEach((li) => {
      li.remove();
    });
    document.querySelectorAll('#sellerList .sm-comp-role-wrap').forEach((wrap) => {
      wrap.remove();
    });
  }

  function loadDraftOverride() {
    try {
      const raw = localStorage.getItem(draftStorageKey());
      state.draftOverride = safeParse(raw, null);
    } catch (_) {
      state.draftOverride = null;
    }
  }

  function saveDraftOverride(override) {
    state.draftOverride = override;
    try {
      const key = draftStorageKey();
      if (override) {
        localStorage.setItem(key, JSON.stringify(override));
      } else {
        localStorage.removeItem(key);
      }
    } catch (_) {}
  }

  function loadPendingOnboarding(ns = ownerNamespace()) {
    try {
      const raw = localStorage.getItem(pendingOnboardingKey(ns));
      return safeParse(raw, null);
    } catch (_) {
      return null;
    }
  }

  function savePendingOnboarding(payload, ns = ownerNamespace()) {
    try {
      if (payload) localStorage.setItem(pendingOnboardingKey(ns), JSON.stringify(payload));
      else localStorage.removeItem(pendingOnboardingKey(ns));
    } catch (_) {}
  }

  function stripSampleContamination(entries) {
    if (isSampleMode()) return entries;
    return (entries || []).filter((e) => {
      const blob = `${e.value || ''} ${e.label || ''} ${e.source_url || ''}`.toLowerCase();
      return !BANNED_SAMPLE_TERMS.some((term) => blob.includes(term));
    });
  }

  function toast(msg) {
    if (window.museShell?.toast) window.museShell.toast(msg);
  }

  // --- Guest Sample Mode Local Profile ---
  function loadGuestSampleState() {
    const saved = safeParse(localStorage.getItem(guestSampleKey()), null);
    if (saved) return saved;
    return {
      businessName: 'Studio Sample (Guest Demo)',
      preferences: {
        goal: 'Grow gallery inquiries & direct canvas sales',
        audience: 'Art collectors & cultural gift buyers',
        access: { channels: ['instagram', 'facebook', 'website'], minutes_per_week: 30 },
        taste: { subjects_to_avoid: [] },
        context_note: '',
      },
      memoryEntries: [
        {
          id: 'sample-obs-pages',
          key: 'catalog_summary',
          label: 'Sample catalog reference',
          value: 'Sample workspace only · scan your own shop to replace this sample',
          kind: 'observation',
          scope: 'shop_default',
          source: 'sample_snapshot',
          scan_date: new Date().toISOString().slice(0, 10),
          confidence: 'observed',
          status: 'accepted',
          seller_edited: false,
        },
      ],
      competitorEntries: [
        {
          name: 'Gallery Peer Reference',
          url: 'https://example.org/gallery-peer',
          role: 'similar_audience',
          rationale: 'Example watched peer in guest demo mode',
          reason: 'Example watched peer in guest demo mode',
          selected: true,
        },
      ],
    };
  }

  // --- Server Load / Save / Sync ---
  async function loadServerMemory(force = false) {
    const uid = currentOwnerId();
    const expectedSample = isSampleMode();
    const stateTag = `${uid || 'guest'}:${expectedSample ? 'sample' : 'own'}`;
    if (!force && state.loadedForOwner === stateTag) return;
    if (state.loadedForOwner !== '__init__' && state.loadedForOwner !== stateTag) {
      clearPrivateMemoryUI();
    }
    const gen = ++state.activeGeneration;
    state.ownerId = uid;
    state.loadedForOwner = stateTag;
    const initialDraft = urlDraftParam();
    if (initialDraft) state.draftId = initialDraft;
    loadDraftOverride();

    if (!uid) {
      state.authenticated = false;
      if (expectedSample) {
        const sample = loadGuestSampleState();
        state.businessName = sample.businessName;
        state.businessType = null;
        state.preferences = sample.preferences;
        state.memoryEntries = sample.memoryEntries;
        state.competitorEntries = sample.competitorEntries;
      }
      if (!isCurrentRequestContext(gen, uid, expectedSample)) return;
      renderHomeUI();
      renderStudioBar();
      return;
    }

    const res = await apiJson('/api/v1/seller-memory', { method: 'GET' });
    if (!isCurrentRequestContext(gen, uid, expectedSample)) return;

    if (res.ok && res.data) {
      const serverOwner = res.data.owner_id ?? uid;
      if (res.data.authenticated && serverOwner !== uid) return;
      state.authenticated = Boolean(res.data.authenticated);
      state.version = Number(res.data.version || 0);
      state.businessName = res.data.business_name || '';
      state.businessType = ['products', 'services', 'both'].includes(res.data.business_type) ? res.data.business_type : null;
      state.preferences = res.data.preferences || {};
      state.voiceProfile = res.data.voice_profile || {};
      state.memoryEntries = stripSampleContamination(res.data.memory_entries || []);
      state.competitorEntries = res.data.competitor_entries || [];
      state.suggestedUpdates = res.data.suggested_updates || [];
      state.dismissSignals = res.data.dismiss_signals || [];
      state.contentSources = (res.data.content_sources && typeof res.data.content_sources === 'object')
        ? res.data.content_sources
        : {};
      state.youtubeHandle = typeof res.data.youtube_handle === 'string'
        ? res.data.youtube_handle
        : '';
      state.serverBaseline = cloneDeep({
        preferences: state.preferences,
        voiceProfile: state.voiceProfile,
        memoryEntries: state.memoryEntries,
        competitorEntries: state.competitorEntries,
      });
    }

    // Flush any pending onboarding edits created right before navigation
    const pending = loadPendingOnboarding(uid);
    if (pending && Array.isArray(pending.memory_entries) && pending.memory_entries.length) {
      await syncPendingOnboardingToServer(pending, uid, gen);
      if (!isCurrentRequestContext(gen, uid, expectedSample)) return;
    }

    const onStudio = location.pathname.startsWith('/today') || location.pathname.startsWith('/create');
    if (document.getElementById('loop-improve') || onStudio) {
      await fetchRecommendations(false, { gen, expectedOwner: uid, expectedSample });
      if (!isCurrentRequestContext(gen, uid, expectedSample)) return;
    }
    renderHomeUI();
    renderStudioBar();
  }

  async function syncPendingOnboardingToServer(pending, uid, gen = state.activeGeneration) {
    if (!uid || currentOwnerId() !== uid || gen !== state.activeGeneration) return;
    const mergedEntries = mergeEntriesList(state.memoryEntries, pending.memory_entries || []);
    const nextComps =
      Array.isArray(state.competitorEntries) && state.competitorEntries.length
        ? state.competitorEntries
        : pending.competitors || [];
    const nextPrefs = {
      ...(state.preferences || {}),
      ...(pending.preferences || {}),
      competitor_entries: nextComps,
    };
    const expectedVersion = Number.isInteger(state.version) ? state.version : 0;
    const saveRes = await apiJson('/api/v1/seller-memory', {
      method: 'PUT',
      body: JSON.stringify({
        expected_owner: uid,
        expected_version: expectedVersion,
        preferences: nextPrefs,
        memory_entries: mergedEntries,
        competitor_entries: nextComps,
      }),
    });
    if (gen !== state.activeGeneration || currentOwnerId() !== uid) return;
    if (saveRes.ok && saveRes.data) {
      state.version = Number(saveRes.data.version || state.version);
      state.preferences = saveRes.data.preferences || nextPrefs;
      state.memoryEntries = saveRes.data.memory_entries || mergedEntries;
      state.competitorEntries = saveRes.data.competitor_entries || nextComps;
      state.serverBaseline = cloneDeep({
        preferences: state.preferences,
        voiceProfile: state.voiceProfile,
        memoryEntries: state.memoryEntries,
        competitorEntries: state.competitorEntries,
      });
      savePendingOnboarding(null, uid);
    }
  }

  function isPlainObject(val) {
    return Boolean(val && typeof val === 'object' && !Array.isArray(val));
  }

  function valuesEqual(a, b) {
    try {
      return JSON.stringify(a) === JSON.stringify(b);
    } catch (_) {
      return a === b;
    }
  }

  function threeWayMerge(base, server, local) {
    if (!isPlainObject(server) && !isPlainObject(local)) {
      if (valuesEqual(local, base)) return cloneDeep(server);
      return cloneDeep(local !== undefined ? local : server);
    }
    const baseObj = isPlainObject(base) ? base : {};
    const srvObj = isPlainObject(server) ? server : {};
    const locObj = isPlainObject(local) ? local : {};
    const out = cloneDeep(srvObj, {});
    const keys = new Set([...Object.keys(baseObj), ...Object.keys(srvObj), ...Object.keys(locObj)]);
    keys.forEach((k) => {
      const bVal = baseObj[k];
      const sVal = srvObj[k];
      const lVal = locObj[k];
      const inSrv = Object.prototype.hasOwnProperty.call(srvObj, k);
      const inLoc = Object.prototype.hasOwnProperty.call(locObj, k);
      const inBase = Object.prototype.hasOwnProperty.call(baseObj, k);
      if (isPlainObject(sVal) && isPlainObject(lVal)) {
        out[k] = threeWayMerge(bVal, sVal, lVal);
      } else if (!inLoc) {
        if (inBase && !valuesEqual(sVal, bVal)) {
          out[k] = cloneDeep(sVal);
        } else if (!inBase && inSrv) {
          out[k] = cloneDeep(sVal);
        } else {
          delete out[k];
        }
      } else if (!inSrv) {
        if (!inBase || !valuesEqual(lVal, bVal)) {
          out[k] = cloneDeep(lVal);
        }
      } else if (valuesEqual(lVal, bVal)) {
        out[k] = cloneDeep(sVal);
      } else {
        out[k] = cloneDeep(lVal);
      }
    });
    return out;
  }

  function threeWayMergeEntries(baseList, serverList, localList) {
    const baseMap = new Map((baseList || []).filter((e) => e && e.id).map((e) => [e.id, e]));
    const srvMap = new Map((serverList || []).filter((e) => e && e.id).map((e) => [e.id, cloneDeep(e)]));
    const out = new Map(srvMap);
    (localList || []).forEach((loc) => {
      if (!loc || !loc.id) return;
      const base = baseMap.get(loc.id);
      const srv = srvMap.get(loc.id);
      if (!srv) {
        if (!base || !valuesEqual(loc, base)) out.set(loc.id, cloneDeep(loc));
        return;
      }
      if (base && valuesEqual(loc, base)) {
        out.set(loc.id, cloneDeep(srv));
      } else if (srv.seller_edited && !loc.seller_edited) {
        out.set(loc.id, cloneDeep(srv));
      } else {
        out.set(loc.id, threeWayMerge(base || {}, srv, loc));
      }
    });
    return Array.from(out.values());
  }

  function mergeCompetitorEntries(baseComps, serverComps, localComps) {
    const compKey = (c) => (c?.url || c?.name || '').toLowerCase();
    const baseMap = new Map((baseComps || []).filter((c) => compKey(c)).map((c) => [compKey(c), c]));
    const srvMap = new Map((serverComps || []).filter((c) => compKey(c)).map((c) => [compKey(c), cloneDeep(c)]));
    const out = new Map(srvMap);
    (localComps || []).forEach((loc) => {
      const k = compKey(loc);
      if (!k) return;
      const base = baseMap.get(k);
      const srv = srvMap.get(k);
      if (!srv) {
        out.set(k, cloneDeep(loc));
      } else if (base && valuesEqual(loc, base)) {
        out.set(k, cloneDeep(srv));
      } else {
        out.set(k, threeWayMerge(base || {}, srv, loc));
      }
    });
    return Array.from(out.values());
  }

  function mergeEntriesList(base, incoming) {
    const byId = new Map();
    (base || []).forEach((e) => {
      if (e && e.id) byId.set(e.id, cloneDeep(e));
    });
    (incoming || []).forEach((e) => {
      if (!e || !e.id) return;
      const prev = byId.get(e.id);
      if (prev && prev.seller_edited && !e.seller_edited) {
        return; // Preserve seller edits unless newer entry was also seller-edited
      }
      byId.set(e.id, prev ? { ...prev, ...cloneDeep(e) } : cloneDeep(e));
    });
    return Array.from(byId.values());
  }

  let persistQueue = Promise.resolve();

  function persistToServer(opts = {}) {
    const boundOwner = currentOwnerId();
    const boundGen = state.activeGeneration;
    const boundSample = isSampleMode();
    const snapshot = {
      preferences: cloneDeep(opts.preferences !== undefined ? opts.preferences : state.preferences, {}),
      voiceProfile: cloneDeep(opts.voiceProfile !== undefined ? opts.voiceProfile : state.voiceProfile, {}),
      memoryEntries: cloneDeep(opts.memoryEntries !== undefined ? opts.memoryEntries : state.memoryEntries, []),
      competitorEntries: cloneDeep(opts.competitorEntries !== undefined ? opts.competitorEntries : state.competitorEntries, []),
      forceVersion: opts.forceVersion !== undefined ? opts.forceVersion : null,
      boundOwner,
      boundGen,
      boundSample,
    };
    const run = persistQueue.then(
      () => _persistToServerOnce(snapshot),
      () => _persistToServerOnce(snapshot)
    );
    persistQueue = run.catch(() => {});
    return run;
  }

  async function _persistToServerOnce({
    preferences,
    voiceProfile,
    memoryEntries,
    competitorEntries,
    forceVersion = null,
    boundOwner,
    boundGen,
    boundSample,
  }) {
    if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) {
      return { ok: false, stale: true };
    }
    if (!boundOwner) {
      // Guest demo device-local persistence only for matching guest session
      if (boundSample) {
        localStorage.setItem(
          guestSampleKey(),
          JSON.stringify({
            businessName: state.businessName,
            preferences,
            memoryEntries,
            competitorEntries,
          })
        );
      }
      state.preferences = preferences;
      state.memoryEntries = memoryEntries;
      state.competitorEntries = competitorEntries;
      return { ok: true, guest: true };
    }

    const expectedVersion = forceVersion !== null
      ? forceVersion
      : (Number.isInteger(state.version) ? state.version : 0);

    const res = await apiJson('/api/v1/seller-memory', {
      method: 'PUT',
      headers: { 'X-Muse-Owner': boundOwner },
      body: JSON.stringify({
        expected_version: expectedVersion,
        expected_owner: boundOwner,
        preferences,
        voice_profile: voiceProfile,
        memory_entries: memoryEntries,
        competitor_entries: competitorEntries,
      }),
    });

    if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) {
      return { ok: false, stale: true };
    }

    if (res.status === 409 && res.data && res.data.server_version !== undefined) {
      state.conflictPending = {
        ownerId: boundOwner,
        gen: boundGen,
        base: cloneDeep(state.serverBaseline, {
          preferences: {},
          voiceProfile: {},
          memoryEntries: [],
          competitorEntries: [],
        }),
        local: {
          preferences,
          voiceProfile,
          memoryEntries,
          competitorEntries,
        },
        server: {
          version: res.data.server_version,
          preferences: res.data.server_preferences || {},
          voiceProfile: res.data.server_voice_profile || {},
          memoryEntries: res.data.server_memory_entries || [],
          competitorEntries: res.data.server_competitor_entries || [],
        },
      };
      openConflictModal();
      return { ok: false, conflict: true };
    }

    if (res.ok && res.data) {
      state.version = Number(res.data.version || state.version + 1);
      state.preferences = res.data.preferences || preferences;
      state.voiceProfile = res.data.voice_profile || voiceProfile;
      state.memoryEntries = res.data.memory_entries || memoryEntries;
      state.competitorEntries = res.data.competitor_entries || competitorEntries;
      state.suggestedUpdates = res.data.suggested_updates || state.suggestedUpdates;
      state.serverBaseline = cloneDeep({
        preferences: state.preferences,
        voiceProfile: state.voiceProfile,
        memoryEntries: state.memoryEntries,
        competitorEntries: state.competitorEntries,
      });
      return { ok: true };
    }
    toast(res.data?.detail || `Could not save memory (HTTP ${res.status})`);
    return { ok: false };
  }

  async function fetchRecommendations(showSpinner = true, ctx = null) {
    const gen = ctx?.gen ?? state.activeGeneration;
    const expectedOwner = ctx && 'expectedOwner' in ctx ? ctx.expectedOwner : currentOwnerId();
    const expectedSample = ctx && 'expectedSample' in ctx ? ctx.expectedSample : isSampleMode();
    const seq = ++state.recSeq;

    const activePref = {
      ...(state.preferences || {}),
      memory_entries: state.memoryEntries || [],
    };
    const res = await apiJson('/api/v1/seller-memory/recommend', {
      method: 'POST',
      headers: expectedOwner ? { 'X-Muse-Owner': expectedOwner } : {},
      body: JSON.stringify({
        business_name: state.businessName || deriveSignedInBusinessName() || 'Your Studio',
        business_type: state.businessType || null,
        product_name: state.draftOverride?.product_name || null,
        preferences: activePref,
        voice_profile: state.voiceProfile || {},
        competitor_entries: state.competitorEntries || [],
        content_videos: !expectedSample && Array.isArray(state.contentSources?.youtube?.videos)
          ? state.contentSources.youtube.videos
          : undefined,
        draft_override: state.draftOverride || null,
        dismiss_signals: state.dismissSignals || [],
        previous_top_id: state.previousTopId || null,
      }),
    });
    if (!isCurrentRequestContext(gen, expectedOwner, expectedSample) || seq !== state.recSeq) {
      return null;
    }
    if (res.ok && res.data) {
      state.recommendResult = res.data;
      const top = res.data.recommendations?.[0];
      if (top?.id) state.previousTopId = top.id;
      if (showSpinner) {
        renderHomeRecommendations();
        renderStudioBar();
      }
      return res.data;
    }
    return null;
  }

  function deriveSignedInBusinessName() {
    const raw = safeParse(localStorage.getItem('muse.onboarding.v1'), null);
    return raw?.business_name || '';
  }

  // --- Shared Voice & Text Proposal Review UI ---
  function buildProposalReviewList(entries, onChange) {
    const list = el('div', { class: 'sm-memory-list' });
    entries.forEach((entry, idx) => {
      if (entry.status === 'dismissed') return;
      const badgeCls = `sm-badge sm-badge-${entry.kind || 'preference'}`;
      const badgeText = KIND_LABELS[entry.kind] || 'Preference';

      const row = el('div', {
        class: 'sm-memory-row',
        'data-sm-entry-id': entry.id,
        'data-sm-kind': entry.kind || 'preference',
      });

      const badges = el('div', { class: 'sm-badge-row' },
        el('span', { class: badgeCls }, badgeText),
        el('span', { class: 'sm-badge' }, SOURCE_LABELS[entry.source] || entry.source || 'Shop')
      );
      if (entry.seller_edited) {
        badges.appendChild(el('span', { class: 'sm-badge sm-badge-edited' }, 'Edited by you · preserved'));
      }
      if (entry.kind === 'interpretation' && entry.confidence !== 'confirmed') {
        badges.appendChild(el('span', { class: 'sm-badge sm-badge-interpretation' }, 'Needs your confirm'));
      }

      const topRow = el('div', { class: 'sm-memory-row-top' },
        el('strong', {}, entry.label || entry.key),
        badges
      );

      const meta = el('div', { class: 'sm-memory-meta' });
      if (entry.source_url) {
        const validatedUrl = safeHttpUrl(entry.source_url);
        meta.appendChild(
          validatedUrl
            ? el('span', {}, 'Source: ', el('a', { href: validatedUrl, target: '_blank', rel: 'noopener noreferrer' }, validatedUrl))
            : el('span', {}, `Source: ${String(entry.source_url)}`)
        );
      }
      if (entry.scan_date) {
        meta.appendChild(el('span', {}, `Scanned: ${entry.scan_date}`));
      }
      if (entry.uncertainty) {
        meta.appendChild(el('span', {}, entry.uncertainty));
      }

      const input = el('input', {
        type: 'text',
        class: 'sm-memory-input',
        value: entry.value || '',
        'aria-label': `Edit ${entry.label || entry.key}`,
      });
      input.addEventListener('change', () => {
        const nextVal = input.value.trim();
        if (!nextVal) return;
        entry.value = nextVal;
        entry.seller_edited = true;
        entry.confidence = 'confirmed';
        entry.status = 'accepted';
        onChange?.('edit', entry, idx);
      });

      const btns = el('div', { class: 'sm-btn-row' });
      if (entry.status !== 'accepted' || entry.confidence === 'inferred') {
        const confirmBtn = el('button', { type: 'button', class: 'sm-btn' }, 'Confirm');
        confirmBtn.addEventListener('click', () => {
          entry.value = input.value.trim() || entry.value;
          entry.status = 'accepted';
          entry.confidence = 'confirmed';
          onChange?.('confirm', entry, idx);
        });
        btns.appendChild(confirmBtn);
      }
      const removeBtn = el('button', { type: 'button', class: 'sm-btn sm-btn-danger' }, 'Dismiss');
      removeBtn.addEventListener('click', () => {
        entry.status = 'dismissed';
        onChange?.('dismiss', entry, idx);
      });
      btns.appendChild(removeBtn);

      row.append(topRow, input, meta, btns);
      list.appendChild(row);
    });
    return list;
  }

  function buildVoiceAndNoteWidget({ onAcceptEntries, existingEntriesFn }) {
    const wrap = el('div', { class: 'sm-voice-box' });
    const title = el('strong', {}, 'Add context by text or voice note (review before saving)');
    const noteLabel = el('label', { class: 'wk-label', for: 'smFreeContextInput', style: 'display:block;margin-top:6px;' },
      'Anything else Muse should know? (goal, avoided topics, caption style, time, prices)'
    );
    const textarea = el('textarea', {
      id: 'smFreeContextInput',
      class: 'sm-textarea',
      maxlength: '1200',
      placeholder: 'e.g. Never suggest TikTok, keep captions short, I have 15 minutes a week, archival prints start at $35.',
    });

    const btnRow = el('div', { class: 'sm-btn-row', style: 'margin-top:8px;' });
    const interpretBtn = el('button', { type: 'button', id: 'smInterpretTextBtn', class: 'sm-btn sm-btn-primary' },
      'Turn note into review items (0 runs)'
    );
    const sampleVoiceBtn = el('button', { type: 'button', id: 'smUseVoiceFixtureBtn', class: 'sm-btn' },
      'Use sample watercolor voice note (demo · 0 runs)'
    );
    // The watercolor note belongs to the sample shop; a seller's own memory never offers it.
    if (!isSampleMode()) sampleVoiceBtn.style.display = 'none';
    btnRow.append(interpretBtn, sampleVoiceBtn);

    // Live consent-gated voice upload/record row
    const consentRow = el('label', { class: 'sm-field-inline', style: 'margin-top:10px;display:flex;align-items:flex-start;' });
    const consentCb = el('input', { type: 'checkbox', id: 'smVoiceConsentCheck' });
    consentRow.append(
      consentCb,
      el('span', {}, 'Consent to transcribe live audio (costs 1 Muse run when live; raw audio and unapproved transcripts are never saved).')
    );

    const liveVoiceRow = el('div', { class: 'sm-btn-row', style: 'margin-top:6px;' });
    const audioInput = el('input', {
      type: 'file',
      id: 'smVoiceUploadInput',
      accept: 'audio/*',
      style: 'max-width:220px;font-size:0.78rem;',
    });
    const recordBtn = el('button', { type: 'button', id: 'smVoiceRecordBtn', class: 'sm-btn' }, 'Record voice');
    const voiceStatus = el('div', { class: 'sm-sub', id: 'smVoiceStatus', role: 'status' });
    liveVoiceRow.append(recordBtn, audioInput);

    const transcriptPreview = el('div', { id: 'smVoiceTranscriptBox', hidden: true, style: 'margin-top:8px;' });
    const transcriptInput = el('textarea', {
      id: 'smVoiceTranscriptEdit',
      class: 'sm-textarea',
      'aria-label': 'Editable transcript before saving',
    });
    const reviewTranscriptBtn = el('button', { type: 'button', id: 'smReviewTranscriptBtn', class: 'sm-btn sm-btn-primary' },
      'Extract items from transcript to review'
    );
    let lastTranscriptSource = 'voice_demo_fixture';
    let lastFixtureId = null;

    transcriptPreview.append(
      el('label', { for: 'smVoiceTranscriptEdit', style: 'font-size:0.78rem;font-weight:600;display:block;margin-bottom:4px;' },
        'Unapproved transcript (edit freely before extracting items; nothing is saved yet):'
      ),
      transcriptInput,
      el('div', { class: 'sm-btn-row', style: 'margin-top:6px;' }, reviewTranscriptBtn)
    );

    const reviewArea = el('div', { id: 'smProposalReviewArea', style: 'margin-top:10px;' });
    let pendingProposals = [];
    let pendingConflicts = [];

    function renderReviewArea() {
      reviewArea.textContent = '';
      if (!pendingProposals.length && !pendingConflicts.length) return;
      if (pendingConflicts.length) {
        pendingConflicts.forEach((c) => {
          reviewArea.appendChild(
            el('div', { class: 'sm-suggestion-banner' }, `Notice: ${c.message}`)
          );
        });
      }
      const list = buildProposalReviewList(pendingProposals, () => renderReviewArea());
      const activeCount = pendingProposals.filter((p) => p.status !== 'dismissed').length;
      if (activeCount > 0) {
        const approveAllBtn = el('button', {
          type: 'button',
          id: 'smApproveProposalsBtn',
          class: 'sm-btn sm-btn-primary',
        }, `Approve ${activeCount} item(s) to profile`);
        approveAllBtn.addEventListener('click', async () => {
          const accepted = pendingProposals
            .filter((p) => p.status !== 'dismissed')
            .map((p) => ({ ...p, status: 'accepted', confidence: 'confirmed' }));
          pendingProposals = [];
          pendingConflicts = [];
          renderReviewArea();
          transcriptPreview.hidden = true;
          await onAcceptEntries(accepted);
        });
        reviewArea.append(
          el('div', { class: 'sm-sub' }, 'Review items below before adding them to your saved memory:'),
          list,
          approveAllBtn
        );
      }
    }

    async function runInterpret({ text, sourceType, fixtureId }) {
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      const seq = ++state.interpretSeq;
      voiceStatus.textContent = '';
      const res = await apiJson('/api/v1/seller-memory/interpret', {
        method: 'POST',
        headers: boundOwner ? { 'X-Muse-Owner': boundOwner } : {},
        body: JSON.stringify({
          text: text || '',
          source_type: sourceType,
          fixture_id: fixtureId || null,
          existing_entries: existingEntriesFn ? existingEntriesFn() : state.memoryEntries,
        }),
      });
      if (!isCurrentRequestContext(boundGen, boundOwner, boundSample) || seq !== state.interpretSeq) {
        return;
      }
      if (!res.ok) {
        voiceStatus.textContent = res.data?.detail || 'Could not interpret note.';
        return;
      }
      pendingProposals = res.data.proposed_entries || [];
      pendingConflicts = res.data.conflicts || [];
      renderReviewArea();
      if (!pendingProposals.length && res.data.unclear?.length) {
        voiceStatus.textContent = res.data.unclear[0];
      }
    }

    interpretBtn.addEventListener('click', () => {
      const txt = textarea.value.trim();
      if (!txt) {
        voiceStatus.textContent = 'Type a short note first, or click the sample voice note.';
        return;
      }
      runInterpret({ text: txt, sourceType: 'typed' });
    });

    sampleVoiceBtn.addEventListener('click', async () => {
      voiceStatus.textContent = 'Loading demo watercolor voice transcript (0 runs)...';
      const fixRes = await apiJson('/api/v1/seller-memory/voice-fixtures', { method: 'GET' });
      const fixture = fixRes.data?.fixtures?.[0];
      if (!fixture) {
        voiceStatus.textContent = 'Sample voice note unavailable.';
        return;
      }
      lastTranscriptSource = 'voice_demo_fixture';
      lastFixtureId = fixture.id;
      transcriptInput.value = fixture.transcript;
      transcriptPreview.hidden = false;
      voiceStatus.textContent = `${fixture.title} loaded (0 runs). Review or edit transcript, then click Extract.`;
    });

    reviewTranscriptBtn.addEventListener('click', () => {
      runInterpret({
        text: transcriptInput.value.trim(),
        sourceType: lastTranscriptSource,
        fixtureId: lastFixtureId,
      });
    });

    async function handleAudioBase64(b64, filename) {
      if (!consentCb.checked) {
        voiceStatus.textContent = 'Please check the consent box first. You can also type your note above for free.';
        return;
      }
      voiceStatus.textContent = 'Transcribing clip (1 Muse run when live)...';
      const res = await apiJson('/api/v1/seller-memory/voice/transcribe', {
        method: 'POST',
        body: JSON.stringify({
          audio_base64: b64,
          filename: filename || 'voice_note.webm',
          consent_confirmed: true,
        }),
      });
      if (!res.ok) {
        voiceStatus.textContent =
          `${res.data?.detail || 'Live transcription is unavailable in demo mode.'} Type your note above for free instead.`;
        return;
      }
      lastTranscriptSource = 'voice_approved_transcript';
      lastFixtureId = null;
      transcriptInput.value = res.data.transcript || '';
      transcriptPreview.hidden = false;
      voiceStatus.textContent = 'Transcript ready for review. Nothing saved until you approve.';
    }

    audioInput.addEventListener('change', () => {
      const file = audioInput.files?.[0];
      if (!file) return;
      if (!consentCb.checked) {
        voiceStatus.textContent = 'Please confirm consent above before transcribing audio, or type your note for free.';
        audioInput.value = '';
        return;
      }
      const reader = new FileReader();
      reader.onload = () => handleAudioBase64(String(reader.result || ''), file.name);
      reader.readAsDataURL(file);
    });

    let recorder = null;
    recordBtn.addEventListener('click', async () => {
      if (!consentCb.checked) {
        voiceStatus.textContent = 'Check consent first before recording, or use typed note / sample voice note (0 runs).';
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        voiceStatus.textContent = 'Browser microphone recording is unavailable here. Upload an audio clip or type your note above.';
        return;
      }
      if (recorder && recorder.state === 'recording') {
        recorder.stop();
        recordBtn.textContent = 'Record voice';
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (ev) => ev.data?.size && chunks.push(ev.data);
        recorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: 'audio/webm' });
          const reader = new FileReader();
          reader.onload = () => handleAudioBase64(String(reader.result || ''), 'recording.webm');
          reader.readAsDataURL(blob);
        };
        recorder.start();
        recordBtn.textContent = 'Stop recording';
        voiceStatus.textContent = 'Recording... click Stop recording when done.';
      } catch (_) {
        voiceStatus.textContent = 'Microphone permission declined. Upload an audio file or type your note above for free.';
      }
    });

    wrap.append(title, noteLabel, textarea, btnRow, consentRow, liveVoiceRow, voiceStatus, transcriptPreview, reviewArea);
    return wrap;
  }

  // --- /welcome Integration (Step 1 Scan Review + Step 4 Context & Sync) ---
  function initOnboardingHooks() {
    const step1 = document.getElementById('wkStep1');
    const step4 = document.getElementById('wkStep4');
    if (!step1 || !step4) return;

    let reviewBox = document.getElementById('smOnboardingScanReview');
    if (!reviewBox) {
      reviewBox = el('div', { id: 'smOnboardingScanReview', class: 'sm-card', hidden: true });
      const proofBox = document.getElementById('wkShopProof');
      if (proofBox) proofBox.insertAdjacentElement('afterend', reviewBox);
      else step1.appendChild(reviewBox);
    }

    function renderOnboardingScanReview() {
      if (!state.onboardingEntries.length && !state.onboardingScanWarnings.length) {
        reviewBox.hidden = true;
        return;
      }
      reviewBox.hidden = false;
      reviewBox.textContent = '';

      const header = el('div', { class: 'sm-card-header' },
        el('div', {},
          el('h2', { class: 'sm-card-title' }, 'What Muse found on your public pages'),
          el('p', { class: 'sm-sub' },
            'Observed facts come straight from your pages. Interpretations are guesses: edit, confirm, or dismiss any item.'
          )
        ),
        el('span', { class: 'sm-badge sm-badge-observation' }, '0 runs')
      );
      reviewBox.appendChild(header);

      if (state.onboardingScanWarnings.length) {
        state.onboardingScanWarnings.forEach((w) => {
          reviewBox.appendChild(el('div', { class: 'sm-suggestion-banner' }, w));
        });
      }

      if (state.onboardingScanDiff.length) {
        const diffBox = el('div', { id: 'smRescanDiffBox', class: 'sm-diff-box' },
          el('strong', {}, 'Rescan comparison (your manual edits were preserved):')
        );
        state.onboardingScanDiff.forEach((d) => {
          if (d.change_type === 'unchanged') return;
          const row = el('div', { class: 'sm-diff-item' },
            el('div', {},
              el('strong', {}, `${d.label}: `),
              d.preserves_seller_edit
                ? el('span', { class: 'sm-badge sm-badge-edited' }, 'Preserved your edit')
                : el('span', { class: 'sm-badge' }, d.change_type)
            ),
            el('div', {}, `Before: ${d.before_value || '—'} → New scan: ${d.after_value || '—'}`)
          );
          if (d.preserves_seller_edit && d.after_value) {
            const acceptNewBtn = el('button', {
              type: 'button',
              class: 'sm-btn',
              style: 'margin-top:4px;',
            }, 'Use new scan value instead');
            acceptNewBtn.addEventListener('click', () => {
              const target = state.onboardingEntries.find((e) => e.id === d.entry_id);
              if (target) {
                target.value = d.after_value;
                target.seller_edited = false;
                target.scan_date = d.scan_date || target.scan_date;
                state.onboardingScanDiff = state.onboardingScanDiff.filter((x) => x.entry_id !== d.entry_id);
                renderOnboardingScanReview();
              }
            });
            row.appendChild(acceptNewBtn);
          }
          diffBox.appendChild(row);
        });
        if (diffBox.querySelector('.sm-diff-item')) reviewBox.appendChild(diffBox);
      }

      const list = buildProposalReviewList(state.onboardingEntries, () => {
        renderOnboardingScanReview();
        persistOnboardingLocalEntries();
      });
      reviewBox.appendChild(list);
      persistOnboardingLocalEntries();
    }

    function persistOnboardingLocalEntries() {
      const uid = ownerNamespace();
      const rawOnb = safeParse(localStorage.getItem('muse.onboarding.v1'), {}) || {};
      const active = state.onboardingEntries.filter((e) => e.status !== 'dismissed');
      savePendingOnboarding(
        {
          memory_entries: active,
          competitors: rawOnb.competitors || [],
          preferences: {
            goal: document.getElementById('wkPrefFocus')?.value?.trim() || undefined,
          },
        },
        uid
      );
    }

    window.addEventListener('muse:scan-complete', async (ev) => {
      const detail = ev.detail || {};
      if (window.museAccount?.ready) {
        try { await window.museAccount.ready(); } catch (_) {}
      }
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      const seq = ++state.scanSeq;
      const items = (detail.data?.discovered_catalog_items || []).slice(0, 20);
      const priceHints = detail.data?.detected_price_hints || [];
      const snapshotItems = items.map((item, idx) => ({
        url: item.url,
        title: item.title,
        bucket: item.bucket || 'products',
        // Only forward detected price hints when present; NEVER invent!
        price_hint: item.price_hint || (idx < priceHints.length ? priceHints[idx] : null),
      }));

      const scanRes = await apiJson('/api/v1/seller-memory/scan', {
        method: 'POST',
        headers: boundOwner ? { 'X-Muse-Owner': boundOwner } : {},
        body: JSON.stringify({
          business_name: detail.businessName || 'Your Shop',
          website_url: detail.primaryUrl || '',
          extra_urls: detail.extraUrls || [],
          existing_entries: state.onboardingEntries,
          snapshot_items: snapshotItems,
        }),
      });
      if (!isCurrentRequestContext(boundGen, boundOwner, boundSample) || seq !== state.scanSeq) {
        return;
      }
      if (!scanRes.ok || !scanRes.data) return;

      const blockedNotes = (detail.data?.channels || [])
        .filter((c) => c.status === 'vision_or_manual' && c.note)
        .map((c) => c.note);
      state.onboardingScanWarnings = Array.from(
        new Set([...(scanRes.data.partial_warnings || []), ...blockedNotes])
      );
      state.onboardingScanUrl = scanRes.data.source_url || detail.primaryUrl || '';
      state.onboardingScanDate = scanRes.data.scan_date || '';
      state.onboardingScanDiff = scanRes.data.diff || [];

      const incoming = (scanRes.data.proposed_entries || []).map((e) => ({
        ...e,
        status: 'accepted', // Ready unless seller explicitly dismisses
      }));
      state.onboardingEntries = mergeEntriesList(state.onboardingEntries, incoming);
      renderOnboardingScanReview();
    });

    // Mount Step 4 "Anything else Muse should know?" + voice widget
    if (!document.getElementById('smOnboardingStep4Box')) {
      const step4Box = el('div', { id: 'smOnboardingStep4Box', class: 'sm-card' });
      const widget = buildVoiceAndNoteWidget({
        existingEntriesFn: () => state.onboardingEntries,
        onAcceptEntries: async (accepted) => {
          state.onboardingEntries = mergeEntriesList(state.onboardingEntries, accepted);
          renderStep4Summary();
          renderOnboardingScanReview();
          toast(`Added ${accepted.length} reviewed item(s) to your profile.`);
        },
      });
      const step4Summary = el('div', { id: 'smStep4ReviewSummary', class: 'sm-sub', style: 'margin-top:8px;' });
      function renderStep4Summary() {
        const active = state.onboardingEntries.filter((e) => e.status !== 'dismissed');
        const obsCount = active.filter((e) => e.kind === 'observation').length;
        const intCount = active.filter((e) => e.kind === 'interpretation').length;
        const prefCount = active.filter((e) => e.kind === 'preference' || e.kind === 'goal').length;
        step4Summary.textContent = `Ready to save with your workspace: ${obsCount} observed fact(s), ${intCount} interpretation(s), ${prefCount} typed/voice preference(s).`;
      }
      renderStep4Summary();
      step4Box.append(widget, step4Summary);

      const actionsRow = step4.querySelector('.wk-actions');
      if (actionsRow) actionsRow.insertAdjacentElement('beforebegin', step4Box);
      else step4.appendChild(step4Box);
    }

    // Also include free text in Step 4 even if user clicks Finish directly without clicking "Turn note into review items"
    const captureStep4Typed = () => {
      const txt = document.getElementById('smFreeContextInput')?.value?.trim();
      const focusTxt = document.getElementById('wkPrefFocus')?.value?.trim();
      const rawOnb = safeParse(localStorage.getItem('muse.onboarding.v1'), {}) || {};
      const mins = Number(rawOnb.preferences?.minutes_per_week || 0) || null;
      const toAdd = [];
      if (focusTxt) {
        toAdd.push({
          id: 'pref-goal',
          key: 'goal',
          label: 'Primary goal',
          value: focusTxt,
          kind: 'goal',
          scope: 'shop_default',
          source: 'onboarding_questions',
          confidence: 'confirmed',
          status: 'accepted',
        });
      }
      if (mins) {
        toAdd.push({
          id: 'pref-minutes',
          key: 'minutes_per_week',
          label: 'Weekly time budget',
          value: `${mins} minutes / week`,
          kind: 'preference',
          scope: 'shop_default',
          source: 'onboarding_questions',
          confidence: 'confirmed',
          status: 'accepted',
        });
      }
      if (txt) {
        toAdd.push({
          id: 'pref-context-note',
          key: 'context_note',
          label: 'Seller context note',
          value: txt.slice(0, 320),
          kind: 'preference',
          scope: 'shop_default',
          source: 'user_input',
          confidence: 'confirmed',
          status: 'accepted',
        });
      }
      if (toAdd.length) {
        state.onboardingEntries = mergeEntriesList(state.onboardingEntries, toAdd);
      }
      persistOnboardingLocalEntries();
    };

    document.getElementById('wkStep4FinishBtn')?.addEventListener('click', captureStep4Typed, true);
    document.getElementById('wkStep4SkipBtn')?.addEventListener('click', captureStep4Typed, true);

    // Watch #wkStepDone becoming visible -> sync reviewed memory + competitor roles to PUT /api/v1/seller-memory
    const stepDone = document.getElementById('wkStepDone');
    if (stepDone) {
      const obs = new MutationObserver(async () => {
        if (stepDone.hidden) return;
        const uid = currentOwnerId();
        const boundGen = state.activeGeneration;
        const boundSample = isSampleMode();
        if (!uid) return;
        const pending = loadPendingOnboarding(uid);
        if (!pending) return;
        // Fetch current server version post-/onboarding/build, then save cleanly
        const cur = await apiJson('/api/v1/seller-memory', {
          method: 'GET',
          headers: { 'X-Muse-Owner': uid },
        });
        if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
        if (cur.ok && cur.data) {
          state.version = Number(cur.data.version || 0);
          state.preferences = cur.data.preferences || {};
          state.memoryEntries = cur.data.memory_entries || [];
          state.competitorEntries = cur.data.competitor_entries || [];
        }
        await syncPendingOnboardingToServer(pending, uid, boundGen);
        if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
        stepDone.dataset.smSynced = 'true';
      });
      obs.observe(stepDone, { attributes: true, attributeFilter: ['hidden'] });
    }
  }

  // --- Home Workspace (/) Context Panel, Watchlist Roles & Recommendations ---
  function renderHomeUI() {
    const improveSec = document.getElementById('loop-improve');
    const loopNav = document.querySelector('#journey nav.jr-loop');
    if (!improveSec && !loopNav) return;

    let panel = document.getElementById('smContextPanel');
    if (!panel) {
      panel = el('section', { id: 'smContextPanel', class: 'sm-card', 'aria-label': 'Your context and seller memory' });
      if (loopNav) {
        loopNav.insertAdjacentElement('afterend', panel);
      } else {
        const recos = improveSec.querySelector('ol.jr-recos');
        if (recos) recos.insertAdjacentElement('beforebegin', panel);
        else improveSec.prepend(panel);
      }
    }
    panel.hidden = false;

    const pref = state.preferences || {};
    const draft = state.draftOverride || {};
    const draftIgnoredIds = Array.isArray(draft.ignore_entry_ids)
      ? draft.ignore_entry_ids
      : (Array.isArray(draft.ignored_entry_ids) ? draft.ignored_entry_ids : []);
    const isDraftActive = Boolean(
      draft &&
      (draft.active || draft.goal || draft.minutes_per_week || draft.context_note || draft.product_name || draft.destination || draftIgnoredIds.length)
    );
    const guestDemo = isSampleMode();

    panel.textContent = '';

    const titleRow = el('div', { class: 'sm-card-header' },
      el('div', {},
        el('h3', { class: 'sm-card-title' }, 'Your context'),
        el('p', { class: 'sm-sub' },
          isDraftActive
            ? 'Showing temporary "This draft" overrides. Your saved shop defaults remain intact.'
            : 'Used to personalize your top recommendations and ad defaults.'
        )
      ),
      el('div', { class: 'sm-btn-row' },
        el('button', {
          type: 'button',
          id: 'smOpenMemoryBtn',
          class: 'sm-btn',
        }, `What Muse remembers (${(state.memoryEntries || []).filter((e) => e.status !== 'dismissed').length})`)
      )
    );
    panel.appendChild(titleRow);
    panel.querySelector('#smOpenMemoryBtn')?.addEventListener('click', openMemoryModal);

    // Nothing remembered yet: one line and a way in, instead of the whole form.
    const rememberedCount = (state.memoryEntries || []).filter((e) => e.status !== 'dismissed').length;
    const pendingSuggestion = (state.suggestedUpdates || []).some((s) => !s.status || s.status === 'pending');
    if (!guestDemo && !isDraftActive && !rememberedCount && !pendingSuggestion && !state.homePanelExpanded) {
      panel.classList.add('sm-card-compact');
      const sub = titleRow.querySelector('.sm-sub');
      // Setup already saves a goal and weekly minutes; "Nothing saved yet" contradicted the move below.
      const goalSaved = String(state.preferences?.goal || '').trim();
      const minutesSaved = Number(state.preferences?.access?.minutes_per_week) || 0;
      const byGoal = goalSaved ? `your goal (${goalSaved.toLowerCase()})` : 'your goal';
      const byTime = minutesSaved ? `your ${minutesSaved} minutes a week` : 'the time you have each week';
      if (sub) sub.textContent = goalSaved || minutesSaved
        ? `Muse ranks your moves by ${byGoal} and ${byTime}.`
        : 'Muse ranks your moves by your goal and the time you have each week. Nothing saved yet.';
      const memBtn = titleRow.querySelector('#smOpenMemoryBtn');
      if (memBtn) memBtn.textContent = 'What Muse remembers';
      const openBtn = el('button', { type: 'button', id: 'smExpandContextBtn', class: 'sm-btn sm-btn-primary' }, goalSaved ? 'Change your goal' : 'Set your goal');
      openBtn.addEventListener('click', () => {
        state.homePanelExpanded = true;
        renderHomeUI();
      });
      panel.appendChild(el('div', { class: 'sm-btn-row' }, openBtn));
      renderWatchlistControls();
      renderHomeRecommendations();
      return;
    }
    panel.classList.remove('sm-card-compact');


    // Pending feedback suggestions banner (never auto-applied!)
    if ((state.suggestedUpdates || []).length) {
      const sugWrap = el('div', { id: 'smSuggestionContainer' });
      state.suggestedUpdates.forEach((sug) => {
        if (sug.status && sug.status !== 'pending') return;
        const box = el('div', { class: 'sm-suggestion-banner', 'data-suggestion-id': sug.id },
          el('div', {},
            el('strong', {}, `Suggested update: ${sug.label}`),
            ` — ${sug.proposed_value}`,
            el('div', { class: 'sm-sub', style: 'margin:2px 0 6px;' }, sug.reason_signal)
          )
        );
        const row = el('div', { class: 'sm-btn-row' });
        const appBtn = el('button', {
          type: 'button',
          class: 'sm-btn sm-btn-primary',
          'data-approve-suggestion': sug.id,
        }, 'Approve & save');
        appBtn.addEventListener('click', () => handleSuggestionDecision(sug.id, 'approve'));
        const disBtn = el('button', {
          type: 'button',
          class: 'sm-btn',
          'data-dismiss-suggestion': sug.id,
        }, 'Dismiss');
        disBtn.addEventListener('click', () => handleSuggestionDecision(sug.id, 'dismiss'));
        row.append(appBtn, disBtn);
        box.appendChild(row);
        sugWrap.appendChild(box);
      });
      panel.appendChild(sugWrap);
    }

    // Scope switcher: This draft vs Save as shop default + active draft slot
    const scopeBar = el('div', { class: 'sm-badge-row', style: 'justify-content:space-between;' });
    const scopeToggle = el('div', { class: 'sm-scope-toggle', role: 'group', 'aria-label': 'Context scope' });
    const draftBtn = el('button', {
      type: 'button',
      id: 'smScopeDraftBtn',
      class: `sm-scope-btn${state.scope === 'draft' ? ' is-active' : ''}`,
    }, 'This draft (temporary)');
    const defaultBtn = el('button', {
      type: 'button',
      id: 'smScopeDefaultBtn',
      class: `sm-scope-btn${state.scope === 'shop_default' ? ' is-active' : ''}`,
    }, 'Shop default (saved)');
    draftBtn.addEventListener('click', () => {
      state.scope = 'draft';
      renderHomeUI();
    });
    defaultBtn.addEventListener('click', () => {
      state.scope = 'shop_default';
      renderHomeUI();
    });
    scopeToggle.append(draftBtn, defaultBtn);
    scopeBar.appendChild(scopeToggle);

    const activeDraftId = currentDraftId();
    const draftSelect = el('select', {
      id: 'smDraftSlotSelect',
      class: 'sm-select',
      'aria-label': 'Active draft slot',
      style: 'max-width:170px;',
    });
    const draftSlots = ['default', 'draft-2'];
    if (!draftSlots.includes(activeDraftId)) draftSlots.push(activeDraftId);
    draftSlots.forEach((slotId) => {
      const label = slotId === 'default' ? 'Draft 1 (main)' : (slotId === 'draft-2' ? 'Draft 2 (alt)' : `Draft: ${slotId}`);
      const opt = el('option', { value: slotId }, label);
      if (slotId === activeDraftId) opt.selected = true;
      draftSelect.appendChild(opt);
    });
    draftSelect.addEventListener('change', async () => {
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      state.draftId = draftSelect.value || 'default';
      loadDraftOverride();
      await fetchRecommendations(true, { gen: boundGen, expectedOwner: boundOwner, expectedSample: boundSample });
      if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
      renderHomeUI();
    });
    scopeBar.appendChild(draftSelect);

    if (isDraftActive) {
      scopeBar.appendChild(el('span', { class: 'sm-badge sm-badge-draft' }, 'Draft override active'));
    }
    panel.appendChild(scopeBar);

    const showingDraft = state.scope === 'draft';
    const goalVal = showingDraft ? (draft.goal ?? pref.goal ?? '') : (pref.goal ?? '');
    const minVal = showingDraft
      ? (draft.minutes_per_week ?? pref.access?.minutes_per_week ?? 30)
      : (pref.access?.minutes_per_week ?? 30);
    const audienceVal = showingDraft ? (draft.audience ?? pref.audience ?? '') : (pref.audience ?? '');
    const productVal = showingDraft ? (draft.product_name ?? '') : '';
    const destinationVal = showingDraft ? (draft.destination ?? '') : '';

    const destDatalist = el('datalist', { id: 'smDestDatalist' },
      el('option', { value: 'website' }),
      el('option', { value: 'etsy' }),
      el('option', { value: 'instagram' }),
      el('option', { value: 'fineartamerica' }),
      el('option', { value: 'saatchi' })
    );

    const grid = el('div', { class: 'sm-grid-2' },
      el('div', { class: 'sm-field' },
        el('label', { for: 'smCtxGoal' }, 'Goal for right now'),
        el('input', {
          type: 'text',
          id: 'smCtxGoal',
          class: 'sm-input',
          value: goalVal,
          placeholder: 'e.g. Promote autumn gift prints under $45',
        })
      ),
      el('div', { class: 'sm-field' },
        el('label', { for: 'smCtxMinutes' }, 'Time budget (minutes / week)'),
        el('input', {
          type: 'number',
          id: 'smCtxMinutes',
          class: 'sm-input',
          value: String(minVal),
          min: '5',
          max: '600',
        })
      ),
      el('div', { class: 'sm-field' },
        el('label', { for: 'smCtxAudience' }, 'Target buyer'),
        el('input', {
          type: 'text',
          id: 'smCtxAudience',
          class: 'sm-input',
          value: audienceVal,
          placeholder: 'e.g. Gift buyers & nature lovers',
        })
      ),
      el('div', { class: 'sm-field' },
        el('label', { for: 'smCtxProduct' }, 'Featured item / offer (optional)'),
        el('input', {
          type: 'text',
          id: 'smCtxProduct',
          class: 'sm-input',
          value: productVal,
          placeholder: 'e.g. Meadow Mist 8x10 Print',
        })
      ),
      el('div', { class: 'sm-field' },
        el('label', { for: 'smCtxDestination' }, 'Destination / channel (optional)'),
        el('input', {
          type: 'text',
          id: 'smCtxDestination',
          class: 'sm-input',
          list: 'smDestDatalist',
          value: destinationVal,
          placeholder: 'e.g. website, etsy, instagram',
        }),
        destDatalist
      )
    );
    panel.appendChild(grid);

    const actions = el('div', { class: 'sm-btn-row', style: 'margin-top:10px;' });
    const applyDraftBtn = el('button', {
      type: 'button',
      id: 'smApplyDraftBtn',
      class: 'sm-btn',
    }, 'Apply to this draft (0 runs)');
    const saveDefaultBtn = el('button', {
      type: 'button',
      id: 'smSaveDefaultBtn',
      class: 'sm-btn sm-btn-primary',
    }, guestDemo ? 'Save sample preference' : 'Save as shop default');
    actions.append(applyDraftBtn, saveDefaultBtn);

    if (isDraftActive) {
      const clearDraftBtn = el('button', {
        type: 'button',
        id: 'smClearDraftBtn',
        class: 'sm-btn sm-btn-ghost',
      }, 'Clear draft override');
      clearDraftBtn.addEventListener('click', async () => {
        const boundGen = state.activeGeneration;
        const boundOwner = currentOwnerId();
        const boundSample = isSampleMode();
        saveDraftOverride(null);
        await fetchRecommendations(true, { gen: boundGen, expectedOwner: boundOwner, expectedSample: boundSample });
        if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
        renderHomeUI();
      });
      actions.appendChild(clearDraftBtn);
    }

    if (guestDemo) {
      const resetSampleBtn = el('button', {
        type: 'button',
        id: 'smResetSampleBtn',
        class: 'sm-btn sm-btn-ghost',
      }, 'Reset sample');
      resetSampleBtn.addEventListener('click', async () => {
        localStorage.removeItem(guestSampleKey());
        saveDraftOverride(null);
        await loadServerMemory(true);
        toast('Sample demo context reset on this device.');
      });
      actions.appendChild(resetSampleBtn);
    }

    applyDraftBtn.addEventListener('click', async () => {
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      const nextDraft = {
        ...(state.draftOverride || {}),
        active: true,
        goal: document.getElementById('smCtxGoal')?.value?.trim() || '',
        minutes_per_week: Number(document.getElementById('smCtxMinutes')?.value || 30),
        audience: document.getElementById('smCtxAudience')?.value?.trim() || '',
        product_name: document.getElementById('smCtxProduct')?.value?.trim() || '',
        destination: document.getElementById('smCtxDestination')?.value?.trim() || '',
      };
      saveDraftOverride(nextDraft);
      await fetchRecommendations(true, { gen: boundGen, expectedOwner: boundOwner, expectedSample: boundSample });
      if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
      renderHomeUI();
      toast('Applied to this draft only. Your saved shop defaults are unchanged.');
    });

    saveDefaultBtn.addEventListener('click', async () => {
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      const nextGoal = document.getElementById('smCtxGoal')?.value?.trim() || '';
      const nextMinutes = Number(document.getElementById('smCtxMinutes')?.value || 30);
      const nextAudience = document.getElementById('smCtxAudience')?.value?.trim() || '';
      const prevGoal = state.preferences?.goal || '';
      const prevMinutes = Number(state.preferences?.access?.minutes_per_week || 30);
      const prevAudience = state.preferences?.audience || '';
      const nextPrefs = {
        ...(state.preferences || {}),
        goal: nextGoal,
        audience: nextAudience,
        access: { ...(state.preferences?.access || {}), minutes_per_week: nextMinutes },
      };
      const updates = [];
      if (nextGoal && nextGoal !== prevGoal) {
        updates.push({
          id: 'pref-goal',
          key: 'goal',
          label: 'Primary goal',
          value: nextGoal,
          kind: 'goal',
          scope: 'shop_default',
          source: 'user_input',
          confidence: 'confirmed',
          status: 'accepted',
          seller_edited: true,
        });
      }
      if (nextMinutes !== prevMinutes) {
        updates.push({
          id: 'pref-minutes',
          key: 'minutes_per_week',
          label: 'Weekly time budget',
          value: `${nextMinutes} minutes / week`,
          kind: 'preference',
          scope: 'shop_default',
          source: 'user_input',
          confidence: 'confirmed',
          status: 'accepted',
          seller_edited: true,
        });
      }
      if (nextAudience && nextAudience !== prevAudience) {
        updates.push({
          id: 'pref-audience',
          key: 'audience',
          label: 'Target buyers',
          value: nextAudience,
          kind: 'preference',
          scope: 'shop_default',
          source: 'user_input',
          confidence: 'confirmed',
          status: 'accepted',
          seller_edited: true,
        });
      }
      const nextEntries = mergeEntriesList(state.memoryEntries, updates);
      saveDraftOverride(null);
      const saved = await persistToServer({ preferences: nextPrefs, memoryEntries: nextEntries });
      if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
      if (saved.ok) {
        await fetchRecommendations(true, { gen: boundGen, expectedOwner: boundOwner, expectedSample: boundSample });
        if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
        renderHomeUI();
        toast('Saved as your shop default.');
      }
    });

    panel.appendChild(actions);

    renderWatchlistControls();
    renderHomeRecommendations();
  }

  function renderWatchlistControls() {
    const sellerList = document.getElementById('sellerList');
    if (!sellerList || isSampleMode()) return;
    if (!state.competitorEntries || !state.competitorEntries.length) return;

    const items = Array.from(sellerList.querySelectorAll('li'));
    if (!items.length) return;

    items.forEach((li, idx) => {
      // Match competitor entry by URL/name or index
      const text = (li.textContent || '').toLowerCase();
      const comp =
        state.competitorEntries.find(
          (c) => (c.url && text.includes(c.url.replace(/^https?:\/\//, '').toLowerCase())) ||
            (c.name && text.includes(c.name.toLowerCase()))
        ) || state.competitorEntries[idx];
      const existing = li.querySelector('.sm-comp-role-wrap');
      if (existing) {
        // After a reload (a saved analysis updates the note), show the saved note unless the
        // seller is typing in it.
        const input = existing.querySelector('.sm-comp-rationale');
        if (comp && input && document.activeElement !== input) input.value = comp.rationale || comp.reason || '';
        return;
      }
      if (!comp) return;

      const wrap = el('div', { class: 'sm-comp-role-wrap' });
      const roleSelect = el('select', {
        class: 'sm-select sm-comp-role sm-home-comp-role',
        'aria-label': `Watch reason for ${comp.name || comp.url}`,
      });
      Object.entries(ROLE_LABELS).forEach(([val, lbl]) => {
        const opt = el('option', { value: val }, lbl);
        if ((comp.role || 'similar_audience') === val) opt.selected = true;
        roleSelect.appendChild(opt);
      });

      const rationaleInput = el('input', {
        type: 'text',
        class: 'sm-input sm-comp-rationale sm-home-comp-rationale',
        value: comp.rationale || comp.reason || '',
        placeholder: 'Reason for watching...',
        'aria-label': `Rationale for ${comp.name || comp.url}`,
      });

      function onCompUpdate() {
        const compUrl = comp.url || '';
        const compName = comp.name || '';
        const compIdx = idx;
        const boundGen = state.activeGeneration;
        const boundOwner = currentOwnerId();
        const boundSample = isSampleMode();
        const runUpdate = async () => {
          if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
          const nextEntries = Array.isArray(state.competitorEntries) ? [...state.competitorEntries] : [];
          let targetIdx = nextEntries.findIndex(
            (c) => (compUrl && c.url === compUrl) || (compName && c.name === compName)
          );
          if (targetIdx < 0) targetIdx = compIdx;
          const liveComp = nextEntries[targetIdx];
          if (!liveComp) return;
          const nextRole = roleSelect.value;
          const nextRationale = rationaleInput.value.trim();
          nextEntries[targetIdx] = {
            ...liveComp,
            role: nextRole,
            rationale: nextRationale,
            reason: nextRationale || liveComp.reason || '',
          };
          state.competitorEntries = nextEntries;
          await fetchRecommendations(true, {
            gen: boundGen,
            expectedOwner: boundOwner,
            expectedSample: boundSample,
          });
          if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
          if (boundOwner) {
            await persistToServer({ competitorEntries: state.competitorEntries });
          }
          if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
          toast(`Updated watch reason to ${ROLE_LABELS[nextRole]}.`);
        };
        const queued = (state.compUpdateQueue || Promise.resolve()).then(runUpdate, runUpdate);
        state.compUpdateQueue = queued.catch(() => {});
        return queued;
      }

      roleSelect.addEventListener('change', onCompUpdate);
      rationaleInput.addEventListener('change', onCompUpdate);
      wrap.append(el('label', { class: 'sm-field-inline' }, 'Watch role: ', roleSelect), rationaleInput);
      li.appendChild(wrap);
    });
  }

  function createStudioHandoff(rec, fallbackDef = {}) {
    const moveDef = rec?.editor_defaults || fallbackDef || {};
    const ns = ownerNamespace();
    const draftId = currentDraftId();
    const sampleMode = isSampleMode();
    const id = `sm_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const payload = {
      id,
      owner_id: ns,
      workspace_mode: currentWorkspaceMode(),
      draft_id: draftId,
      created_at: new Date().toISOString(),
      recommendation_id: rec?.id || moveDef.recommendation_id || '',
      title: rec?.title || moveDef.recommendation_title || '',
      action: rec?.action || moveDef.recommendation_action || '',
      why_this_fits: rec?.why_this_fits || moveDef.why_this_fits || '',
      // More minutes than the seller has this week: /create says "Heads up", not "Why this fits".
      over_budget: Boolean(rec?.over_budget),
      output_provenance: sampleMode ? 'artist_example' : (moveDef.output_provenance || rec?.output_provenance || 'suggested_starting_approach'),
      output_label: sampleMode ? 'Artist example' : (moveDef.output_label || rec?.output_label || 'Suggested starting approach'),
      organic_first: moveDef.organic_first !== undefined ? Boolean(moveDef.organic_first) : (rec?.organic_first !== undefined ? Boolean(rec.organic_first) : true),
      organic_guidance_note: moveDef.organic_guidance_note || rec?.organic_guidance_note || 'Start with an organic post or story first; only promote if you already have a product and offer ready.',
      unconfirmed_audience: moveDef.unconfirmed_audience || rec?.unconfirmed_audience || '',
      audience_confirmed: Boolean(moveDef.audience_confirmed),
      approved_facts: Array.isArray(moveDef.approved_facts) ? moveDef.approved_facts : [],
      missing_facts: Array.isArray(moveDef.missing_facts) ? moveDef.missing_facts : (Array.isArray(rec?.missing_facts) ? rec.missing_facts : []),
      placement: moveDef.placement || 'feed',
      placement_note: moveDef.placement_note || 'App export preset (not verified Meta policy)',
      channel: rec?.channel || moveDef.channel || '',
      goal: moveDef.goal || rec?.goal || 'story',
      cta: moveDef.cta || rec?.cta || '',
      business_name: moveDef.business_name || state.businessName || '',
      product_name: moveDef.product_name || '',
      destination: moveDef.destination || state.draftOverride?.destination || '',
      destination_url: moveDef.destination_url || moveDef.product_link || rec?.destination_url || '',
      product_link: moveDef.product_link || moveDef.destination_url || rec?.destination_url || '',
      price_claim: moveDef.price_claim || rec?.price_claim || '',
      caption_length: moveDef.caption_length || 'medium',
      tone: moveDef.tone || 'neutral',
      words_to_avoid: Array.isArray(moveDef.words_to_avoid) ? moveDef.words_to_avoid : [],
      minutes_per_week: moveDef.minutes_per_week || null,
      context_summary: moveDef.context_summary || '',
    };
    try {
      const prefix = `muse.sm.handoff.${encodeURIComponent(ns)}.`;
      const existing = [];
      for (let i = 0; i < localStorage.length; i += 1) {
        const k = localStorage.key(i);
        if (k && k.startsWith(prefix)) existing.push(k);
      }
      if (existing.length > 24) {
        existing.slice(0, existing.length - 20).forEach((k) => localStorage.removeItem(k));
      }
      localStorage.setItem(handoffStorageKey(id, ns), JSON.stringify(payload));
    } catch (_) {}
    return id;
  }

  function readActiveStudioHandoff() {
    try {
      const hid = new URLSearchParams(location.search).get('sm_handoff');
      if (!hid) return null;
      const ns = ownerNamespace();
      const raw = localStorage.getItem(handoffStorageKey(hid, ns));
      const payload = safeParse(raw, null);
      if (!payload || payload.owner_id !== ns || payload.workspace_mode !== currentWorkspaceMode()) {
        return null;
      }
      return payload;
    } catch (_) {
      return null;
    }
  }

  function renderHomeRecommendations() {
    const improveSec = document.getElementById('loop-improve');
    if (!improveSec || isSampleMode() || !state.recommendResult) return;
    const recos = state.recommendResult.recommendations || [];

    let banner = document.getElementById('smWhatChangedBanner');
    if (!banner) {
      banner = el('div', { id: 'smWhatChangedBanner', class: 'sm-what-changed', hidden: true, role: 'status' });
      const panel = document.getElementById('smContextPanel');
      if (panel) panel.insertAdjacentElement('afterend', banner);
    }
    if (state.recommendResult.what_changed && recos.length) {
      banner.textContent = state.recommendResult.what_changed;
      banner.hidden = false;
    } else {
      banner.textContent = '';
      banner.hidden = true;
    }

    let missingBanner = document.getElementById('smMissingInfoBanner');
    if (!missingBanner) {
      missingBanner = el('div', { id: 'smMissingInfoBanner', class: 'sm-what-changed', hidden: true, role: 'status' });
      if (banner) banner.insertAdjacentElement('afterend', missingBanner);
    }
    const missingPrompt = state.recommendResult.missing_info_prompt || '';
    if (missingPrompt && (!recos.length || state.recommendResult.all_channels_excluded)) {
      missingBanner.textContent = missingPrompt;
      missingBanner.hidden = false;
    } else {
      missingBanner.textContent = '';
      missingBanner.hidden = true;
    }

    let topCard = document.getElementById('smTopMovePreview');
    if (!topCard) {
      topCard = el('div', { id: 'smTopMovePreview', class: 'sm-card' });
      (missingBanner || banner).insertAdjacentElement('afterend', topCard);
    }

    const listEl = improveSec.querySelector('ol.jr-recos');
    if (!recos.length) {
      topCard.textContent = '';
      topCard.hidden = true;
      topCard.dataset.smTopId = '';
      if (listEl) listEl.textContent = '';
      if (typeof window.museShell?.refreshTriage === 'function') {
        window.museShell.refreshTriage();
      }
      return;
    }

    const top = recos[0];
    topCard.hidden = false;
    topCard.dataset.smTopId = top.id || '';
    topCard.textContent = '';
    const openImproveBtn = el('button', {
      type: 'button',
      id: 'smShowImproveTabBtn',
      class: 'sm-btn',
    }, `See all ${recos.length} ranked moves`);
    openImproveBtn.addEventListener('click', () => {
      if (typeof window.museShell?.showStage === 'function') {
        window.museShell.showStage('loop-improve', true);
      } else {
        location.hash = '#loop-improve';
      }
    });
    topCard.append(
      el('div', { class: 'sm-card-header' },
        el('div', {},
          el('span', { class: 'sm-badge sm-badge-goal' }, 'Top next move right now'),
          el('div', { style: 'font-weight:700;margin-top:4px;' }, `${top.title} · about ${top.estimated_minutes || 15} minutes`)
        ),
        openImproveBtn
      ),
      el('div', { style: 'font-size:0.88rem;margin-bottom:6px;' }, top.action || ''),
      el('div', { class: 'sm-why-line' }, `${whyLabel(top)}: ${top.why_this_fits || ''}`)
    );

    if (!listEl) return;
    listEl.textContent = '';

    const def = state.recommendResult.editor_defaults || {};
    const draftId = currentDraftId();
    recos.slice(0, 5).forEach((rec) => {
      const handoffId = createStudioHandoff(rec, def);
      const qs = new URLSearchParams();
      qs.set('sm_handoff', handoffId);
      qs.set('draft', draftId);
      if (isSampleMode()) qs.set('workspace', 'sample');

      const usedChips = el('div', { class: 'sm-used-chips' }, el('span', { style: 'font-weight:600;' }, 'Used from memory:'));
      if (rec.used_entries && rec.used_entries.length) {
        rec.used_entries.forEach((u) => {
          const chip = el('span', { class: 'sm-used-chip' },
            `${u.label}: ${u.value}`,
            el('button', {
              type: 'button',
              title: 'Ignore this entry for the current draft only',
              'aria-label': `Ignore ${u.label} for this draft`,
            }, 'Ignore for draft')
          );
          chip.querySelector('button')?.addEventListener('click', async () => {
            const boundGen = state.activeGeneration;
            const boundOwner = currentOwnerId();
            const boundSample = isSampleMode();
            const prevDraft = state.draftOverride || {};
            const existingIgnored = Array.isArray(prevDraft.ignore_entry_ids)
              ? prevDraft.ignore_entry_ids
              : (Array.isArray(prevDraft.ignored_entry_ids) ? prevDraft.ignored_entry_ids : []);
            const curIgnored = new Set(existingIgnored);
            curIgnored.add(u.id);
            const nextDraft = { ...prevDraft, active: true, ignore_entry_ids: Array.from(curIgnored) };
            delete nextDraft.ignored_entry_ids;
            saveDraftOverride(nextDraft);
            await fetchRecommendations(true, {
              gen: boundGen,
              expectedOwner: boundOwner,
              expectedSample: boundSample,
            });
            if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
            renderHomeUI();
            toast(`Ignored "${u.label}" for this draft only.`);
          });
          usedChips.appendChild(chip);
        });
      } else {
        usedChips.appendChild(el('span', { class: 'sm-sub', style: 'margin:0;' }, 'Your saved shop defaults'));
      }

      const provenanceLabel = isSampleMode()
        ? 'Artist example'
        : (rec.output_label || rec.editor_defaults?.output_label || 'Suggested starting approach');
      const organicNote = rec.organic_guidance_note || rec.editor_defaults?.organic_guidance_note || '';
      const missingFacts = Array.isArray(rec.missing_facts)
        ? rec.missing_facts
        : (Array.isArray(rec.editor_defaults?.missing_facts) ? rec.editor_defaults.missing_facts : []);

      const metaBox = el('div', { class: 'sm-reco-meta' },
        el('div', { style: 'margin-bottom:4px;' },
          el('span', {
            class: 'sm-chip',
            'data-sm-provenance': isSampleMode() ? 'artist_example' : (rec.output_provenance || 'suggested_starting_approach'),
          }, provenanceLabel)
        ),
        el('div', { class: 'sm-why-line' }, `${whyLabel(rec)}: ${rec.why_this_fits || ''}`),
        organicNote ? el('div', { class: 'sm-why-line' }, organicNote) : null,
        missingFacts.length ? el('div', { class: 'sm-why-line', 'data-sm-missing-facts': 'true' }, `Missing facts: ${missingFacts.join(' · ')}`) : null,
        usedChips
      );

      const makeAdLink = el('a', {
        href: `/create?${qs.toString()}`,
        class: 'sm-btn sm-btn-primary',
        style: 'text-decoration:none;',
      }, 'Make ad');
      const draftPostLink = el('a', {
        href: `/today?${qs.toString()}`,
        class: 'sm-btn',
        style: 'text-decoration:none;',
      }, 'Draft daily post');
      const refreshHandoffHref = () => {
        const freshId = createStudioHandoff(rec, def);
        const nextQs = new URLSearchParams({ sm_handoff: freshId, draft: currentDraftId() }).toString();
        makeAdLink.href = `/create?${nextQs}`;
        draftPostLink.href = `/today?${nextQs}`;
      };
      makeAdLink.addEventListener('click', refreshHandoffHref);
      draftPostLink.addEventListener('click', refreshHandoffHref);

      const li = el('li', { 'data-sm-reco-id': rec.id },
        el('div', { style: 'font-weight:700;' }, `${rec.title} · about ${rec.estimated_minutes || 15} minutes`),
        el('div', { style: 'margin-top:4px;font-size:0.9rem;' }, rec.action || ''),
        el('div', { class: 'sm-btn-row', style: 'margin-top:6px;' }, makeAdLink, draftPostLink),
        metaBox
      );
      listEl.appendChild(li);
    });

    if (typeof window.museShell?.refreshTriage === 'function') {
      window.museShell.refreshTriage();
    }
  }

  async function handleSuggestionDecision(suggestionId, decision) {
    const uid = currentOwnerId();
    const boundGen = state.activeGeneration;
    const boundSample = isSampleMode();
    if (!uid) return;
    const res = await apiJson(`/api/v1/seller-memory/suggestions/${encodeURIComponent(suggestionId)}/respond`, {
      method: 'POST',
      headers: { 'X-Muse-Owner': uid },
      body: JSON.stringify({ decision, expected_owner: uid }),
    });
    if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
    if (res.ok && res.data) {
      state.version = Number(res.data.version || state.version);
      state.preferences = res.data.preferences || state.preferences;
      state.voiceProfile = res.data.voice_profile || state.voiceProfile;
      state.memoryEntries = res.data.memory_entries || state.memoryEntries;
      state.suggestedUpdates = res.data.suggested_updates || [];
      await fetchRecommendations(true, { gen: boundGen, expectedOwner: uid, expectedSample: boundSample });
      if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
      renderHomeUI();
      if (document.getElementById('smMemoryModalBackdrop')?.hidden === false) {
        renderMemoryModalBody();
      }
      toast(decision === 'approve' ? 'Suggestion approved and saved to your profile.' : 'Suggestion dismissed.');
    }
  }

  // --- "What Muse Remembers" Modal ---
  let modalBodyEl = null;
  function ensureMemoryModal() {
    let backdrop = document.getElementById('smMemoryModalBackdrop');
    if (backdrop) return backdrop;
    backdrop = el('div', {
      id: 'smMemoryModalBackdrop',
      class: 'sm-modal-backdrop',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'smMemoryModalTitle',
      hidden: true,
    });
    const modal = el('div', { class: 'sm-modal' });
    const header = el('div', { class: 'sm-card-header' },
      el('h2', { id: 'smMemoryModalTitle', class: 'sm-card-title' }, 'What Muse remembers'),
      el('button', { type: 'button', id: 'smCloseMemoryModalBtn', class: 'sm-btn' }, 'Close')
    );
    modalBodyEl = el('div', { id: 'smMemoryModalBody' });
    modal.append(header, modalBodyEl);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);

    backdrop.querySelector('#smCloseMemoryModalBtn')?.addEventListener('click', () => {
      backdrop.hidden = true;
    });
    backdrop.addEventListener('click', (ev) => {
      if (ev.target === backdrop) backdrop.hidden = true;
    });
    return backdrop;
  }

  const BUSINESS_TYPE_LABELS = { products: 'Products', services: 'Services', both: 'Products and services' };
  const SETUP_CHANNEL_LABELS = {
    linkedin: 'LinkedIn', youtube: 'YouTube', tiktok: 'TikTok', x: 'X', instagram: 'Instagram',
    facebook: 'Facebook', website: 'Website', email: 'Email', pinterest: 'Pinterest',
  };

  function safeYouTubeWatchUrl(video) {
    const vid = video && typeof video.video_id === 'string' ? video.video_id.trim() : '';
    if (!/^[A-Za-z0-9_-]{11}$/.test(vid)) return '';
    return `https://www.youtube.com/watch?v=${vid}`;
  }

  function renderYouTubeSourceBlock(parent) {
    if (isSampleMode() || !state.authenticated) return;
    const savedYoutube = state.contentSources && typeof state.contentSources.youtube === 'object'
      ? state.contentSources.youtube
      : null;
    const savedVideos = (savedYoutube && Array.isArray(savedYoutube.videos) ? savedYoutube.videos : [])
      .filter((v) => Boolean(safeYouTubeWatchUrl(v)));

    const wrap = el('div', {
      id: 'smYouTubeSourceBlock',
      class: 'sm-youtube-source',
      style: 'margin-top:10px;padding-top:10px;border-top:1px solid var(--border,#e5e1d8);max-width:100%;box-sizing:border-box;',
    });
    wrap.appendChild(el('div', {
      style: 'font-weight:600;font-size:0.86rem;margin:0 0 4px;',
    }, 'Your YouTube videos'));
    wrap.appendChild(el('p', {
      class: 'sm-sub',
      style: 'margin:0 0 6px;',
    }, state.youtubeHandle
      ? `Muse reads the title of each video you paste. Paste links from your channel (${state.youtubeHandle}).`
      : 'Muse reads the title of each video you paste.'));

    if (savedVideos.length) {
      const ul = el('ul', {
        id: 'smYouTubeVideoList',
        style: 'margin:0 0 8px;padding-left:18px;font-size:0.84rem;display:grid;gap:4px;',
      });
      savedVideos.forEach((video) => {
        const watchUrl = safeYouTubeWatchUrl(video);
        if (!watchUrl) return;
        const li = el('li', { style: 'overflow-wrap:anywhere;' });
        li.appendChild(el('a', {
          href: watchUrl,
          target: '_blank',
          rel: 'noopener noreferrer',
          class: 'sm-link',
        }, String(video.title || 'Untitled video')));
        if (video.author_name) {
          li.appendChild(el('span', { class: 'sm-sub' }, ` · ${String(video.author_name)}`));
        }
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
    }

    const label = el('label', {
      for: 'smYouTubeLinksInput',
      style: 'display:block;font-size:0.82rem;font-weight:600;margin:0 0 4px;',
    }, 'Paste links to your videos (one per line, up to 5)');
    const textarea = el('textarea', {
      id: 'smYouTubeLinksInput',
      class: 'sm-memory-input',
      rows: '3',
      placeholder: 'https://www.youtube.com/watch?v=...\nhttps://youtu.be/...',
      'aria-label': 'Paste links to your videos (one per line, up to 5)',
      style: 'width:100%;max-width:100%;box-sizing:border-box;resize:vertical;font-family:inherit;',
    });
    textarea.value = savedVideos.map((v) => safeYouTubeWatchUrl(v)).filter(Boolean).join('\n');

    const actions = el('div', { style: 'display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;' });
    const saveBtn = el('button', {
      type: 'button',
      id: 'smYouTubeSaveBtn',
      class: 'sm-btn',
    }, 'Save videos (free)');
    const removeBtn = savedVideos.length
      ? el('button', { type: 'button', id: 'smYouTubeRemoveBtn', class: 'sm-btn' }, 'Remove')
      : null;

    const statusEl = el('div', {
      id: 'smYouTubeStatus',
      class: 'sm-sub',
      role: 'status',
      'aria-live': 'polite',
      style: 'margin-top:6px;overflow-wrap:anywhere;',
    });

    async function runYouTubeAction(payload, controls) {
      const boundGen = state.activeGeneration;
      const boundOwner = currentOwnerId();
      const boundSample = isSampleMode();
      controls.forEach((c) => { if (c) c.disabled = true; });
      statusEl.textContent = payload.remove ? 'Removing YouTube videos…' : 'Reading video titles…';
      try {
        const res = await apiJson('/api/v1/seller-memory/sources/youtube', {
          method: 'POST',
          body: JSON.stringify({
            ...payload,
            expected_version: state.version,
            expected_owner: boundOwner,
          }),
        });
        if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
        if (!res.ok) {
          statusEl.textContent = (res.data && res.data.detail)
            ? String(res.data.detail)
            : 'Could not read those video links right now.';
          controls.forEach((c) => { if (c) c.disabled = false; });
          if (res.status === 409) {
            await loadServerMemory(true);
            if (currentOwnerId() === boundOwner && isSampleMode() === boundSample) renderMemoryModalBody();
          }
          return;
        }
        await loadServerMemory(true);
        if (currentOwnerId() === boundOwner && isSampleMode() === boundSample) renderMemoryModalBody();
      } catch (_err) {
        if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
        statusEl.textContent = 'Could not reach Muse right now. Try again shortly.';
        controls.forEach((c) => { if (c) c.disabled = false; });
      }
    }

    const controls = [saveBtn, removeBtn, textarea];
    saveBtn.addEventListener('click', () => {
      const urls = textarea.value
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      if (!urls.length) {
        statusEl.textContent = 'Paste at least one YouTube video link.';
        return;
      }
      runYouTubeAction({ urls }, controls);
    });
    actions.appendChild(saveBtn);
    if (removeBtn) {
      removeBtn.addEventListener('click', () => runYouTubeAction({ remove: true }, controls));
      actions.appendChild(removeBtn);
    }

    wrap.append(label, textarea, actions, statusEl);
    parent.appendChild(wrap);
  }

  // What setup told Muse, shown first so "What Muse remembers" is never empty for a seller who
  // finished setup. Read-only here; setup is where it changes (saving uses no runs).
  function renderSetupFacts() {
    if (isSampleMode() || !state.authenticated) return;
    const pref = state.preferences || {};
    const minutes = Number(pref.access?.minutes_per_week) || 0;
    const channels = (Array.isArray(pref.access?.channels) ? pref.access.channels : [])
      .map((c) => SETUP_CHANNEL_LABELS[String(c).toLowerCase()] || String(c))
      .filter(Boolean);
    const comps = (state.competitorEntries || []).filter((c) => c && c.selected !== false);
    const rows = [
      ['Business', state.businessName],
      ['What you offer', BUSINESS_TYPE_LABELS[state.businessType] || ''],
      ['Goal', String(pref.goal || '').trim()],
      ['Time for marketing', minutes ? `${minutes} minutes a week` : ''],
      ['Channels', channels.join(', ')],
      ['Competitors you watch', comps.map((c) => c.name || c.url).join(', ')],
    ].filter(([, value]) => value);
    const section = el('div', { id: 'smSetupFacts', class: 'sm-setup-facts' });
    section.appendChild(el('h3', { style: 'font-size:0.9rem;margin:4px 0 6px;' }, 'From your setup'));
    if (rows.length) {
      const list = el('dl', { class: 'sm-setup-list', style: 'display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:0 0 6px;font-size:0.86rem;' });
      rows.forEach(([label, value]) => {
        list.append(el('dt', { style: 'color:var(--muted,#6b6b6b);' }, label), el('dd', { style: 'margin:0;overflow-wrap:anywhere;' }, value));
      });
      section.appendChild(list);
      section.appendChild(el('a', { href: '/welcome', class: 'sm-link', id: 'smEditSetupLink' }, 'Change these in setup →'));
    }
    renderYouTubeSourceBlock(section);
    modalBodyEl.appendChild(section);
  }

  function renderMemoryModalBody() {
    if (!modalBodyEl) return;
    modalBodyEl.textContent = '';
    renderSetupFacts();

    const entries = (state.memoryEntries || []).filter((e) => e.status !== 'dismissed');
    const groups = [
      { key: 'observation', title: 'Observed facts (from your pages)' },
      { key: 'interpretation', title: 'Interpretations (tentative guesses)' },
      { key: 'pref_goal', title: 'Preferences, goals & notes' },
    ];

    groups.forEach((grp) => {
      const items = entries.filter((e) =>
        grp.key === 'pref_goal' ? (e.kind === 'preference' || e.kind === 'goal') : e.kind === grp.key
      );
      modalBodyEl.appendChild(el('h3', { style: 'font-size:0.9rem;margin:12px 0 6px;' }, grp.title));
      if (!items.length) {
        modalBodyEl.appendChild(el('p', { class: 'sm-sub' }, 'None saved in this section yet.'));
        return;
      }
      const list = el('div', { class: 'sm-memory-list' });
      items.forEach((entry) => {
        const row = el('div', { class: 'sm-memory-row', 'data-modal-entry-id': entry.id },
          el('div', { class: 'sm-memory-row-top' },
            el('strong', {}, entry.label || entry.key),
            el('span', { class: `sm-badge sm-badge-${entry.kind || 'preference'}` }, KIND_LABELS[entry.kind] || 'Preference')
          )
        );
        const savedValEl = el('div', { class: 'sm-sub', style: 'margin:2px 0 6px;color:var(--ink,#222);overflow-wrap:anywhere;' }, entry.value || '');
        const inp = el('input', { type: 'text', class: 'sm-memory-input', value: entry.value || '', 'aria-label': `Edit ${entry.label || entry.key}` });
        const meta = el('div', { class: 'sm-memory-meta' });
        if (entry.source) meta.appendChild(el('span', {}, SOURCE_LABELS[entry.source] || entry.source));
        if (entry.source_url) {
          const validatedUrl = safeHttpUrl(entry.source_url);
          meta.appendChild(
            validatedUrl
              ? el('a', { href: validatedUrl, target: '_blank', rel: 'noopener noreferrer' }, validatedUrl)
              : el('span', {}, `Source: ${String(entry.source_url)}`)
          );
        }
        if (entry.scan_date) meta.appendChild(el('span', {}, `Scan date: ${entry.scan_date}`));
        if (entry.uncertainty) meta.appendChild(el('span', {}, entry.uncertainty));

        const saveBtn = el('button', { type: 'button', class: 'sm-btn sm-btn-primary' }, 'Save edit');
        saveBtn.addEventListener('click', async () => {
          const boundGen = state.activeGeneration;
          const boundOwner = currentOwnerId();
          const boundSample = isSampleMode();
          entry.value = inp.value.trim();
          entry.seller_edited = true;
          entry.confidence = 'confirmed';
          entry.status = 'accepted';
          const ok = await persistToServer({ memoryEntries: state.memoryEntries });
          if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
          if (ok.ok) {
            await fetchRecommendations(true, {
              gen: boundGen,
              expectedOwner: boundOwner,
              expectedSample: boundSample,
            });
            if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
            renderHomeUI();
            renderMemoryModalBody();
            toast('Updated saved memory.');
          }
        });

        const forgetBtn = el('button', {
          type: 'button',
          class: 'sm-btn sm-btn-danger',
          'data-forget-entry': entry.id,
        }, 'Forget');
        forgetBtn.addEventListener('click', async () => {
          const boundGen = state.activeGeneration;
          const uid = currentOwnerId();
          const boundSample = isSampleMode();
          if (uid) {
            const delRes = await apiJson(`/api/v1/seller-memory/entries/${encodeURIComponent(entry.id)}`, {
              method: 'DELETE',
              headers: { 'X-Muse-Owner': uid },
            });
            if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
            if (delRes.ok && delRes.data) {
              state.version = Number(delRes.data.version || state.version);
              state.preferences = delRes.data.preferences || state.preferences;
              state.voiceProfile = delRes.data.voice_profile || state.voiceProfile;
              state.memoryEntries = delRes.data.memory_entries || [];
            } else {
              // Entry may only exist locally
              state.memoryEntries = state.memoryEntries.filter((x) => x.id !== entry.id);
              await persistToServer({ memoryEntries: state.memoryEntries });
            }
          } else {
            state.memoryEntries = state.memoryEntries.filter((x) => x.id !== entry.id);
          }
          if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
          await fetchRecommendations(true, { gen: boundGen, expectedOwner: uid, expectedSample: boundSample });
          if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
          renderHomeUI();
          renderMemoryModalBody();
          toast(`Forgot "${entry.label || entry.key}".`);
        });

        row.append(savedValEl, inp, meta, el('div', { class: 'sm-btn-row' }, saveBtn, forgetBtn));
        list.appendChild(row);
      });
      modalBodyEl.appendChild(list);
    });

    // Add free-text / voice note inside modal too
    const addWidget = buildVoiceAndNoteWidget({
      existingEntriesFn: () => state.memoryEntries,
      onAcceptEntries: async (accepted) => {
        const boundGen = state.activeGeneration;
        const boundOwner = currentOwnerId();
        const boundSample = isSampleMode();
        const nextEntries = mergeEntriesList(state.memoryEntries, accepted);
        const ok = await persistToServer({ memoryEntries: nextEntries });
        if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
        if (ok.ok) {
          await fetchRecommendations(true, {
            gen: boundGen,
            expectedOwner: boundOwner,
            expectedSample: boundSample,
          });
          if (!isCurrentRequestContext(boundGen, boundOwner, boundSample)) return;
          renderHomeUI();
          renderMemoryModalBody();
          toast(`Added ${accepted.length} item(s) to saved memory.`);
        }
      },
    });
    modalBodyEl.appendChild(addWidget);
  }

  function openMemoryModal() {
    const backdrop = ensureMemoryModal();
    renderMemoryModalBody();
    const sampleVoiceBtn = document.getElementById('smUseVoiceFixtureBtn');
    if (sampleVoiceBtn) sampleVoiceBtn.style.display = isSampleMode() ? '' : 'none';
    backdrop.hidden = false;
  }

  // --- 409 Conflict Resolution Modal ---
  function openConflictModal() {
    const c = state.conflictPending;
    if (!c) return;
    let backdrop = document.getElementById('smConflictModalBackdrop');
    if (!backdrop) {
      backdrop = el('div', {
        id: 'smConflictModalBackdrop',
        class: 'sm-modal-backdrop',
        role: 'dialog',
        'aria-modal': 'true',
        hidden: true,
      });
      document.body.appendChild(backdrop);
    }
    backdrop.textContent = '';
    const localGoal = c.local.preferences?.goal || '(unchanged)';
    const localMins = c.local.preferences?.access?.minutes_per_week ?? '—';
    const srvGoal = c.server.preferences?.goal || '(none)';
    const srvMins = c.server.preferences?.access?.minutes_per_week ?? '—';

    const keepBtn = el('button', { type: 'button', id: 'smConflictKeepMineBtn', class: 'sm-btn sm-btn-primary' }, 'Keep my changes');
    const useSrvBtn = el('button', { type: 'button', id: 'smConflictUseSavedBtn', class: 'sm-btn' }, 'Use saved elsewhere');
    const mergeBtn = el('button', { type: 'button', id: 'smConflictMergeBtn', class: 'sm-btn' }, 'Merge both edits');

    keepBtn.addEventListener('click', async () => {
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) {
        state.conflictPending = null;
        backdrop.hidden = true;
        return;
      }
      const ok = await persistToServer({
        preferences: c.local.preferences,
        voiceProfile: c.local.voiceProfile,
        memoryEntries: c.local.memoryEntries,
        competitorEntries: c.local.competitorEntries,
        forceVersion: c.server.version,
      });
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) return;
      if (ok.ok) {
        state.conflictPending = null;
        backdrop.hidden = true;
        await fetchRecommendations(true, { gen: c.gen, expectedOwner: c.ownerId, expectedSample: false });
        if (!isCurrentRequestContext(c.gen, c.ownerId, false)) return;
        renderHomeUI();
        toast('Kept your edits.');
      }
    });

    useSrvBtn.addEventListener('click', async () => {
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) {
        state.conflictPending = null;
        backdrop.hidden = true;
        return;
      }
      state.version = c.server.version;
      state.preferences = c.server.preferences;
      state.voiceProfile = c.server.voiceProfile;
      state.memoryEntries = c.server.memoryEntries;
      state.competitorEntries = c.server.competitorEntries;
      state.serverBaseline = cloneDeep({
        preferences: state.preferences,
        voiceProfile: state.voiceProfile,
        memoryEntries: state.memoryEntries,
        competitorEntries: state.competitorEntries,
      });
      state.conflictPending = null;
      backdrop.hidden = true;
      await fetchRecommendations(true, { gen: c.gen, expectedOwner: c.ownerId, expectedSample: false });
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) return;
      renderHomeUI();
      toast('Loaded version saved elsewhere.');
    });

    mergeBtn.addEventListener('click', async () => {
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) {
        state.conflictPending = null;
        backdrop.hidden = true;
        return;
      }
      const base = c.base || {};
      const mergedEntries = threeWayMergeEntries(
        base.memoryEntries || [],
        c.server.memoryEntries || [],
        c.local.memoryEntries || []
      );
      const mergedPrefs = threeWayMerge(
        base.preferences || {},
        c.server.preferences || {},
        c.local.preferences || {}
      );
      const mergedVoice = threeWayMerge(
        base.voiceProfile || {},
        c.server.voiceProfile || {},
        c.local.voiceProfile || {}
      );
      const mergedComps = mergeCompetitorEntries(
        base.competitorEntries || [],
        c.server.competitorEntries || [],
        c.local.competitorEntries || []
      );
      const alignedEntries = mergedEntries.map((entry) => {
        if (!entry || (entry.scope || 'shop_default') !== 'shop_default' || entry.status === 'dismissed') {
          return entry;
        }
        if (entry.key === 'goal' && mergedPrefs.goal && mergedPrefs.goal !== c.local.preferences?.goal) {
          return { ...entry, value: mergedPrefs.goal };
        }
        if (
          entry.key === 'audience' &&
          mergedPrefs.audience &&
          mergedPrefs.audience !== c.local.preferences?.audience
        ) {
          return { ...entry, value: mergedPrefs.audience };
        }
        const mergedMins = mergedPrefs.access?.minutes_per_week;
        if (
          entry.key === 'minutes_per_week' &&
          mergedMins &&
          mergedMins !== c.local.preferences?.access?.minutes_per_week
        ) {
          return { ...entry, value: `${mergedMins} minutes / week` };
        }
        return entry;
      });
      const ok = await persistToServer({
        preferences: mergedPrefs,
        voiceProfile: mergedVoice,
        memoryEntries: alignedEntries,
        competitorEntries: mergedComps,
        forceVersion: c.server.version,
      });
      if (!isCurrentRequestContext(c.gen, c.ownerId, false)) return;
      if (ok.ok) {
        state.conflictPending = null;
        backdrop.hidden = true;
        await fetchRecommendations(true, { gen: c.gen, expectedOwner: c.ownerId, expectedSample: false });
        if (!isCurrentRequestContext(c.gen, c.ownerId, false)) return;
        renderHomeUI();
        toast('Merged both versions.');
      }
    });

    const modal = el('div', { class: 'sm-modal' },
      el('h2', { class: 'sm-card-title' }, 'Your profile changed in another browser or tab'),
      el('p', { class: 'sm-sub' }, 'Neither edit was overwritten. Choose how to combine them:'),
      el('div', { class: 'sm-conflict-grid' },
        el('div', { class: 'sm-conflict-col' },
          el('strong', {}, 'Your unsaved edits'),
          el('div', {}, `Goal: ${localGoal}`),
          el('div', {}, `Time each week: ${localMins} minutes`),
          el('div', {}, `Items: ${(c.local.memoryEntries || []).length}`)
        ),
        el('div', { class: 'sm-conflict-col' },
          el('strong', {}, 'Saved in other session'),
          el('div', {}, `Goal: ${srvGoal}`),
          el('div', {}, `Time each week: ${srvMins} minutes`),
          el('div', {}, `Items: ${(c.server.memoryEntries || []).length}`)
        )
      ),
      el('div', { class: 'sm-btn-row' }, keepBtn, useSrvBtn, mergeBtn)
    );
    backdrop.appendChild(modal);
    backdrop.hidden = false;
  }

  // --- /today & /create Studio Integration ---
  function resolveActiveStudioContext() {
    const handoff = readActiveStudioHandoff();
    const recos = state.recommendResult?.recommendations || [];
    const matchedRec = handoff?.recommendation_id
      ? recos.find((r) => r.id === handoff.recommendation_id)
      : null;
    const selectedRec = matchedRec || (handoff ? handoff : recos[0]) || null;
    const def =
      matchedRec?.editor_defaults ||
      (handoff
        ? {
            recommendation_id: handoff.recommendation_id,
            recommendation_title: handoff.title,
            recommendation_action: handoff.action,
            business_name: handoff.business_name,
            product_name: handoff.product_name,
            destination: handoff.destination,
            destination_url: handoff.destination_url || handoff.product_link || '',
            product_link: handoff.product_link || handoff.destination_url || '',
            channel: handoff.channel,
            goal: handoff.goal,
            cta: handoff.cta,
            caption_length: handoff.caption_length,
            tone: handoff.tone,
            words_to_avoid: handoff.words_to_avoid,
            price_claim: handoff.price_claim,
            minutes_per_week: handoff.minutes_per_week,
            context_summary: handoff.context_summary,
            why_this_fits: handoff.why_this_fits,
          }
        : state.recommendResult?.editor_defaults || {});
    return { handoff, selectedRec, def };
  }

  // The ranker's editor defaults carry goal keys; the chip shows words a seller would use.
  const GOAL_LABELS = {
    story: ['Tell the story behind it', 'Share what you do'],
    gift: ['Show it as a gift', 'Show a client result'],
    visits: ['Bring people to your website', 'Bring people to your website'],
    visit: ['Bring people to your website', 'Bring people to your website'],
  };
  function goalLabel(goal) {
    const words = GOAL_LABELS[String(goal || '')];
    if (!words) return String(goal || 'One good post');
    return words[state.businessType === 'services' ? 1 : 0];
  }

  function renderStudioBar() {
    const isToday = location.pathname.startsWith('/today');
    const isCreate = location.pathname.startsWith('/create');
    if (!isToday && !isCreate) return;
    if (isSampleMode() && !state.draftOverride?.active) return;

    const { handoff, selectedRec, def } = resolveActiveStudioContext();
    if (!handoff && !state.recommendResult && !state.preferences?.goal) return;

    const main = document.querySelector('main') || document.body;
    let bar = document.getElementById('smStudioContextBar');
    if (!bar) {
      bar = el('section', { id: 'smStudioContextBar', class: 'sm-card', style: 'margin:10px auto;max-width:1120px;' });
      main.prepend(bar);
    }
    bar.hidden = false;
    bar.dataset.smSelectedRecoId = selectedRec?.recommendation_id || selectedRec?.id || '';

    const badges = el('div', { class: 'sm-badge-row' },
      el('span', { class: 'sm-badge sm-badge-goal' }, `Goal: ${goalLabel(state.draftOverride?.goal || def.goal || state.preferences?.goal)}`)
    );
    if (selectedRec?.title) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-preference' }, `Selected move: ${selectedRec.title}`));
    }
    if (def.minutes_per_week) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-preference' }, `Up to ${def.minutes_per_week} minutes a week`));
    }
    if (def.price_claim) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-observation' }, `Observed price: ${def.price_claim}`));
    }
    if (def.words_to_avoid?.length) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-warn' }, `Avoid: ${def.words_to_avoid.join(', ')}`));
    }
    if (selectedRec?.competitor_used) {
      badges.appendChild(el('span', { class: 'sm-badge' }, `Compare: ${selectedRec.competitor_used} (${ROLE_LABELS[selectedRec.competitor_role] || selectedRec.competitor_role})`));
    }

    const memBtn = el('button', { type: 'button', class: 'sm-btn' }, 'What Muse remembers');
    memBtn.addEventListener('click', openMemoryModal);
    const applyBtn = el('button', { type: 'button', id: 'smStudioApplyBtn', class: 'sm-btn sm-btn-primary' }, 'Use this move in my post');
    applyBtn.addEventListener('click', () => {
      applyEditorDefaults(true);
      toast('Your post now follows this move. Change anything you like.');
    });

    const subtitleWhy = selectedRec?.why_this_fits || def.why_this_fits || '';
    bar.textContent = '';
    bar.append(
      el('div', { class: 'sm-card-header' },
        el('div', {},
          el('strong', {}, def.business_name ? `Your context · ${def.business_name}` : 'Your context'),
          subtitleWhy ? el('div', { class: 'sm-sub', style: 'margin:2px 0 0;' }, `${whyLabel(selectedRec)}: ${subtitleWhy}`) : null
        ),
        el('div', { class: 'sm-btn-row' }, memBtn, applyBtn)
      ),
      badges
    );

    applyEditorDefaults(false);
  }

  function applyEditorDefaults(force) {
    const { handoff, def } = resolveActiveStudioContext();
    if (!def || !Object.keys(def).length) return;
    if (handoff && !force) return;
    const linkUrl = def.destination_url || def.product_link || '';
    const isVideoMove = (def.recommendation_id || '') === 'move-share-video' && Boolean(linkUrl);
    const fields = [
      ['sellerName', def.business_name],
      ['productName', def.product_name],
      ['productLink', linkUrl],
      ['destinationUrl', linkUrl],
      ['productPrice', def.price_claim],
      ['price', def.price_claim],
      ['goal', def.goal],
    ];
    fields.forEach(([id, val]) => {
      const node = document.getElementById(id);
      if (!node || !val) return;
      if (node.dataset.smUserEdited === '1' && !force) return;
      if (!node.dataset.smBound) {
        node.dataset.smBound = '1';
        node.addEventListener('input', () => {
          node.dataset.smUserEdited = '1';
        });
      }
      const isVideoMoveOverride =
        isVideoMove &&
        (id === 'productName' || id === 'productLink' || id === 'destinationUrl') &&
        node.dataset.smUserEdited !== '1';
      if (
        force ||
        isVideoMoveOverride ||
        !node.value ||
        BANNED_SAMPLE_TERMS.some((t) => node.value.toLowerCase().includes(t))
      ) {
        node.value = val;
        node.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  }

  // --- Boot & Event Wiring ---
  function initObservers() {
    const sellerList = document.getElementById('sellerList');
    if (sellerList) {
      const obs = new MutationObserver(() => renderWatchlistControls());
      obs.observe(sellerList, { childList: true });
    }

    const recosList = document.querySelector('#loop-improve ol.jr-recos');
    if (recosList) {
      const recObs = new MutationObserver(() => {
        if (isSampleMode() || !state.recommendResult?.recommendations?.length) return;
        const firstLi = recosList.querySelector('li');
        if (firstLi && !firstLi.hasAttribute('data-sm-reco-id')) {
          renderHomeRecommendations();
        }
      });
      recObs.observe(recosList, { childList: true });
    }

    window.addEventListener('muse:signals-updated', async () => {
      const uid = currentOwnerId();
      const boundGen = state.activeGeneration;
      const boundSample = isSampleMode();
      if (!uid) return;
      const evalRes = await apiJson('/api/v1/seller-memory/suggestions/evaluate', {
        method: 'POST',
        headers: { 'X-Muse-Owner': uid },
      });
      if (!isCurrentRequestContext(boundGen, uid, boundSample)) return;
      if (evalRes.ok && evalRes.data) {
        state.suggestedUpdates = evalRes.data.suggested_updates || [];
        renderHomeUI();
      }
    });

    window.addEventListener('muse:account-change', () => {
      const nextTag = stateTagForCurrent();
      if (state.loadedForOwner !== '__init__' && nextTag !== state.loadedForOwner) {
        clearPrivateMemoryUI();
        loadServerMemory(true);
      } else if (state.loadedForOwner === '__init__') {
        loadServerMemory(false);
      }
    });

    window.addEventListener('muse:workspace-reset', () => {
      clearPrivateMemoryUI();
      loadServerMemory(true);
    });

    window.addEventListener('muse:mode-change', () => {
      if (stateTagForCurrent() !== state.loadedForOwner) {
        clearPrivateMemoryUI();
        loadServerMemory(true);
      }
    });

    window.addEventListener('focus', () => {
      const nextTag = stateTagForCurrent();
      if (state.loadedForOwner !== '__init__' && nextTag !== state.loadedForOwner) {
        clearPrivateMemoryUI();
        loadServerMemory(true);
      }
    });
  }

  // A move longer than this week's minutes leads only when nothing fits (the ranker sets
  // over_budget), so its reason is a heads-up, not "Why this fits".
  function whyLabel(rec) { return rec && rec.over_budget ? 'Heads up' : 'Why this fits'; }

  function start() {
    initOnboardingHooks();
    initObservers();
    if (window.museAccount?.ready) {
      window.museAccount.ready().then(() => loadServerMemory(false)).catch(() => loadServerMemory(false));
      // React cleanly to sign-in / sign-out transitions
      setInterval(() => {
        const nextTag = stateTagForCurrent();
        if (state.loadedForOwner !== '__init__' && nextTag !== state.loadedForOwner) {
          clearPrivateMemoryUI();
          loadServerMemory(true);
        }
      }, 900);
    } else {
      loadServerMemory(false);
    }
  }

  window.museSellerMemory = Object.freeze({
    reload: () => loadServerMemory(true),
    getState: () => ({ ...state }),
    getOnboardingMemoryEntries: () =>
      (state.onboardingEntries || []).filter((e) => e.status !== 'dismissed'),
    openMemoryModal,
    createStudioHandoff,
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
