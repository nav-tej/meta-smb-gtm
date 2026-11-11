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
    preferences: {},
    voiceProfile: {},
    memoryEntries: [],
    competitorEntries: [],
    suggestedUpdates: [],
    dismissSignals: [],
    draftOverride: null,
    scope: 'draft', // 'draft' | 'shop_default'
    recommendResult: null,
    previousTopId: null,
    onboardingEntries: [],
    onboardingScanDiff: [],
    onboardingScanWarnings: [],
    onboardingScanUrl: '',
    onboardingScanDate: '',
    conflictPending: null,
    loadedForOwner: '__init__',
  };

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

  function ownerNamespace() {
    return currentOwnerId() || 'guest';
  }

  function draftStorageKey(ns = ownerNamespace()) {
    return `muse.sm.draft.${ns}`;
  }

  function pendingOnboardingKey(ns = ownerNamespace()) {
    return `muse.sm.pending_onb.${ns}`;
  }

  function guestSampleKey() {
    return 'muse.sm.guest_sample.v1';
  }

  function isSampleMode() {
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
      headers: { ...authHeaders(), ...(options.headers || {}) },
      ...options,
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
    state.version = 0;
    state.businessName = '';
    state.preferences = {};
    state.voiceProfile = {};
    state.memoryEntries = [];
    state.competitorEntries = [];
    state.suggestedUpdates = [];
    state.dismissSignals = [];
    state.draftOverride = null;
    state.recommendResult = null;
    state.previousTopId = null;
    state.conflictPending = null;
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
      if (override) {
        localStorage.setItem(draftStorageKey(), JSON.stringify(override));
      } else {
        localStorage.removeItem(draftStorageKey());
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
    if (!force && state.loadedForOwner === (uid || 'guest')) return;
    if (state.loadedForOwner !== '__init__' && state.loadedForOwner !== (uid || 'guest')) {
      resetInMemoryState();
    }
    state.ownerId = uid;
    state.loadedForOwner = uid || 'guest';
    loadDraftOverride();

    if (!uid) {
      state.authenticated = false;
      if (isSampleMode()) {
        const sample = loadGuestSampleState();
        state.businessName = sample.businessName;
        state.preferences = sample.preferences;
        state.memoryEntries = sample.memoryEntries;
        state.competitorEntries = sample.competitorEntries;
      }
      renderHomeUI();
      renderStudioBar();
      return;
    }

    const res = await apiJson('/api/v1/seller-memory', { method: 'GET' });
    if (res.ok && res.data) {
      state.authenticated = Boolean(res.data.authenticated);
      state.version = Number(res.data.version || 0);
      state.businessName = res.data.business_name || '';
      state.preferences = res.data.preferences || {};
      state.voiceProfile = res.data.voice_profile || {};
      state.memoryEntries = stripSampleContamination(res.data.memory_entries || []);
      state.competitorEntries = res.data.competitor_entries || [];
      state.suggestedUpdates = res.data.suggested_updates || [];
      state.dismissSignals = res.data.dismiss_signals || [];
    }

    // Flush any pending onboarding edits created right before navigation
    const pending = loadPendingOnboarding(uid);
    if (pending && Array.isArray(pending.memory_entries) && pending.memory_entries.length) {
      await syncPendingOnboardingToServer(pending, uid);
    }

    const onStudio = location.pathname.startsWith('/today') || location.pathname.startsWith('/create');
    if (document.getElementById('loop-improve') || onStudio) {
      await fetchRecommendations(false);
    }
    renderHomeUI();
    renderStudioBar();
  }

  async function syncPendingOnboardingToServer(pending, uid) {
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
    const saveRes = await apiJson('/api/v1/seller-memory', {
      method: 'PUT',
      body: JSON.stringify({
        expected_owner: uid,
        expected_version: state.version || null,
        preferences: nextPrefs,
        memory_entries: mergedEntries,
        competitor_entries: nextComps,
      }),
    });
    if (saveRes.ok && saveRes.data) {
      state.version = Number(saveRes.data.version || state.version);
      state.preferences = saveRes.data.preferences || nextPrefs;
      state.memoryEntries = saveRes.data.memory_entries || mergedEntries;
      state.competitorEntries = saveRes.data.competitor_entries || nextComps;
      savePendingOnboarding(null, uid);
    }
  }

  function mergeEntriesList(base, incoming) {
    const byId = new Map();
    (base || []).forEach((e) => {
      if (e && e.id) byId.set(e.id, e);
    });
    (incoming || []).forEach((e) => {
      if (!e || !e.id) return;
      const prev = byId.get(e.id);
      if (prev && prev.seller_edited && !e.seller_edited) {
        return; // Preserve seller edits unless newer entry was also seller-edited
      }
      byId.set(e.id, e);
    });
    return Array.from(byId.values());
  }

  let persistQueue = Promise.resolve();

  function persistToServer(opts = {}) {
    const run = persistQueue.then(() => _persistToServerOnce(opts), () => _persistToServerOnce(opts));
    persistQueue = run.catch(() => {});
    return run;
  }

  async function _persistToServerOnce({
    preferences = state.preferences,
    voiceProfile = state.voiceProfile,
    memoryEntries = state.memoryEntries,
    competitorEntries = state.competitorEntries,
    forceVersion = null,
  } = {}) {
    const uid = currentOwnerId();
    if (!uid) {
      // Guest demo device-local persistence only
      if (isSampleMode()) {
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

    const res = await apiJson('/api/v1/seller-memory', {
      method: 'PUT',
      body: JSON.stringify({
        expected_version: forceVersion !== null ? forceVersion : state.version,
        expected_owner: uid,
        preferences,
        voice_profile: voiceProfile,
        memory_entries: memoryEntries,
        competitor_entries: competitorEntries,
      }),
    });

    if (res.status === 409 && res.data && res.data.server_version !== undefined) {
      state.conflictPending = {
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
      return { ok: true };
    }
    toast(res.data?.detail || `Could not save memory (HTTP ${res.status})`);
    return { ok: false };
  }

  async function fetchRecommendations(showSpinner = true) {
    const activePref = {
      ...(state.preferences || {}),
      memory_entries: state.memoryEntries || [],
    };
    const res = await apiJson('/api/v1/seller-memory/recommend', {
      method: 'POST',
      body: JSON.stringify({
        business_name: state.businessName || deriveSignedInBusinessName() || 'Your Studio',
        product_name: state.draftOverride?.product_name || null,
        preferences: activePref,
        voice_profile: state.voiceProfile || {},
        competitor_entries: state.competitorEntries || [],
        draft_override: state.draftOverride || null,
        dismiss_signals: state.dismissSignals || [],
        previous_top_id: state.previousTopId || null,
      }),
    });
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
        meta.appendChild(
          el('span', {}, 'Source: ', el('a', { href: entry.source_url, target: '_blank', rel: 'noopener' }, entry.source_url))
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
        'Unapproved transcript (edit freely before extracting items — nothing is saved yet):'
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
      voiceStatus.textContent = '';
      const res = await apiJson('/api/v1/seller-memory/interpret', {
        method: 'POST',
        body: JSON.stringify({
          text: text || '',
          source_type: sourceType,
          fixture_id: fixtureId || null,
          existing_entries: existingEntriesFn ? existingEntriesFn() : state.memoryEntries,
        }),
      });
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
            'Observed facts come straight from your pages. Interpretations are tentative hypotheses — edit, confirm, or dismiss any item.'
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
        body: JSON.stringify({
          business_name: detail.businessName || 'Your Shop',
          website_url: detail.primaryUrl || '',
          extra_urls: detail.extraUrls || [],
          existing_entries: state.onboardingEntries,
          snapshot_items: snapshotItems,
        }),
      });
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
        if (!uid) return;
        const pending = loadPendingOnboarding(uid);
        if (!pending) return;
        // Fetch current server version post-/onboarding/build, then save cleanly
        const cur = await apiJson('/api/v1/seller-memory', { method: 'GET' });
        if (cur.ok && cur.data) {
          state.version = Number(cur.data.version || 0);
          state.preferences = cur.data.preferences || {};
          state.memoryEntries = cur.data.memory_entries || [];
          state.competitorEntries = cur.data.competitor_entries || [];
        }
        await syncPendingOnboardingToServer(pending, uid);
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

    const pref = state.preferences || {};
    const draft = state.draftOverride || {};
    const isDraftActive = Boolean(draft && (draft.active || draft.goal || draft.minutes_per_week || draft.context_note || (draft.ignored_entry_ids || []).length));
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

    // Scope switcher: This draft vs Save as shop default
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
        saveDraftOverride(null);
        await fetchRecommendations(true);
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
      const nextDraft = {
        ...(state.draftOverride || {}),
        active: true,
        goal: document.getElementById('smCtxGoal')?.value?.trim() || '',
        minutes_per_week: Number(document.getElementById('smCtxMinutes')?.value || 30),
        audience: document.getElementById('smCtxAudience')?.value?.trim() || '',
        product_name: document.getElementById('smCtxProduct')?.value?.trim() || '',
      };
      saveDraftOverride(nextDraft);
      await fetchRecommendations(true);
      renderHomeUI();
      toast('Applied to this draft only — saved shop defaults unchanged.');
    });

    saveDefaultBtn.addEventListener('click', async () => {
      const nextGoal = document.getElementById('smCtxGoal')?.value?.trim() || '';
      const nextMinutes = Number(document.getElementById('smCtxMinutes')?.value || 30);
      const nextAudience = document.getElementById('smCtxAudience')?.value?.trim() || '';
      const nextPrefs = {
        ...(state.preferences || {}),
        goal: nextGoal,
        audience: nextAudience,
        access: { ...(state.preferences?.access || {}), minutes_per_week: nextMinutes },
      };
      const updates = [];
      if (nextGoal) {
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
      if (nextAudience) {
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
      if (saved.ok) {
        await fetchRecommendations(true);
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
      if (li.querySelector('.sm-comp-role-wrap')) return;
      // Match competitor entry by URL/name or index
      const text = (li.textContent || '').toLowerCase();
      const comp =
        state.competitorEntries.find(
          (c) => (c.url && text.includes(c.url.replace(/^https?:\/\//, '').toLowerCase())) ||
            (c.name && text.includes(c.name.toLowerCase()))
        ) || state.competitorEntries[idx];
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
        const runUpdate = async () => {
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
          await fetchRecommendations(true);
          if (currentOwnerId()) {
            await persistToServer({ competitorEntries: state.competitorEntries });
          }
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

  function renderHomeRecommendations() {
    const improveSec = document.getElementById('loop-improve');
    if (!improveSec || isSampleMode() || !state.recommendResult) return;
    const recos = state.recommendResult.recommendations || [];
    if (!recos.length) return;

    let banner = document.getElementById('smWhatChangedBanner');
    if (!banner) {
      banner = el('div', { id: 'smWhatChangedBanner', class: 'sm-what-changed', hidden: true, role: 'status' });
      const panel = document.getElementById('smContextPanel');
      if (panel) panel.insertAdjacentElement('afterend', banner);
    }
    if (state.recommendResult.what_changed) {
      banner.textContent = state.recommendResult.what_changed;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }

    const top = recos[0];
    let topCard = document.getElementById('smTopMovePreview');
    if (!topCard) {
      topCard = el('div', { id: 'smTopMovePreview', class: 'sm-card' });
      banner.insertAdjacentElement('afterend', topCard);
    }
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
          el('div', { style: 'font-weight:700;margin-top:4px;' }, `${top.title} · ~${top.estimated_minutes || 15} min`)
        ),
        openImproveBtn
      ),
      el('div', { style: 'font-size:0.88rem;margin-bottom:6px;' }, top.action || ''),
      el('div', { class: 'sm-why-line' }, `Why this fits: ${top.why_this_fits || ''}`)
    );

    const listEl = improveSec.querySelector('ol.jr-recos');
    if (!listEl) return;
    listEl.textContent = '';

    const def = state.recommendResult.editor_defaults || {};
    recos.slice(0, 5).forEach((rec) => {
      const qs = new URLSearchParams();
      qs.set('idea', rec.title || '');
      qs.set('from_memory', '1');
      if (def.goal) qs.set('goal', def.goal);
      if (def.business_name) qs.set('seller_name', def.business_name);
      if (def.product_name) qs.set('product_name', def.product_name);

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
            const curIgnored = new Set(state.draftOverride?.ignored_entry_ids || []);
            curIgnored.add(u.id);
            saveDraftOverride({
              ...(state.draftOverride || {}),
              active: true,
              ignored_entry_ids: Array.from(curIgnored),
            });
            await fetchRecommendations(true);
            renderHomeUI();
            toast(`Ignored "${u.label}" for this draft only.`);
          });
          usedChips.appendChild(chip);
        });
      } else {
        usedChips.appendChild(el('span', { class: 'sm-sub', style: 'margin:0;' }, 'Your saved shop defaults'));
      }

      const metaBox = el('div', { class: 'sm-reco-meta' },
        el('div', { class: 'sm-why-line' }, `Why this fits: ${rec.why_this_fits || ''}`),
        usedChips
      );

      const li = el('li', { 'data-sm-reco-id': rec.id },
        el('div', { style: 'font-weight:700;' }, `${rec.title} · ~${rec.estimated_minutes || 15} min`),
        el('div', { style: 'margin-top:4px;font-size:0.9rem;' }, rec.action || ''),
        el('div', { class: 'sm-btn-row', style: 'margin-top:6px;' },
          el('a', { href: `/create?${qs.toString()}`, class: 'sm-btn sm-btn-primary', style: 'text-decoration:none;' }, 'Make ad'),
          el('a', { href: `/today?${qs.toString()}`, class: 'sm-btn', style: 'text-decoration:none;' }, 'Draft daily post')
        ),
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
    if (!uid) return;
    const res = await apiJson(`/api/v1/seller-memory/suggestions/${encodeURIComponent(suggestionId)}/respond`, {
      method: 'POST',
      body: JSON.stringify({ decision, expected_owner: uid }),
    });
    if (res.ok && res.data) {
      state.version = Number(res.data.version || state.version);
      state.preferences = res.data.preferences || state.preferences;
      state.voiceProfile = res.data.voice_profile || state.voiceProfile;
      state.memoryEntries = res.data.memory_entries || state.memoryEntries;
      state.suggestedUpdates = res.data.suggested_updates || [];
      await fetchRecommendations(true);
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

  function renderMemoryModalBody() {
    if (!modalBodyEl) return;
    modalBodyEl.textContent = '';

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
        if (entry.source_url) meta.appendChild(el('a', { href: entry.source_url, target: '_blank', rel: 'noopener' }, entry.source_url));
        if (entry.scan_date) meta.appendChild(el('span', {}, `Scan date: ${entry.scan_date}`));
        if (entry.uncertainty) meta.appendChild(el('span', {}, entry.uncertainty));

        const saveBtn = el('button', { type: 'button', class: 'sm-btn sm-btn-primary' }, 'Save edit');
        saveBtn.addEventListener('click', async () => {
          entry.value = inp.value.trim();
          entry.seller_edited = true;
          entry.confidence = 'confirmed';
          entry.status = 'accepted';
          const ok = await persistToServer({ memoryEntries: state.memoryEntries });
          if (ok.ok) {
            await fetchRecommendations(true);
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
          const uid = currentOwnerId();
          if (uid) {
            const delRes = await apiJson(`/api/v1/seller-memory/entries/${encodeURIComponent(entry.id)}`, {
              method: 'DELETE',
            });
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
          await fetchRecommendations(true);
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
        const nextEntries = mergeEntriesList(state.memoryEntries, accepted);
        const ok = await persistToServer({ memoryEntries: nextEntries });
        if (ok.ok) {
          await fetchRecommendations(true);
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
      const ok = await persistToServer({
        preferences: c.local.preferences,
        voiceProfile: c.local.voiceProfile,
        memoryEntries: c.local.memoryEntries,
        competitorEntries: c.local.competitorEntries,
        forceVersion: c.server.version,
      });
      if (ok.ok) {
        state.conflictPending = null;
        backdrop.hidden = true;
        await fetchRecommendations(true);
        renderHomeUI();
        toast('Kept your edits.');
      }
    });

    useSrvBtn.addEventListener('click', async () => {
      state.version = c.server.version;
      state.preferences = c.server.preferences;
      state.voiceProfile = c.server.voiceProfile;
      state.memoryEntries = c.server.memoryEntries;
      state.competitorEntries = c.server.competitorEntries;
      state.conflictPending = null;
      backdrop.hidden = true;
      await fetchRecommendations(true);
      renderHomeUI();
      toast('Loaded version saved elsewhere.');
    });

    mergeBtn.addEventListener('click', async () => {
      const mergedEntries = mergeEntriesList(c.server.memoryEntries, c.local.memoryEntries);
      const mergedPrefs = {
        ...c.server.preferences,
        ...c.local.preferences,
        access: { ...(c.server.preferences?.access || {}), ...(c.local.preferences?.access || {}) },
      };
      const ok = await persistToServer({
        preferences: mergedPrefs,
        voiceProfile: c.local.voiceProfile,
        memoryEntries: mergedEntries,
        competitorEntries: c.local.competitorEntries?.length ? c.local.competitorEntries : c.server.competitorEntries,
        forceVersion: c.server.version,
      });
      if (ok.ok) {
        state.conflictPending = null;
        backdrop.hidden = true;
        await fetchRecommendations(true);
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
          el('div', {}, `Time/week: ${localMins} min`),
          el('div', {}, `Items: ${(c.local.memoryEntries || []).length}`)
        ),
        el('div', { class: 'sm-conflict-col' },
          el('strong', {}, 'Saved in other session'),
          el('div', {}, `Goal: ${srvGoal}`),
          el('div', {}, `Time/week: ${srvMins} min`),
          el('div', {}, `Items: ${(c.server.memoryEntries || []).length}`)
        )
      ),
      el('div', { class: 'sm-btn-row' }, keepBtn, useSrvBtn, mergeBtn)
    );
    backdrop.appendChild(modal);
    backdrop.hidden = false;
  }

  // --- /today & /create Studio Integration ---
  function renderStudioBar() {
    const isToday = location.pathname.startsWith('/today');
    const isCreate = location.pathname.startsWith('/create');
    if (!isToday && !isCreate) return;
    if (isSampleMode() && !state.draftOverride?.active) return;

    const main = document.querySelector('main') || document.body;
    let bar = document.getElementById('smStudioContextBar');
    if (!bar) {
      bar = el('section', { id: 'smStudioContextBar', class: 'sm-card', style: 'margin:10px auto;max-width:1120px;' });
      main.prepend(bar);
    }

    const def = state.recommendResult?.editor_defaults || {};
    const top = state.recommendResult?.recommendations?.[0];
    const badges = el('div', { class: 'sm-badge-row' },
      el('span', { class: 'sm-badge sm-badge-goal' }, `Goal: ${state.draftOverride?.goal || state.preferences?.goal || def.goal || 'Focus post'}`)
    );
    if (def.minutes_per_week) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-preference' }, `<= ${def.minutes_per_week} min/wk`));
    }
    if (def.price_claim) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-observation' }, `Observed price: ${def.price_claim}`));
    }
    if (def.words_to_avoid?.length) {
      badges.appendChild(el('span', { class: 'sm-badge sm-badge-warn' }, `Avoid: ${def.words_to_avoid.join(', ')}`));
    }
    if (top?.competitor_used) {
      badges.appendChild(el('span', { class: 'sm-badge' }, `Compare: ${top.competitor_used} (${ROLE_LABELS[top.competitor_role] || top.competitor_role})`));
    }

    const memBtn = el('button', { type: 'button', class: 'sm-btn' }, 'What Muse remembers');
    memBtn.addEventListener('click', openMemoryModal);
    const applyBtn = el('button', { type: 'button', id: 'smStudioApplyBtn', class: 'sm-btn sm-btn-primary' }, 'Apply defaults to editor');
    applyBtn.addEventListener('click', () => {
      applyEditorDefaults(true);
      toast('Applied your saved context to empty/default studio fields.');
    });

    bar.textContent = '';
    bar.append(
      el('div', { class: 'sm-card-header' },
        el('div', {},
          el('strong', {}, def.business_name ? `Your context · ${def.business_name}` : 'Your context'),
          top?.why_this_fits ? el('div', { class: 'sm-sub', style: 'margin:2px 0 0;' }, `Why this fits: ${top.why_this_fits}`) : null
        ),
        el('div', { class: 'sm-btn-row' }, memBtn, applyBtn)
      ),
      badges
    );

    applyEditorDefaults(false);
  }

  function applyEditorDefaults(force) {
    const def = state.recommendResult?.editor_defaults;
    if (!def) return;
    const fields = [
      ['sellerName', def.business_name],
      ['productName', def.product_name],
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
      if (force || !node.value || BANNED_SAMPLE_TERMS.some((t) => node.value.toLowerCase().includes(t))) {
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
      if (!currentOwnerId()) return;
      const evalRes = await apiJson('/api/v1/seller-memory/suggestions/evaluate', { method: 'POST' });
      if (evalRes.ok && evalRes.data) {
        state.suggestedUpdates = evalRes.data.suggested_updates || [];
        renderHomeUI();
      }
    });

    window.addEventListener('focus', () => {
      const uid = currentOwnerId();
      if (uid !== state.ownerId) {
        loadServerMemory(true);
      }
    });
  }

  function start() {
    initOnboardingHooks();
    initObservers();
    if (window.museAccount?.ready) {
      window.museAccount.ready().then(() => loadServerMemory(true)).catch(() => loadServerMemory(true));
      // React cleanly to sign-in / sign-out transitions
      setInterval(() => {
        const uid = currentOwnerId();
        if (uid !== state.ownerId) loadServerMemory(true);
      }, 900);
    } else {
      loadServerMemory(true);
    }
  }

  window.museSellerMemory = Object.freeze({
    reload: () => loadServerMemory(true),
    getState: () => ({ ...state }),
    getOnboardingMemoryEntries: () =>
      (state.onboardingEntries || []).filter((e) => e.status !== 'dismissed'),
    openMemoryModal,
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
