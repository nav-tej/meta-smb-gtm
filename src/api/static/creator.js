'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { accountLive: false, step: 0, presets: null, workspace: 'sarabjit_singh', custom: false, copyEdited: false, sceneEdited: false, goal: 'story', placement: 'instagram_feed', original: '', image: '', imageKind: 'original', sampleImage: '', imageMeta: null, imageFrame: { fit: 'contain', x: 0, y: 0 }, live: false, defaultLive: false, readiness: null, busy: false, revision: 0, paint: 0, product: {}, headline: '', caption: '', scene: '', cta: '', provenance: 'Original-photo layout. No new image generated.', idea_id: null, shopWebsiteUrl: '', handoffActive: false, handoffContext: null, handoffId: null };

  const draftNamespace = 'creator';
  const draftFields = ['workspace', 'custom', 'copyEdited', 'sceneEdited', 'goal', 'placement', 'original', 'image', 'imageKind', 'sampleImage', 'imageMeta', 'imageFrame', 'product', 'headline', 'caption', 'scene', 'cta', 'provenance', 'artwork', 'idea_id', 'handoffActive', 'handoffContext', 'handoffId'];
  function isSampleMode() {
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
  }
  function requestedHandoffId() {
    try {
      return typeof location !== 'undefined' ? new URLSearchParams(location.search).get('sm_handoff') : null;
    } catch (_) {
      return null;
    }
  }
  function readRecommendationHandoff(uid = window.museAccount?.getSnapshot?.()?.user?.id || window.museAccount?.current?.()?.id || null) {
    try {
      const hid = requestedHandoffId();
      if (!hid) return null;
      const ns = uid ? String(uid) : 'guest';
      const mode = isSampleMode() ? 'sample' : 'own';
      const raw = localStorage.getItem(`muse.sm.handoff.${encodeURIComponent(ns)}.${encodeURIComponent(hid)}`);
      const payload = raw ? JSON.parse(raw) : null;
      if (!payload || payload.owner_id !== ns || payload.workspace_mode !== mode) return null;
      const createdMs = payload.created_at ? Date.parse(payload.created_at) : NaN;
      if (!Number.isFinite(createdMs) || (Date.now() - createdMs) > 24 * 60 * 60 * 1000) return null;
      return payload;
    } catch (_) {
      return null;
    }
  }
  function activePlacement() {
    if (state.placement === 'instagram_story' || state.placement === 'facebook_feed' || state.placement === 'instagram_feed') return state.placement;
    if ($('postFacebook')?.checked && !$('postInstagram')?.checked) return 'facebook_feed';
    return 'instagram_feed';
  }
  function editorDocument() { return { schema: 1, ...Object.fromEntries(draftFields.map(key => [key, state[key]])), offers, channels: postingChannels(), step: state.step }; }
  const isDraftObject = value => !!value && typeof value === 'object' && !Array.isArray(value);
  function applyDocument(data) {
    if (data?.schema !== 1 || typeof data.product?.name !== 'string' || !Object.hasOwn(goals, data.goal) || !['original', 'image', 'sampleImage'].every(key => !data[key] || samplePath(data[key]) || mediaAssetPath(data[key]) || validInline(data[key]))) throw new Error('Unsupported creator draft.');
    if (!isDraftObject(data.offers || {}) || !Array.isArray(data.channels) || ['headline', 'caption', 'scene', 'provenance'].some(key => typeof data[key] !== 'string')) throw new Error('Invalid creator draft fields.');
    state.artwork = null;
    state.handoffActive = false;
    state.handoffContext = null;
    state.handoffId = null;
    for (const key of draftFields) if (data[key] !== undefined) state[key] = cloneDraft(data[key]);
    state.handoffActive = Boolean(state.handoffActive && isDraftObject(state.handoffContext));
    if (!state.handoffActive) {
      state.handoffContext = null;
      state.handoffId = null;
    }
    if (!isDraftObject(state.imageFrame)) state.imageFrame = { fit: 'contain', x: 0, y: 0 };
    offers = cloneDraft(data.offers || {}); state.revision += 1;
    setProductFields(); $('promotionDestination').value = state.product.destination || 'other';
    $('headline').value = state.headline; $('caption').value = state.caption; $('scene').value = state.scene;
    $('postInstagram').checked = data.channels?.includes('instagram'); $('postFacebook').checked = data.channels?.includes('facebook');
    $('artistChannels').hidden = state.custom; $('reviewed').checked = false;
    syncFrameControls(); clearNotice(); updateChoices(); refreshPreview();
    go(Number.isInteger(data.step) ? Math.max(0, Math.min(2, data.step)) : 0);
  }
  function localDraftPresent() { try { return !!localStorage.getItem(deviceKey()); } catch { return true; } }

  // Editor-local adapter: keep this contract aligned in creator.js and today.js.
  let draftReady = false, draftOwner = null, draftOwnerBound = false, draftEpoch = 0, cloudBusy = false;
  let activeSampleMode = isSampleMode(), creatorInitializedOnce = false;
  let cloudBase, conflictValue, recoveryDraft, applyingDraft = false;
  const cloneDraft = value => JSON.parse(JSON.stringify(value));
  const draftStatus = text => { $('draftStatus').textContent = text; };
  const isEffectiveSample = () => (typeof activeSampleMode === 'boolean' ? activeSampleMode : isSampleMode());
  const deviceKey = () => `muse-editor-v1:${draftNamespace}:${isEffectiveSample() ? 'sample' : (draftOwner ? 'account:' + encodeURIComponent(draftOwner) : 'guest')}`;
  function persistDraft() {
    if (!draftReady || applyingDraft) return;
    try { localStorage.setItem(deviceKey(), JSON.stringify(editorDocument())); draftStatus('Saved on this device. Account saving is manual.'); return true; }
    catch { draftStatus('Device storage failed or is full. Download a draft backup now, or save to your account before closing.'); return false; }
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
      const params = typeof location !== 'undefined' ? new URLSearchParams(location.search) : null;
      if (isEffectiveSample() && ((params?.get('idea') && findPreviewSpec(params.get('idea'))) || window.museModes?.isSampleArtwork?.(params?.get('artwork')))) return false;
      const raw = localStorage.getItem(deviceKey());
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
      if (typeof window.museModes === 'undefined' && typeof window.museAccount === 'undefined') {
        draftReady = true;
        recoverDevice();
      }
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
  const fields = { productName: 'name', productPrice: 'price', sellerName: 'seller', productDescription: 'description', productLink: 'link', productCollection: 'collection' };
  const destinations = { pixels: 'Pixels', fineartamerica: 'Fine Art America', saatchi: 'Saatchi Art', website: 'Artist website', other: 'My shop / inquiry page' };
  let offers = {};
  function postingChannels() { return [['postInstagram', 'instagram'], ['postFacebook', 'facebook']].filter(([id]) => $(id).checked).map(([, name]) => name); }
  const isSampleProductUrl = (url) => /sarabjit|fineartamerica\.com\/profiles\/sarabjit|saatchiart\.com\/sarabjit/i.test(String(url || ''));
  function stripSampleOffersAndLink() {
    Object.keys(offers).forEach((k) => {
      if (isSampleProductUrl(offers[k]?.link)) delete offers[k];
    });
    if (isSampleProductUrl(state.product.link)) state.product.link = '';
  }
  function resetOffers(artist) {
    offers = artist ? {
      pixels: { link: 'https://sarabjit-singh.pixels.com/', price: '' },
      fineartamerica: { link: 'https://fineartamerica.com/profiles/sarabjit-singh/art/paintings', price: '' },
      saatchi: { link: 'https://www.saatchiart.com/sarabjitsingh', price: '' },
      website: { link: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html', price: '$75' }
    } : {};
    state.product.destination = artist ? 'pixels' : 'other';
    $('promotionDestination').value = state.product.destination;
    $('postInstagram').checked = true; $('postFacebook').checked = true;
    $('artistChannels').hidden = !artist;
    if (artist) Object.assign(state.product, offers.pixels);
  }
  function switchDestination() {
    if (state.busy) return;
    sync(); offers[state.product.destination] = { price: state.product.price, link: state.product.link };
    const next = $('promotionDestination').value;
    if (!Object.hasOwn(destinations, next)) return;
    state.product.destination = next;
    Object.assign(state.product, offers[next] || { price: '', link: '' });
    setProductFields(); changed();
    notify(`Destination changed to ${destinations[next]}. Its price and link are separate. Check that this artwork is listed there and review any prices or promises in your caption.`);
  }
  function destinationNote() {
    const destination = state.product.destination;
    if (!state.custom && state.workspace === 'sarabjit_singh') {
      if (destination === 'website') return 'The saved artist website offer lists $75 for a signed 12×12-inch print. Confirm current price and availability. This offer does not apply to other shops.';
      if (destination === 'saatchi') return 'You use Saatchi for a different, more abstract selection. Choose a matching artwork and its exact listing. No price is copied from Pixels or Fine Art America.';
      if (destination === 'pixels' || destination === 'fineartamerica') return 'This is your shop link, unless you replace it with an exact artwork listing. Confirm the artwork, size and price there. Pixels and Fine Art America are related storefronts; this app does not sync their offers.';
    }
    return 'Paste the matching product or inquiry page. Price is optional and belongs only to this destination. Your other destinations keep their own details in this tab.';
  }
  function postingChecklist() {
    const channels = postingChannels(); const label = destinations[state.product.destination]; const link = safeLink(state.product.link);
    return [
      `Review the original artwork, caption, availability and ${label} offer. A series label here does not change your shop collections.`,
      ...(channels.includes('instagram') ? ['Instagram: upload the feed image and paste your caption. Add the destination to your profile or a Story link sticker; a URL in a feed caption is not a clickable product link.'] : []),
      ...(channels.includes('facebook') ? ['Facebook: upload the image to your page and paste your caption with the destination link. If Instagram shares to your linked page, check that post before posting again.'] : []),
      link ? `Destination (${label}): ${link}. Open it and check it leads to the intended artwork or shop before sharing.` : 'No destination link added. Add one if you want people to visit your shop, or invite an inquiry without promising checkout.',
      'Download saves files to your device. You publish from your own account; this app has not connected to Instagram or Facebook.'
    ];
  }
  const goals = {
    story: ['Let the work tell its story', 'Pair a clear product image with a personal introduction. Tell people what makes this piece meaningful to you.'],
    gift: ['A thoughtful gift, with a story', 'Show the product clearly and explain the care or meaning behind it. Let the recipient decide whether it feels right for them.'],
    visit: ['Make the next step easy', 'Keep the image simple, explain what is available, and point people to your existing product or inquiry page.']
  };
  const safeLink = (value) => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } };
  const samplePath = (value) => typeof value === 'string' && /^\/samples\/[a-zA-Z0-9_.-]+$/.test(value) ? value : '';
  const mediaAssetPath = (value) => typeof value === 'string' && /^\/api\/v1\/account\/media\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(value) ? value : '';
  const validInline = (value) => typeof value === 'string' && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length < 4000000;
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
    const input = $('productPhoto');
    if (!input) return;
    try { if ($('moreDetails')) $('moreDetails').open = true; } catch {}
    input.click();
  }
  function notify(message, kind = '', action = null) {
    const noticeEl = $('notice');
    if (!noticeEl) return;
    noticeEl.hidden = false;
    noticeEl.className = `notice ${kind}`;
    if (!action) {
      noticeEl.textContent = message;
      return;
    }
    if (typeof noticeEl.replaceChildren === 'function' && typeof document.createElement === 'function') {
      noticeEl.replaceChildren();
      const span = document.createElement('span');
      span.textContent = message;
      if (noticeEl.append) noticeEl.append(span); else if (noticeEl.appendChild) noticeEl.appendChild(span);
      if (typeof action.onClick === 'function') {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = action.text || 'Continue';
        btn.className = 'secondary notice-action-btn';
        btn.addEventListener('click', action.onClick);
        if (noticeEl.append) noticeEl.append(btn); else if (noticeEl.appendChild) noticeEl.appendChild(btn);
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
        if (noticeEl.append) noticeEl.append(a); else if (noticeEl.appendChild) noticeEl.appendChild(a);
      }
      if (!noticeEl.childNodes?.length) noticeEl.textContent = message;
    } else {
      noticeEl.textContent = message;
    }
  }
  function clearNotice() {
    const noticeEl = $('notice');
    if (noticeEl) {
      noticeEl.hidden = true;
      noticeEl.className = 'notice';
      if (typeof noticeEl.replaceChildren === 'function') noticeEl.replaceChildren();
      else noticeEl.textContent = '';
    }
    const offerEl = $('exportDoneOffer');
    if (offerEl) offerEl.hidden = true;
  }

  function markIdeaExported() {
    try {
      const ideaId = state.idea_id || (typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null);
      const uid = window.museAccount?.getSnapshot?.()?.user?.id || null;
      const ACTIONS_KEY = uid ? `muse.actions.${uid}` : 'muse.actions';
      const raw = localStorage.getItem(ACTIONS_KEY) || '{}';
      const all = typeof raw === 'string' && raw ? JSON.parse(raw) : {};
      const actionKey = ideaId || 'custom-post';
      all[actionKey] = {
        ...(all[actionKey] || {}),
        status: 'done',
        title: state.headline || state.product.name || 'Creator Studio Post',
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
    const offerEl = $('exportDoneOffer');
    if (offerEl) offerEl.hidden = false;
    notify('Post exported using your current headline. Copy the matching caption before posting.', '', { href: '/progress', text: 'Log result →' });
  }

  function applyIdea(spec) {
    if (!spec) return;
    state.idea = spec;
    state.idea_id = spec.insight_id;
    state.headline = spec.headline;
    state.caption = spec.caption;
    state.copyEdited = true;
    state.sceneEdited = true;
    if (spec.product_name) {
      state.product.name = spec.product_name;
    }
    if (spec.image_ref && samplePath(spec.image_ref)) {
      state.original = samplePath(spec.image_ref);
      state.image = samplePath(spec.image_ref);
      state.sampleImage = samplePath(spec.image_ref);
      state.imageKind = 'original';
    }
    state.cta = spec.cta || '';
    const mappedGoal = spec.goal || (spec.insight_id.includes('gift') ? 'gift' : (spec.insight_id.includes('starter') || spec.insight_id.includes('visit') || spec.insight_id.includes('home') ? 'visit' : 'story'));
    if (Object.hasOwn(goals, mappedGoal)) {
      state.goal = mappedGoal;
      document.querySelectorAll?.('.goal, [data-goal]').forEach((b) => {
        const active = b.dataset.goal === mappedGoal;
        b.classList.toggle('selected', active);
        b.setAttribute('aria-pressed', String(active));
      });
    }
    state.placement = spec.placement || (spec.placement === 'facebook_feed' ? 'facebook_feed' : 'instagram_feed');
    if (state.placement === 'facebook_feed') {
      $('postFacebook').checked = true;
      $('postInstagram').checked = false;
    } else {
      $('postInstagram').checked = true;
      $('postFacebook').checked = false;
    }
    state.revision += 1;
    $('headline').value = state.headline;
    $('caption').value = state.caption;
    $('productName').value = state.product.name || '';
    if ($('ideaTitle')) $('ideaTitle').textContent = spec.headline;
    if ($('ideaReason')) $('ideaReason').textContent = spec.why_this || '';
    $('productImageCaption').textContent = `${state.product.name || spec.headline} · loaded from research recommendation.`;
    refreshPreview();
    notify(`Loaded recommendation: ${spec.headline}. Evidence: ${spec.why_this || ''}`);
  }
  function renderHandoffGuidance() {
    const box = $('handoffGuidanceBox');
    const quickBtn = $('quickExportFeedBtn');
    const ctx = state.handoffActive ? state.handoffContext : null;
    if (quickBtn) quickBtn.hidden = !ctx;
    if (!box) return;
    if (!ctx) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    if ($('handoffProvenanceBadge')) $('handoffProvenanceBadge').textContent = ctx.output_label || 'Suggested starting approach';
    if ($('handoffPlacementNote')) $('handoffPlacementNote').textContent = ctx.placement_note || 'App export preset (not verified Meta policy)';
    if ($('handoffWhyFits')) $('handoffWhyFits').textContent = ctx.why_this_fits ? `Why this fits: ${ctx.why_this_fits}` : '';
    if ($('handoffOrganicNote')) $('handoffOrganicNote').textContent = ctx.organic_guidance_note || '';
    if ($('handoffApprovedFacts')) {
      const facts = Array.isArray(ctx.approved_facts)
        ? ctx.approved_facts
            .map((f) => (typeof f === 'string' ? f : (f && (f.label || f.value) ? `${f.label ? `${f.label}: ` : ''}${f.value || ''}` : '')))
            .filter(Boolean)
        : [];
      $('handoffApprovedFacts').textContent = facts.length ? `Approved facts: ${facts.join(' · ')}` : '';
      $('handoffApprovedFacts').hidden = !facts.length;
    }
    if ($('handoffMissingFacts')) {
      const missing = Array.isArray(ctx.missing_facts) ? ctx.missing_facts.filter(Boolean) : [];
      $('handoffMissingFacts').textContent = missing.length ? `Missing facts (not assumed): ${missing.join(' · ')}` : '';
      $('handoffMissingFacts').hidden = !missing.length;
    }
    if ($('audienceHypothesis') && document.activeElement !== $('audienceHypothesis')) {
      $('audienceHypothesis').value = ctx.unconfirmed_audience || '';
    }
  }
  function applyRecommendationHandoff(handoff) {
    if (!handoff) return;
    state.handoffActive = true;
    state.handoffId = handoff.id || requestedHandoffId() || null;
    state.handoffContext = {
      output_provenance: isSampleMode() ? 'artist_example' : (handoff.output_provenance || 'suggested_starting_approach'),
      output_label: isSampleMode() ? 'Artist example' : (handoff.output_label || 'Suggested starting approach'),
      organic_first: handoff.organic_first !== false,
      organic_guidance_note: handoff.organic_guidance_note || 'Start with an organic post or story first; only promote if you already have a product and offer ready.',
      unconfirmed_audience: handoff.unconfirmed_audience || '',
      audience_confirmed: Boolean(handoff.audience_confirmed),
      approved_facts: Array.isArray(handoff.approved_facts) ? handoff.approved_facts : [],
      missing_facts: Array.isArray(handoff.missing_facts) ? handoff.missing_facts : [],
      placement_note: handoff.placement_note || 'App export preset (not verified Meta policy)',
      why_this_fits: handoff.why_this_fits || '',
    };
    const ownSession = !isSampleMode();
    if (ownSession) {
      state.custom = true;
      stripSampleOffersAndLink();
      if (!state.original || samplePath(state.original)) {
        state.original = '';
        state.image = '';
        state.sampleImage = '';
      } else {
        state.image = state.image && !samplePath(state.image) ? state.image : state.original;
      }
      state.artwork = null;
      state.imageKind = 'original';
      if ($('artistExample')) { $('artistExample').hidden = true; if ($('artistExample').style) $('artistExample').style.display = 'none'; }
      if ($('tryNext')) { $('tryNext').hidden = true; if ($('tryNext').style) $('tryNext').style.display = 'none'; }
    }
    const existingProduct = String(state.product.name || '').trim();
    const isGenericProduct = !existingProduct || existingProduct === 'Ek Onkar · artwork promotion' || existingProduct === 'Your Artwork' || existingProduct.startsWith('Artwork by ');
    if (handoff.business_name) {
      state.product.seller = handoff.business_name;
    }
    if (handoff.product_name && (handoff.product_name !== handoff.business_name || isGenericProduct)) {
      state.product.name = handoff.product_name;
    } else if (isGenericProduct && handoff.business_name) {
      state.product.name = `${handoff.business_name} featured work`;
    }
    if (handoff.price_claim !== undefined) {
      state.product.price = handoff.price_claim || '';
    }
    if (handoff.destination) {
      const destKey = Object.hasOwn(destinations, handoff.destination) ? handoff.destination : 'other';
      state.product.destination = destKey;
      $('promotionDestination').value = destKey;
    }
    const mappedGoal = Object.hasOwn(goals, handoff.goal) ? handoff.goal : 'story';
    state.goal = mappedGoal;
    document.querySelectorAll?.('.goal, [data-goal]').forEach((b) => {
      const active = b.dataset.goal === mappedGoal;
      b.classList.toggle('selected', active);
      b.setAttribute('aria-pressed', String(active));
    });
    const ch = String(handoff.channel || '').toLowerCase();
    if (ch === 'facebook') {
      state.placement = 'facebook_feed';
      $('postFacebook').checked = true;
      $('postInstagram').checked = false;
    } else {
      state.placement = 'instagram_feed';
      $('postInstagram').checked = true;
      $('postFacebook').checked = false;
    }
    state.idea_id = handoff.recommendation_id || handoff.id || null;
    state.cta = handoff.cta || '';
    state.headline = handoff.title || state.product.name || 'Your next shop post';
    state.caption = handoff.action || `Share ${state.product.name || 'your work'} with buyers.`;
    state.copyEdited = true;
    state.sceneEdited = true;
    state.provenance = state.original ? 'Original-photo layout. Using your selected recommendation.' : 'Original-photo layout. Add your product photo if not attached yet.';
    state.revision += 1;
    setProductFields();
    $('headline').value = state.headline;
    $('caption').value = state.caption;
    if ($('ideaTitle')) $('ideaTitle').textContent = state.headline;
    if ($('ideaReason')) $('ideaReason').textContent = handoff.why_this_fits || '';
    $('productImageCaption').textContent = state.original
      ? `${state.product.name || state.headline} · your photo kept with selected move.`
      : 'Your product photo will appear here.';
    $('reviewed').checked = false;
    updateChoices();
    renderHandoffGuidance();
    go(0);
    persistDraft();
    notify(`Loaded selected move (${state.handoffContext.output_label}): ${state.headline}.`);
  }
  function sync() {
    for (const [id, key] of Object.entries(fields)) state.product[key] = $(id).value.trim();
    if (state.product.destination) offers[state.product.destination] = { price: state.product.price, link: state.product.link };
    state.headline = $('headline').value.trim(); state.caption = $('caption').value.trim(); state.scene = $('scene').value.trim();
  }
  function changed(event) {
    if (['headline', 'caption'].includes(event?.target?.id)) state.copyEdited = true;
    if (event?.target?.id === 'scene') state.sceneEdited = true;
    if (['postInstagram', 'postFacebook'].includes(event?.target?.id)) {
      if ($('postFacebook')?.checked && !$('postInstagram')?.checked) {
        state.placement = 'facebook_feed';
      } else if ($('postInstagram')?.checked && !$('postFacebook')?.checked) {
        state.placement = 'instagram_feed';
      }
    }
    state.revision += 1; $('reviewed').checked = false; sync();
    if (state.custom && !state.copyEdited && ['productName', 'productDescription'].includes(event?.target?.id)) starter();
    refreshPreview();
  }
  function starter() {
    const name = state.product.name || 'My product';
    state.headline = name;
    state.caption = state.custom ? `Meet ${name}. ${state.product.description || 'Made with care, ready to share.'}` : state.workspace === 'sarabjit_singh' ? (state.artwork ? `${state.artwork.name} by Sarabjit Singh${state.artwork.series ? `, from her ${state.artwork.series} work` : ''}.` : 'Ek Onkar by Sarabjit Singh explores connection and equality through color and form.') + ' A print for a space that matters to you. Ask the artist about available editions.' : 'A moment for your daily chai ritual. Explore this stoneware and brass set from our illustrative shop collection.';
    if (state.goal === 'gift') state.caption += ' A thoughtful gift starts with a story.';
    if (state.goal === 'visit') state.caption += ' Visit the product page to learn more.';
    state.caption = state.caption.slice(0, 600);
    if (!state.sceneEdited) state.scene = 'Warm neutral room, simple light oak console, soft daylight, clean wall and a restrained frame. Describe only the surroundings; do not change the product.';
    $('headline').value = state.headline; $('caption').value = state.caption; $('scene').value = state.scene;
  }
  function setProductFields() { for (const [id, key] of Object.entries(fields)) $(id).value = state.product[key] || ''; }
  function selectExample(workspace) {
    if (state.busy) return;
    state.workspace = workspace; state.custom = false; state.copyEdited = false; state.sceneEdited = false; state.revision += 1; state.artwork = null; state.handoffActive = false; state.handoffContext = null; state.handoffId = null;
    const ws = state.presets?.workspaces?.[workspace]; const art = ws?.artworks_showcase?.[0];
    state.product = workspace === 'sarabjit_singh' ? { name: 'Ek Onkar · artwork promotion', price: '', seller: 'Art of Sarabjit Singh', description: 'Ek Onkar by Sarabjit Singh explores connection and equality. Check the selected shop for the matching artwork, available formats and current offer.', link: '', collection: '' } : { name: 'Stoneware & brass chai set', price: '$54', seller: 'Saffron & Clay', description: 'Illustrative product example: a stoneware and brass chai set.', link: '', collection: '' };
    resetOffers(workspace === 'sarabjit_singh');
    state.original = samplePath(art?.original_image) || (workspace === 'sarabjit_singh' ? '/samples/ek_onkar_original.jpg' : '/samples/etsy_chai_set_product_visual_live.webp');
    state.sampleImage = samplePath(art?.staged_image) || (workspace === 'sarabjit_singh' ? '/samples/ek_onkar_collector_room_live.webp' : '/samples/etsy_chai_set_product_visual_live.webp');
    originalLayout(); setProductFields(); starter(); $('reviewed').checked = false; $('moreDetails').open = false;
    clearNotice();
    $('productFactNote').textContent = workspace === 'sarabjit_singh' ? 'Confirm the matching artwork and offer at your chosen destination. Frame is staging only. Preview image is not a print master.' : 'Illustrative shop and sample pricing. These are saved examples, not a connected shop.';
    $('productImageCaption').textContent = workspace === 'sarabjit_singh' ? 'Ek Onkar · original artwork preview. Source: Art of Sarabjit Singh.' : 'Illustrative product image generated for the example shop.';
    updateChoices(); refreshPreview();
  }
  function updateChoices() {
    const isArtist = isEffectiveSample() && !state.custom && state.workspace === 'sarabjit_singh';
    const isCeramics = isEffectiveSample() && !state.custom && state.workspace === 'etsy_ceramics';
    const isOwn = !isEffectiveSample() || state.custom;
    if ($('artistExample')) {
      $('artistExample').hidden = false;
      if ($('artistExample').style) $('artistExample').style.display = '';
      $('artistExample').classList.toggle('selected', isArtist);
      $('artistExample').setAttribute('aria-pressed', String(isArtist));
    }
    if ($('ceramicsExample')) {
      $('ceramicsExample').classList.toggle('selected', isCeramics);
      $('ceramicsExample').setAttribute('aria-pressed', String(isCeramics));
    }
    if ($('customProduct')) {
      $('customProduct').classList.toggle('selected', isOwn);
      $('customProduct').setAttribute('aria-pressed', String(isOwn));
    }
    document.querySelectorAll('[data-goal]').forEach((b) => {
      const active = b.dataset.goal === state.goal;
      b.classList.toggle('selected', active);
      b.setAttribute('aria-pressed', String(active));
    });
  }
  function originalLayout() { state.image = state.original; state.imageKind = 'original'; state.provenance = state.custom ? 'Original-photo layout. No personalized image generated.' : state.workspace === 'etsy_ceramics' ? 'Original example layout using a saved AI product image.' : 'Layout using the original artwork preview. No new image generated.'; refreshPreview(); }
  function newProduct() {
    if (state.busy) return;
    state.custom = true; state.copyEdited = false; state.sceneEdited = false; state.revision += 1; state.product = { name: '', price: '', seller: '', description: '', link: '', collection: '' }; resetOffers(false); state.original = ''; state.image = ''; state.sampleImage = ''; state.provenance = 'Add a photo to create your own product layout.';
    setProductFields(); starter(); updateChoices(); $('reviewed').checked = false; clearNotice(); $('productFactNote').textContent = 'Your photo is saved on this device when storage is available. A live request sends it to Muse only when you choose to generate.'; $('productImageCaption').textContent = 'Your product photo will appear here.'; $('moreDetails').open = true; refreshPreview(); $('productName').focus();
  }
  function imageElement(src) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('We could not open that image. Try a JPEG, PNG or WebP photo.')); image.src = src; }); }
  async function upload(file) {
    const ownerEpoch = draftEpoch;
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('Choose a JPEG, PNG or WebP photo smaller than 10 MB.');
    const url = URL.createObjectURL(file);
    try {
      const image = await imageElement(url); if (ownerEpoch !== draftEpoch) return; const scale = Math.min(1, 1400 / Math.max(image.width, image.height)); const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale)); const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      let quality = .88; let data = canvas.toDataURL('image/jpeg', quality); while (data.length > 1300000 && quality > .35) { quality -= .1; data = canvas.toDataURL('image/jpeg', quality); }
      if (data.length > 1300000) throw new Error('This photo is still too large. Please choose a smaller image.');
      if (!state.custom) newProduct();
      state.original = data;
      state.imageMeta = { id: 'upload-local', title: file.name || 'Uploaded product photo', sourceUrl: '', width: image.width, height: image.height, isLowRes: Math.min(image.width, image.height) < 600 || Math.max(image.width, image.height) < 800, provenance: 'upload', confirmed: true };
      state.imageFrame = { fit: 'contain', x: 0, y: 0 };
      syncFrameControls();
      state.revision += 1; originalLayout(); $('reviewed').checked = false; renderImagePicker(); notify('Photo ready. Add your product details, then choose an idea.');
    } finally { URL.revokeObjectURL(url); }
  }
  const SAMPLE_IMAGE_ORIGINALS = [
    { id: 'sample-orig-ek-onkar', title: 'Ek Onkar — Original artwork', image_data_url: '/samples/ek_onkar_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' },
    { id: 'sample-orig-naam-japo', title: 'Naam Japo — Original artwork', image_data_url: '/samples/naam_japo_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' },
    { id: 'sample-orig-kirat-karo', title: 'Kirat Karo — Original artwork', image_data_url: '/samples/kirat_karo_original.jpg', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Art of Sarabjit Singh · Original artwork', width: 900, height: 900, is_low_res: false, provenance: 'sample_original' }
  ];
  const SAMPLE_IMAGE_GENERATED = [
    { id: 'sample-gen-ek-onkar', title: 'Ek Onkar collector room (Saved AI scene)', image_data_url: '/samples/ek_onkar_collector_room_live.webp', source_url: 'https://www.artofsarabjitsingh.com/guru-nanak-dev-ekonkar.html', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' },
    { id: 'sample-gen-naam-japo', title: 'Naam Japo gallery wall (Saved AI scene)', image_data_url: '/samples/naam_japo_restored_gallery_live.webp', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' },
    { id: 'sample-gen-kirat-karo', title: 'Kirat Karo collector room (Saved AI scene)', image_data_url: '/samples/kirat_karo_collector_room_live.webp', source_url: 'https://www.artofsarabjitsingh.com/', source_label: 'Saved AI ad example (not original painting)', width: 1024, height: 1024, is_low_res: false, provenance: 'sample_generated' }
  ];
  const IMAGE_EMPTY_MSG = 'We couldn’t retrieve an image from this page. Try an artwork/product link or upload a photo.';
  let imagePickerSource = isEffectiveSample() ? 'sample' : 'website';
  let websiteImageCandidates = [];
  let imageFetchController = null;
  let imageFetchSeq = 0;

  function abortWebsiteImageFetch() {
    imageFetchSeq += 1;
    if (imageFetchController) {
      try { imageFetchController.abort(); } catch {}
      imageFetchController = null;
    }
  }

  function syncFrameControls() {
    const f = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    if ($('creatorCropToggle')) $('creatorCropToggle').textContent = f.fit === 'cover' ? 'Fill / Crop (active)' : 'Fit full image';
    if ($('creatorFrameX')) $('creatorFrameX').value = String(Number.isFinite(Number(f.x)) ? Number(f.x) : 0);
    if ($('creatorFrameY')) $('creatorFrameY').value = String(Number.isFinite(Number(f.y)) ? Number(f.y) : 0);
  }

  function formatImageMetaNote(meta) {
    if (!meta) return '';
    const dims = meta.width && meta.height ? `${meta.width} × ${meta.height} px` : 'Size unknown';
    if (meta.isLowRes) return `Low-res web preview (${dims}) — suitable for social preview, not a print master.`;
    if (meta.provenance === 'sample_original') return `Original artwork preview (${dims}) · Sample studio.`;
    if (meta.provenance === 'sample_generated') return `Saved AI ad example (${dims}) · Staging example.`;
    if (meta.provenance === 'upload') return `Uploaded photo (${dims}) · Kept on this device.`;
    return `Selected from your website (${dims}) · Confirm it matches your work.`;
  }

  function selectCandidateImage(item) {
    if (!item || !item.image_data_url) return;
    if (!isEffectiveSample() && item.provenance?.startsWith('sample_')) return;
    state.original = item.image_data_url;
    state.image = item.image_data_url;
    state.imageKind = item.provenance === 'sample_generated' ? 'saved' : 'original';
    state.imageFrame = { fit: 'contain', x: 0, y: 0 };
    state.imageMeta = {
      id: item.id || '',
      title: String(item.title || 'Selected image').slice(0, 160),
      sourceUrl: safeLink(item.source_url) || '',
      imageUrl: safeLink(item.image_url) || '',
      width: item.width || null,
      height: item.height || null,
      isLowRes: Boolean(item.is_low_res),
      provenance: item.provenance || 'website',
      confirmed: true,
    };
    if (!isEffectiveSample()) state.custom = true;
    state.provenance = item.provenance === 'sample_generated'
      ? 'Saved AI scene example. Compare against the original artwork.'
      : item.provenance === 'website'
        ? 'Selected from your website. Confirm this image matches your work.'
        : 'Original-photo layout. No new image generated.';
    state.revision += 1;
    $('reviewed').checked = false;
    if ($('productFactNote')) $('productFactNote').textContent = formatImageMetaNote(state.imageMeta);
    if ($('productImageCaption')) $('productImageCaption').textContent = formatImageMetaNote(state.imageMeta);
    syncFrameControls();
    refreshPreview();
    renderImagePicker();
    notify('Image selected. You can reposition, crop, or swap it anytime.');
  }

  function renderCandidateCard(item) {
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
      warn.textContent = `Low-resolution web preview (${dims}) — not a print master.`;
      card.append(warn);
    }

    const srcHref = safeLink(item.source_url);
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
    btn.addEventListener('click', () => selectCandidateImage(item));
    card.append(btn);
    return card;
  }

  function renderImagePicker() {
    const picker = $('imagePicker');
    const grid = $('imageCandidatesGrid');
    const status = $('imagePickerStatus');
    const sampleBtn = $('imgSrcSampleBtn');
    const websiteBtn = $('imgSrcWebsiteBtn');
    const confirmEl = $('imagePickerConfirm');
    if (!picker || !grid || !status) return;

    const inSample = isEffectiveSample();
    if (sampleBtn) sampleBtn.hidden = !inSample;
    if (!inSample && imagePickerSource === 'sample') imagePickerSource = 'website';
    if (websiteBtn) websiteBtn.classList.toggle('is-active', imagePickerSource === 'website');
    if (sampleBtn) sampleBtn.classList.toggle('is-active', inSample && imagePickerSource === 'sample');
    if (confirmEl) confirmEl.textContent = state.imageMeta ? formatImageMetaNote(state.imageMeta) : '';

    grid.replaceChildren();
    if (inSample && imagePickerSource === 'sample') {
      status.textContent = 'Checked-in sample artwork (originals separated from saved AI examples).';
      const origHeading = document.createElement('div');
      origHeading.className = 'muse-image-group-title';
      origHeading.textContent = 'Original artwork';
      grid.append(origHeading);
      for (const art of SAMPLE_IMAGE_ORIGINALS) grid.append(renderCandidateCard(art));

      const genHeading = document.createElement('div');
      genHeading.className = 'muse-image-group-title';
      genHeading.textContent = 'Saved generated ad examples';
      grid.append(genHeading);
      for (const art of SAMPLE_IMAGE_GENERATED) grid.append(renderCandidateCard(art));
      return;
    }

    if (!websiteImageCandidates.length) {
      if (!status.dataset.explicitMessage) {
        status.textContent = 'Enter your website or choose a listing to browse verified images, or upload a photo.';
      }
      return;
    }
    status.textContent = `Found ${websiteImageCandidates.length} image option${websiteImageCandidates.length === 1 ? '' : 's'} on your page. Select “Use this image” to apply.`;
    for (const item of websiteImageCandidates) grid.append(renderCandidateCard(item));
  }

  async function fetchWebsiteImageCandidates(rawPageUrl) {
    if (!$('imageCandidatesGrid')?.tagName || isEffectiveSample()) return;
    const cleanUrl = safeLink(rawPageUrl);
    if (!cleanUrl) return;
    abortWebsiteImageFetch();
    const seq = ++imageFetchSeq;
    const ownerEpoch = draftEpoch;
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    imageFetchController = controller;
    const status = $('imagePickerStatus');
    if (status) {
      delete status.dataset.explicitMessage;
      status.textContent = 'Checking this page for product & artwork images…';
    }
    imagePickerSource = 'website';
    try {
      const response = await fetch('/api/v1/product-reference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: cleanUrl }),
        signal: controller?.signal,
      });
      if (ownerEpoch !== draftEpoch || seq !== imageFetchSeq || isEffectiveSample()) return;
      const data = await response.json().catch(() => ({}));
      if (ownerEpoch !== draftEpoch || seq !== imageFetchSeq || isEffectiveSample()) return;
      if (!response.ok) {
        websiteImageCandidates = [];
        if (status) {
          status.dataset.explicitMessage = '1';
          status.textContent = IMAGE_EMPTY_MSG;
        }
        renderImagePicker();
        return;
      }
      const list = Array.isArray(data.image_candidates) && data.image_candidates.length
        ? data.image_candidates
        : (validInline(data.image_data_url) ? [{ id: 'web-1', image_data_url: data.image_data_url, source_url: data.url || cleanUrl, title: data.title || 'Found on page', width: data.image_width || null, height: data.image_height || null, is_low_res: Boolean(data.is_low_res), provenance: 'website' }] : []);
      websiteImageCandidates = list;
      if (!list.length && status) {
        status.dataset.explicitMessage = '1';
        status.textContent = IMAGE_EMPTY_MSG;
      }
      renderImagePicker();
    } catch (err) {
      if (err?.name === 'AbortError') return;
      if (ownerEpoch !== draftEpoch || seq !== imageFetchSeq || isEffectiveSample()) return;
      websiteImageCandidates = [];
      if (status) {
        status.dataset.explicitMessage = '1';
        status.textContent = IMAGE_EMPTY_MSG;
      }
      renderImagePicker();
    } finally {
      if (imageFetchController === controller) imageFetchController = null;
    }
  }

  function showImportedItems(items, businessName) {
    const box = $('importResults'); box.replaceChildren();
    if (!items.length) { box.hidden = false; $('importHint').textContent = 'No product listings were found. Some marketplaces block automatic reading; add the details and photo below, or try your own website.'; return; }
    const title = document.createElement('p'); title.className = 'small'; title.textContent = `Choose a listing from ${businessName}:`; box.append(title);
    for (const item of items) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'import-item';
      const info = document.createElement('span'); info.className = 'import-item-info';
      const slug = item.url?.split('/').filter(Boolean).pop()?.replace(/[-_]+/g, ' ') || '';
      const listingName = item.title || slug || 'Untitled product';
      const name = document.createElement('strong'); name.textContent = listingName; info.append(name);
      const sourceUrl = safeLink(item.url); if (sourceUrl) { const source = document.createElement('small'); source.textContent = new URL(sourceUrl).hostname; info.append(source); }
      button.append(info);
      if (item.price_hint) { const price = document.createElement('span'); price.textContent = item.price_hint; button.append(price); }
      button.addEventListener('click', () => {
        if (!state.original) newProduct();
        else state.custom = true;
        $('productName').value = listingName.slice(0, 180); $('productLink').value = safeLink(item.url) || '';
        $('sellerName').value = (businessName || '').slice(0, 120); $('productPrice').value = (item.price_hint || '').slice(0, 40);
        if (!state.copyEdited) $('productDescription').value = '';
        sync();
        if (!state.copyEdited) starter();
        changed();
        if (!state.original) $('productImageCaption').textContent = 'Choose an image from your website or upload a matching product photo.';
        if (item.url) fetchWebsiteImageCandidates(item.url);
        notify('Listing details added. Review and choose an image beside the listing.'); $('productName').focus();
      }); box.append(button);
    }
    box.hidden = false; $('importHint').textContent = 'Choose a listing to fill its title, price hint, and link, then pick an image in “Choose an image”.';
  }
  async function importProducts() {
    const ownerEpoch = draftEpoch;
    if (state.busy) return;
    const url = safeLink($('shopUrl').value.trim());
    if (!url) { notify('Enter your shop website starting with https://.', 'error'); $('shopUrl').focus(); return; }
    if (isOfflineNow()) { notify('You appear to be offline. Your work is saved on this device — reconnect and try again.', 'error'); return; }
    setBusy(true, 'importProducts'); $('importResults').hidden = true; notify('Looking for public product listings… This can take a little while.', 'busy');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch('/api/v1/ingest-storefront', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_name: ((state.custom ? $('sellerName').value.trim() : '') || new URL(url).hostname.replace(/^www\./, '')).slice(0, 160), website_url: url, max_urls_per_source: 30 }), signal: controller.signal });
      let data = {}; try { data = await response.json(); } catch { /* Gateways may return an HTML timeout page. */ }
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) throw new Error('Your session expired. Sign in again or enter the product details below.');
        throw new Error(typeof data.detail === 'string' && !/<html|traceback/i.test(data.detail) ? data.detail : 'We could not read that shop website. You can still enter the details below.');
      }
      if (ownerEpoch !== draftEpoch) return; const items = data.discovered_catalog_items || []; showImportedItems(items, data.business_name || 'your shop');
      const fetched = (data.channels || []).some((channel) => channel.status === 'fetched');
      if (fetched && $('saveShopWebsite')?.checked && !isEffectiveSample()) {
        await persistShopWebsiteUrl(url);
      }
      if (!isEffectiveSample()) {
        const candidatePage = items[0]?.url || url;
        fetchWebsiteImageCandidates(candidatePage);
      }
      notify(items.length ? `Found ${items.length} public listing${items.length === 1 ? '' : 's'}. Choose one to bring its details into your post.` : fetched ? 'We reached your website but did not find product listings. You can enter details below.' : 'This site did not allow automatic reading. You can still enter details below or try your own website.');
    } catch (error) {
      const msg = error.name === 'AbortError'
        ? 'This shop is taking too long to respond. Try again later or enter the details below.'
        : isOfflineNow() || /failed to fetch|networkerror/i.test(error?.message || '')
          ? 'You appear to be offline or the site could not be reached. Your work is still here.'
          : `${error.message} Your work is still here.`;
      notify(msg, 'error');
    }
    finally { clearTimeout(timer); setBusy(false); }
  }
  // First visit on this device. The account workspace says when the seller has a saved shop
  // website (see autoImportPending in workspace-modes.js). When My workspace opens here with
  // that signal, the seller's own listings are offered, once per device, under "Find products"
  // without a click and without locking the wizard. Nothing in the draft changes until the
  // seller picks a listing. The scan is a public crawl: no Muse run is used.
  let autoImportRunning = false;
  async function autoImportSavedShop(owner, shopName = '', workspace = null) {
    const modes = window.museModes;
    if (autoImportRunning || !owner || !modes?.autoImportPending?.(owner, 'create', workspace)) return;
    const url = safeLink(state.shopWebsiteUrl);
    // No saved website, a photo already chosen, or past the product step: do not ask again.
    if (!url || state.original || state.step !== 0) { modes.finishAutoImport?.(owner, 'create'); return; }
    // Busy or offline: try again on the next visit.
    if (state.busy || isOfflineNow()) return;
    const epoch = draftEpoch;
    const host = new URL(url).hostname.replace(/^www\./, '');
    const current = () => epoch === draftEpoch && draftReady && draftOwner === owner && !isEffectiveSample();
    let tried = false;
    autoImportRunning = true;
    const hint = $('importHint'); const hintBefore = hint.textContent;
    const looking = `Looking for your listings on ${host}, your saved shop website…`;
    hint.textContent = looking;
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch('/api/v1/ingest-storefront', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_name: (shopName || host).slice(0, 160), website_url: url, max_urls_per_source: 30 }), signal: controller.signal });
      let data = {}; try { data = await response.json(); } catch { /* Gateways may return an HTML timeout page. */ }
      if (!current()) return;
      tried = true;
      if (!response.ok) throw new Error('Shop website could not be read.');
      // A manual scan started meanwhile shows its own results.
      if (state.busy) return;
      const items = data.discovered_catalog_items || [];
      showImportedItems(items, data.business_name || shopName || 'your shop');
      if (!items.length) return;
      if (!state.original) fetchWebsiteImageCandidates(items[0].url || url);
      notify(`Found ${items.length} listing${items.length === 1 ? '' : 's'} on ${host}. Choose one to bring its details into your post.`);
    } catch {
      if (!current()) return;
      tried = true;
      hint.textContent = `We could not read ${host} automatically. Choose “Find products” to try again, or enter the details below.`;
    } finally {
      clearTimeout(timer);
      autoImportRunning = false;
      if (tried) modes.finishAutoImport?.(owner, 'create');
      // Abandoned part-way or overtaken by a manual scan: never leave "Looking…" on screen.
      if (hint.textContent === looking) hint.textContent = hintBefore;
    }
  }
  function validateProduct() { sync(); if (!state.product.name) { notify('Give your product a name first.', 'error'); $('productName').focus(); return false; } if (!state.original) { if ($('moreDetails')) $('moreDetails').open = true; notify('Add a product photo first to preview or export your image.', 'error', { text: 'Add photo', onClick: promptPhotoUpload }); return false; } if (state.product.link && !safeLink(state.product.link)) { $('moreDetails').open = true; notify('Use a complete http:// or https:// product link, or leave it empty.', 'error'); $('productLink').focus(); return false; } return true; }
  function go(step) {
    if (state.busy || (step > 0 && !validateProduct())) return;
    if (step === 3 && !postingChannels().length) { notify('Choose Instagram or Facebook for this post before sharing.', 'error'); go(0); return; }
    if (step === 3 && (!$('reviewed').checked || !state.headline || !state.caption)) { notify('Check your wording and product details, then tick the review box before sharing.', 'error'); go(2); return; }
    state.step = step;
    document.querySelectorAll('[data-panel]').forEach((el) => { el.hidden = Number(el.dataset.panel) !== step; });
    document.querySelectorAll('[data-step]').forEach((el) => { if (Number(el.dataset.step) === step) el.setAttribute('aria-current', 'step'); else el.removeAttribute('aria-current'); });
    $('backButton').disabled = step === 0; $('nextButton').hidden = step === 3; $('nextButton').textContent = (state.handoffActive && step === 0) ? 'Make it yours →' : (['Choose an idea →', 'Make it yours →', 'Ready to share →'][step] || 'Continue'); $('stepCount').textContent = `Step ${step + 1} of 4`; $('tryNext').hidden = state.custom || state.workspace !== 'sarabjit_singh';
    refreshPreview(); const h = document.querySelector(`[data-panel="${step}"] h2`); h.tabIndex = -1; h.focus({ preventScroll: true }); h.scrollIntoView({ behavior: 'auto', block: 'start' });
  }
  function refreshPreview() {
    persistDraft();
    for (const id of ['productImage', 'originalCompare']) { if (state.original) { $(id).src = state.original; $(id).hidden = false; } else { $(id).removeAttribute('src'); $(id).hidden = true; } }
    if ($('directPhotoUpload')) $('directPhotoUpload').textContent = state.original ? 'Change photo' : 'Add photo';
    if ($('shareMissingPhoto')) $('shareMissingPhoto').hidden = !!state.original;
    if (state.image) { $('sceneCompare').src = state.image; $('sceneCompare').hidden = false; } else { $('sceneCompare').removeAttribute('src'); $('sceneCompare').hidden = true; }
    $('sceneLabel').textContent = state.imageKind === 'original' ? 'Original-photo layout' : state.imageKind === 'saved' ? 'Saved AI scene' : 'New AI scene';
    $('previewShop').textContent = state.product.seller || 'Your shop'; $('previewHeadline').textContent = state.headline; $('previewCaption').textContent = state.caption; $('imageProvenance').textContent = state.provenance; $('shareTitle').textContent = state.product.name || 'Your product'; $('shareProvenance').textContent = state.provenance;
    if (state.idea?.why_this && $('ideaReason')) $('ideaReason').textContent = state.idea.why_this;
    if (state.idea?.headline && $('ideaTitle')) $('ideaTitle').textContent = state.idea.headline;
    const link = safeLink(state.product.link); $('listingLink').hidden = !link; if (link) $('listingLink').href = link;
    $('destinationNote').textContent = destinationNote();
    $('productPrice').placeholder = `Optional ${destinations[state.product.destination]} price`;
    $('postingSummary').textContent = `${postingChannels().map((c) => c === 'instagram' ? 'Instagram' : 'Facebook').join(' + ') || 'Choose a posting channel'} → ${destinations[state.product.destination]}${state.product.collection ? ` · ${state.product.collection}` : ''}. ${state.product.price ? `Selected offer: ${state.product.price}.` : 'No price included.'}`;
    $('postingSteps').replaceChildren(); for (const line of postingChecklist()) { const li = document.createElement('li'); li.textContent = line; $('postingSteps').append(li); }
    $('listingLink').textContent = `Check ${destinations[state.product.destination]} destination ↗`;
    const activePl = activePlacement();
    const feedText = activePl === 'facebook_feed' ? 'Download Facebook feed image ' : 'Download feed image ';
    const sizeText = activePl === 'facebook_feed' ? '1080 × 1080 PNG' : '1080 × 1350 PNG';
    for (const feedBtn of [$('downloadFeed'), $('quickExportFeedBtn')]) {
      if (!feedBtn) continue;
      if (typeof feedBtn.replaceChildren === 'function' && typeof document.createTextNode === 'function') {
        feedBtn.replaceChildren();
        feedBtn.append(document.createTextNode(feedText));
        const span = document.createElement('span');
        span.textContent = sizeText;
        feedBtn.append(span);
      } else {
        feedBtn.textContent = `${feedText}${sizeText}`;
      }
    }
    renderHandoffGuidance();
    const previewHeight = activePl === 'facebook_feed' ? 1080 : activePl === 'instagram_story' ? 1920 : 1350;
    const previewEl = $('previewCanvas');
    if (previewEl?.classList) {
      previewEl.classList.toggle('is-story-9x16', activePl === 'instagram_story');
      previewEl.classList.toggle('is-square-1x1', activePl === 'facebook_feed');
      previewEl.classList.toggle('is-feed-4x5', activePl !== 'instagram_story' && activePl !== 'facebook_feed');
    }
    const paint = ++state.paint; drawLayout(previewHeight).then((canvas) => {
      if (paint !== state.paint) return;
      const preview = $('previewCanvas');
      preview.width = 1080;
      preview.height = previewHeight;
      preview.getContext('2d').clearRect(0, 0, 1080, previewHeight);
      preview.getContext('2d').drawImage(canvas, 0, 0);
    }).catch(() => {});
  }
  function wrap(ctx, text, x, y, maxWidth, lineHeight, maxLines = 3) {
    const words = String(text).split(/\s+/); let line = ''; let count = 0;
    for (const word of words) { const next = line ? `${line} ${word}` : word; if (ctx.measureText(next).width > maxWidth && line) { ctx.fillText(line, x, y); y += lineHeight; count += 1; line = word; if (count >= maxLines - 1) break; } else line = next; }
    if (line) ctx.fillText(line, x, y); return y;
  }
  async function drawLayout(height) {
    const canvas = document.createElement('canvas'); canvas.width = 1080; canvas.height = height; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#f6f3eb'; ctx.fillRect(0, 0, 1080, height); ctx.fillStyle = '#263d35'; ctx.font = '24px sans-serif'; ctx.fillText((state.product.seller || 'Made with care').slice(0, 55), 80, 90);
    if (state.image) {
      const img = await imageElement(state.image);
      const area = { x: 80, y: 150, w: 920, h: height - 510 };
      const frame = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
      const scale = frame.fit === 'cover'
        ? Math.max(area.w / img.width, area.h / img.height)
        : Math.min(area.w / img.width, area.h / img.height);
      const w = img.width * scale, h = img.height * scale;
      const offX = (Math.max(-50, Math.min(50, Number(frame.x) || 0)) / 100) * Math.abs(area.w - w);
      const offY = (Math.max(-50, Math.min(50, Number(frame.y) || 0)) / 100) * Math.abs(area.h - h);
      ctx.fillStyle = '#e9e7dc';
      ctx.fillRect(area.x, area.y, area.w, area.h);
      ctx.save?.();
      ctx.beginPath?.();
      ctx.rect?.(area.x, area.y, area.w, area.h);
      ctx.clip?.();
      ctx.drawImage(img, area.x + (area.w - w) / 2 + offX, area.y + (area.h - h) / 2 + offY, w, h);
      ctx.restore?.();
    }
    ctx.fillStyle = '#263d35'; ctx.font = '46px Georgia'; wrap(ctx, state.headline || state.product.name || 'Your next shop post', 80, height - 280, 920, 55, 3); ctx.font = '25px sans-serif'; ctx.fillText((state.product.price || '').slice(0, 45), 80, height - 90); ctx.textAlign = 'right'; ctx.fillText((state.cta || 'Discover the story').slice(0, 35), 1000, height - 90); return canvas;
  }
  function spendLive(label) {
    try { if (window.museShell?.spendLive) window.museShell.spendLive(label); else if (window.museShell?.spend) window.museShell.spend(label); } catch {}
    try { if (window.museAccount?.refresh) window.museAccount.refresh().catch(() => {}); } catch {}
  }
  let lockedFocus = null;
  function setBusy(busy, activeId = '') {
    if (busy && document.activeElement && document.activeElement !== document.body) {
      lockedFocus = document.activeElement;
    }
    state.busy = busy;
    document.querySelectorAll('button').forEach((b) => { b.disabled = busy; });
    for (const id of [...Object.keys(fields), 'promotionDestination', 'postInstagram', 'postFacebook', 'shopUrl', 'headline', 'caption', 'scene', 'productPhoto', 'liveMode', 'reviewed', 'saveShopWebsite', 'saveWebsiteOnlyBtn']) if ($(id)) $(id).disabled = busy;
    $('backButton').disabled = busy || state.step === 0;
    const importBusy = busy && activeId === 'importProducts';
    const editorBusy = busy && activeId !== 'importProducts';
    $('importProducts').setAttribute('aria-busy', String(importBusy));
    $('draftButton').setAttribute('aria-busy', String(editorBusy));
    $('generateButton').setAttribute('aria-busy', String(editorBusy));
    if (!busy && lockedFocus && document.contains(lockedFocus) && !lockedFocus.disabled) {
      try { lockedFocus.focus({ preventScroll: true }); } catch {}
      lockedFocus = null;
    }
  }
  async function request(payload) {
    if (isOfflineNow()) throw new Error('You appear to be offline. Your edits are saved on this device — reconnect and try again.');
    const encoded = JSON.stringify(payload); if (new TextEncoder().encode(encoded).length > 3500000) throw new Error('This photo and text are too large together. Choose a smaller image.');
    // Account mode: live runs come from the signed-in account's plan; liveReady() shows sign-in/quota prompts.
    if (state.live && state.accountLive && window.museAccount?.liveReady && !window.museAccount.liveReady()) throw new Error('Sign in with a confirmed email and runs left to create with Muse.');
    if (state.live && !window.museAccount && (!state.readiness || state.readiness.default_mode !== 'live')) throw new Error('Live Muse AI requires a signed-in account with remaining runs.');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 285000);
    try {
      const response = await fetch('/api/v1/generate-ads' + (state.live ? '?live=true' : ''), { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: encoded, signal: controller.signal });
      if (!response.ok) {
        let detail = '';
        try {
          const body = await response.json();
          detail = typeof body.detail === 'string' && !/<html|traceback/i.test(body.detail)
            ? body.detail.slice(0, 350)
            : body.detail?.error === 'media_response_too_large'
              ? 'Muse finished, but the image was too large to send to this tab. Your original photo is still here. Check your saved output before trying again; do not rerun yet.'
              : '';
        } catch {}
        if (response.status === 401 || response.status === 403) {
          throw new Error(detail || 'Your session expired before Muse started, so no run was used. Sign in again; your edits are still here.');
        }
        if (response.status === 402 || response.status === 429) {
          throw new Error(detail || 'You have reached your current run allowance. Check your plan or wait a moment — your edits are still here.');
        }
        if (response.status >= 500) {
          throw new Error(detail || 'Muse is temporarily unavailable right now. No run was used and your edits are still here — please try again shortly.');
        }
        throw new Error(detail || 'Muse could not complete this request right now. Your edits are still here.');
      }
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('This request timed out. It may still be processing and may be billed. Your edits are safe; check completion before generating again.');
      if (isOfflineNow() || /failed to fetch|networkerror/i.test(error?.message || '')) throw new Error('You appear to be offline or the server could not be reached. Your edits are safe on this device — reconnect and try again.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  async function sourceData() { if (validInline(state.original)) return state.original; const response = await fetch(state.original); if (!response.ok) throw new Error('Could not load the original photo.'); const blob = await response.blob(); return await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob); }); }
  function productPayload() { return { title: state.product.name, description: state.product.description, price: state.product.price || undefined, brand_notes: `Seller: ${state.product.seller}. Goal: ${goals[state.goal][0]}. Destination: ${destinations[state.product.destination]}. Series: ${state.product.collection || 'Not assigned'}. Only use supplied product facts. Never assume the same artwork or price exists in another shop. Never invent scarcity, materials or reviews. For this artist, Etsy is closed. Do not recommend Etsy or state a price unless it is supplied for the selected destination.` }; }
  function researchContext() {
    // User uploads must never inherit an unrelated example shop's competitor claims.
    if (!state.custom) return state.presets?.workspaces?.[state.workspace]?.competitor_brief;
    return { competitor_url: '', competitor_domain: 'not-researched',
      seller_context: state.product.description, summary: 'No competitor research was performed. Use only seller-supplied facts.',
      new_product_frequency: 'Unknown', signals: { competitor_domain: 'not-researched', total_urls: 0 } };
  }
  function promotionResearchContext() {
    const context = researchContext();
    if (state.custom || state.workspace !== 'sarabjit_singh' || !context || typeof context !== 'object') return context;
    const safe = JSON.parse(JSON.stringify(context));
    safe.seller_context = 'Artist-reported channels: Pixels, Fine Art America, Saatchi Art, artist website, Instagram and linked Facebook page. Etsy is closed.';
    safe.summary = 'Use competitor content and category patterns only as inspiration for a respectful story-led post. Do not recommend a marketplace or state prices, discounts, scarcity, materials, or product claims.';
    safe.pricing_signals = [];
    safe.detected_price_hints = [];
    safe.actionable_insights = (safe.actionable_insights || []).filter((item) => !/etsy|\$|price|cheap|discount|starter print/i.test(JSON.stringify(item)));
    safe.competitor_gaps = (safe.competitor_gaps || []).filter((item) => !/etsy|\$|price|cheap|discount|starter print/i.test(String(item)));
    if (safe.signals) safe.signals = { ...safe.signals, detected_price_hints: [] };
    return safe;
  }
  async function draft() {
    const ownerEpoch = draftEpoch;
    if (state.busy || !validateProduct()) return;
    if (!state.live) { notify('Saved mode uses editable starter copy. Enable Live Muse AI below (1 run) to write a new draft.'); return; }
    if (window.museShell?.canRun && !window.museShell.canRun('Fresh Muse draft')) return;
    setBusy(true); notify('Muse is writing your draft. Your current words are kept until the new draft is ready…', 'busy');
    try { const result = await request({ draft: true, product: productPayload(), competitor_brief: promotionResearchContext(), placements: [activePlacement()], variants_per_placement: 1, use_comfyui: false }); if (ownerEpoch !== draftEpoch) return; const variant = result.variants?.[0]; if (!variant) throw new Error('Muse returned no editable draft. Your previous copy is still here.'); state.copyEdited = true; state.sceneEdited = true; state.headline = variant.headline; state.caption = variant.primary_text; state.scene = variant.image_prompt; $('headline').value = state.headline; $('caption').value = state.caption; $('scene').value = state.scene; $('reviewed').checked = false; refreshPreview(); spendLive('Fresh Muse draft'); notify('Fresh Muse draft ready. Read it through and make it sound like you.'); } catch (error) { try { window.museAccount?.refresh?.().catch(() => {}); } catch {} notify(error.message, 'error'); } finally { setBusy(false); }
  }
  async function generate() {
    const ownerEpoch = draftEpoch;
    if (state.busy || !validateProduct()) return;
    if (!state.live && !state.custom && typeof window !== 'undefined' && window.museShell) { if (window.museShell.requireRun && !window.museShell.requireRun('Ad scene')) return; setBusy(true); try { await window.museShell.progress('Staging your painting', ['Reading the saved Muse Image result', 'Fitting it to the feed layout', 'Adding your words']); } finally { setBusy(false); } }
    if (ownerEpoch !== draftEpoch) return;
    if (!state.live) { if (state.custom) { originalLayout(); notify('Your original-photo layout is ready. Saved mode does not generate personalized AI scenes.'); } else { state.image = state.sampleImage; state.imageKind = 'saved'; state.provenance = 'Saved Muse image from this example. No new image generated; compare details against the original. Frame and room are staging only.'; refreshPreview(); notify('Saved scene loaded. Your edited copy stays yours.'); } $('reviewed').checked = false; return; }
    if (!state.scene || !state.headline || !state.caption) { notify('Add your headline, caption and setting before creating an image.', 'error'); return; }
    if (window.museShell?.canRun && !window.museShell.canRun('Live Muse scene')) return;
    setBusy(true); notify('Muse is creating your scene. This can take a few minutes. Please keep this tab open…', 'busy');
    try {
      const product = { ...productPayload(), image_base64: await sourceData() };
      if (ownerEpoch !== draftEpoch) return;
      const placement = activePlacement();
      const result = await request({ product, draft: false, placements: [placement], variants_per_placement: 1, use_comfyui: false, muse_workflow_mode: 'product_visuals', brief: { product_title: state.product.name, positioning_hook: goals[state.goal][0], preserve_product_note: 'Compare generated product details against the original before publishing.', estimated_paid_calls: 1, variants: [{ variant_id: 'v1', include: true, placement: placement, headline: state.headline, primary_text: state.caption, image_prompt: state.scene, target_audience: 'People interested in this product and the maker’s story', angle_rationale: 'Seller-selected promotion goal' }] } });
      const creative = result.creatives?.[0]; if (!creative) throw new Error('Muse returned no image. Your original-photo layout is still available.');
      if (String(creative.produced_by).startsWith('demo-cache')) throw new Error('The server returned a saved example, not a new image. Live mode was not confirmed. Your original is still available.');
      const assetUrl = mediaAssetPath(creative.media_asset_url);
      const inlineUrl = validInline(creative.media_data_url) ? creative.media_data_url : '';
      const nextImage = assetUrl || inlineUrl;
      if (!nextImage) throw new Error('Muse completed the request, but this server has not delivered a usable inline image. Check saved output before trying again.');
      let chosenImage = nextImage;
      try {
        await imageElement(chosenImage);
      } catch (imgErr) {
        if (assetUrl && inlineUrl) {
          chosenImage = inlineUrl;
          await imageElement(chosenImage);
        } else {
          throw imgErr;
        }
      }
      if (ownerEpoch !== draftEpoch) return;
      state.image = chosenImage; state.imageKind = 'live'; state.provenance = `Generated with ${creative.produced_by || 'Muse'}. Review the artwork against the original. Product details can change; room and frame are staging only.`; $('reviewed').checked = false; refreshPreview(); spendLive('Live Muse scene'); notify('Your new scene is ready. Compare details with the original, or choose “Use original photo”. Check the draft storage status before closing this tab.');
    } catch (error) { try { window.museAccount?.refresh?.().catch(() => {}); } catch {} notify(error.message, 'error'); } finally { setBusy(false); }
  }
  function saveBlob(blob, suffix) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${(state.product.name || 'promotion').replace(/[^a-z0-9]+/gi, '-').slice(0, 60)}-${suffix}`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  async function download(height) {
    if (state.busy || !validateProduct()) return;
    if (!$('reviewed').checked) { notify('Review your image and wording before downloading.', 'error'); go(2); return; }
    setBusy(true);
    try {
      sync();
      const targetHeight = height || (activePlacement() === 'facebook_feed' ? 1080 : activePlacement() === 'instagram_story' ? 1920 : 1350);
      const canvas = await drawLayout(targetHeight);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('Could not create the download.');
      const suffix = targetHeight === 1350 ? 'feed.png' : targetHeight === 1080 ? 'facebook-feed.png' : 'story.png';
      saveBlob(blob, suffix);
      window.museTrack?.('post_downloaded', { placement: activePlacement(), height: targetHeight, page: '/create' });
      notify('Image downloaded using your current headline. Copy the matching caption before posting.');
      markIdeaExported();
    } catch (e) {
      notify(e.message, 'error');
    } finally {
      setBusy(false);
    }
  }
  function campaignPack() { sync(); return { product: { ...state.product, link: safeLink(state.product.link) }, goal: state.goal, idea_id: state.idea_id || undefined, cta: state.cta || undefined, headline: state.headline, caption: state.caption, scene_prompt: state.scene, image_provenance: state.provenance, image_meta: state.imageMeta, image_frame: state.imageFrame, mode: state.imageKind, posting_channels: postingChannels(), note: 'Download the image separately. This pack does not launch ads or publish posts. Destination details are kept only in this tab; prices are not synced.', posting_checklist: postingChecklist() }; }
  if ($('imgSrcWebsiteBtn')) $('imgSrcWebsiteBtn').addEventListener('click', () => { imagePickerSource = 'website'; renderImagePicker(); });
  if ($('imgSrcSampleBtn')) $('imgSrcSampleBtn').addEventListener('click', () => { if (!isEffectiveSample()) return; imagePickerSource = 'sample'; renderImagePicker(); });
  if ($('creatorCropToggle')) $('creatorCropToggle').addEventListener('click', () => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, fit: cur.fit === 'cover' ? 'contain' : 'cover' };
    syncFrameControls(); refreshPreview();
  });
  if ($('creatorFrameX')) $('creatorFrameX').addEventListener('input', (e) => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, x: Number(e.target.value) || 0 };
    refreshPreview();
  });
  if ($('creatorFrameY')) $('creatorFrameY').addEventListener('input', (e) => {
    const cur = isDraftObject(state.imageFrame) ? state.imageFrame : { fit: 'contain', x: 0, y: 0 };
    state.imageFrame = { ...cur, y: Number(e.target.value) || 0 };
    refreshPreview();
  });
  if ($('creatorFrameReset')) $('creatorFrameReset').addEventListener('click', () => {
    state.imageFrame = { fit: 'contain', x: 0, y: 0 };
    syncFrameControls(); refreshPreview();
  });
  for (const id of [...Object.keys(fields), 'headline', 'caption', 'scene']) $(id).addEventListener('input', changed);
  $('artistExample').addEventListener('click', () => {
    if (window.museModes && !isEffectiveSample()) { window.museModes.enterSampleMode({ sample: 'sarabjit_singh' }); return; }
    selectExample('sarabjit_singh');
  });
  $('ceramicsExample').addEventListener('click', () => {
    if (window.museModes && !isEffectiveSample()) {
      window.museModes.enterSampleMode({ sample: 'etsy_ceramics' });
      selectExample('etsy_ceramics');
      return;
    }
    selectExample('etsy_ceramics');
  });
  $('customProduct').addEventListener('click', () => {
    if (window.museModes && isEffectiveSample()) { window.museModes.goToOwnWorkspace(); return; }
    newProduct();
  });
  $('importProducts').addEventListener('click', importProducts);
  $('promotionDestination').addEventListener('change', switchDestination);
  for (const id of ['postInstagram', 'postFacebook']) $(id).addEventListener('change', changed);
  $('downloadInstructions').addEventListener('click', () => { if (state.busy || !$('reviewed').checked || !postingChannels().length) { notify('Review your post and choose a posting channel before downloading instructions.', 'error'); return; } const pack = campaignPack(); saveBlob(new Blob([`${pack.product.name}\n${$('postingSummary').textContent}\n\n${pack.headline}\n\n${pack.caption}\n\n${pack.posting_checklist.map((line, i) => `${i + 1}. ${line}`).join('\n\n')}`], { type: 'text/plain' }), 'posting-instructions.txt'); markIdeaExported(); });
  $('productPhoto').addEventListener('change', async (event) => { if (state.busy) return; try { await upload(event.target.files?.[0]); } catch (e) { notify(e.message, 'error'); } });
  if ($('shareAddPhotoBtn')) $('shareAddPhotoBtn').addEventListener('click', promptPhotoUpload);
  const stepButtons = [...document.querySelectorAll('[data-step]')];
  stepButtons.forEach((el, idx) => {
    el.addEventListener('click', () => go(Number(el.dataset.step)));
    el.addEventListener('keydown', (event) => {
      const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!delta) return;
      event.preventDefault();
      const next = stepButtons[(idx + delta + stepButtons.length) % stepButtons.length];
      go(Number(next.dataset.step));
      if (Number(next.dataset.step) === state.step) next.focus();
    });
  });
  const goalButtons = [...document.querySelectorAll('[data-goal]')];
  goalButtons.forEach((el, idx) => {
    el.addEventListener('click', () => {
      state.goal = el.dataset.goal;
      goalButtons.forEach((b) => {
        const active = b === el;
        b.classList.toggle('selected', active);
        b.setAttribute('aria-pressed', String(active));
      });
      $('ideaTitle').textContent = goals[state.goal][0];
      $('ideaReason').textContent = goals[state.goal][1];
      if (!state.copyEdited) starter();
      sync();
      refreshPreview();
      $('reviewed').checked = false;
    });
    el.addEventListener('keydown', (event) => {
      const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!delta) return;
      event.preventDefault();
      const next = goalButtons[(idx + delta + goalButtons.length) % goalButtons.length];
      next.click();
      next.focus();
    });
  });
  $('nextButton').addEventListener('click', () => go((state.handoffActive && state.step === 0) ? 2 : Math.min(3, state.step + 1))); $('backButton').addEventListener('click', () => go((state.handoffActive && state.step === 2) ? 0 : Math.max(0, state.step - 1)));
  $('quickExportFeedBtn')?.addEventListener('click', () => {
    if (!postingChannels().length) { notify('Choose Instagram or Facebook for this post before sharing.', 'error'); go(0); return; }
    download(activePlacement() === 'facebook_feed' ? 1080 : 1350);
  });
  $('audienceHypothesis')?.addEventListener('input', () => {
    if (state.handoffContext) {
      state.handoffContext.unconfirmed_audience = $('audienceHypothesis').value;
      state.revision += 1;
      persistDraft();
    }
  }); $('originalButton').addEventListener('click', () => { originalLayout(); $('reviewed').checked = false; }); $('draftButton').addEventListener('click', draft); $('generateButton').addEventListener('click', generate);
  $('downloadFeed').addEventListener('click', () => download(activePlacement() === 'facebook_feed' ? 1080 : 1350)); $('downloadStory').addEventListener('click', () => download(1920)); if ($('downloadSquare')) $('downloadSquare').addEventListener('click', () => download(1080)); $('downloadPack').addEventListener('click', () => { if (state.busy) return; if (!$('reviewed').checked) { notify('Review your product details and wording before downloading.', 'error'); return; } saveBlob(new Blob([JSON.stringify(campaignPack(), null, 2)], { type: 'application/json' }), 'campaign.json'); markIdeaExported(); });
  $('copyCaption').addEventListener('click', async () => {
    sync();
    const ctaLine = state.cta && !state.caption.includes(state.cta) ? `\n\n${state.cta}` : '';
    const text = `${state.headline}\n\n${state.caption}${ctaLine}${safeLink(state.product.link) ? '\n\n' + safeLink(state.product.link) : ''}`;
    try {
      await navigator.clipboard.writeText(text);
      notify('Your current caption and link are copied.');
      return;
    } catch {}
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      if (ok) {
        notify('Your current caption and link are copied.');
        return;
      }
    } catch {}
    notify('Clipboard access is unavailable. Select and copy your caption from the edit screen.', 'error', { text: 'Open edit screen', onClick: () => go(2) });
  });
  $('liveMode').addEventListener('change', () => {
    if ($('liveMode').checked && state.readiness && !state.readiness.provider_key_configured) {
      $('liveMode').checked = false;
      notify('Live Muse AI is unavailable on this server right now. Saved examples and manual editing still work.', 'error');
    } else if ($('liveMode').checked && window.museAccount?.liveReady && !window.museAccount.liveReady()) {
      $('liveMode').checked = false;
    } else if ($('liveMode').checked && !window.museAccount && !state.defaultLive) {
      $('liveMode').checked = false;
      notify('Sign in with a verified email and remaining runs to use live Muse AI.', 'error');
    }
    state.live = $('liveMode').checked;
    updateMode();
  });
  function syncAccountLive(snapshot = window.museAccount?.getSnapshot?.()) {
    const eligibilityEl = $('liveEligibilityNote');
    const serverReady = !state.readiness || state.readiness.provider_key_configured !== false;
    if (!serverReady) {
      if (state.live) { $('liveMode').checked = false; state.live = false; }
      $('liveMode').disabled = true;
      if (eligibilityEl) eligibilityEl.textContent = 'Live Muse AI is unavailable on this server right now. Manual editing and free downloads (0 runs) remain available.';
      updateMode();
      return;
    }
    $('liveMode').disabled = false;
    state.accountLive = state.readiness?.accounts_required === true && state.readiness?.provider_key_configured === true;
    const user = snapshot?.user || null;
    const remaining = snapshot?.usage && Number.isFinite(snapshot.usage.remaining) ? Math.max(0, snapshot.usage.remaining) : null;
    const eligible = Boolean(user && user.email_verified && snapshot?.live_available !== false && (remaining === null || remaining > 0));
    if (window.museAccount) {
      const autoOn = Boolean(state.accountLive && eligible);
      if (state.live !== autoOn && snapshot?.user) {
        $('liveMode').checked = autoOn;
        state.live = autoOn;
      } else if (!user && state.live) {
        $('liveMode').checked = false;
        state.live = false;
      }
    }
    if (eligibilityEl) {
      if (!user) eligibilityEl.textContent = 'Sign in with a confirmed email to use live Muse AI (1 run per live request; manual editing & downloads cost 0 runs).';
      else if (!user.email_verified) eligibilityEl.textContent = 'Confirm your email first to unlock live Muse AI (1 run per live request).';
      else if (remaining !== null && remaining <= 0) eligibilityEl.textContent = '0 runs remaining this period. Manual editing & downloads remain free (0 runs).';
      else eligibilityEl.textContent = `${remaining === null ? 'Unlimited' : `${remaining} ${remaining === 1 ? 'run' : 'runs'} left`} · Live AI draft or image uses 1 run. Editing & downloads cost 0 runs.`;
    }
    updateMode();
  }
  if (typeof window.addEventListener === 'function') window.addEventListener('account-change', (event) => syncAccountLive(event.detail));
  function updateMode() { const live = state.live; $('modeBadge').textContent = live ? 'Live Muse AI · 1 run per generation' : 'Draft & manual mode · 0 runs used'; $('modeBadge').classList.toggle('live', live); $('generateButton').textContent = live ? 'Create my image (1 run)' : 'Preview a room scene'; $('draftHint').textContent = live ? 'A live draft uses 1 run with your product details. Check every claim before sharing.' : 'Starter & manual editing cost 0 runs. Enable live Muse AI below (1 run) for custom AI writing.'; }

  const SAMPLE_ARTWORK_FALLBACKS = {
    ek_onkar: { id: 'ek_onkar', title: 'Ek Onkar · 12×12-inch print', original_image: '/samples/ek_onkar_original.jpg', staged_image: '/samples/ek_onkar_collector_room_live.webp', series: 'Sikh Sacred Word' },
    naam_japo: { id: 'naam_japo', title: 'Naam Japo · 12×12-inch print', original_image: '/samples/naam_japo_original.jpg', staged_image: '/samples/naam_japo_restored_gallery_live.webp', series: 'Sikh Sacred Word' },
    kirat_karo: { id: 'kirat_karo', title: 'Kirat Karo · 12×12-inch print', original_image: '/samples/kirat_karo_original.jpg', staged_image: '/samples/kirat_karo_collector_room_live.webp', series: 'Sikh Sacred Word' },
    golden_temple: { id: 'golden_temple', title: 'Golden Temple · fine art print', original_image: '/samples/golden_temple_holiday_gift_live.webp', staged_image: '/samples/golden_temple_holiday_gift_live.webp', series: 'Sacred Spaces' },
    diptych: { id: 'diptych', title: 'Ek Onkar + Kirat Karo diptych', original_image: '/samples/ek_onkar_original.jpg', staged_image: '/samples/diptych_ek_onkar_kirat_karo_live.webp', series: 'Sikh Sacred Word' },
    etsy_chai: { id: 'etsy_chai', title: 'Stoneware & brass chai set', original_image: '/samples/etsy_chai_set_product_visual_live.webp', staged_image: '/samples/etsy_chai_set_product_visual_live.webp', series: 'Tableware' },
  };

  function requestedPlacementParam() {
    try {
      const p = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('placement') : null;
      return (p === 'instagram_feed' || p === 'instagram_story' || p === 'facebook_feed') ? p : '';
    } catch (_) { return ''; }
  }

  function applyPlacementChoice(placement) {
    if (!placement) return;
    state.placement = placement;
    if (placement === 'facebook_feed') {
      $('postInstagram').checked = false;
      $('postFacebook').checked = true;
    } else if (placement === 'instagram_story' || placement === 'instagram_feed') {
      $('postInstagram').checked = true;
      $('postFacebook').checked = false;
    }
    if ($('downloadFeed') && $('downloadStory') && $('downloadSquare')) {
      $('downloadFeed').className = placement === 'instagram_feed' ? 'primary' : 'secondary';
      $('downloadStory').className = placement === 'instagram_story' ? 'primary' : 'secondary';
      $('downloadSquare').className = placement === 'facebook_feed' ? 'primary' : 'secondary';
    }
  }

  function applyArtwork(art) {
    const names = { ek_onkar: 'Ek Onkar', diptych_combine: 'Ek Onkar + Kirat Karo diptych', diptych: 'Ek Onkar + Kirat Karo diptych', naam_japo: 'Naam Japo', kirat_karo: 'Kirat Karo' };
    const name = names[art.id] || String(art.title || 'Artwork').replace(/^\d+\.\s*[^:]*:\s*/, '').slice(0, 80);
    state.custom = false;
    state.workspace = 'sarabjit_singh';
    state.artwork = { id: art.id, name, series: String(art.series || '').slice(0, 80) };
    state.product.name = name;
    state.product.seller = 'Art of Sarabjit Singh';
    state.product.description = `${name} by Sarabjit Singh. Check the selected shop for the matching artwork, available formats and current offer.`;
    state.original = samplePath(art.original_image) || state.original;
    state.sampleImage = samplePath(art.staged_image) || state.sampleImage;
    state.revision += 1;
    originalLayout(); setProductFields(); starter(); $('reviewed').checked = false; updateChoices(); refreshPreview();
    $('productImageCaption').textContent = `${name} · original artwork preview. Source: Art of Sarabjit Singh.`;
    notify(`Loaded sample artwork: ${name}. Choose “Preview a room scene” in step 3 to use its saved sample scene.`);
  }

  function initNeutralWorkspace(sellerLabel = 'Your Studio', productLabel = 'My studio product', preserveShopInput = false) {
    state.custom = true;
    state.workspace = 'own';
    state.artwork = null;
    state.idea_id = null;
    state.handoffActive = false;
    state.handoffContext = null;
    state.handoffId = null;
    state.product = {
      name: productLabel,
      seller: sellerLabel,
      series: '',
      price: '',
      description: `Original piece from ${sellerLabel}. Add your own details or paste your shop URL above.`,
      link: '',
      destination: 'website',
    };
    state.original = '';
    state.image = '';
    state.sampleImage = '';
    if (!preserveShopInput && $('shopUrl') && state.shopWebsiteUrl) $('shopUrl').value = state.shopWebsiteUrl;
    $('productFactNote').textContent = 'Your photo and edits stay on this device until you save or request live Muse AI.';
    $('productImageCaption').textContent = 'Your product photo will appear here.';
    originalLayout();
    setProductFields();
    starter();
    updateChoices();
    $('reviewed').checked = false;
    refreshPreview();
  }

  async function persistShopWebsiteUrl(rawUrl) {
    const clean = safeLink(rawUrl);
    if (!clean) {
      notify('Enter a complete website starting with https:// or http:// first.', 'error');
      $('shopUrl')?.focus();
      return false;
    }
    const mode = window.museModes?.current?.();
    if (!mode?.ownerId || mode.state !== 'account_own' || !window.museAccount?.loadWorkspace || !window.museAccount?.saveWorkspace) {
      notify('Sign in to My workspace to save a permanent shop website.', 'error');
      return false;
    }
    const guard = window.museModes.bindAsyncGuard();
    try {
      const ws = await window.museAccount.loadWorkspace(mode.ownerId);
      if (!guard.isCurrent()) return false;
      const doc = ws?.document || {};
      const existingOnb = doc.onboarding || {};
      const prevUrls = Array.isArray(existingOnb.shop_urls) ? existingOnb.shop_urls.filter(Boolean) : [];
      const nextUrls = [clean, ...prevUrls.filter((u) => u !== clean)].slice(0, 5);
      const nextDoc = {
        ...doc,
        onboarding: {
          ...existingOnb,
          shop_urls: nextUrls,
        },
      };
      await window.museAccount.saveWorkspace(nextDoc, mode.ownerId);
      if (!guard.isCurrent()) return false;
      state.shopWebsiteUrl = clean;
      if ($('savedShopWebsiteNote')) $('savedShopWebsiteNote').textContent = `Saved studio website: ${clean}`;
      notify(`Saved ${clean} as your shop website in My workspace.`);
      return true;
    } catch (err) {
      if (guard.isCurrent()) notify(err?.message || 'Could not save your shop website right now.', 'error');
      return false;
    }
  }

  if ($('saveWebsiteOnlyBtn')) {
    $('saveWebsiteOnlyBtn').addEventListener('click', () => {
      persistShopWebsiteUrl($('shopUrl')?.value?.trim() || '');
    });
  }

  let creatorModeSeq = 0;
  async function applyCreatorMode(modeState) {
    const seq = ++creatorModeSeq;
    const s = modeState || window.museModes?.current?.() || { state: 'guest_entry', isSample: isSampleMode(), isLoading: false, isError: false, isExpired: false, ownerId: null };
    if (s.isLoading || s.isError || s.isExpired) {
      draftReady = false;
      if ($('shopWebsiteSaveRow')) $('shopWebsiteSaveRow').hidden = true;
      return;
    }

    const nextOwner = s.ownerId || window.museAccount?.getSnapshot()?.user?.id || null;
    if (draftOwnerBound && nextOwner !== draftOwner) {
      return;
    }

    if (creatorInitializedOnce && draftReady && activeSampleMode !== !!s.isSample) {
      persistDraft();
    }
    // Listings found for one workspace must not stay on offer in the other.
    if (activeSampleMode !== !!s.isSample && $('importResults')) { $('importResults').replaceChildren?.(); $('importResults').hidden = true; }
    activeSampleMode = !!s.isSample;
    draftOwner = nextOwner;
    draftOwnerBound = true;
    abortWebsiteImageFetch();
    websiteImageCandidates = [];
    imagePickerSource = activeSampleMode ? 'sample' : 'website';
    if ($('imagePickerStatus')) delete $('imagePickerStatus').dataset.explicitMessage;

    const saveRow = $('shopWebsiteSaveRow');
    if (saveRow) saveRow.hidden = s.state !== 'account_own';
    if ($('artistExample')) {
      $('artistExample').hidden = false;
      if ($('artistExample').style) $('artistExample').style.display = '';
    }
    if ($('tryNext')) {
      $('tryNext').hidden = !s.isSample;
      if ($('tryNext').style) $('tryNext').style.display = s.isSample ? '' : 'none';
    }

    const params = typeof location !== 'undefined' ? new URLSearchParams(location.search) : null;
    const placement = requestedPlacementParam() || s.sampleParams?.placement || '';
    const requestedIdea = params?.get('idea') || s.sampleParams?.idea || '';
    const requestedArt = params?.get('artwork') || s.sampleParams?.artwork || '';

    if (s.isSample) {
      // Signed in but setup not finished: say this is demo data and point to the wizard.
      if (s.state === 'account_sample') window.museModes?.checkSetupPending?.(s.ownerId);
      let restored = false;
      applyingDraft = true;
      try {
        const sampleChoice = params?.get('sample') === 'etsy_ceramics' ? 'etsy_ceramics' : 'sarabjit_singh';
        selectExample(sampleChoice);
        restored = recoverDevice();
        const ideaSpec = requestedIdea ? findPreviewSpec(requestedIdea) : null;
        if (ideaSpec) {
          applyIdea(ideaSpec);
        } else if (requestedArt) {
          const presetArt = state.presets?.workspaces?.sarabjit_singh?.artworks_showcase?.find((a) => a && a.id === requestedArt) || SAMPLE_ARTWORK_FALLBACKS[requestedArt];
          if (presetArt) applyArtwork(presetArt);
        } else if (!restored) {
          const requestedGoal = params?.get('goal') || null;
          if (requestedGoal && Object.hasOwn(goals, requestedGoal)) document.querySelector?.(`[data-goal="${requestedGoal}"]`)?.click();
        }
        if (placement) {
          applyPlacementChoice(placement);
          refreshPreview();
        }
        updateChoices();
        syncFrameControls();
        renderImagePicker();
      } finally {
        applyingDraft = false;
        creatorInitializedOnce = true;
      }
      draftReady = true;
      return;
    }

    // account_own or guest_entry
    let recovered = false;
    applyingDraft = true;
    try {
      recovered = recoverDevice();
      if (!recovered) {
        initNeutralWorkspace('Your Studio', 'My studio artwork');
      }
      if (placement) {
        applyPlacementChoice(placement);
        refreshPreview();
      }
      updateChoices();
      syncFrameControls();
      renderImagePicker();
    } finally {
      applyingDraft = false;
      creatorInitializedOnce = true;
    }
    draftReady = true;

    let savedShop = null;
    if (s.state === 'account_own' && s.ownerId && window.museAccount?.loadWorkspace) {
      const guard = window.museModes?.bindAsyncGuard?.() || { isCurrent: () => true };
      try {
        const ws = await window.museAccount.loadWorkspace(s.ownerId);
        if (seq !== creatorModeSeq || !guard.isCurrent()) return;
        const onb = ws?.document?.onboarding || {};
        const shopUrls = Array.isArray(onb.shop_urls) ? onb.shop_urls.filter(Boolean) : [];
        const shopName = String(onb.business_name || '').trim();
        state.shopWebsiteUrl = shopUrls[0] || '';
        if ($('savedShopWebsiteNote')) {
          $('savedShopWebsiteNote').textContent = state.shopWebsiteUrl
            ? `Saved studio website: ${state.shopWebsiteUrl}`
            : 'No shop website saved in My workspace yet.';
        }
        if ($('shopUrl') && !$('shopUrl').value && state.shopWebsiteUrl) {
          $('shopUrl').value = state.shopWebsiteUrl;
        }
        if (!recovered && shopName) {
          initNeutralWorkspace(shopName, `Product from ${shopName}`, true);
        }
        savedShop = { name: shopName, workspace: ws };
      } catch {
        if (seq !== creatorModeSeq) return;
        if ($('savedShopWebsiteNote')) $('savedShopWebsiteNote').textContent = 'Add a shop website above to import your products.';
      }
    }
    // Only after this account's workspace loaded, and never over a recommendation handoff.
    if (savedShop && !requestedHandoffId()) autoImportSavedShop(s.ownerId, savedShop.name, savedShop.workspace);
    const handoffId = requestedHandoffId();
    const handoff = readRecommendationHandoff(s.ownerId);
    if (handoffId && state.handoffId === handoffId && state.handoffActive && state.handoffContext) {
      renderHandoffGuidance();
    } else if (handoff) {
      applyRecommendationHandoff(handoff);
    } else if (handoffId) {
      state.handoffActive = false;
      state.handoffContext = null;
      state.handoffId = null;
      renderHandoffGuidance();
      notify('That recommendation link is expired, invalid, or belongs to a different account/mode. Your current draft was kept safe.', 'error');
    } else {
      renderHandoffGuidance();
    }
  }

  const standaloneVm = typeof window.museModes === 'undefined' && typeof window.museAccount === 'undefined';
  if (standaloneVm) {
    selectExample('sarabjit_singh');
    const vmPlacement = requestedPlacementParam();
    if (vmPlacement) applyPlacementChoice(vmPlacement);
    initDrafts();
    syncFrameControls();
    renderImagePicker();
  } else {
    initDrafts();
    if (window.museModes?.subscribe) window.museModes.subscribe((m) => { applyCreatorMode(m); });
    if (window.museModes?.resolve) window.museModes.resolve().then((m) => { applyCreatorMode(m); });
    else applyCreatorMode();
  }

  const presetsGuard = window.museModes?.bindAsyncGuard?.() || { isCurrent: () => true };
  Promise.allSettled([fetch('/api/v1/demo-presets').then((r) => { if (!r.ok) throw new Error(); return r.json(); }), fetch('/api/v1/readiness').then((r) => { if (!r.ok) throw new Error(); return r.json(); })]).then(([presets, readiness]) => {
    if (readiness.status === 'fulfilled') {
      state.readiness = readiness.value;
      state.defaultLive = readiness.value.default_mode === 'live';
      state.accountLive = readiness.value.accounts_required === true && readiness.value.provider_key_configured === true;
      syncAccountLive();
    }
    updateMode();
    if (!presetsGuard.isCurrent()) return;
    if (presets.status === 'fulfilled') {
      state.presets = presets.value;
      const modeNow = window.museModes?.current?.();
      const requestedArt = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('artwork') : null;
      if ((modeNow?.isSample || standaloneVm) && requestedArt && !state.custom) {
        const art = state.presets?.workspaces?.sarabjit_singh?.artworks_showcase?.find((a) => a && a.id === requestedArt) || SAMPLE_ARTWORK_FALLBACKS[requestedArt];
        if (art && samplePath(art.staged_image)) {
          applyArtwork(art);
          const pl = requestedPlacementParam();
          if (pl) { applyPlacementChoice(pl); refreshPreview(); }
        }
      }
    } else if (window.museModes?.isSampleMode?.() || standaloneVm) {
      notify('Sample example loaded. Preset research details are temporarily unavailable.', 'error');
    }
  });

  if (standaloneVm) {
    const requestedIdea = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('idea') : null;
    const ideaSpec = requestedIdea ? findPreviewSpec(requestedIdea) : null;
    if (ideaSpec) {
      applyIdea(ideaSpec);
      window.museTrack?.('post_started', { idea_id: requestedIdea, source: 'creator' });
    } else {
      const requestedGoal = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('goal') : null;
      if (requestedGoal && Object.hasOwn(goals, requestedGoal)) document.querySelector?.(`[data-goal="${requestedGoal}"]`)?.click();
      window.museTrack?.('post_started', { idea_id: null, goal: requestedGoal || 'default', source: 'creator' });
    }
  }
  // Expose a read-only snapshot for focused offline contract checks; never expose credentials or keys.
  window.museCreatorSnapshot = () => JSON.parse(JSON.stringify({ ...campaignPack(), placement: activePlacement() }));
  window.museDrawLayout = (height) => drawLayout(height);
})();
