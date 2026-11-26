'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const names = { instagram: 'Instagram', facebook: 'Facebook', x: 'X', tiktok: 'TikTok' };
  const SAMPLE_DESTINATIONS = { pixels: 'Pixels', fineartamerica: 'Fine Art America', saatchi: 'Saatchi Art', website: 'Artist website', other: 'My shop / inquiry page' };
  const OWN_DESTINATIONS = { website: 'My website', booking: 'Booking or contact page', etsy: 'Etsy shop or listing', shopify: 'Shopify store', other: 'Other link' };
  const storageKey = 'muse-daily-v1';
  const standaloneVm = typeof window.museModes === 'undefined' && typeof window.museAccount === 'undefined';
  const isSampleMode = () => {
    if (window.museModes?.isSampleMode) return window.museModes.isSampleMode();
    try {
      if (typeof location === 'undefined') return false;
      const params = new URLSearchParams(location.search);
      if (params.get('workspace') === 'own') return false;
      if (params.get('workspace') === 'sample') return true;
      const idea = params.get('idea');
      const artwork = params.get('artwork');
      return Boolean((idea && !/^(own|shop|user):/i.test(idea)) || (artwork && !/^(own|shop|user):/i.test(artwork)));
    } catch (_) { return false; }
  };
  const safeURL = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const originalSample = '/samples/ek_onkar_original.jpg';
  const sampleProduct = () => ({ title: 'Ek Onkar', description: 'An artwork by Sarabjit Singh exploring connection and equality through color and form.', seller: 'Art of Sarabjit Singh', collection: '', price: '', destination_url: 'https://sarabjit-singh.pixels.com/', destination: 'pixels' });
  // What the signed-in seller offers, from setup ("products", "services", "both" or null).
  let ownBusinessType = null;
  const offersServices = () => ownBusinessType === 'services';
  // Until the seller picks an item, the label says so instead of inventing an item name.
  const neutralProduct = (shopName = '', shopUrl = '') => {
    const services = offersServices();
    const pick = services ? 'choose a service or offer' : 'choose an item';
    return {
      title: shopName ? `${shopName} · ${pick}` : pick.charAt(0).toUpperCase() + pick.slice(1),
      description: '',
      seller: shopName || '',
      collection: '',
      price: '',
      destination_url: safeURL(shopUrl) || '',
      destination: 'website',
      placeholder: true,
    };
  };
  // Placeholder titles saved by earlier versions of this page.
  const legacyPlaceholder = title => title === 'My studio item' || /^Featured piece · /.test(title);
  function readRecommendationHandoff(uid = window.museAccount?.getSnapshot?.()?.user?.id || window.museAccount?.current?.()?.id || null) {
    try {
      const hid = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('sm_handoff') : null;
      if (!hid) return null;
      const ns = uid ? String(uid) : 'guest';
      const mode = isSampleMode() ? 'sample' : 'own';
      const raw = localStorage.getItem(`muse.sm.handoff.${encodeURIComponent(ns)}.${encodeURIComponent(hid)}`);
      const payload = raw ? JSON.parse(raw) : null;
      if (!payload || payload.owner_id !== ns || payload.workspace_mode !== mode) return null;
      return payload;
    } catch (_) {
      return null;
    }
  }
  const bootAsSample = standaloneVm || isSampleMode();
  const state = {
    product: bootAsSample ? sampleProduct() : neutralProduct(),
    original: bootAsSample ? originalSample : '',
    image: bootAsSample ? originalSample : '',
    imageMode: 'original',
    imageMeta: null,
    imageFrame: { fit: 'contain', x: 0, y: 0 },
    source: bootAsSample ? 'Suggested from the artist example' : 'Suggested from my workspace',
    shopWebsiteUrl: '', cta: '', why_this: '', idea_id: null,
    channel: 'instagram',
    format: 'image',
    goal: 'visits',
    salesGoal: null,
    performance: null,
    plans: {},
    edits: {},
    selected: 0,
    posted: {},
    offers: {},
    busy: false,
    revision: 0,
    paint: 0,
    live: false,
    readiness: null,
  };

  const draftNamespace = 'daily';
  function editorDocument() { return { schema: 1, ...Object.fromEntries(['product', 'original', 'image', 'imageMode', 'imageMeta', 'imageFrame', 'source', 'channel', 'selected', 'format', 'goal', 'salesGoal', 'performance', 'plans', 'edits', 'posted', 'offers', 'cta', 'why_this', 'idea_id'].map(key => [key, state[key]])) }; }
  const isDraftObject = value => !!value && typeof value === 'object' && !Array.isArray(value);
  function applyDocument(data) {
    if (!data || (data.schema !== undefined && data.schema !== 1) || typeof data.product?.title !== 'string' || (data.original !== '' && !imageSource(data.original))) throw new Error('Unsupported daily draft.');
    for (const key of ['plans', 'edits', 'posted', 'offers']) if (data[key] !== undefined && !isDraftObject(data[key])) throw new Error('Invalid daily draft fields.');
    state.plans = {}; state.edits = {}; state.posted = {}; state.offers = {}; state.performance = null; state.salesGoal = null; state.cta = ''; state.why_this = ''; state.idea_id = null; state.imageMeta = null; state.imageFrame = { fit: 'contain', x: 0, y: 0 };
      for (const key of ['product', 'original', 'imageMeta', 'imageFrame', 'source', 'salesGoal', 'performance', 'posted', 'offers', 'cta', 'why_this', 'idea_id']) if (data[key] !== undefined) state[key] = data[key];
      if (!isDraftObject(state.imageFrame)) state.imageFrame = { fit: 'contain', x: 0, y: 0 };
      state.channel = Object.hasOwn(names, data.channel) ? data.channel : 'instagram';
      state.format = ['image', 'video', 'text'].includes(data.format) ? data.format : 'image';
      state.goal = ['visits', 'inquiries', 'sales'].includes(data.goal) ? data.goal : 'visits';
      if (data.plans && typeof data.plans === 'object') state.plans = data.plans;
      if (data.edits && typeof data.edits === 'object') state.edits = data.edits;
      const posts = state.plans[state.channel]?.posts;
      state.selected = Array.isArray(posts) && Number.isInteger(data.selected) && data.selected >= 0 && data.selected < posts.length ? data.selected : 0;
      state.image = imageSource(data.image) ? data.image : state.original;
      state.imageMode = data.imageMode === 'live' ? 'live' : 'original';
      state.product.destination_url = safeURL(state.product.destination_url);
      state.product.destination = normalizeDestination(state.product.destination);

    state.revision += 1; $('reviewed').checked = false; populateSetup(); render();
  }
  function persist() { persistDraft(); }

  // Editor-local adapter: keep this contract aligned in creator.js and today.js.
  let draftReady = false, draftOwner = null, draftOwnerBound = false, draftEpoch = 0, cloudBusy = false;
  let activeSampleMode = isSampleMode(), todayInitializedOnce = false;
  let cloudBase, conflictValue, recoveryDraft, applyingDraft = false;
  const cloneDraft = value => JSON.parse(JSON.stringify(value));
  const draftStatus = text => { $('draftStatus').textContent = text; };
  const isEffectiveSample = () => (typeof activeSampleMode === 'boolean' ? activeSampleMode : isSampleMode());
  const activeDestinations = () => isEffectiveSample() ? SAMPLE_DESTINATIONS : OWN_DESTINATIONS;
  const normalizeDestination = key => Object.hasOwn(activeDestinations(), key) ? key : 'other';
  const shopLabel = key => activeDestinations()[normalizeDestination(key)];
  function syncDestinationOptions() {
    const select = $('destination');
    if (typeof select.replaceChildren === 'function') {
      select.replaceChildren();
      for (const [value, label] of Object.entries(activeDestinations())) {
        const option = document.createElement('option');
        option.value = value; option.textContent = label;
        select.append(option);
      }
    }
    state.product.destination = normalizeDestination(state.product.destination);
    select.value = state.product.destination;
  }
  const offerWords = () => offersServices() ? 'service or offer' : ownBusinessType === 'both' ? 'product or service' : 'product';
  // The sample artist keeps its wording; a seller's own workspace gets labels that fit what they offer.
  function applyOfferWording() {
    const sample = isEffectiveSample();
    const services = !sample && offersServices();
    const find = selector => (typeof document.querySelector === 'function' ? document.querySelector(selector) : null);
    const swap = (el, ownText, attr) => {
      if (!el || !el.dataset) return;
      const key = attr ? `sample${attr}` : 'sampleText';
      if (el.dataset[key] === undefined) el.dataset[key] = attr ? (el.getAttribute?.(attr) || '') : el.textContent;
      const text = sample ? el.dataset[key] : ownText;
      if (attr) el.setAttribute?.(attr, text); else el.textContent = text;
    };
    swap(find('#noPhoto span'), 'Add a photo to finish this post.');
    swap(find('label[for="productLink"]'), 'Link people should visit');
    swap(find('label[for="sellerName"]'), services ? 'Your name / business' : 'Your name / shop');
    swap(find('#goal option[value="visits"]'), services ? 'Website visits' : 'Shop visits');
    swap($('quickFindItems'), services ? 'Find items on my site' : 'Find products');
    swap($('saveWebsiteOnlyBtn'), 'Save website only');
    swap($('itemHint'), `Choose the page for this ${offerWords()}. Each destination keeps its own price and link.`);
    swap($('sceneNote'), 'AI scenes can change details in your photo. Compare with your original.');
    const prompt = $('scenePrompt');
    if (prompt?.dataset) {
      const samplePrompt = 'A simple, softly lit room. Keep attention on the artwork.';
      const nextPrompt = sample ? samplePrompt : `A simple, softly lit setting. Keep attention on the ${offerWords()}.`;
      const previousDefault = prompt.dataset.defaultPrompt || samplePrompt;
      // Refresh defaults without replacing a scene the seller has written.
      if (prompt.value === previousDefault) prompt.value = nextPrompt;
      prompt.dataset.defaultPrompt = nextPrompt;
    }
    swap($('productName'), services ? 'Name the service or offer' : 'Name the item you are sharing', 'placeholder');
    swap(find('label[for="shopUrl"]'), services ? 'Website or page link' : 'Shop or product link');
    swap($('readListing'), services ? 'Use this page' : 'Use this listing');
    swap($('shopUrl'), services ? 'https://your-website.com' : 'https://your-shop.com', 'placeholder');
    swap($('quickShopUrl'), services ? 'https://your-website.com' : 'https://your-shop.com', 'placeholder');
    swap($('researchSavedLink'), 'Open your full workspace →');
    swap($('researchSavedLink'), '/', 'href');
  }
  const deviceKey = () => `muse-editor-v1:${draftNamespace}:${isEffectiveSample() ? 'sample' : (draftOwner ? 'account:' + encodeURIComponent(draftOwner) : 'guest')}`;
  function persistDraft() {
    if (!draftReady || applyingDraft) return;
    try { localStorage.setItem(deviceKey(), JSON.stringify(editorDocument())); draftStatus(`Saved on this device.${!isEffectiveSample() && draftOwner ? ' Save to account to open it on another device.' : ''}`); return true; }
    catch { draftStatus('Device storage failed or is full. Download a backup now, or save to your account before closing.'); return false; }
  }
  // Once the editor knows its workspace, say where the draft lives instead of leaving a loading line,
  // offer account saving only where it applies, and offer recovery only when there is something to recover.
  function settleDraftStatus() {
    const sample = isEffectiveSample();
    draftStatus(sample
      ? 'Sample shop drafts stay on this device and never mix with your own.'
      : draftOwner
        ? 'Your draft is kept on this device as you edit. Save to account to open it on another device.'
        : 'Your draft is kept on this device as you edit. Sign in to save it to an account.');
    $('saveAccountDraft').hidden = sample;
    $('loadAccountDraft').hidden = sample;
    try { $('recoverDraft').hidden = !(recoveryDraft || localStorage.getItem(deviceKey() + ':before-load')); } catch { /* leave the button as it is */ }
  }
  function installDocument(data) {
    const previous = cloneDraft(editorDocument());
    applyingDraft = true;
    try { applyDocument(cloneDraft(data)); }
    catch (error) { applyDocument(previous); throw error; }
    finally { applyingDraft = false; }
  }
  function recoverDevice() {
    try {
      const requestedIdea = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null;
      settleDraftStatus();
      if (isEffectiveSample() && requestedIdea && findPreviewSpec(requestedIdea)) return false;
      const raw = localStorage.getItem(deviceKey()) || (!isEffectiveSample() && !draftOwner ? localStorage.getItem(storageKey) : null);
      if (raw) { installDocument(JSON.parse(raw)); draftStatus('Recovered this device’s draft. Review before sharing.'); return true; }
      return false;
    } catch { draftStatus('Could not recover device storage. Keep this tab open; download a backup or load your account draft.'); return false; }
  }
  function currentOwner(epoch, owner) {
    return draftReady && epoch === draftEpoch && owner === draftOwner && owner === window.museAccount?.getSnapshot()?.user?.id;
  }
  async function accountDraft(action) {
    const api = window.museAccount;
    if (!draftReady || cloudBusy || state.busy) return;
    if (isEffectiveSample()) {
      draftStatus('Sample shop mode stays separate from your account drafts. Choose Back to my workspace to save or load your own drafts.');
      return;
    }
    if (!draftOwner || !api) { api?.open?.('signin'); draftStatus('Sign in, then choose Save to account or Load from account. Device drafts are not transferred automatically.'); return; }
    const epoch = draftEpoch, owner = draftOwner;
    const local = cloneDraft(editorDocument());
    cloudBusy = true;
    try {
      await api.refresh?.();
      if (!currentOwner(epoch, owner)) return;
      // Always read first: preserve every other editor and unknown workspace field.
      const workspace = await api.loadWorkspace(owner);
      if (workspace?.owner_id !== undefined && workspace.owner_id !== owner) {
        const error = new Error('The account changed in another tab. Reload your workspace.');
        error.status = 409;
        throw error;
      }
      await api.refresh?.();
      if (!currentOwner(epoch, owner)) return;
      const documentValue = workspace.document || {};
      if (!isDraftObject(documentValue) || (documentValue.documents !== undefined && !isDraftObject(documentValue.documents))) throw new Error('Unsupported account workspace. Nothing was replaced.');
      const remote = documentValue.documents?.[draftNamespace];
      const fingerprint = JSON.stringify(remote);
      if (action === 'load') {
        if (state.busy || JSON.stringify(editorDocument()) !== JSON.stringify(local)) { draftStatus('Your draft changed while loading. Retry Load from account when ready; your edits are intact.'); return; }
        if (!remote) { draftStatus('No account draft for this editor yet. Save this draft first.'); return; }
        // Backup must succeed before replacing unsaved work.
        if (fingerprint === JSON.stringify(local)) { cloudBase = fingerprint; draftStatus('Account draft loaded (already matches this device; previous backup unchanged).'); return; }
        localStorage.setItem(deviceKey() + ':before-load', JSON.stringify(local));
        recoveryDraft = cloneDraft(local); $('recoverDraft').hidden = false;
        installDocument(remote); cloudBase = fingerprint; conflictValue = undefined;
        $('replaceAccountDraft').hidden = true;
        if (persistDraft()) draftStatus('Account draft loaded. Recover previous device draft if needed.');
      } else {
        if ((remote !== undefined || cloudBase !== undefined) && fingerprint !== JSON.stringify(local) && fingerprint !== cloudBase && !(action === 'replace' && fingerprint === conflictValue)) {
          conflictValue = fingerprint; $('replaceAccountDraft').hidden = false;
          draftStatus('A different account draft exists. Download a backup, then Load from account or explicitly Replace account draft. Your device draft is unchanged.'); return;
        }
        if (!currentOwner(epoch, owner)) return;
        // Refresh again after the GET to catch account changes in another tab.
        await api.refresh?.();
        if (!currentOwner(epoch, owner)) return;
        const saved = await api.saveWorkspace({ ...documentValue, documents: { ...documentValue.documents, [draftNamespace]: local } }, owner);
        if (saved?.owner_id !== undefined && saved.owner_id !== owner) {
          const error = new Error('The account changed while saving. Reload your workspace.');
          error.status = 409;
          throw error;
        }
        if (!currentOwner(epoch, owner)) return;
        cloudBase = JSON.stringify(local); conflictValue = undefined; $('replaceAccountDraft').hidden = true;
        draftStatus('Saved to your account. Later edits stay on this device until you save again.');
      }
    } catch (error) {
      if (/account changed/i.test(error?.message || '')) api.refresh?.().catch?.(() => {});
      if (!currentOwner(epoch, owner)) return;
      if (/account changed/i.test(error?.message || '')) { conflictValue = undefined; $('replaceAccountDraft').hidden = true; draftStatus('Account changed in another tab. Your draft is intact on this device; reload or sign back into your original account.'); }
      else if (error.status === 409) { conflictValue = undefined; $('replaceAccountDraft').hidden = true; draftStatus('Save conflict: another device saved first. Your draft is intact. Download a backup, then Load from account or Save to account to compare again.'); }
      else draftStatus(`Account operation failed. Your draft is intact. Retry, or download a backup before closing. ${error.message || ''}`);
    } finally { cloudBusy = false; }
  }
  function initDrafts() {
    $('saveAccountDraft').addEventListener('click', () => accountDraft('save'));
    $('loadAccountDraft').addEventListener('click', () => accountDraft('load'));
    $('replaceAccountDraft').addEventListener('click', () => accountDraft('replace'));
    $('downloadDraft').addEventListener('click', () => saveBlob(new Blob([JSON.stringify(editorDocument())], { type: 'application/json' }), 'draft-backup.json'));
    $('recoverDraft').addEventListener('click', () => {
      if (!draftReady || cloudBusy || state.busy) return;
      try { const prior = recoveryDraft || JSON.parse(localStorage.getItem(deviceKey() + ':before-load') || 'null'); if (prior) { installDocument(prior); persistDraft(); } else draftStatus('No previous device draft is available.'); }
      catch { draftStatus('Could not recover the previous draft. Keep your downloaded backup.'); }
    });
    const start = () => {
      draftOwner = window.museAccount?.getSnapshot()?.user?.id || null;
      draftOwnerBound = true;
      if (standaloneVm) { draftReady = true; recoverDevice(); }
      window.addEventListener?.('muse:account-change', event => {
        if ((event.detail?.user?.id || null) === draftOwner) {
          if (!draftReady) {
            draftEpoch += 1; cloudBase = undefined; conflictValue = undefined; $('replaceAccountDraft').hidden = true;
            draftReady = true; document.querySelector?.('main')?.removeAttribute('hidden');
            $('draftBoundaryStatus').textContent = ''; persistDraft();
          }
          return;
        }
        const stored = persistDraft();
        // A new document lifetime prevents pending editor jobs from writing under a new owner.
        draftReady = false; draftEpoch += 1; state.revision += 1; state.paint += 1; state.live = false;
        document.querySelector?.('main')?.setAttribute('hidden', '');
        draftStatus('Account changed. Reloading the editor for this account…');
        document.querySelectorAll('dialog').forEach(dialog => dialog.close());
        if (stored) window.location?.reload();
        else $('draftBoundaryStatus').textContent = 'Unsaved work is held privately in this tab because device storage failed. Do not close it. Sign back into the previous account to recover and download it.';
      });
    };
    if (window.museAccount?.ready) window.museAccount.ready().then(start);
    else start();
    window.addEventListener?.('pagehide', persistDraft);
    window.addEventListener?.('pageshow', event => { if (event.persisted) window.location?.reload(); });
  }
  let setupBackup = null;
  const inline = value => typeof value === 'string' && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length <= 4000000;
  const mediaAsset = value => typeof value === 'string' && /^\/api\/v1\/account\/media\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(value);
  const imageSource = value => inline(value) || mediaAsset(value) || /^\/samples\/[a-zA-Z0-9_.-]+$/.test(value || '');
  const isOfflineNow = () => Boolean(window.museShell?.isOffline?.() || (typeof navigator !== 'undefined' && navigator.onLine === false));
  const DEFAULT_PREVIEWS = [
    {
      insight_id: 'idea-1-empowering-women',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      goal: 'story',
      headline: 'Sikh Women of Strength — Mai Bhago & Kaur Legacy',
      caption: 'While mainstream Sikh art galleries feature warrior heroes, our Empowering Women series honors the courage, devotion, and leadership of Sikh women across history. Archival museum-grade prints starting at $18. Tap to discover the full collection on Pixels.',
      cta: 'Explore series',
      image_ref: '/samples/naam_japo_restored_gallery_live.webp',
      why_this: 'SikhiArt has 8 shop collections for warriors and saints, but zero for women. Lead with your unique collection.',
      product_name: 'Mai Bhago — Empowering Women'
    },
    {
      insight_id: 'idea-2-starter-prints',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      goal: 'visit',
      headline: 'Timeless Sikh Heritage Art from $14',
      caption: 'Museum-grade fine art shouldn’t require a $100+ commitment. Start your art wall with authentic archival prints on luster paper, beginning at just $14. Handcrafted with reverence.',
      cta: 'Shop prints from $14',
      image_ref: '/samples/ek_onkar_collector_room_live.webp',
      why_this: '3 of 4 competitors start at $60+. Leading with $14 prints wins gift and first-time buyers.',
      product_name: 'Ek Onkar luster print ($14)'
    },
    {
      insight_id: 'idea-3-gift-ready',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      goal: 'gift',
      headline: 'The Thoughtful Spiritual Gift That Lasts a Lifetime',
      caption: 'Looking for a meaningful housewarming, wedding, or Gurpurab gift? A fine art print of the Golden Temple brings peace and timeless reflection into any home. Custom gift notes available with every order.',
      cta: 'Send as a gift',
      image_ref: '/samples/golden_temple_holiday_gift_live.webp',
      why_this: 'Competitors use gift seasonal wording but charge $60–$129+. You can offer curated $20–$50 gifts.',
      product_name: 'Harmandir Sahib Golden Temple print'
    },
    {
      insight_id: 'idea-4-home-titles',
      source: 'ranked_idea',
      placement: 'facebook_feed',
      goal: 'visit',
      headline: 'Listing Optimization: \'For Your Home\' Decor Titles',
      caption: 'Search visibility update for your shop: Add \'for your home\' to high-intent titles to capture buyers searching for sacred decor rather than generic paintings.',
      cta: 'Update listings',
      image_ref: '/samples/kirat_karo_collector_room_live.webp',
      why_this: 'SikhiArt adds \'for Your Home\' to almost every title to rank in Google & Etsy home decor searches.',
      product_name: 'Ek Onkar Sacred Sikh Art Print for Your Home'
    },
    {
      insight_id: 'idea-5-painting-story',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      goal: 'story',
      headline: 'The Story Behind Ek Onkar: One Infinite Creator',
      caption: 'Behind every brushstroke is a meditation on unity. When I painted this Ek Onkar piece, I wanted the sacred symbol to emerge from quiet gold and deep crimson — a daily reminder that the Divine dwells in all creation. What feeling does it bring to your quiet space?',
      cta: 'Read the story',
      image_ref: '/samples/diptych_ek_onkar_kirat_karo_live.webp',
      why_this: 'Competitors post impersonal product specs. A five-sentence story behind the art builds true emotional connection.',
      product_name: 'Ek Onkar — One Infinite Creator'
    }
  ];

  function findPreviewSpec(id) {
    if (!id || typeof id !== 'string') return null;
    return DEFAULT_PREVIEWS.find((p) => p.insight_id === id) || null;
  }

  function promptPhotoUpload() {
    $('photo')?.click();
  }
  function notice(message, error = false, busy = false, action = null) {
    const el = $('notice');
    if (!el) return;
    el.hidden = false;
    el.className = error ? 'error' : (busy ? 'busy' : '');
    if (!action) {
      el.textContent = message;
      return;
    }
    if (typeof el.replaceChildren === 'function' && typeof document.createElement === 'function') {
      el.replaceChildren();
      const span = document.createElement('span');
      span.textContent = message;
      if (el.append) el.append(span); else if (el.appendChild) el.appendChild(span);
      if (typeof action.onClick === 'function') {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = action.text || 'Continue';
        btn.className = 'secondary notice-action-btn';
        btn.addEventListener('click', action.onClick);
        if (el.append) el.append(btn); else if (el.appendChild) el.appendChild(btn);
      } else if (action.href) {
        const a = document.createElement('a');
        a.href = action.href;
        a.textContent = action.text;
        a.className = 'notice-action';
        if (a.style) {
          a.style.marginLeft = '8px';
          a.style.fontWeight = 'bold';
          a.style.color = 'inherit';
          a.style.textDecoration = 'underline';
        }
        if (el.append) el.append(a); else if (el.appendChild) el.appendChild(a);
      }
      if (!el.childNodes?.length) el.textContent = message;
    } else {
      el.textContent = message;
    }
  }

  function markIdeaExported() {
    try {
      const ideaId = state.idea_id || (typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null);
      const uid = window.museAccount?.getSnapshot?.()?.user?.id || null;
      const ACTIONS_KEY = uid ? `muse.actions.${uid}` : 'muse.actions';
      const raw = localStorage.getItem(ACTIONS_KEY) || '{}';
      const all = typeof raw === 'string' && raw ? JSON.parse(raw) : {};
      const actionKey = ideaId || 'today-post';
      all[actionKey] = {
        ...(all[actionKey] || {}),
        status: 'done',
        title: state.product.title || 'Daily Desk Post',
        href: location.pathname + location.search,
        page: location.pathname,
        at: new Date().toISOString()
      };
      localStorage.setItem(ACTIONS_KEY, JSON.stringify(all));
      if (typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(new StorageEvent('storage', { key: ACTIONS_KEY }));
      }
      window.museTrack?.('idea_done', { action_id: actionKey, idea_id: ideaId });
    } catch (_) {}
    const logLink = $('logResultLink');
    if (logLink) logLink.hidden = false;
    notice('Post exported. Paste it into your channel.', false, false, { href: '/progress', text: 'Log result →' });
  }

  function applyIdea(spec) {
    if (!spec) return;
    state.idea = spec;
    state.idea_id = spec.insight_id;
    state.why_this = spec.why_this || '';
    state.product.title = spec.product_name || spec.headline;
    state.source = 'Recommended research move';
    if (spec.image_ref && imageSource(spec.image_ref)) {
      state.original = spec.image_ref;
      state.image = spec.image_ref;
      state.imageMode = 'original';
    }
    if (spec.placement === 'facebook_feed') {
      state.channel = 'facebook';
    } else {
      state.channel = 'instagram';
    }
    document.querySelectorAll?.('[data-channel]').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.channel === state.channel));
    });
    $('postHook').value = spec.headline;
    $('postCaption').value = spec.caption;
    $('itemTitle').textContent = state.product.title;
    $('dailyReason').textContent = spec.why_this || 'Start with your work. We’ll help with the words.';
    state.cta = spec.cta || '';
    state.edits[`${state.channel}:0:${state.format}`] = { hook: spec.headline, caption: spec.caption };
    render();
    persist();
  }
  function applyRecommendationHandoff(handoff) {
    if (!handoff) return;
    if (!isSampleMode() && (state.original === originalSample || state.product.title === 'Ek Onkar')) {
      state.original = '';
      state.image = '';
      state.imageMode = 'original';
      if (state.product.title === 'Ek Onkar') state.product.title = 'Featured Artwork';
      if (state.product.seller === 'Art of Sarabjit Singh') state.product.seller = '';
    }
    const existingTitle = String(state.product.title || '').trim();
    const isGenericTitle = !existingTitle || existingTitle === 'Ek Onkar' || existingTitle === 'Featured Artwork' || Boolean(state.product.placeholder);
    if (handoff.business_name) state.product.seller = handoff.business_name;
    if (handoff.product_name && (handoff.product_name !== handoff.business_name || isGenericTitle)) {
      state.product.title = handoff.product_name;
      delete state.product.placeholder;
    }
    if (handoff.price_claim !== undefined && handoff.price_claim !== '') {
      state.product.price = handoff.price_claim;
    }
    if (handoff.destination) {
      state.product.destination = normalizeDestination(handoff.destination);
    }
    if (handoff.channel && Object.hasOwn(names, String(handoff.channel).toLowerCase())) {
      state.channel = String(handoff.channel).toLowerCase();
      state.format = state.channel === 'tiktok' ? 'video' : (state.channel === 'x' ? 'text' : 'image');
    }
    state.goal = handoff.goal === 'gift' || offersServices() ? 'inquiries' : 'visits';
    state.selected = 0;
    state.idea_id = handoff.recommendation_id || handoff.id || null;
    state.why_this = handoff.why_this_fits || '';
    state.cta = handoff.cta || '';
    state.source = 'Selected recommendation';
    const hook = handoff.title || (state.product.placeholder ? '' : state.product.title) || (isSampleMode() ? 'Featured Artwork' : 'Something new to share');
    const caption = handoff.action || state.product.description || 'Share your work directly with buyers.';
    ['image', 'video', 'text'].forEach((fmt) => {
      state.edits[`${state.channel}:0:${fmt}`] = { hook, caption };
    });
    state.plans = {};
    state.revision += 1;
    populateSetup();
    render();
    persist();
  }
  const BUSY_BUTTONS = ['musePlan', 'museImage', 'findItems', 'readListing', 'getPost'];
  let lockedFocus = null;
  function lock(busy, activeId = '') {
    if (busy && document.activeElement && document.activeElement !== document.body) {
      lockedFocus = document.activeElement;
    }
    state.busy = busy;
    document.querySelectorAll('button, input, select, textarea').forEach(el => { el.disabled = busy; });
    for (const id of BUSY_BUTTONS) $(id)?.setAttribute('aria-busy', String(Boolean(busy && activeId === id)));
    document.body.classList.toggle('exporting', busy);
    if (!busy && lockedFocus && document.contains(lockedFocus) && !lockedFocus.disabled) {
      try { lockedFocus.focus({ preventScroll: true }); } catch {}
      lockedFocus = null;
    }
  }
  function invalidate() { state.revision += 1; $('reviewed').checked = false; }
  function currentPlan() { return state.plans[state.channel]; }
  function currentPost() { return currentPlan()?.posts?.[state.selected] || null; }
  const editKey = () => `${state.channel}:${state.selected}:${state.format}`;
  function currentCopy() { return { hook: $('postHook').value.trim(), caption: $('postCaption').value.trim() }; }
  function saveEdit() { state.edits[editKey()] = currentCopy(); invalidate(); $('copyCount').textContent = `${$('postCaption').value.length} characters`; persist(); paint(); }
  function formatCopy(post) {
    const stored = state.edits[editKey()];
    if (stored) return stored;
    if (!post) return { hook: state.product.title, caption: state.product.description };
    return { hook: post.hook, caption: post.caption };
  }
  function postIdentity() { return JSON.stringify([state.product.title, state.product.destination_url, state.channel, state.format, state.selected, currentCopy()]); }
  async function jsonRequest(path, payload, live = false) {
    if (isOfflineNow()) throw new Error('You appear to be offline. Your edits are saved on this device. Reconnect and try again.');
    const control = new AbortController(); const timer = setTimeout(() => control.abort(), live ? 285000 : 45000);
    try {
      const init = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: control.signal };
      const shell = window.museShell;
      // Saved-mode requests retry on network/5xx errors; billed live requests never auto-retry.
      const response = !live && shell?.fetch ? await shell.fetch(path, init, { safe: true, timeoutMs: 45000 }) : await fetch(path + (live ? '?live=true' : ''), init);
      if (live) { shell?.syncCredits?.(); if (response.headers?.get?.('X-Muse-Fallback')) shell?.toast?.('Live Muse was unavailable, so saved results are shown. No run was used.', 'warn'); }
      let data; try { data = await response.json(); } catch { throw new Error('The server could not finish. Your edits are still here.'); }
      if (!response.ok) {
        const detail = typeof data.detail === 'string' && !/<html|traceback/i.test(data.detail) ? data.detail : '';
        // The status travels with the message: a refused website scan (429) is not a finished try.
        const fail = (message) => Object.assign(new Error(message), { status: response.status });
        if (response.status === 401 || response.status === 403) throw fail(detail || 'Your session expired before Muse started, so no run was used. Sign in again; your edits are still here.');
        if (response.status === 402 || response.status === 429) throw fail(detail || 'You have reached your current run allowance. Check your plan or wait a moment; your edits are still here.');
        if (response.status >= 500) throw fail(detail || 'Muse is temporarily unavailable right now. No run was used and your edits are still here. Please try again shortly.');
        throw fail(detail || 'Check the item details and try again.');
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error(live ? 'Muse timed out and may still be processing. Check completion before paying for another request.' : 'That site is taking too long. Enter your item below.');
      if (isOfflineNow() || /failed to fetch|networkerror/i.test(error?.message || '')) throw new Error('You appear to be offline or Muse could not be reached. Your edits are still here. Reconnect and try again.');
      throw error;
    }
    finally { clearTimeout(timer); }
  }
  function planPayload(live) { return { product: { title: state.product.title, description: state.product.description, price: state.product.price || undefined, destination_url: safeURL(state.product.destination_url) || undefined, seller: state.product.seller, collection: state.product.collection }, channels: [state.channel], goal: state.goal, business_type: isEffectiveSample() ? undefined : (ownBusinessType || 'products'), sales_goal: state.salesGoal || undefined, performance: state.performance || undefined, use_muse: live }; }
  async function buildPlan(live = false, force = false) {
    if (state.busy) return;
    if (live && !liveReady()) return;
    if (!force && !live && currentPlan()) { render(); return; }
    // No item chosen yet: the local starter plan, never "Meet <placeholder label>" from the server.
    if (!live && state.product.placeholder) { state.plans[state.channel] = starterPlanForToday(state.product); state.selected = 0; invalidate(); render(); persist(); return; }
    const channel = state.channel; const revision = state.revision;
    const shouldLock = live || force;
    if (shouldLock) lock(true, live ? 'musePlan' : '');
    if (live) notice('Muse is writing three posts from your item and goal…', false, true);
    try {
      const plan = await jsonRequest('/api/v1/content-plan', planPayload(live), live);
      if (!Array.isArray(plan.posts) || plan.posts.length !== 3) throw new Error('No usable plan came back. Your existing post is unchanged.');
      if (state.revision !== revision || state.channel !== channel) return;
      state.plans[channel] = plan; state.selected = 0;
      if (live) { for (const key of Object.keys(state.edits)) if (key.startsWith(channel + ':')) delete state.edits[key]; notice('Muse plan ready. Check the words and make them yours.'); }
      invalidate(); render(); persist();
    } catch (error) { notice(error.message, true); }
    finally { if (shouldLock) lock(false); }
  }
  function render() {
    applyOfferWording();
    const plan = currentPlan(); const post = currentPost(); const copy = formatCopy(post);
    $('itemTitle').textContent = state.product.title; $('itemSource').textContent = state.source;
    $('dailyReason').textContent = state.why_this || `Start with ${state.product.title || 'your item'} on ${names[state.channel]}. Review, take it with you, done.`;
    $('postHook').value = copy.hook || ''; $('postCaption').value = copy.caption || ''; $('copyCount').textContent = `${(copy.caption || '').length} characters`;
    $('format').value = state.format;
    document.querySelectorAll('[data-channel]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.channel === state.channel)));
    $('planMode').textContent = plan?.mode === 'muse' ? 'Muse Spark draft' : 'Starter draft';
    const linkWords = isEffectiveSample() ? 'shop link' : 'link';
    const tips = {
      instagram: `Use the image for Feed. Put your ${linkWords} in your profile or a Story link sticker.`,
      facebook: `Add your ${linkWords} to the caption. Check linked Instagram sharing before posting twice.`,
      x: 'Keep one clear point and one link. Add an image description when you upload.',
      tiktok: 'Start with a visual hook. Use vertical video and captions; add suitable audio in TikTok.'
    };
    $('channelTip').textContent = tips[state.channel];
    const sampleWords = isEffectiveSample();
    $('visualDirection').textContent = post?.visual_direction || (sampleWords ? 'Show the original artwork clearly, then a detail and your invitation.' : 'Show your photo clearly, then one detail and your invitation.');
    const url = safeURL(state.product.destination_url); $('destinationLink').hidden = !url; if (url) $('destinationLink').href = url;
    $('destinationLink').textContent = `${shopLabel(state.product.destination)} ↗`;
    $('offerNote').textContent = state.product.price ? `${state.product.price} · confirm before posting` : 'No price included';
    $('imageNote').textContent = state.imageMode === 'live' ? (sampleWords ? 'Muse scene · compare artwork details' : 'Muse scene · compare it with your photo') : 'Original image · fitted without cropping';
    const label = state.format === 'text' ? 'Copy ready-to-post text' : state.format === 'video' ? 'Get short video + caption' : 'Get photo + caption'; $('getPost').textContent = label;
    $('deliveryNote').textContent = state.format === 'video' ? `Makes a silent 6-second ${sampleWords ? 'artwork clip' : 'clip from your image'}. Add voice or audio in your app. You post it yourself.` : state.format === 'text' ? 'Copies your post. Instagram and TikTok need a visual; use this text with your image or video.' : 'Downloads the image and copies your text. You post from your account.';
    $('postedStatus').textContent = state.posted[postIdentity()] ? 'Marked posted on this device' : '';
    $('noPhoto').hidden = !!state.image || state.format === 'text';
    if ($('uploadPhotoText')) $('uploadPhotoText').textContent = state.image ? 'Change photo' : 'Add photo';
    $('planCards').replaceChildren();
    const postsList = plan?.posts || [];
    for (const [i, item] of postsList.entries()) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'plan-card'; button.setAttribute('aria-pressed', String(i === state.selected));
      const timing = document.createElement('span'); timing.textContent = `${item.day_offset === 0 ? 'TODAY' : `IN ${item.day_offset} DAYS`} · ${names[item.channel]} · ${(i === state.selected ? state.format : item.format).toUpperCase()}`;
      const title = document.createElement('strong'); title.textContent = state.edits[`${state.channel}:${i}:${item.format}`]?.hook || item.hook;
      const tip = document.createElement('span'); tip.textContent = item.posting_tip;
      button.append(timing, title, tip);
      button.addEventListener('click', () => { if (state.busy) return; state.selected = i; state.format = item.format; invalidate(); render(); persist(); });
      button.addEventListener('keydown', event => {
        const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (!delta || !postsList.length || state.busy) return;
        event.preventDefault();
        const nextIdx = (i + delta + postsList.length) % postsList.length;
        state.selected = nextIdx;
        state.format = postsList[nextIdx].format;
        invalidate(); render(); persist();
        $('planCards').querySelectorAll('.plan-card')[nextIdx]?.focus();
      });
      $('planCards').append(button);
    }
    $('insightTitle').textContent = state.performance ? `${state.performance.clicks} shop clicks · ${state.performance.sales} sales` : 'Give people one clear next step.';
    $('insightAction').textContent = plan?.insight?.next_action || 'Post once, then note the visits or inquiries it brings.';
    $('resultsSource').textContent = (state.performance ? 'Your last-7-days counts · no post-level attribution' : 'No performance data added') + (state.salesGoal ? ` · weekly goal: ${state.salesGoal} sales${plan?.insight?.sales_remaining != null ? ` · ${plan.insight.sales_remaining} to go` : ''}` : '');
    $('sources').replaceChildren();
    for (const source of plan?.sources || []) { const url = safeURL(source.url); if (!url) continue; const a = document.createElement('a'); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = source.title; $('sources').append(a); }
    paint();
  }
  function loadImage(src) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('We could not open the photo. Choose a JPEG, PNG or WebP.')); image.src = src; }); }
  function fitText(ctx, text, x, y, width, size, maxLines = 2) {
    ctx.font = `${size}px Georgia`; const words = String(text).split(/\s+/); const lines = []; let line = '';
    for (const word of words) { const next = line ? `${line} ${word}` : word; if (ctx.measureText(next).width > width && line) { lines.push(line); line = word; } else line = next; }
    if (line) lines.push(line);
    if (lines.length > maxLines && size > 26) return fitText(ctx, text, x, y, width, size - 2, maxLines);
    lines.slice(0, maxLines).forEach((value, i) => ctx.fillText(value, x, y + i * (size + 10)));
  }
  async function layout(height, src = state.image, copy = currentCopy()) {
    const canvas = document.createElement('canvas'); canvas.width = 1080; canvas.height = height; const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f6f3eb'; ctx.fillRect(0, 0, 1080, height); ctx.fillStyle = '#253d34'; ctx.font = '25px sans-serif'; ctx.fillText((state.product.seller || 'Made with care').slice(0, 50), 80, 95);
    if (src) {
      const image = await loadImage(src);
      const area = { x: 80, y: 150, w: 920, h: height - 520 };
      const frame = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
      const scale = frame.fit === 'cover'
        ? Math.max(area.w / image.width, area.h / image.height)
        : Math.min(area.w / image.width, area.h / image.height);
      const w = image.width * scale;
      const h = image.height * scale;
      const offX = (Math.max(-50, Math.min(50, Number(frame.x) || 0)) / 100) * Math.abs(area.w - w);
      const offY = (Math.max(-50, Math.min(50, Number(frame.y) || 0)) / 100) * Math.abs(area.h - h);
      ctx.save?.();
      ctx.beginPath?.();
      ctx.rect?.(area.x, area.y, area.w, area.h);
      ctx.clip?.();
      ctx.drawImage(image, area.x + (area.w - w) / 2 + offX, area.y + (area.h - h) / 2 + offY, w, h);
      ctx.restore?.();
    }
    ctx.fillStyle = '#253d34'; fitText(ctx, copy.hook || state.product.title, 80, height - 280, 880, 46, 3);
    ctx.font = '24px sans-serif'; ctx.fillText((state.cta || currentPost()?.cta || 'Explore the work').slice(0, 55), 80, height - 95); return canvas;
  }
  function paint() { const token = ++state.paint; const height = state.format === 'video' ? 1920 : 1350; layout(height).then(canvas => { if (token !== state.paint) return; const preview = $('postCanvas'); preview.width = canvas.width; preview.height = canvas.height; preview.getContext('2d').drawImage(canvas, 0, 0); }).catch(error => notice(error.message, true)); }
  function saveBlob(blob, suffix) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${state.product.title.replace(/[^a-z0-9]+/gi, '-').slice(0, 45)}-${state.channel}-${suffix}`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
  function captionText() { const copy = currentCopy(); const url = safeURL(state.product.destination_url); let text = `${copy.hook}\n\n${copy.caption}`; const cta = state.cta || currentPost()?.cta; if (cta && !text.includes(cta)) text += `\n\n${cta}`; if (url && ['facebook', 'x'].includes(state.channel) && !text.includes(url)) text += `\n\n${url}`; if (url && ['instagram', 'tiktok'].includes(state.channel) && !/profile link|link in my profile/i.test(text)) text += isEffectiveSample() ? '\n\nExplore the work through the link in my profile.' : `\n\nLearn more about this ${offerWords()} through the link in my profile.`; return text; }
  async function copyText() {
    const text = captionText(); let timeout;
    try {
      await Promise.race([navigator.clipboard.writeText(text), new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Clipboard unavailable')), 1500); })]);
      return true;
    } catch { saveBlob(new Blob([text], { type: 'text/plain' }), 'caption.txt'); return false; }
    finally { clearTimeout(timeout); }
  }
  function reviewed() {
    if (state.format !== 'text' && !state.image) { notice('Add the matching product photo first.', true, false, { text: 'Add photo', onClick: promptPhotoUpload }); return false; }
    if (!$('reviewed').checked) { notice('Check the image, words and destination, then tick the review box.', true); $('reviewed').focus(); return false; }
    if (!currentCopy().hook || !currentCopy().caption) { notice('Add an opening line and caption.', true); return false; }
    if (state.channel === 'x' && captionText().length > 280) { notice('Shorten your X post to 280 characters including the link.', true); return false; }
    return true;
  }
  async function makeClip() {
    if (typeof MediaRecorder === 'undefined' || typeof HTMLCanvasElement.prototype.captureStream !== 'function') throw new Error('Video export is unavailable in this browser. Download a photo or follow the video direction in your plan.');
    const source = await layout(1920); const canvas = document.createElement('canvas'); canvas.width = 1080; canvas.height = 1920; const ctx = canvas.getContext('2d'); ctx.drawImage(source, 0, 0);
    const stream = canvas.captureStream(12); const mime = ['video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
    if (!mime) { stream.getTracks().forEach(track => track.stop()); throw new Error('No supported video format. Use the photo export or your phone camera.'); }
    return new Promise((resolve, reject) => {
      const chunks = []; let frame = 0; let animation; const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 3000000 });
      const cleanup = () => { cancelAnimationFrame(animation); stream.getTracks().forEach(track => track.stop()); };
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { cleanup(); reject(new Error('Video export failed. Your photo and words are still ready.')); };
      recorder.onstop = () => { cleanup(); const blob = new Blob(chunks, { type: mime.split(';')[0] }); if (!blob.size) reject(new Error('Video export was empty. Try the photo format.')); else resolve(blob); };
      recorder.start(); const started = performance.now();
      const draw = () => { ctx.drawImage(source, 0, 0); frame += 1; const seconds = (performance.now() - started) / 1000; const alpha = .1 + .05 * Math.sin(frame / 12); ctx.fillStyle = `rgba(39,83,68,${alpha})`; ctx.fillRect(80, 1825, Math.min(920, seconds / 6 * 920), 5); if (seconds >= 6) recorder.stop(); else animation = requestAnimationFrame(draw); }; animation = requestAnimationFrame(draw);
    });
  }
  async function getPost() {
    if (state.busy || !reviewed()) return; lock(true, 'getPost');
    try {
      if (state.format === 'text') { await copyText(); notice('Text ready. Paste it into your post.'); return; }
      notice(state.format === 'video' ? 'Preparing your six-second clip… Keep this tab open.' : 'Preparing your post…', false, true);
      const blob = state.format === 'video' ? await makeClip() : await new Promise(async (resolve, reject) => { try { (await layout(1350)).toBlob(value => value ? resolve(value) : reject(new Error('Could not export the image.')), 'image/png'); } catch (error) { reject(error); } });
      saveBlob(blob, state.format === 'video' ? `clip.${blob.type === 'video/mp4' ? 'mp4' : 'webm'}` : 'feed.png'); const copied = await copyText();
      window.museTrack?.('post_downloaded', { placement: state.format || 'feed', page: '/today' });
      markIdeaExported();
      notice(`${state.format === 'video' ? 'Clip' : 'Image'} downloaded. ${copied ? 'Caption copied' : 'Caption downloaded'}. Open ${names[state.channel]} and add your post.`);
    } catch (error) { notice(error.message, true); } finally { lock(false); }
  }
  function populateSetup() {
    syncDestinationOptions();
    const p = state.product; $('productName').value = p.placeholder ? '' : p.title; $('sellerName').value = p.seller || ''; $('productDescription').value = p.description || ''; $('destination').value = p.destination || 'other'; $('price').value = p.price || ''; $('productLink').value = p.destination_url || ''; $('collection').value = p.collection || ''; $('goal').value = state.goal; $('salesGoal').value = state.salesGoal || '';
  }
  function openSetup() {
    if (state.busy) return;
    setupBackup = JSON.parse(JSON.stringify({ product: state.product, original: state.original, image: state.image, imageMode: state.imageMode, source: state.source, goal: state.goal, salesGoal: state.salesGoal, performance: state.performance, plans: state.plans, edits: state.edits, offers: state.offers, selected: state.selected }));
    populateSetup(); $('setup').showModal();
  }
  function cancelSetup() { if (state.busy) return; if (setupBackup) Object.assign(state, setupBackup); setupBackup = null; invalidate(); render(); $('setup').close(); }
  async function applyItem(event) {
    event.preventDefault(); if (state.busy) return;
    const url = $('productLink').value.trim(); if (url && !safeURL(url)) { notice('Use a complete http or https listing link.', true); return; }
    const product = { title: $('productName').value.trim(), seller: $('sellerName').value.trim(), description: $('productDescription').value.trim(), price: $('price').value.trim(), destination_url: safeURL(url), destination: $('destination').value, collection: $('collection').value.trim() };
    if (!product.title) return;
    if (product.title !== state.product.title && state.original === originalSample) { state.original = ''; state.image = ''; state.source = 'Your item · add a matching photo'; }
    state.product = product; state.goal = $('goal').value; state.salesGoal = Number($('salesGoal').value) || null; state.plans = {}; state.edits = {}; state.selected = 0; setupBackup = null; invalidate(); $('setup').close(); await buildPlan(false, true); persist();
  }
  function draftDestination() {
    const old = state.product.destination; state.offers[old] = { price: $('price').value, url: $('productLink').value };
    const next = $('destination').value; const offer = state.offers[next] || { price: '', url: '' }; state.product.destination = next; $('price').value = offer.price; $('productLink').value = offer.url;
    $('itemHint').textContent = isEffectiveSample()
      ? `${shopLabel(next)} keeps its own price and link. Choose a matching listing; other shops may carry different work.`
      : `${shopLabel(next)} keeps its own price and link. Choose the matching page for this ${offerWords()}.`;
  }
  const TODAY_SAMPLE_ORIGINALS = [
    { id: 'sample-orig-ek-onkar', title: 'Ek Onkar — Original artwork', image_data_url: '/samples/ek_onkar_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' },
    { id: 'sample-orig-naam-japo', title: 'Naam Japo — Original artwork', image_data_url: '/samples/naam_japo_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' },
    { id: 'sample-orig-kirat-karo', title: 'Kirat Karo — Original artwork', image_data_url: '/samples/kirat_karo_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' }
  ];
  const TODAY_SAMPLE_GENERATED = [
    { id: 'sample-gen-ek-onkar', title: 'Ek Onkar collector room (Saved AI scene)', image_data_url: '/samples/ek_onkar_collector_room_live.webp', source_url: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' },
    { id: 'sample-gen-naam-japo', title: 'Naam Japo gallery wall (Saved AI scene)', image_data_url: '/samples/naam_japo_restored_gallery_live.webp', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' },
    { id: 'sample-gen-kirat-karo', title: 'Kirat Karo collector room (Saved AI scene)', image_data_url: '/samples/kirat_karo_collector_room_live.webp', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' }
  ];
  const IMAGE_EMPTY_MSG = 'We couldn’t retrieve an image from this page. Try an artwork/product link or upload a photo.';
  let todayImageSource = isEffectiveSample() ? 'sample' : 'website';
  let todayWebsiteCandidates = [];
  let todayImgController = null;
  let todayImgSeq = 0;

  function abortTodayImageFetch() {
    todayImgSeq += 1;
    if (todayImgController) {
      try { todayImgController.abort(); } catch {}
      todayImgController = null;
    }
  }

  function syncTodayFrameControls() {
    const f = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    if ($('todayCropToggle')) $('todayCropToggle').textContent = f.fit === 'cover' ? 'Fill / Crop (active)' : 'Fit full image';
    if ($('todayFrameX')) $('todayFrameX').value = String(Number.isFinite(Number(f.x)) ? Number(f.x) : 0);
    if ($('todayFrameY')) $('todayFrameY').value = String(Number.isFinite(Number(f.y)) ? Number(f.y) : 0);
  }

  function formatTodayImageNote(meta) {
    if (!meta) return '';
    const dims = meta.width && meta.height ? `${meta.width} × ${meta.height} px` : 'Size unknown';
    if (meta.isLowRes) return `Low-res web preview (${dims}): fine for social posts, not for printing.`;
    if (meta.provenance === 'sample_original') return `Original artwork preview (${dims}) · Sample studio.`;
    if (meta.provenance === 'sample_generated') return `Saved AI ad example (${dims}) · Staging example.`;
    if (meta.provenance === 'upload') return `Uploaded photo (${dims}) · Kept on this device.`;
    return `Selected from your website (${dims}) · Confirm it matches your work.`;
  }

  function selectTodayCandidateImage(item) {
    if (!item || !item.image_data_url) return;
    if (!isEffectiveSample() && item.provenance?.startsWith('sample_')) return;
    state.original = item.image_data_url;
    state.image = item.image_data_url;
    state.imageMode = item.provenance === 'sample_generated' ? 'live' : 'original';
    state.imageFrame = { fit: 'contain', x: 0, y: 0 };
    state.imageMeta = {
      id: item.id || '',
      title: String(item.title || 'Selected image').slice(0, 160),
      sourceUrl: safeURL(item.source_url) || '',
      imageUrl: safeURL(item.image_url) || '',
      width: item.width || null,
      height: item.height || null,
      isLowRes: Boolean(item.is_low_res),
      provenance: item.provenance || 'website',
      confirmed: true,
    };
    state.source = formatTodayImageNote(state.imageMeta);
    syncTodayFrameControls();
    invalidate();
    render();
    renderTodayImagePicker();
    persist();
    notice('Image selected. You can reposition, crop, or swap it anytime.');
  }

  function renderTodayCandidateCard(item) {
    const card = document.createElement('div');
    card.className = 'muse-image-card' + (state.original && state.original === item.image_data_url ? ' is-selected' : '');
    const img = document.createElement('img');
    img.src = item.image_data_url;
    img.alt = String(item.title || 'Product candidate');
    card.append(img);

    const titleEl = document.createElement('strong');
    titleEl.textContent = String(item.title || 'Found on page');
    card.append(titleEl);

    const metaEl = document.createElement('span');
    metaEl.className = 'muse-image-meta';
    const dims = item.width && item.height ? `${item.width} × ${item.height} px` : 'Dimensions unknown';
    metaEl.textContent = item.source_label ? `${item.source_label} · ${dims}` : dims;
    card.append(metaEl);

    if (item.is_low_res) {
      const warn = document.createElement('span');
      warn.className = 'muse-image-warn';
      warn.textContent = `Low-resolution web preview (${dims}): fine for social posts, not for printing.`;
      card.append(warn);
    }

    const srcHref = safeURL(item.source_url);
    if (srcHref) {
      const a = document.createElement('a');
      a.href = srcHref;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = 'Source page ↗';
      card.append(a);
    }

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'secondary';
    btn.textContent = state.original === item.image_data_url ? 'Selected ✓' : 'Use this image';
    btn.setAttribute('data-use-image-id', String(item.id || ''));
    btn.addEventListener('click', () => selectTodayCandidateImage(item));
    card.append(btn);
    return card;
  }

  function renderTodayImagePicker() {
    const picker = $('todayImagePicker');
    const grid = $('todayImageCandidatesGrid');
    const status = $('todayImagePickerStatus');
    const sampleBtn = $('todayImgSrcSampleBtn');
    const websiteBtn = $('todayImgSrcWebsiteBtn');
    const confirmEl = $('todayImagePickerConfirm');
    if (!picker || !grid || !status) return;

    const inSample = isEffectiveSample();
    if (sampleBtn) sampleBtn.hidden = !inSample;
    if (!inSample && todayImageSource === 'sample') todayImageSource = 'website';
    if (websiteBtn) websiteBtn.classList.toggle('is-active', todayImageSource === 'website');
    if (sampleBtn) sampleBtn.classList.toggle('is-active', inSample && todayImageSource === 'sample');
    if (confirmEl) confirmEl.textContent = state.imageMeta ? formatTodayImageNote(state.imageMeta) : '';

    grid.replaceChildren();
    if (inSample && todayImageSource === 'sample') {
      status.textContent = 'Checked-in sample artwork (originals separated from saved AI examples).';
      const origHeading = document.createElement('div');
      origHeading.className = 'muse-image-group-title';
      origHeading.textContent = 'Original artwork';
      grid.append(origHeading);
      for (const art of TODAY_SAMPLE_ORIGINALS) grid.append(renderTodayCandidateCard(art));

      const genHeading = document.createElement('div');
      genHeading.className = 'muse-image-group-title';
      genHeading.textContent = 'Saved generated ad examples';
      grid.append(genHeading);
      for (const art of TODAY_SAMPLE_GENERATED) grid.append(renderTodayCandidateCard(art));
      return;
    }

    if (!todayWebsiteCandidates.length) {
      if (!status.dataset.explicitMessage) {
        status.textContent = isEffectiveSample()
          ? 'Enter your shop or product URL above to browse verified images, or upload your own photo.'
          : 'Enter your website or one of its pages above to see its images, or upload your own photo.';
      }
      return;
    }
    status.textContent = `Found ${todayWebsiteCandidates.length} image option${todayWebsiteCandidates.length === 1 ? '' : 's'} on your page. Select “Use this image” to apply.`;
    for (const item of todayWebsiteCandidates) grid.append(renderTodayCandidateCard(item));
  }

  async function useReference(url, { preserveExisting = false, selectIfEmpty = true } = {}) {
    const ownerEpoch = draftEpoch;
    const safe = safeURL(url); if (!safe) throw new Error('Enter a complete shop or listing link.');
    abortTodayImageFetch();
    const seq = ++todayImgSeq;
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    todayImgController = controller;
    const statusEl = $('todayImagePickerStatus');
    if (statusEl) {
      delete statusEl.dataset.explicitMessage;
      statusEl.textContent = 'Checking this page for product & artwork images…';
    }
    try {
      const response = await fetch('/api/v1/product-reference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: safe }),
        signal: controller?.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not read listing.');
      if (ownerEpoch !== draftEpoch || seq !== todayImgSeq) return;

      const hadPhoto = Boolean(state.original);
      const hasEdits = Object.keys(state.edits || {}).length > 0;
      if (!preserveExisting || (!hasEdits && !hadPhoto)) {
        state.product = { title: data.title || new URL(safe).hostname, description: data.description || '', price: data.price_hint || '', seller: new URL(safe).hostname, destination_url: safeURL(data.url) || safe, destination: 'other', collection: '' };
        state.offers = {}; state.plans = {}; state.selected = 0; state.performance = null;
        if (!preserveExisting) state.edits = {};
      }

      const candidates = Array.isArray(data.image_candidates) && data.image_candidates.length
        ? data.image_candidates
        : (inline(data.image_data_url) ? [{ id: 'web-1', image_data_url: data.image_data_url, source_url: data.url || safe, title: data.title || new URL(safe).hostname, width: data.image_width || null, height: data.image_height || null, is_low_res: Boolean(data.is_low_res), provenance: 'website' }] : []);
      todayWebsiteCandidates = candidates;
      if (!candidates.length && statusEl) {
        statusEl.dataset.explicitMessage = '1';
        statusEl.textContent = IMAGE_EMPTY_MSG;
      }
      if (!preserveExisting) {
        const first = candidates[0] || null;
        state.original = first ? first.image_data_url : '';
        state.image = state.original;
        state.imageMode = 'original';
        state.imageMeta = first ? { id: first.id, title: first.title, sourceUrl: safeURL(first.source_url) || safe, imageUrl: safeURL(first.image_url) || '', width: first.width || null, height: first.height || null, isLowRes: Boolean(first.is_low_res), provenance: 'website', confirmed: true } : null;
        state.source = first ? formatTodayImageNote(state.imageMeta) : `From ${new URL(safe).hostname} · check product facts`;
      } else if (!hadPhoto && selectIfEmpty && candidates[0]) {
        const first = candidates[0];
        state.original = first.image_data_url;
        state.image = first.image_data_url;
        state.imageMode = 'original';
        state.imageMeta = { id: first.id, title: first.title, sourceUrl: safeURL(first.source_url) || safe, imageUrl: safeURL(first.image_url) || '', width: first.width || null, height: first.height || null, isLowRes: Boolean(first.is_low_res), provenance: 'website', confirmed: true };
        state.source = formatTodayImageNote(state.imageMeta);
      }
      invalidate(); populateSetup(); renderTodayImagePicker();
      if ($('importStatus')) $('importStatus').textContent = candidates.length ? (data.source_note || 'Listing ready. Choose an image or check details.') : IMAGE_EMPTY_MSG;
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (ownerEpoch !== draftEpoch || seq !== todayImgSeq) return;
      todayWebsiteCandidates = [];
      if (statusEl) {
        statusEl.dataset.explicitMessage = '1';
        statusEl.textContent = IMAGE_EMPTY_MSG;
      }
      renderTodayImagePicker();
      throw err;
    } finally {
      if (todayImgController === controller) todayImgController = null;
    }
  }
  async function readListing() {
    if (state.busy) return;
    lock(true, 'readListing'); $('importStatus').classList?.add?.('busy'); $('importStatus').textContent = 'Reading listing details…';
    try { await useReference($('shopUrl').value); notice('Listing selected. Check its details, then use this item.'); }
    catch (error) { $('importStatus').textContent = error.message; }
    finally { $('importStatus').classList?.remove?.('busy'); lock(false); }
  }
  async function persistShopWebsiteUrl(rawUrl) {
    const clean = safeURL(rawUrl);
    if (!clean) { notice('Enter a valid shop website starting with https:// or http://.', true); return false; }
    const mode = window.museModes?.current?.();
    if (!mode || mode.state !== 'account_own' || !mode.ownerId || !window.museAccount?.loadWorkspace || !window.museAccount?.saveWorkspace) {
      notice('Sign in and switch to My workspace to save your shop website across visits.', true);
      return false;
    }
    const guard = window.museModes.bindAsyncGuard();
    try {
      const ws = await window.museAccount.loadWorkspace(mode.ownerId);
      if (!guard.isCurrent()) return false;
      const existingDoc = ws?.document && typeof ws.document === 'object' ? ws.document : {};
      const existingOnb = existingDoc.onboarding && typeof existingDoc.onboarding === 'object' ? existingDoc.onboarding : {};
      const currentUrls = Array.isArray(existingOnb.shop_urls) ? existingOnb.shop_urls.filter(Boolean) : [];
      const nextUrls = [clean, ...currentUrls.filter((u) => u !== clean)].slice(0, 6);
      const nextDoc = { ...existingDoc, onboarding: { ...existingOnb, shop_urls: nextUrls } };
      await window.museAccount.saveWorkspace(nextDoc, mode.ownerId);
      if (!guard.isCurrent()) return false;
      state.shopWebsiteUrl = clean;
      if ($('savedShopWebsiteNote')) $('savedShopWebsiteNote').textContent = `Saved website: ${clean}`;
      if ($('quickShopUrl') && !$('quickShopUrl').value) $('quickShopUrl').value = clean;
      notice(`Saved ${clean} as your shop website in My workspace.`);
      return true;
    } catch (error) {
      if (guard.isCurrent()) notice(error?.message || 'Could not save your shop website right now.', true);
      return false;
    }
  }
  function listingChoices(data) {
    const items = (data?.discovered_catalog_items || []).filter(item => safeURL(item.url));
    const products = items.filter(item => ['products', 'listings'].includes(item.bucket));
    return products.length ? products : items;
  }
  // An import clears the three-post plan when it replaces the item. buildPlan returns early
  // while the page is locked, so release the lock first and let it take its own. A plan the
  // seller already has (which may be a paid Muse plan) is kept, never rebuilt.
  async function planAfterImport() {
    lock(false);
    if (!currentPlan()) await buildPlan(false, true);
  }
  function renderListingChoices(choices) {
    $('importItems').replaceChildren();
    for (const [i, item] of choices.entries()) { const button = document.createElement('button'); button.type = 'button'; button.textContent = `${i === 0 ? 'Suggested: ' : ''}${item.title || 'View listing'}`; button.addEventListener('click', async () => { if (state.busy) return; lock(true, 'readListing'); try { await useReference(item.url, { preserveExisting: true, selectIfEmpty: false }); render(); await planAfterImport(); persist(); } catch (error) { $('importStatus').textContent = error.message; notice(error.message, true); } finally { lock(false); } }); $('importItems').append(button); }
  }

  // First visit on this device. The account workspace says when the seller has a saved shop
  // website (see autoImportPending in workspace-modes.js). When My workspace opens here with
  // that signal and a draft that is still the untouched placeholder, the seller's own listings
  // are brought in without a click, once per device. The scan is a public crawl (no Muse run) and
  // does not lock the page; only the short step that applies the first listing does.
  let autoImportRunning = false;
  function placeholderDraft(shopName = '') {
    if (state.original || state.image || Object.keys(state.edits || {}).length) return false;
    const title = state.product?.title || '';
    return Boolean(state.product?.placeholder) || legacyPlaceholder(title) || title === neutralProduct(shopName).title || title === neutralProduct().title;
  }
  async function autoImportSavedShop(owner, shopName = '', workspace = null) {
    const modes = window.museModes;
    if (autoImportRunning || !owner || !modes?.autoImportPending?.(owner, 'today', workspace)) return;
    const url = safeURL(state.shopWebsiteUrl);
    // Nothing to bring in, or the seller is already working on something here: do not ask again.
    if (!url || !placeholderDraft(shopName)) { modes.finishAutoImport?.(owner, 'today'); return; }
    // The scan looks for product listings; a services website has none to find.
    if (offersServices()) {
      modes.finishAutoImport?.(owner, 'today');
      if ($('importStatus')) $('importStatus').textContent = 'Name a service or offer below, or paste a link to one of your pages.';
      return;
    }
    // Busy or offline: try again on the next visit.
    if (state.busy || isOfflineNow()) return;
    const epoch = draftEpoch;
    const host = new URL(url).hostname.replace(/^www\./, '');
    const current = () => epoch === draftEpoch && draftReady && draftOwner === owner && !isEffectiveSample();
    const status = text => { if ($('importStatus')) $('importStatus').textContent = text; };
    const count = n => `${n} listing${n === 1 ? '' : 's'}`;
    let tried = false;
    autoImportRunning = true;
    const looking = `Looking for your listings on ${host}, your saved shop website. You can keep working.`;
    status(looking);
    notice(looking, false, true);
    try {
      const data = await jsonRequest('/api/v1/ingest-storefront', { website_url: url, business_name: shopName || host, max_urls_per_source: 20 });
      if (!current()) return;
      const choices = listingChoices(data);
      if (!choices.length) {
        tried = true;
        status('No listings found automatically. Paste a product link or enter your item below.');
        notice(`We could not find listings on ${host} automatically. Paste a product link above, or choose “Enter details manually”.`);
        return;
      }
      renderListingChoices(choices);
      if (state.busy || !placeholderDraft(shopName)) {
        // The seller started on something while the scan ran: offer the listings, change nothing.
        tried = true;
        status(`Found ${count(choices.length)} on ${host}. Choose one to use it.`);
        notice(`Found ${count(choices.length)} on ${host}. Choose “Change” to pick one. Your draft is unchanged.`);
        return;
      }
      let opened = true;
      lock(true, 'findItems');
      try { await useReference(choices[0].url, { preserveExisting: true, selectIfEmpty: false }); }
      catch { opened = false; }
      finally { lock(false); }
      if (!current()) return;
      if (!opened) {
        tried = true;
        status(`Found ${count(choices.length)} on ${host}. Choose one to use it.`);
        notice(`Found ${count(choices.length)} on ${host}, but could not open the first one. Choose “Change” to pick a listing.`);
        return;
      }
      // A workspace refresh can cancel the listing read; try again on the next visit.
      if (placeholderDraft(shopName)) return;
      tried = true;
      state.source = `From ${host} · check product facts`;
      state.why_this = '';
      render();
      await planAfterImport();
      if (!current()) return;
      persist();
      status(`Listings loaded from ${host}. Choose an image in “Choose an image” or select another listing.`);
      notice(`Started with “${state.product.title}” from ${host}. Choose an image below, or choose “Change” to pick another listing.`);
    } catch (error) {
      if (!current()) return;
      // Too many scans from this connection: Muse did not try, so the next visit tries again.
      if (error?.status === 429) {
        status(error.message);
        notice(error.message);
        return;
      }
      tried = true;
      status(`We could not read ${host} automatically. ${error?.message || ''}`.trim());
      notice(`We could not read ${host} automatically. Choose “Find products” to try again, or enter your item manually.`);
    } finally {
      autoImportRunning = false;
      if (tried) modes.finishAutoImport?.(owner, 'today');
      // Abandoned part-way (workspace switched or refreshed): never leave "Looking…" on screen.
      if ($('importStatus')?.textContent === looking) status('Pick from your shop, or enter an item below.');
      if ($('notice')?.textContent === looking) { $('notice').hidden = true; $('notice').className = ''; $('notice').textContent = ''; }
    }
  }
  async function findItems(sourceOverride = '') {
    const ownerEpoch = draftEpoch;
    if (state.busy) return;
    const raw = (typeof sourceOverride === 'string' && sourceOverride ? sourceOverride : ($('shopUrl')?.value || $('quickShopUrl')?.value || '')).trim();
    const url = safeURL(raw);
    if (!url) {
      $('importStatus').textContent = 'Enter a full shop URL.';
      notice('Enter your shop website starting with https://.', true);
      ($('quickShopUrl') || $('shopUrl'))?.focus?.();
      return;
    }
    if ($('shopUrl')) $('shopUrl').value = url;
    if ($('quickShopUrl')) $('quickShopUrl').value = url;
    lock(true, 'findItems'); $('importStatus').classList?.add?.('busy'); $('importStatus').textContent = 'Finding a product for your next post…'; $('importItems').replaceChildren();
    notice('Scanning your website for products… Your current draft stays intact.', false, true);
    try {
      const data = await jsonRequest('/api/v1/ingest-storefront', { website_url: url, business_name: new URL(url).hostname, max_urls_per_source: 20 });
      if (ownerEpoch !== draftEpoch) return;
      const choices = listingChoices(data);
      const fetched = (data.channels || []).some(channel => channel.status === 'fetched');
      if (fetched && $('saveShopWebsite')?.checked && !isEffectiveSample()) {
        await persistShopWebsiteUrl(url);
      }
      if (!choices.length) {
        $('importStatus').textContent = 'No items found. Paste a product link or enter one below.';
        notice('No product listings came back automatically. Enter your item details below; your draft is still here.');
        return;
      }
      renderListingChoices(choices);
      await useReference(choices[0].url, { preserveExisting: true, selectIfEmpty: false });
      if (ownerEpoch !== draftEpoch) return;
      render();
      await planAfterImport();
      persist();
      $('importStatus').textContent = 'Listings loaded. Choose an image in “Choose an image” or select a listing.';
      notice('Website scanned. Your draft and photo are kept; choose an image below when ready.');
    } catch (error) {
      $('importStatus').textContent = error.message;
      notice(`${error.message} Your existing draft is intact.`, true);
    } finally { $('importStatus').classList?.remove?.('busy'); lock(false); }
  }
  async function upload(file) {
    const ownerEpoch = draftEpoch;
    if (!file || state.busy) return; if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10000000) { notice('Choose a JPEG, PNG or WebP under 10 MB.', true); return; }
    const url = URL.createObjectURL(file); lock(true);
    try { const image = await loadImage(url); if (ownerEpoch !== draftEpoch) return; const canvas = document.createElement('canvas'); const scale = Math.min(1, 1400 / Math.max(image.width, image.height)); canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale); const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height); const data = canvas.toDataURL('image/jpeg', .8); if (!inline(data)) throw new Error('Try a smaller photo.'); state.original = data; state.image = data; state.imageMode = 'original'; state.imageFrame = { fit: 'contain', x: 0, y: 0 }; state.imageMeta = { id: 'upload-local', title: file.name || 'Uploaded product photo', sourceUrl: '', width: image.width, height: image.height, isLowRes: Math.min(image.width, image.height) < 600 || Math.max(image.width, image.height) < 800, provenance: 'upload', confirmed: true }; state.source = formatTodayImageNote(state.imageMeta); syncTodayFrameControls(); invalidate(); render(); renderTodayImagePicker(); persist(); notice('Photo ready. Check your post and take it with you.'); }
    catch (error) { notice(error.message, true); } finally { URL.revokeObjectURL(url); lock(false); }
  }
  // Signed-in accounts with verified emails and runs left unlock live Muse AI (1 run per live request).
  function syncAccountLive(snapshot = window.museAccount?.getSnapshot?.()) {
    const toggle = $('liveMode');
    const note = $('readinessNote');
    const musePlanBtn = $('musePlan');
    const planLabel = $('musePlan');
    const configured = state.readiness ? state.readiness.provider_key_configured === true : null;
    if (configured === false) {
      state.live = false;
      if (toggle) { toggle.checked = false; toggle.disabled = true; }
      if (musePlanBtn) musePlanBtn.disabled = true;
      if (note) note.textContent = 'Live Muse AI is not available yet. Starter plans and exports (0 runs) still work.';
      return;
    }
    const eligible = !!(snapshot?.user?.email_verified && snapshot?.live_available);
    const hasAccountReq = state.readiness?.accounts_required === true || typeof window.museAccount !== 'undefined';
    if (hasAccountReq) {
      state.live = eligible && (toggle ? toggle.checked !== false || !state.live : true);
      if (!eligible) state.live = false;
      if (toggle) { toggle.disabled = !eligible; toggle.checked = eligible && state.live; }
      if (musePlanBtn) musePlanBtn.disabled = !eligible;
    } else if (toggle) {
      toggle.disabled = false;
    }
    if (!note) return;
    if (snapshot?.auth_status === 'error' || snapshot?.auth_status === 'expired') {
      note.textContent = 'Account check needs attention above. Local editing uses 0 runs.';
      return;
    }
    if (!snapshot?.user) {
      note.textContent = 'Starter plans & editing use 0 runs. Sign in with a verified email for live Muse AI (1 run per live request).';
      return;
    }
    if (!snapshot.user.email_verified) {
      note.textContent = `Signed in as ${snapshot.user.email || 'your account'}. Verify your email to unlock live Muse AI (1 run per live request). Starter plans use 0 runs.`;
      return;
    }
    if (!snapshot.live_available) {
      note.textContent = `Signed in as ${snapshot.user.email || 'your account'} · 0 live runs left (${snapshot.runs_remaining ?? 0}). Starter plans & exports use 0 runs.`;
      return;
    }
    const runs = snapshot?.usage && Number.isFinite(snapshot.usage.remaining) ? Math.max(0, snapshot.usage.remaining) : snapshot?.runs_remaining;
    const runsText = typeof runs === 'number' ? `${runs} run${runs === 1 ? '' : 's'} remaining` : 'active plan';
    note.textContent = `Signed in as ${snapshot.user.email || 'your account'} · ${runsText} · 1 run per live Muse request · Starter plans use 0 runs.`;
    void planLabel;
  }
  if (typeof window.addEventListener === 'function') {
    window.addEventListener('muse:account-change', (event) => syncAccountLive(event.detail));
    window.addEventListener('account-change', (event) => syncAccountLive(event.detail));
  }
  function liveReady() {
    if (!state.readiness?.provider_key_configured) { notice('Live Muse AI is not available yet. Starter drafts still work with 0 runs.', true); return false; }
    const needsAccount = state.readiness?.accounts_required === true || typeof window.museAccount !== 'undefined';
    if (!needsAccount) {
      if (!state.live) { notice('Enable live Muse AI above (uses 1 run per live request) first.', true); return false; }
      return true;
    }
    if (window.museAccount?.liveReady?.() !== true) {
      const snap = window.museAccount?.getSnapshot?.();
      if (!snap?.user) notice('Sign in to use live Muse AI (1 run per request). Manual editing uses 0 runs.', true);
      else if (!snap.user.email_verified) notice('Verify your email to unlock live Muse AI (1 run per request).', true);
      else notice('No live runs remaining on your plan right now. Starter plans use 0 runs.', true);
      return false;
    }
    if ($('liveMode') && !$('liveMode').checked) { notice('Turn on Enable live Muse AI above (1 run per live request) first.', true); return false; }
    state.live = true;
    return true;
  }
  async function museImage() {
    const ownerEpoch = draftEpoch;
    if (state.busy || !liveReady()) return; if (!state.original) { notice('Add your original photo first.', true, false, { text: 'Add photo', onClick: promptPhotoUpload }); return; }
    lock(true, 'museImage'); notice('Muse is creating a new scene. This is a billed image request…', false, true);
    try {
      let data = state.original; if (!inline(data)) { const response = await fetch(data); if (!response.ok) throw new Error('Could not load your source photo.'); data = await new Promise((resolve, reject) => { response.blob().then(blob => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob); }).catch(reject); }); }
      const copy = currentCopy(); const prompt = $('scenePrompt').value.trim(); if (!prompt || !copy.hook || !copy.caption) throw new Error('Add a scene, opening line and caption first.');
      if (ownerEpoch !== draftEpoch) return;
      const response = await jsonRequest('/api/v1/generate-ads', { product: { title: state.product.title, description: state.product.description, price: state.product.price || undefined, image_base64: data }, draft: false, placements: ['instagram_feed'], variants_per_placement: 1, use_comfyui: false, muse_workflow_mode: 'product_visuals', brief: { product_title: state.product.title, positioning_hook: copy.hook, estimated_paid_calls: 1, preserve_product_note: 'Compare with original before posting.', variants: [{ variant_id: 'daily1', placement: 'instagram_feed', include: true, headline: copy.hook.slice(0, 120), primary_text: copy.caption.slice(0, 600), image_prompt: prompt }] } }, true);
      const creative = response.creatives?.[0];
      const assetUrl = mediaAsset(creative?.media_asset_url) ? creative.media_asset_url : '';
      const inlineUrl = inline(creative?.media_data_url) ? creative.media_data_url : '';
      const nextImage = assetUrl || inlineUrl;
      if (!creative || String(creative.produced_by).startsWith('demo-cache') || !nextImage) throw new Error('No usable new image delivered. Check completion before regenerating. Your original is still here.');
      let chosenImage = nextImage;
      try {
        await loadImage(chosenImage);
      } catch (imgErr) {
        if (assetUrl && inlineUrl) {
          chosenImage = inlineUrl;
          await loadImage(chosenImage);
        } else {
          throw imgErr;
        }
      }
      if (ownerEpoch !== draftEpoch) return;
      state.image = chosenImage; state.imageMode = 'live'; invalidate(); render(); persist(); notice('Muse scene ready. Compare the artwork with your original before using it.');
    } catch (error) { notice(error.message, true); } finally { lock(false); }
  }
  for (const id of ['openSetup', 'changeItem']) $(id).addEventListener('click', openSetup);
  $('closeSetup').addEventListener('click', cancelSetup);
  $('setup').addEventListener('cancel', event => { event.preventDefault(); cancelSetup(); });
  $('itemForm').addEventListener('submit', applyItem); $('destination').addEventListener('change', draftDestination);
  $('manualItem').addEventListener('click', () => { if (state.busy) return; state.product = { title: '', description: '', seller: '', collection: '', price: '', destination_url: '', destination: 'other' }; state.original = ''; state.image = ''; state.imageMode = 'original'; state.plans = {}; state.edits = {}; state.offers = {}; state.performance = null; state.source = 'Your item'; invalidate(); populateSetup(); render(); $('productName').focus(); });
  $('findItems').addEventListener('click', findItems); $('readListing').addEventListener('click', readListing);
  $('photo').addEventListener('change', event => upload(event.target.files?.[0]));
  if ($('noPhotoAddBtn')) $('noPhotoAddBtn').addEventListener('click', promptPhotoUpload);
  for (const id of ['postHook', 'postCaption']) $(id).addEventListener('input', saveEdit);
  const channelButtons = [...document.querySelectorAll('[data-channel]')];
  channelButtons.forEach((button, idx) => {
    button.addEventListener('click', async () => {
      if (state.busy) return;
      state.channel = button.dataset.channel;
      state.selected = 0;
      state.format = state.channel === 'tiktok' ? 'video' : state.channel === 'x' ? 'text' : 'image';
      channelButtons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.channel === state.channel)));
      invalidate(); await buildPlan(); persist();
    });
    button.addEventListener('keydown', event => {
      const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!delta || state.busy) return;
      event.preventDefault();
      const next = channelButtons[(idx + delta + channelButtons.length) % channelButtons.length];
      next.focus();
      next.click();
    });
  });
  $('format').addEventListener('change', () => { state.format = $('format').value; invalidate(); render(); persist(); });
  $('getPost').addEventListener('click', getPost);
  $('copyOnly').addEventListener('click', async () => { if (state.busy || !reviewed()) return; const copied = await copyText(); notice(copied ? 'Post copied. Paste it into your channel.' : 'Caption downloaded.'); });
  $('markPosted').addEventListener('click', () => { if (state.busy || !reviewed()) return; state.posted[postIdentity()] = new Date().toISOString(); persist(); render(); markIdeaExported(); notice('Marked posted on this device. You’re done for today. Add results when you have them.', false, false, { href: '/progress', text: 'Log result →' }); });
  $('downloadPlan').addEventListener('click', () => { const plan = currentPlan(); if (!plan || state.busy) return; const rows = plan.posts.map((post, i) => { const edited = state.edits[`${state.channel}:${i}:${post.format}`]; return `${post.day_offset === 0 ? 'Today' : `In ${post.day_offset} days`} · ${names[post.channel]} · ${post.format}\n${edited?.hook || post.hook}\n${edited?.caption || post.caption}\n${post.visual_direction}\n${post.posting_tip}`; }); saveBlob(new Blob([`${state.product.title}\n${plan.mode === 'muse' ? 'Muse Spark plan' : 'Starter plan'} · manual posting\n\n${rows.join('\n\n')}\n\nDestination: ${safeURL(state.product.destination_url)}\nSuggested days, not scheduled posts. Add only offers you can fulfill.`], { type: 'text/plain' }), 'posting-plan.txt'); });
  $('resultsForm').addEventListener('submit', async event => { event.preventDefault(); if (state.busy) return; const values = {}; for (const key of ['views', 'clicks', 'inquiries', 'sales']) values[key] = Number($(key).value) || 0; if (Object.values(values).some(value => !Number.isSafeInteger(value) || value < 0)) { notice('Use whole, non-negative counts.', true); return; } state.performance = values; state.plans = {}; invalidate(); await buildPlan(false, true); persist(); $('resultsDetails').open = false; });
  $('clearResults').addEventListener('click', async () => { if (state.busy) return; state.performance = null; for (const key of ['views', 'clicks', 'inquiries', 'sales']) $(key).value = ''; state.plans = {}; invalidate(); await buildPlan(false, true); persist(); $('resultsDetails').open = false; });
  $('liveMode')?.addEventListener('change', () => { state.live = !!$('liveMode').checked; });
  $('musePlan').addEventListener('click', () => buildPlan(true, true)); $('museImage').addEventListener('click', museImage);
  $('useOriginal').addEventListener('click', () => { if (state.busy) return; state.image = state.original; state.imageMode = 'original'; invalidate(); render(); persist(); });
  if ($('quickFindItems')) {
    $('quickFindItems').addEventListener('click', () => findItems($('quickShopUrl')?.value?.trim() || ''));
  }
  if ($('saveWebsiteOnlyBtn')) {
    $('saveWebsiteOnlyBtn').addEventListener('click', () => {
      persistShopWebsiteUrl($('quickShopUrl')?.value?.trim() || $('shopUrl')?.value?.trim() || '');
    });
  }
  if ($('todayManualBtn')) {
    $('todayManualBtn').addEventListener('click', () => {
      openSetup();
      $('productName')?.focus();
      $('productName')?.select?.();
    });
  }
  if ($('todaySampleLink')) {
    $('todaySampleLink').addEventListener('click', (event) => {
      if (window.museModes?.enterSampleMode) {
        event.preventDefault();
        window.museModes.enterSampleMode({ sample: 'sarabjit_singh' });
      }
    });
  }

  function starterPlanForToday(product = state.product) {
    if (!isEffectiveSample()) return ownStarterPlan(product);
    const title = product.title || 'your piece';
    const shop = product.seller || 'your studio';
    const ch = state.channel || 'instagram';
    const linkLine = product.destination_url ? `Explore details at ${product.destination_url}.` : 'Save or reply to ask about available formats.';
    return {
      mode: 'starter',
      insight: { next_action: `Share ${title} once on ${names[ch] || ch}, then note visits or replies.` },
      sources: [],
      posts: [
        { day_offset: 0, channel: ch, format: 'image', hook: `Closer look at ${title}`, caption: `Sharing ${title} from ${shop}. ${product.description || ''} ${linkLine}`.trim(), visual_direction: 'Lead with your clear artwork photo, then add one close-up detail.', posting_tip: 'Lead with the main artwork.' },
        { day_offset: 2, channel: ch, format: 'image', hook: `Behind ${title}: materials & story`, caption: `Collectors love knowing what inspired ${title}. Tell people what drew you to this piece and how it fits in a room.`, visual_direction: 'Show texture, brushwork, or studio corner.', posting_tip: 'Add one short studio story.' },
        { day_offset: 5, channel: ch, format: 'video', hook: `In a quiet space · ${title}`, caption: `A calm look at ${title} from ${shop}. ${linkLine}`, visual_direction: 'Slow 6-second crop reveal from detail to full work.', posting_tip: 'Use short vertical framing.' },
      ],
    };
  }

  // A seller's own starter posts: no art wording, and no made-up item name while nothing is chosen.
  function ownStarterPlan(product = state.product) {
    const ch = state.channel || 'instagram';
    const named = !product.placeholder && !legacyPlaceholder(product.title || '');
    const title = named ? product.title : '';
    const shop = product.seller || 'my business';
    const url = safeURL(product.destination_url);
    if (offersServices()) {
      const linkLine = url ? `Learn more or get in touch at ${url}.` : 'Message me to ask how this could work for you.';
      const lead = named ? `${title}${product.description ? `: ${product.description}` : '.'}` : `A quick note on what ${shop} does and who it is for.`;
      return {
        mode: 'starter',
        insight: { next_action: `Share one post on ${names[ch] || ch}, then note replies, messages or calls booked.` },
        sources: [],
        posts: [
          { day_offset: 0, channel: ch, format: 'image', hook: named ? `Who ${title} is for` : `What ${shop} helps with`, caption: `${lead} ${linkLine}`.trim(), visual_direction: 'Use a clear photo of you, your team or an example of the work. A simple card with your headline works too.', posting_tip: 'Say who it is for in the first line.' },
          { day_offset: 2, channel: ch, format: 'image', hook: 'A recent project, in plain words', caption: 'How a recent project went: what the client needed, what changed, and what made the difference.', visual_direction: 'Show the work itself, such as a screen, a page or a before and after, with client details removed.', posting_tip: 'Ask the client first. Use only results you can show.' },
          { day_offset: 5, channel: ch, format: 'video', hook: named ? `How ${title} works` : `How working with ${shop} goes`, caption: `A short look at how working together goes, from the first conversation to the finished work. ${linkLine}`, visual_direction: 'A 6-second clip of your photo with the hook on screen.', posting_tip: 'Use short vertical framing.' },
        ],
      };
    }
    const linkLine = url ? `See details at ${url}.` : 'Save this post or reply to ask about it.';
    const thing = named ? title : `what ${shop} makes`;
    return {
      mode: 'starter',
      insight: { next_action: `Share one post on ${names[ch] || ch}, then note visits or replies.` },
      sources: [],
      posts: [
        { day_offset: 0, channel: ch, format: 'image', hook: named ? `Closer look at ${title}` : `New from ${shop}`, caption: `${named ? `Sharing ${title} from ${shop}.` : `Something new from ${shop}.`} ${product.description || ''} ${linkLine}`.replace(/\s+/g, ' ').trim(), visual_direction: 'Lead with your clearest photo of the item, then add one close-up detail.', posting_tip: 'Lead with the item itself.' },
        { day_offset: 2, channel: ch, format: 'image', hook: named ? `Behind ${title}` : `Behind the scenes at ${shop}`, caption: `People like knowing what goes into ${thing}. Tell them what inspired it and who it is for.`, visual_direction: 'Show materials, a detail, or where the work happens.', posting_tip: 'Add one short story.' },
        { day_offset: 5, channel: ch, format: 'video', hook: named ? `A quiet look · ${title}` : `A quiet look · ${shop}`, caption: `A calm look at ${thing}. ${linkLine}`, visual_direction: 'Slow 6-second crop reveal from a detail to the whole item.', posting_tip: 'Use short vertical framing.' },
      ],
    };
  }

  function resetToNeutralToday(shopName = '', shopUrl = '') {
    const services = offersServices();
    state.product = neutralProduct(shopName, shopUrl);
    state.original = '';
    state.image = '';
    state.imageMode = 'original';
    state.source = shopName ? `My workspace · ${shopName}` : 'Suggested from my workspace';
    state.why_this = services
      ? 'Name one service or offer with “Enter details manually”, or start with the posts below.'
      : shopName
        ? `Start with one item from ${shopName}, or bring in items from your website above.`
        : 'Add your website above, choose an item, or enter details manually.';
    // People who sell a service usually want a conversation, not a shop visit.
    if (services && state.goal === 'visits') state.goal = 'inquiries';
    state.offers = {};
    state.plans = { [state.channel]: starterPlanForToday(state.product) };
    state.edits = {};
    state.selected = 0;
    state.performance = null;
    state.revision += 1;
    if ($('reviewed')) $('reviewed').checked = false;
    populateSetup();
    render();
  }

  let todayModeSeq = 0;
  async function applyTodayMode(modeState) {
    const seq = ++todayModeSeq;
    const s = modeState || window.museModes?.current?.() || { state: 'guest_entry', isSample: isSampleMode(), isLoading: false, isError: false, isExpired: false, ownerId: null };
    if (s.isLoading || s.isError || s.isExpired) {
      draftReady = false;
      if ($('todayWebsiteSaveRow')) $('todayWebsiteSaveRow').hidden = true;
      return;
    }

    const nextOwner = s.ownerId || window.museAccount?.getSnapshot()?.user?.id || null;
    if (draftOwnerBound && nextOwner !== draftOwner) {
      return;
    }

    if (todayInitializedOnce && draftReady && activeSampleMode !== !!s.isSample) {
      persistDraft();
    }
    // Listings found for one workspace must not stay on offer in the other.
    if (activeSampleMode !== !!s.isSample) $('importItems')?.replaceChildren?.();
    activeSampleMode = !!s.isSample;
    draftOwner = nextOwner;
    draftOwnerBound = true;
    abortTodayImageFetch();
    todayWebsiteCandidates = [];
    todayImageSource = activeSampleMode ? 'sample' : 'website';
    if ($('todayImagePickerStatus')) delete $('todayImagePickerStatus').dataset.explicitMessage;

    if ($('todayWebsiteSaveRow')) $('todayWebsiteSaveRow').hidden = s.state !== 'account_own';
    if ($('todaySampleLink')) $('todaySampleLink').hidden = !!s.isSample;

    const requestedIdea = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null;
    const ideaSpec = requestedIdea ? findPreviewSpec(requestedIdea) : null;

    ownBusinessType = null;
    if (s.isSample) {
      // Signed in but setup not finished: say this is demo data and point to the wizard.
      if (s.state === 'account_sample') window.museModes?.checkSetupPending?.(s.ownerId);
      let restored = false;
      applyingDraft = true;
      try {
        state.product = sampleProduct();
        state.original = originalSample;
        state.image = originalSample;
        state.imageMode = 'original';
        state.source = 'Suggested from the artist example';
        state.why_this = '';
        state.offers = {};
        state.plans = {};
        state.edits = {};
        state.selected = 0;
        restored = recoverDevice();
        if (ideaSpec) {
          applyIdea(ideaSpec);
          window.museTrack?.('post_started', { idea_id: requestedIdea, source: 'today' });
        } else if (!restored) {
          state.plans = { [state.channel]: starterPlanForToday(state.product) };
          populateSetup();
          render();
          window.museTrack?.('post_started', { idea_id: null, goal: state.goal || 'daily', source: 'today' });
        }
      } finally {
        applyingDraft = false;
        todayInitializedOnce = true;
      }
      draftReady = true;
      syncTodayFrameControls();
      renderTodayImagePicker();
      buildPlan();
      return;
    }

    // account_own or guest_entry
    let recovered = false;
    applyingDraft = true;
    try {
      recovered = recoverDevice();
      if (!recovered) {
        resetToNeutralToday('', '');
      }
      window.museTrack?.('post_started', { idea_id: null, goal: state.goal || 'daily', source: 'today' });
    } finally {
      applyingDraft = false;
      todayInitializedOnce = true;
    }
    draftReady = true;

    let savedShop = null;
    if (s.state === 'account_own' && s.ownerId && window.museAccount?.loadWorkspace) {
      const guard = window.museModes?.bindAsyncGuard?.() || { isCurrent: () => true };
      try {
        const ws = await window.museAccount.loadWorkspace(s.ownerId);
        if (seq !== todayModeSeq || !guard.isCurrent()) return;
        window.museModes?.noteSetup?.(s.ownerId, ws);
        const onb = ws?.document?.onboarding || {};
        const shopUrls = Array.isArray(onb.shop_urls) ? onb.shop_urls.filter(Boolean) : [];
        const shopName = String(onb.business_name || '').trim();
        ownBusinessType = ['products', 'services', 'both'].includes(onb.business_type) ? onb.business_type : null;
        state.shopWebsiteUrl = shopUrls[0] || '';
        savedShop = { name: shopName, workspace: ws };
        if ($('savedShopWebsiteNote')) {
          $('savedShopWebsiteNote').textContent = state.shopWebsiteUrl
            ? `Saved website: ${state.shopWebsiteUrl}`
            : 'No website saved in My workspace yet.';
        }
        if ($('quickShopUrl') && !$('quickShopUrl').value && state.shopWebsiteUrl) $('quickShopUrl').value = state.shopWebsiteUrl;
        if ($('shopUrl') && !$('shopUrl').value && state.shopWebsiteUrl) $('shopUrl').value = state.shopWebsiteUrl;
        if (!recovered && (shopName || state.shopWebsiteUrl || ownBusinessType)) {
          applyingDraft = true;
          try {
            resetToNeutralToday(shopName, state.shopWebsiteUrl);
          } finally {
            applyingDraft = false;
          }
        } else {
          // Account refresh supplies wording, not a new edit or a replacement save status.
          applyingDraft = true;
          try { applyOfferWording(); }
          finally { applyingDraft = false; }
        }
      } catch {
        if (seq !== todayModeSeq) return;
        if ($('savedShopWebsiteNote')) $('savedShopWebsiteNote').textContent = 'Add a shop website above to import your products.';
      }
    }
    const handoff = readRecommendationHandoff(s.ownerId);
    if (handoff) applyRecommendationHandoff(handoff);
    syncTodayFrameControls();
    renderTodayImagePicker();
    buildPlan();
    // Only after this account's workspace loaded, and never over a recommendation handoff.
    if (savedShop && !handoff) autoImportSavedShop(s.ownerId, savedShop.name, savedShop.workspace);
  }

  if ($('todayImgSrcWebsiteBtn')) $('todayImgSrcWebsiteBtn').addEventListener('click', () => { todayImageSource = 'website'; renderTodayImagePicker(); });
  if ($('todayImgSrcSampleBtn')) $('todayImgSrcSampleBtn').addEventListener('click', () => { if (!isEffectiveSample()) return; todayImageSource = 'sample'; renderTodayImagePicker(); });
  if ($('todayCropToggle')) $('todayCropToggle').addEventListener('click', () => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, fit: cur.fit === 'cover' ? 'contain' : 'cover' };
    syncTodayFrameControls(); paint(); persist();
  });
  if ($('todayFrameX')) $('todayFrameX').addEventListener('input', (e) => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, x: Number(e.target.value) || 0 };
    paint(); persist();
  });
  if ($('todayFrameY')) $('todayFrameY').addEventListener('input', (e) => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, y: Number(e.target.value) || 0 };
    paint(); persist();
  });
  if ($('todayFrameReset')) $('todayFrameReset').addEventListener('click', () => {
    state.imageFrame = { fit: 'contain', x: 0, y: 0 };
    syncTodayFrameControls(); paint(); persist();
  });

  if (standaloneVm) {
    populateSetup(); render(); initDrafts(); syncTodayFrameControls(); renderTodayImagePicker();
    const requestedIdea = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null;
    const ideaSpec = requestedIdea ? findPreviewSpec(requestedIdea) : null;
    if (ideaSpec) {
      applyIdea(ideaSpec);
      window.museTrack?.('post_started', { idea_id: requestedIdea, source: 'today' });
    } else {
      window.museTrack?.('post_started', { idea_id: null, goal: state.goal || 'daily', source: 'today' });
    }
    buildPlan();
  } else {
    initDrafts();
    if (window.museModes?.subscribe) window.museModes.subscribe((m) => { applyTodayMode(m); });
    if (window.museModes?.resolve) window.museModes.resolve().then((m) => { applyTodayMode(m); });
    else applyTodayMode();
  }

  fetch('/api/v1/readiness').then(response => response.json()).then(data => { state.readiness = data; syncAccountLive(); }).catch(() => { if ($('readinessNote')) $('readinessNote').textContent = 'Could not check server configuration. Your draft is still available.'; });
  window.museDailySnapshot = () => JSON.parse(JSON.stringify({ product: state.product, channel: state.channel, format: state.format, copy: currentCopy(), cta: state.cta || currentPost()?.cta || '', why_this: state.why_this, idea_id: state.idea_id, plan: currentPlan(), performance: state.performance, imageMode: state.imageMode, imageMeta: state.imageMeta, imageFrame: state.imageFrame, source: state.source }));
})();
