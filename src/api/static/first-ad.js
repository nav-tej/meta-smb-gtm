'use strict';
(() => {
  const $ = (id) => document.getElementById(id);

  const OUTCOME_INFO = {
    inquiries: {
      label: 'Start conversations & inquiries',
      metaObjective: 'Engagement / Messages (or Traffic to inquiry page) — verify in Ads Manager',
      note: 'Suggested starting approach: Ideal when you take custom orders or sell via DMs without online checkout.',
    },
    visits: {
      label: 'Bring visitors to your shop',
      metaObjective: 'Traffic (Link clicks / Landing page views) — verify in Ads Manager',
      note: 'Suggested starting approach: Sends interested buyers directly to your product or shop listing.',
    },
    sales: {
      label: 'Test a direct product offer',
      metaObjective: 'Sales (Conversions) — requires verified checkout + Meta Pixel',
      note: 'Prerequisite check: If your shop does not have verified checkout and Meta Pixel tracking yet, start with "Start conversations" or "Bring visitors to your shop" first.',
    },
  };

  function defaultDates() {
    const start = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const end = new Date(start.getTime() + 5 * 24 * 60 * 60 * 1000);
    const fmt = (d) => d.toISOString().slice(0, 10);
    return { startDate: fmt(start), endDate: fmt(end) };
  }

  function freshState(sample = false) {
    const dates = defaultDates();
    if (sample) {
      return {
        step: 1,
        outcome: 'visits',
        paidMode: 'paid',
        businessName: 'Art of Sarabjit Singh',
        productName: 'Ek Onkar · 12x12 Print',
        headline: 'Ek Onkar — Hand-painted Sikh art print',
        caption: 'Original calligraphy and spiritual artwork by Sarabjit Singh. View print sizes and framing options in the shop.',
        cta: 'See print sizes',
        destinationType: 'website',
        destinationUrl: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html',
        imageDataUrl: '/samples/ek_onkar_original.jpg',
        audience: 'Unconfirmed starting audience (edit before sharing): People interested in Sikh art, calligraphy, and meaningful home gifts',
        location: 'United States',
        budgetType: 'daily',
        budgetAmount: '10',
        startDate: dates.startDate,
        endDate: dates.endDate,
        reviewed: false,
        candidates: [],
      };
    }
    return {
      step: 1,
      outcome: 'inquiries',
      paidMode: 'organic',
      businessName: 'Your Studio',
      productName: '',
      headline: '',
      caption: '',
      cta: 'Learn more',
      destinationType: 'website',
      destinationUrl: '',
      imageDataUrl: '',
      audience: 'Unconfirmed starting audience (edit before sharing): Buyers looking for handmade studio work',
      location: 'United States',
      budgetType: 'daily',
      budgetAmount: '10',
      startDate: dates.startDate,
      endDate: dates.endDate,
      reviewed: false,
      candidates: [],
    };
  }

  let currentOwnerId = null;
  let state = freshState(true);
  let hydrating = false;

  function isSampleMode() {
    if (window.museModes?.isSampleMode) return window.museModes.isSampleMode();
    try {
      const p = new URLSearchParams(location.search);
      if (p.get('workspace') === 'sample') return true;
      if (p.get('workspace') === 'own') return false;
    } catch (_) {}
    return !currentOwnerId;
  }

  function storageKey() {
    if (isSampleMode()) return 'muse-first-ad-v1:sample';
    return `muse-first-ad-v1:account:${encodeURIComponent(currentOwnerId || 'guest')}`;
  }

  function creatorDraftKey() {
    if (isSampleMode()) return 'muse-editor-v1:creator:sample';
    return `muse-editor-v1:creator:${currentOwnerId ? 'account:' + encodeURIComponent(currentOwnerId) : 'guest'}`;
  }

  function persistState() {
    if (hydrating) return;
    try {
      const copy = { ...state, candidates: [] };
      localStorage.setItem(storageKey(), JSON.stringify(copy));
    } catch (_) {}
  }

  function notify(msg, isError = false) {
    const el = $('faNotice');
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
      el.classList.remove('is-error');
      return;
    }
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle('is-error', Boolean(isError));
  }

  function safeUrl(raw) {
    const v = String(raw || '').trim();
    if (!v) return '';
    try {
      const u = new URL(v);
      return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : null;
    } catch (_) {
      return null;
    }
  }

  function validateStep2() {
    const errEl = $('faUrlError');
    const urlVal = $('faDestinationUrl')?.value.trim() || '';
    if (urlVal && !safeUrl(urlVal)) {
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = 'Enter a complete http:// or https:// destination URL, or leave it blank for DM/organic posts.';
      }
      return false;
    }
    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }
    return true;
  }

  function validateStep3() {
    const bErr = $('faBudgetError');
    const bHint = $('faBudgetHint');
    const dErr = $('faDateError');
    if (bErr) { bErr.hidden = true; bErr.textContent = ''; }
    if (bHint) bHint.textContent = '';
    if (dErr) { dErr.hidden = true; dErr.textContent = ''; }

    if (state.paidMode !== 'paid') return true;

    const rawAmt = String(state.budgetAmount || '').trim();
    const amt = Number(rawAmt);
    const minAmt = state.budgetType === 'lifetime' ? 5 : 1;
    if (!rawAmt || !Number.isFinite(amt) || amt < minAmt) {
      if (bErr) {
        bErr.hidden = false;
        bErr.textContent = `Enter a valid ${state.budgetType} test budget of at least $${minAmt} USD (or switch to Organic $0 in Step 1).`;
      }
      return false;
    }
    if (amt > 500 && bHint) {
      bHint.textContent = 'High test budget (over $500) — double-check before entering this in Meta Ads Manager.';
    } else if (bHint) {
      bHint.textContent = `Planned ${state.budgetType} test cap: $${amt.toFixed(2)} USD (entered manually in Meta Ads Manager; Muse spends $0).`;
    }

    if (!state.startDate) {
      if (dErr) {
        dErr.hidden = false;
        dErr.textContent = 'Choose a start date for your manual test schedule.';
      }
      return false;
    }
    if (state.endDate && state.endDate < state.startDate) {
      if (dErr) {
        dErr.hidden = false;
        dErr.textContent = 'End date must be on or after the start date.';
      }
      return false;
    }
    return true;
  }

  function buildPrerequisites() {
    const items = [];
    const hasImg = Boolean(state.imageDataUrl);
    items.push({ ok: hasImg, text: hasImg ? 'Product image selected for export.' : 'Missing prerequisite: Upload or select a product photo in Step 2.' });
    const hasCopy = Boolean(state.headline.trim() && state.caption.trim());
    items.push({ ok: hasCopy, text: hasCopy ? 'Headline and primary text ready.' : 'Missing prerequisite: Add a headline and primary text in Step 2.' });

    const needsUrl = state.destinationType !== 'instagram_dm' && (state.outcome === 'visits' || state.outcome === 'sales');
    const urlValid = !state.destinationUrl.trim() ? !needsUrl : Boolean(safeUrl(state.destinationUrl));
    items.push({
      ok: urlValid,
      text: urlValid
        ? (state.destinationUrl.trim() ? `Destination URL formatted: ${state.destinationUrl.trim()}` : 'Destination set to DM / organic inquiry (no URL needed).')
        : 'Missing prerequisite: Add a valid https:// destination URL for shop visits or sales.',
    });

    if (state.paidMode === 'paid') {
      const schedOk = validateStep3();
      items.push({
        ok: schedOk,
        text: schedOk
          ? `Manual test schedule set: $${Number(state.budgetAmount).toFixed(2)} USD (${state.budgetType}) starting ${state.startDate}.`
          : 'Missing prerequisite: Fix invalid budget or dates in Step 3.',
      });
      items.push({
        ok: false,
        manual: true,
        text: 'Manual Meta setup required: Meta Ads Manager account, linked Facebook Page / Instagram account, and payment method (Muse cannot verify or log into Meta).',
      });
      if (state.outcome === 'sales') {
        items.push({
          ok: false,
          manual: true,
          text: 'Manual sales setup required: Working online checkout and Meta Pixel / conversion event configured on your store.',
        });
      }
    } else {
      items.push({ ok: true, text: 'Organic post selected ($0 ad spend — no Ads Manager billing required).' });
    }
    return items;
  }

  function renderStep1Guidance() {
    const info = OUTCOME_INFO[state.outcome] || OUTCOME_INFO.inquiries;
    const box = $('faOutcomeGuidance');
    if (!box) return;
    box.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = `${isSampleMode() ? 'Artist example' : 'Suggested starting approach'} · ${info.label}: `;
    const span = document.createElement('span');
    span.textContent = info.note;
    box.append(title, span);
  }

  function renderPreview(canvasEl = $('faPreviewCanvas'), targetHeight = 1350) {
    return new Promise((resolve) => {
      if (!canvasEl) { resolve(null); return; }
      const width = 1080;
      canvasEl.width = width;
      canvasEl.height = targetHeight;
      const ctx = canvasEl.getContext('2d');
      ctx.fillStyle = '#f6f3eb';
      ctx.fillRect(0, 0, width, targetHeight);

      const finishText = () => {
        const barH = Math.round(targetHeight * 0.16);
        ctx.fillStyle = 'rgba(24, 59, 43, 0.92)';
        ctx.fillRect(0, targetHeight - barH, width, barH);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 40px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.fillText((state.headline || state.productName || 'Your studio work').slice(0, 44), 48, targetHeight - barH + 74);
        ctx.font = '28px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.fillStyle = '#dce8e1';
        ctx.fillText((state.businessName || 'Your Studio').slice(0, 48), 48, targetHeight - barH + 128);
        resolve(canvasEl);
      };

      if (!state.imageDataUrl) {
        ctx.fillStyle = '#e8e2d5';
        ctx.fillRect(60, 60, width - 120, targetHeight - 280);
        ctx.fillStyle = '#4f6257';
        ctx.font = 'bold 34px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.fillText('Upload or select a product photo in Step 2', 140, Math.round(targetHeight * 0.44));
        finishText();
        return;
      }

      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const areaH = targetHeight - Math.round(targetHeight * 0.16);
        const scale = Math.min(width / img.width, areaH / img.height);
        const dw = Math.round(img.width * scale);
        const dh = Math.round(img.height * scale);
        const dx = Math.round((width - dw) / 2);
        const dy = Math.round((areaH - dh) / 2);
        ctx.drawImage(img, dx, dy, dw, dh);
        finishText();
      };
      img.onerror = () => finishText();
      img.src = state.imageDataUrl;
    });
  }

  function renderReview() {
    const prereqEl = $('faPrereqList');
    if (prereqEl) {
      prereqEl.replaceChildren();
      buildPrerequisites().forEach((item) => {
        const li = document.createElement('li');
        li.textContent = `${item.ok ? '✓' : (item.manual ? '!' : '✗')} ${item.text}`;
        prereqEl.appendChild(li);
      });
    }

    const summaryEl = $('faHandoffSummary');
    if (summaryEl) {
      summaryEl.replaceChildren();
      const info = OUTCOME_INFO[state.outcome] || OUTCOME_INFO.inquiries;
      const rows = [
        ['Publish status', 'Not published (manual Ads Manager entry required)'],
        ['Provenance', isSampleMode() ? 'Artist example (checked-in sample)' : 'Suggested starting approach'],
        ['Suggested objective', info.metaObjective],
        ['Ad format', state.paidMode === 'paid' ? 'Manual paid test' : 'Organic post ($0 spend)'],
        ['Product', state.productName || 'Not specified'],
        ['Headline', state.headline || 'Not specified'],
        ['Primary text', state.caption || 'Not specified'],
        ['Call to action', state.cta || 'Learn more'],
        ['Destination', `${state.destinationType}${state.destinationUrl ? ' — ' + state.destinationUrl : ''}`],
        ['Audience (unconfirmed)', state.audience || 'Not specified'],
        ['Location', state.location || 'Not specified'],
        ['Budget', state.paidMode === 'paid' ? `$${state.budgetAmount || '0'} USD (${state.budgetType})` : '$0 (Organic)'],
        ['Dates', state.paidMode === 'paid' ? `${state.startDate || '?'} to ${state.endDate || 'open'}` : 'Post when ready'],
      ];
      rows.forEach(([k, v]) => {
        const row = document.createElement('div');
        row.className = 'fa-summary-row';
        const s = document.createElement('strong');
        s.textContent = `${k}:`;
        const t = document.createElement('span');
        t.textContent = v;
        row.append(s, t);
        summaryEl.appendChild(row);
      });
    }
  }

  function syncUiFromState() {
    hydrating = true;
    const sample = isSampleMode();
    if ($('faBidAdviceLink')) $('faBidAdviceLink').href = sample ? '/?workspace=sample#tab-bids' : '/#tab-bids';
    if ($('faProvenanceBadge')) $('faProvenanceBadge').textContent = sample ? 'Artist example' : 'Suggested starting approach';
    if ($('faContextStatus')) {
      $('faContextStatus').textContent = sample
        ? 'Sample mode (Art of Sarabjit Singh) · Separate from your account drafts.'
        : `Signed-in workspace (${state.businessName || 'Your Studio'}) · Saved per account on this device.`;
    }

    document.querySelectorAll('[data-fa-outcome]').forEach((btn) => {
      const active = btn.dataset.faOutcome === state.outcome;
      btn.classList.toggle('is-selected', active);
      btn.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('input[name="faPaidMode"]').forEach((r) => {
      r.checked = r.value === state.paidMode;
    });
    if ($('faProductName')) $('faProductName').value = state.productName || '';
    if ($('faHeadline')) $('faHeadline').value = state.headline || '';
    if ($('faCaption')) $('faCaption').value = state.caption || '';
    if ($('faCta')) $('faCta').value = state.cta || '';
    if ($('faDestinationType')) $('faDestinationType').value = state.destinationType || 'website';
    if ($('faDestinationUrl')) $('faDestinationUrl').value = state.destinationUrl || '';
    if ($('faAudience')) $('faAudience').value = state.audience || '';
    if ($('faLocation')) $('faLocation').value = state.location || '';
    if ($('faBudgetType')) $('faBudgetType').value = state.budgetType || 'daily';
    if ($('faBudgetAmount')) $('faBudgetAmount').value = state.budgetAmount || '';
    if ($('faStartDate')) $('faStartDate').value = state.startDate || '';
    if ($('faEndDate')) $('faEndDate').value = state.endDate || '';
    if ($('faReviewed')) $('faReviewed').checked = Boolean(state.reviewed);

    if ($('faPaidBudgetSection')) $('faPaidBudgetSection').hidden = state.paidMode !== 'paid';
    if ($('faOrganicBudgetNotice')) $('faOrganicBudgetNotice').hidden = state.paidMode === 'paid';
    if ($('faPreviewHeadline')) $('faPreviewHeadline').textContent = state.headline || state.productName || 'Your headline';
    if ($('faPreviewCaption')) $('faPreviewCaption').textContent = state.caption || 'Your primary text will appear here.';

    renderStep1Guidance();
    validateStep2();
    validateStep3();
    renderReview();
    renderPreview();
    goStep(state.step, false);
    hydrating = false;
  }

  function goStep(step, doPersist = true) {
    const target = Math.max(1, Math.min(4, Number(step) || 1));
    if (target > state.step) {
      if (state.step === 2 && !validateStep2()) {
        notify('Please fix the destination URL before continuing.', true);
        return;
      }
      if (state.step === 3 && !validateStep3()) {
        notify('Please fix the budget or schedule errors before reviewing.', true);
        return;
      }
    }
    notify('');
    state.step = target;
    document.querySelectorAll('[data-fa-panel]').forEach((p) => {
      p.hidden = Number(p.dataset.faPanel) !== target;
    });
    document.querySelectorAll('[data-fa-step]').forEach((b) => {
      const active = Number(b.dataset.faStep) === target;
      b.classList.toggle('is-active', active);
      if (active) b.setAttribute('aria-current', 'step');
      else b.removeAttribute('aria-current');
    });
    if ($('faBackBtn')) $('faBackBtn').disabled = target === 1;
    if ($('faNextBtn')) $('faNextBtn').hidden = target === 4;
    if ($('faStepLabel')) $('faStepLabel').textContent = `Step ${target} of 4`;
    if (target === 4) renderReview();
    if (doPersist) persistState();
  }

  async function loadAccountAndDrafts() {
    try {
      const snap = await window.museAccount?.refresh?.().catch(() => null);
      currentOwnerId = snap?.user?.id || window.museAccount?.getSnapshot?.()?.user?.id || null;
    } catch (_) {
      currentOwnerId = null;
    }

    const sample = isSampleMode();
    if ($('faBidAdviceLink')) $('faBidAdviceLink').href = sample ? '/?workspace=sample#tab-bids' : '/#tab-bids';
    let loaded = null;
    try {
      const raw = localStorage.getItem(storageKey());
      if (raw) loaded = JSON.parse(raw);
    } catch (_) {}

    if (loaded && typeof loaded === 'object') {
      state = { ...freshState(sample), ...loaded };
    } else {
      state = freshState(sample);
      // Reuse same-owner/same-mode /create draft read-only if present
      try {
        const cRaw = localStorage.getItem(creatorDraftKey());
        const cDraft = cRaw ? JSON.parse(cRaw) : null;
        if (cDraft && typeof cDraft === 'object') {
          if (cDraft.product?.name) state.productName = cDraft.product.name;
          if (cDraft.product?.seller) state.businessName = cDraft.product.seller;
          if (cDraft.product?.link) state.destinationUrl = cDraft.product.link;
          if (cDraft.product?.destination) state.destinationType = cDraft.product.destination;
          if (cDraft.headline) state.headline = cDraft.headline;
          if (cDraft.caption) state.caption = cDraft.caption;
          if (cDraft.cta) state.cta = cDraft.cta;
          if (cDraft.original || cDraft.image) state.imageDataUrl = cDraft.image || cDraft.original;
          if (cDraft.handoffContext?.unconfirmed_audience) state.audience = cDraft.handoffContext.unconfirmed_audience;
        }
      } catch (_) {}

      if (!sample && currentOwnerId) {
        try {
          const resp = await fetch('/api/v1/seller-memory', { credentials: 'include' });
          if (resp.ok) {
            const sm = await resp.json();
            if (sm?.business_name && state.businessName === 'Your Studio') state.businessName = sm.business_name;
            if (Array.isArray(sm?.shop_urls) && sm.shop_urls[0] && $('faShopUrl')) {
              $('faShopUrl').value = sm.shop_urls[0];
            }
          }
        } catch (_) {}
      }
    }
    syncUiFromState();
  }

  async function importShopImages() {
    const shopUrl = $('faShopUrl')?.value.trim() || '';
    if (!safeUrl(shopUrl)) {
      notify('Enter a valid http:// or https:// shop or product URL first.', true);
      return;
    }
    notify('Loading shop images…');
    try {
      const resp = await fetch('/api/v1/product-reference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: shopUrl }),
      });
      if (!resp.ok) throw new Error(`Status ${resp.status}`);
      const data = await resp.json();
      const cands = Array.isArray(data.image_candidates) ? data.image_candidates : [];
      if (!cands.length && data.image_data_url) {
        cands.push({ id: 'primary', title: data.title || 'Product photo', image_data_url: data.image_data_url });
      }
      const grid = $('faCandidatesGrid');
      if (grid) {
        grid.replaceChildren();
        cands.forEach((c) => {
          const card = document.createElement('div');
          card.className = 'fa-cand';
          const img = document.createElement('img');
          img.src = c.image_data_url;
          img.alt = c.title || 'Candidate image';
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'fa-btn fa-btn-secondary';
          btn.dataset.faCandId = c.id || '';
          btn.textContent = 'Use image';
          btn.addEventListener('click', () => {
            state.imageDataUrl = c.image_data_url;
            if (!state.productName && data.title) state.productName = data.title;
            if (!state.destinationUrl && data.url) state.destinationUrl = data.url;
            persistState();
            syncUiFromState();
            notify('Selected image for your ad preview.');
          });
          card.append(img, btn);
          grid.appendChild(card);
        });
      }
      notify(cands.length ? `Loaded ${cands.length} image candidate(s).` : 'No images found on that page; upload a photo instead.');
    } catch (_) {
      notify('Could not load images from that URL. Upload a photo instead.', true);
    }
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function exportPng(height) {
    if (!state.imageDataUrl) {
      notify('Add or select a product photo in Step 2 before exporting.', true);
      return;
    }
    if (!state.reviewed) {
      notify('Please tick the review checkbox before downloading.', true);
      return;
    }
    const offscreen = document.createElement('canvas');
    await renderPreview(offscreen, height);
    offscreen.toBlob((blob) => {
      if (!blob) return;
      downloadBlob(blob, `muse-first-ad-1080x${height}.png`);
      notify(`Downloaded 1080 × ${height} PNG. Remember: this ad is NOT published yet.`);
    }, 'image/png');
  }

  function exportChecklist() {
    if (!state.reviewed) {
      notify('Please tick the review checkbox before downloading.', true);
      return;
    }
    const info = OUTCOME_INFO[state.outcome] || OUTCOME_INFO.inquiries;
    const prereqs = buildPrerequisites().map((p) => `- [${p.ok ? 'READY' : 'MISSING/MANUAL'}] ${p.text}`).join('\n');
    const txt = [
      'MUSE — RUN YOUR FIRST AD (MANUAL ADS MANAGER HANDOFF)',
      'STATUS: NOT PUBLISHED (Draft only — Muse did not connect to Meta or spend any money)',
      `PROVENANCE: ${isSampleMode() ? 'Artist example (checked-in sample)' : 'Suggested starting approach'}`,
      '',
      `Outcome: ${info.label}`,
      `Suggested Meta Objective: ${info.metaObjective}`,
      `Mode: ${state.paidMode === 'paid' ? 'Manual paid test' : 'Organic post ($0)'}`,
      `Product: ${state.productName || '(not set)'}`,
      `Headline: ${state.headline || '(not set)'}`,
      `Primary Text: ${state.caption || '(not set)'}`,
      `Call to Action: ${state.cta || 'Learn more'}`,
      `Destination: ${state.destinationType} ${state.destinationUrl || '(none)'}`,
      `Audience (Unconfirmed): ${state.audience || '(not set)'}`,
      `Location: ${state.location || '(not set)'}`,
      `Budget: ${state.paidMode === 'paid' ? `$${state.budgetAmount} USD (${state.budgetType})` : '$0 (Organic)'}`,
      `Schedule: ${state.paidMode === 'paid' ? `${state.startDate} to ${state.endDate || 'open'}` : 'Post when ready'}`,
      '',
      'PREREQUISITES:',
      prereqs,
    ].join('\n');
    downloadBlob(new Blob([txt], { type: 'text/plain;charset=utf-8' }), 'muse-first-ad-checklist.txt');
    notify('Downloaded manual Ads Manager checklist (.txt).');
  }

  function bindEvents() {
    document.querySelectorAll('[data-fa-step]').forEach((b) => {
      b.addEventListener('click', () => goStep(Number(b.dataset.faStep)));
    });
    $('faBackBtn')?.addEventListener('click', () => goStep(state.step - 1));
    $('faNextBtn')?.addEventListener('click', () => goStep(state.step + 1));

    document.querySelectorAll('[data-fa-outcome]').forEach((b) => {
      b.addEventListener('click', () => {
        state.outcome = b.dataset.faOutcome;
        persistState();
        syncUiFromState();
      });
    });
    document.querySelectorAll('input[name="faPaidMode"]').forEach((r) => {
      r.addEventListener('change', () => {
        if (r.checked) {
          state.paidMode = r.value;
          persistState();
          syncUiFromState();
        }
      });
    });

    const inputMap = [
      ['faProductName', 'productName'],
      ['faHeadline', 'headline'],
      ['faCaption', 'caption'],
      ['faCta', 'cta'],
      ['faDestinationType', 'destinationType'],
      ['faDestinationUrl', 'destinationUrl'],
      ['faAudience', 'audience'],
      ['faLocation', 'location'],
      ['faBudgetType', 'budgetType'],
      ['faBudgetAmount', 'budgetAmount'],
      ['faStartDate', 'startDate'],
      ['faEndDate', 'endDate'],
    ];
    inputMap.forEach(([id, key]) => {
      const el = $(id);
      if (!el) return;
      const evt = el.tagName === 'SELECT' || el.type === 'date' ? 'change' : 'input';
      el.addEventListener(evt, () => {
        state[key] = el.value;
        persistState();
        if (key === 'destinationUrl') validateStep2();
        if (['budgetType', 'budgetAmount', 'startDate', 'endDate'].includes(key)) validateStep3();
        if (['headline', 'caption', 'productName'].includes(key)) {
          if ($('faPreviewHeadline')) $('faPreviewHeadline').textContent = state.headline || state.productName || 'Your headline';
          if ($('faPreviewCaption')) $('faPreviewCaption').textContent = state.caption || 'Your primary text will appear here.';
          renderPreview();
        }
      });
    });

    $('faReviewed')?.addEventListener('change', () => {
      state.reviewed = $('faReviewed').checked;
      persistState();
    });

    $('faPhotoUpload')?.addEventListener('change', (ev) => {
      const file = ev.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        state.imageDataUrl = String(reader.result || '');
        persistState();
        syncUiFromState();
        notify('Photo uploaded for your ad preview.');
      };
      reader.readAsDataURL(file);
    });

    $('faImportBtn')?.addEventListener('click', importShopImages);
    $('faFinalFeedBtn')?.addEventListener('click', () => exportPng(1350));
    $('faFinalSquareBtn')?.addEventListener('click', () => exportPng(1080));
    $('faDownloadChecklistBtn')?.addEventListener('click', exportChecklist);
    $('faCopyCopyBtn')?.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(`${state.headline}\n\n${state.caption}\n${state.destinationUrl || ''}`);
        notify('Copied ad wording to clipboard.');
      } catch (_) {
        notify('Clipboard unavailable; copy from the summary above.', true);
      }
    });

    window.addEventListener('muse:account-change', () => loadAccountAndDrafts());
    window.addEventListener('muse:workspace-mode-change', () => loadAccountAndDrafts());
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadAccountAndDrafts();
  });
})();
