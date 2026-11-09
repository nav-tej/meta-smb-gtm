'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const names = { instagram: 'Instagram', facebook: 'Facebook', x: 'X', tiktok: 'TikTok' };
  const shops = { pixels: 'Pixels', fineartamerica: 'Fine Art America', saatchi: 'Saatchi Art', website: 'Artist website', other: 'Your shop' };
  const storageKey = 'muse-daily-v1';
  const originalSample = '/samples/ek_onkar_original.jpg';
  const initialProduct = () => ({ title: 'Ek Onkar', description: 'An artwork by Sarabjit Singh exploring connection and equality through color and form.', seller: 'Art of Sarabjit Singh', collection: '', price: '', destination_url: 'https://sarabjit-singh.pixels.com/', destination: 'pixels' });
  const state = { product: initialProduct(), original: originalSample, image: originalSample, imageMode: 'original', source: 'Suggested from the artist example', channel: 'instagram', format: 'image', goal: 'visits', salesGoal: null, performance: null, plans: {}, edits: {}, selected: 0, posted: {}, offers: {}, busy: false, revision: 0, paint: 0, live: false, key: '', readiness: null };

  const draftNamespace = 'daily';
  function editorDocument() { return { schema: 1, ...Object.fromEntries(['product', 'original', 'image', 'imageMode', 'source', 'channel', 'selected', 'format', 'goal', 'salesGoal', 'performance', 'plans', 'edits', 'posted', 'offers'].map(key => [key, state[key]])) }; }
  const isDraftObject = value => !!value && typeof value === 'object' && !Array.isArray(value);
  function applyDocument(data) {
    if (!data || (data.schema !== undefined && data.schema !== 1) || typeof data.product?.title !== 'string' || (data.original !== '' && !imageSource(data.original))) throw new Error('Unsupported daily draft.');
    for (const key of ['plans', 'edits', 'posted', 'offers']) if (data[key] !== undefined && !isDraftObject(data[key])) throw new Error('Invalid daily draft fields.');
    state.plans = {}; state.edits = {}; state.posted = {}; state.offers = {}; state.performance = null; state.salesGoal = null;
      for (const key of ['product', 'original', 'source', 'salesGoal', 'performance', 'posted', 'offers']) if (data[key] !== undefined) state[key] = data[key];
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
      if (!Object.hasOwn(shops, state.product.destination)) state.product.destination = 'other';

    state.revision += 1; $('reviewed').checked = false; populateSetup(); render();
  }
  function persist() { persistDraft(); }

  // Editor-local adapter: keep this contract aligned in creator.js and today.js.
  let draftReady = false, draftOwner = null, draftEpoch = 0, cloudBusy = false;
  let cloudBase, conflictValue, recoveryDraft, applyingDraft = false;
  const cloneDraft = value => JSON.parse(JSON.stringify(value));
  const draftStatus = text => { $('draftStatus').textContent = text; };
  const deviceKey = () => `muse-editor-v1:${draftNamespace}:${draftOwner ? 'account:' + encodeURIComponent(draftOwner) : 'guest'}`;
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
      const raw = localStorage.getItem(deviceKey()) || (!draftOwner ? localStorage.getItem(storageKey) : null);
      if (raw) { installDocument(JSON.parse(raw)); draftStatus('Recovered this device’s draft. Review before sharing.'); }
    } catch { draftStatus('Could not recover device storage. Keep this tab open; download a backup or load your account draft.'); }
  }
  function currentOwner(epoch, owner) {
    return draftReady && epoch === draftEpoch && owner === draftOwner && owner === window.museAccount?.getSnapshot()?.user?.id;
  }
  async function accountDraft(action) {
    const api = window.museAccount;
    if (!draftReady || cloudBusy || state.busy) return;
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
      draftReady = true; recoverDevice();
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
        draftReady = false; draftEpoch += 1; state.revision += 1; state.paint += 1; state.key = ''; state.live = false;
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
  const safeURL = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const inline = value => typeof value === 'string' && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length <= 4000000;
  const mediaAsset = value => typeof value === 'string' && /^\/api\/v1\/account\/media\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(value);
  const imageSource = value => inline(value) || mediaAsset(value) || /^\/samples\/[a-zA-Z0-9_.-]+$/.test(value || '');
  const isOfflineNow = () => Boolean(window.museShell?.isOffline?.() || (typeof navigator !== 'undefined' && navigator.onLine === false));
  function notice(message, error = false, busy = false) { $('notice').hidden = false; $('notice').textContent = message; $('notice').className = error ? 'error' : (busy ? 'busy' : ''); }
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
    if (isOfflineNow()) throw new Error('You appear to be offline. Your edits are saved on this device — reconnect and try again.');
    const control = new AbortController(); const timer = setTimeout(() => control.abort(), live ? 285000 : 45000);
    try {
      const init = { method: 'POST', headers: { 'Content-Type': 'application/json', ...(live && state.key ? { 'X-Demo-Key': state.key } : {}) }, body: JSON.stringify(payload), signal: control.signal };
      const shell = window.museShell;
      // Saved-mode requests retry on network/5xx errors; billed live requests never auto-retry.
      const response = !live && shell?.fetch ? await shell.fetch(path, init, { safe: true, timeoutMs: 45000 }) : await fetch(path + (live ? '?live=true' : ''), init);
      if (live) { shell?.syncCredits?.(); if (response.headers?.get?.('X-Muse-Fallback')) shell?.toast?.('Live Muse was unavailable, so saved results are shown. No run was used.', 'warn'); }
      let data; try { data = await response.json(); } catch { throw new Error('The server could not finish. Your edits are still here.'); }
      if (!response.ok) {
        const detail = typeof data.detail === 'string' && !/<html|traceback/i.test(data.detail) ? data.detail : '';
        if (response.status === 401 || response.status === 403) throw new Error(detail || 'Your session expired before Muse started, so no run was used. Sign in again; your edits are still here.');
        if (response.status === 402 || response.status === 429) throw new Error(detail || 'You have reached your current run allowance. Check your plan or wait a moment — your edits are still here.');
        if (response.status >= 500) throw new Error(detail || 'Muse is temporarily unavailable right now. No run was used and your edits are still here — please try again shortly.');
        throw new Error(detail || 'Check the item details and try again.');
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error(live ? 'Muse timed out and may still be processing. Check completion before paying for another request.' : 'That site is taking too long. Enter your item below.');
      if (isOfflineNow() || /failed to fetch|networkerror/i.test(error?.message || '')) throw new Error('You appear to be offline or the server could not be reached. Your edits are still here — reconnect and try again.');
      throw error;
    }
    finally { clearTimeout(timer); }
  }
  function planPayload(live) { return { product: { title: state.product.title, description: state.product.description, price: state.product.price || undefined, destination_url: safeURL(state.product.destination_url) || undefined, seller: state.product.seller, collection: state.product.collection }, channels: [state.channel], goal: state.goal, sales_goal: state.salesGoal || undefined, performance: state.performance || undefined, use_muse: live }; }
  async function buildPlan(live = false, force = false) {
    if (state.busy) return;
    if (live && !liveReady()) return;
    if (!force && !live && currentPlan()) { render(); return; }
    const channel = state.channel; const revision = state.revision;
    lock(true, live ? 'musePlan' : ''); if (live) notice('Muse is writing three posts from your item and goal…', false, true);
    try {
      const plan = await jsonRequest('/api/v1/content-plan', planPayload(live), live);
      if (!Array.isArray(plan.posts) || plan.posts.length !== 3) throw new Error('No usable plan came back. Your existing post is unchanged.');
      if (state.revision !== revision || state.channel !== channel) return;
      state.plans[channel] = plan; state.selected = 0;
      if (live) { for (const key of Object.keys(state.edits)) if (key.startsWith(channel + ':')) delete state.edits[key]; notice('Muse plan ready. Check the words and make them yours.'); }
      invalidate(); render(); persist();
    } catch (error) { notice(error.message, true); }
    finally { lock(false); }
  }
  function render() {
    const plan = currentPlan(); const post = currentPost(); const copy = formatCopy(post);
    $('itemTitle').textContent = state.product.title; $('itemSource').textContent = state.source;
    $('dailyReason').textContent = `Start with ${state.product.title || 'your item'} on ${names[state.channel]}. Review, take it with you, done.`;
    $('postHook').value = copy.hook || ''; $('postCaption').value = copy.caption || ''; $('copyCount').textContent = `${(copy.caption || '').length} characters`;
    $('format').value = state.format;
    document.querySelectorAll('[data-channel]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.channel === state.channel)));
    $('planMode').textContent = plan?.mode === 'muse' ? 'Muse Spark draft' : 'Starter draft';
    const tips = {
      instagram: 'Use the image for Feed. Put the shop link in your profile or a Story link sticker.',
      facebook: 'Add your shop link to the caption. Check linked Instagram sharing before posting twice.',
      x: 'Keep one clear point and one link. Add an image description when you upload.',
      tiktok: 'Start with a visual hook. Use vertical video and captions; add suitable audio in TikTok.'
    };
    $('channelTip').textContent = tips[state.channel];
    $('visualDirection').textContent = post?.visual_direction || 'Show the original artwork clearly, then a detail and your invitation.';
    const url = safeURL(state.product.destination_url); $('destinationLink').hidden = !url; if (url) $('destinationLink').href = url;
    $('destinationLink').textContent = `${shops[state.product.destination] || 'Your shop'} ↗`;
    $('offerNote').textContent = state.product.price ? `${state.product.price} · confirm before posting` : 'No price included';
    $('imageNote').textContent = state.imageMode === 'live' ? 'Muse scene · compare artwork details' : 'Original image · fitted without cropping';
    const label = state.format === 'text' ? 'Copy ready-to-post text' : state.format === 'video' ? 'Get short video + caption' : 'Get photo + caption'; $('getPost').textContent = label;
    $('deliveryNote').textContent = state.format === 'video' ? 'Makes a silent 6-second artwork clip. Add voice or audio in your app. You post it yourself.' : state.format === 'text' ? 'Copies your post. Instagram and TikTok need a visual; use this text with your image or video.' : 'Downloads the image and copies your text. You post from your account.';
    $('postedStatus').textContent = state.posted[postIdentity()] ? 'Marked posted on this device' : '';
    $('noPhoto').hidden = !!state.image || state.format === 'text';
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
    if (src) { const image = await loadImage(src); const area = { x: 80, y: 150, w: 920, h: height - 520 }; const scale = Math.min(area.w / image.width, area.h / image.height); const w = image.width * scale; const h = image.height * scale; ctx.drawImage(image, area.x + (area.w - w) / 2, area.y + (area.h - h) / 2, w, h); }
    ctx.fillStyle = '#253d34'; fitText(ctx, copy.hook || state.product.title, 80, height - 280, 880, 46, 3);
    ctx.font = '24px sans-serif'; ctx.fillText((currentPost()?.cta || 'Explore the work').slice(0, 55), 80, height - 95); return canvas;
  }
  function paint() { const token = ++state.paint; const height = state.format === 'video' ? 1920 : 1350; layout(height).then(canvas => { if (token !== state.paint) return; const preview = $('postCanvas'); preview.width = canvas.width; preview.height = canvas.height; preview.getContext('2d').drawImage(canvas, 0, 0); }).catch(error => notice(error.message, true)); }
  function saveBlob(blob, suffix) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${state.product.title.replace(/[^a-z0-9]+/gi, '-').slice(0, 45)}-${state.channel}-${suffix}`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
  function captionText() { const copy = currentCopy(); const url = safeURL(state.product.destination_url); let text = `${copy.hook}\n\n${copy.caption}`; const cta = currentPost()?.cta; if (cta && !text.includes(cta)) text += `\n\n${cta}`; if (url && ['facebook', 'x'].includes(state.channel) && !text.includes(url)) text += `\n\n${url}`; if (url && ['instagram', 'tiktok'].includes(state.channel) && !/profile link|link in my profile/i.test(text)) text += '\n\nExplore the work through the link in my profile.'; return text; }
  async function copyText() {
    const text = captionText(); let timeout;
    try {
      await Promise.race([navigator.clipboard.writeText(text), new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Clipboard unavailable')), 1500); })]);
      return true;
    } catch { saveBlob(new Blob([text], { type: 'text/plain' }), 'caption.txt'); return false; }
    finally { clearTimeout(timeout); }
  }
  function reviewed() {
    if (!$('reviewed').checked) { notice('Check the image, words and destination, then tick the review box.', true); $('reviewed').focus(); return false; }
    if (!currentCopy().hook || !currentCopy().caption) { notice('Add an opening line and caption.', true); return false; }
    if (state.channel === 'x' && captionText().length > 280) { notice('Shorten your X post to 280 characters including the link.', true); return false; }
    if (state.format !== 'text' && !state.image) { notice('Add the matching product photo first.', true); return false; } return true;
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
      notice(`${state.format === 'video' ? 'Clip' : 'Image'} downloaded. ${copied ? 'Caption copied' : 'Caption downloaded'} — open ${names[state.channel]} and add your post.`);
    } catch (error) { notice(error.message, true); } finally { lock(false); }
  }
  function populateSetup() {
    const p = state.product; $('productName').value = p.title; $('sellerName').value = p.seller || ''; $('productDescription').value = p.description || ''; $('destination').value = p.destination || 'other'; $('price').value = p.price || ''; $('productLink').value = p.destination_url || ''; $('collection').value = p.collection || ''; $('goal').value = state.goal; $('salesGoal').value = state.salesGoal || '';
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
    $('itemHint').textContent = `${shops[next]} keeps its own price and link. Choose a matching listing; other shops may carry different work.`;
  }
  async function useReference(url) {
    const ownerEpoch = draftEpoch;
    const safe = safeURL(url); if (!safe) throw new Error('Enter a complete shop or listing link.');
    const data = await jsonRequest('/api/v1/product-reference', { url: safe });
    if (ownerEpoch !== draftEpoch) return;
    state.product = { title: data.title || new URL(safe).hostname, description: data.description || '', price: data.price_hint || '', seller: new URL(safe).hostname, destination_url: safeURL(data.url) || safe, destination: 'other', collection: '' };
    state.original = inline(data.image_data_url) ? data.image_data_url : ''; state.image = state.original; state.imageMode = 'original'; state.offers = {}; state.plans = {}; state.edits = {}; state.selected = 0; state.performance = null; state.source = `From ${new URL(safe).hostname} · check product facts`; invalidate(); populateSetup(); $('importStatus').textContent = data.source_note || 'Listing ready. Check the item and photo.';
  }
  async function readListing() {
    if (state.busy) return;
    lock(true, 'readListing'); $('importStatus').classList?.add?.('busy'); $('importStatus').textContent = 'Reading listing details…';
    try { await useReference($('shopUrl').value); notice('Listing selected. Check its details, then use this item.'); }
    catch (error) { $('importStatus').textContent = error.message; }
    finally { $('importStatus').classList?.remove?.('busy'); lock(false); }
  }
  async function findItems() {
    const ownerEpoch = draftEpoch;
    if (state.busy) return; const url = safeURL($('shopUrl').value.trim()); if (!url) { $('importStatus').textContent = 'Enter a full shop URL.'; return; }
    lock(true, 'findItems'); $('importStatus').classList?.add?.('busy'); $('importStatus').textContent = 'Finding a product for your next post…'; $('importItems').replaceChildren();
    try {
      const data = await jsonRequest('/api/v1/ingest-storefront', { website_url: url, business_name: new URL(url).hostname, max_urls_per_source: 20 });
      const items = (data.discovered_catalog_items || []).filter(item => safeURL(item.url)); const products = items.filter(item => ['products', 'listings'].includes(item.bucket)); const choices = products.length ? products : items;
      if (!choices.length) { $('importStatus').textContent = 'No items found. Paste a product link or enter one below.'; return; }
      for (const [i, item] of choices.entries()) { const button = document.createElement('button'); button.type = 'button'; button.textContent = `${i === 0 ? 'Suggested: ' : ''}${item.title || 'View listing'}`; button.addEventListener('click', async () => { if (state.busy) return; lock(true, 'readListing'); try { await useReference(item.url); } catch (error) { $('importStatus').textContent = error.message; } finally { lock(false); } }); $('importItems').append(button); }
      await useReference(choices[0].url); $('importStatus').textContent = 'First product listing selected. Change it below or use this item.';
    } catch (error) { $('importStatus').textContent = error.message; } finally { $('importStatus').classList?.remove?.('busy'); lock(false); }
  }
  async function upload(file) {
    const ownerEpoch = draftEpoch;
    if (!file || state.busy) return; if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10000000) { notice('Choose a JPEG, PNG or WebP under 10 MB.', true); return; }
    const url = URL.createObjectURL(file); lock(true);
    try { const image = await loadImage(url); if (ownerEpoch !== draftEpoch) return; const canvas = document.createElement('canvas'); const scale = Math.min(1, 1400 / Math.max(image.width, image.height)); canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale); const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height); const data = canvas.toDataURL('image/jpeg', .8); if (!inline(data)) throw new Error('Try a smaller photo.'); state.original = data; state.image = data; state.imageMode = 'original'; invalidate(); render(); persist(); notice('Photo ready. Check your post and take it with you.'); }
    catch (error) { notice(error.message, true); } finally { URL.revokeObjectURL(url); lock(false); }
  }
  // Signed-in accounts with runs left create live by default; the settings switch still turns it off.
  function syncAccountLive(snapshot = window.museAccount?.getSnapshot?.()) {
    if (!state.readiness?.accounts_required || !state.readiness?.provider_key_configured) return;
    const on = !!(snapshot?.user?.email_verified && snapshot.live_available);
    state.live = on; const toggle = document.getElementById('liveMode'); if (toggle) toggle.checked = on;
  }
  if (typeof window.addEventListener === 'function') window.addEventListener('account-change', (event) => syncAccountLive(event.detail));
  function liveReady() {
    // Account mode: the signed-in account's plan pays for the run; no presenter key or settings switch.
    if (state.readiness?.accounts_required && state.readiness?.provider_key_configured) { if (window.museAccount?.liveReady?.() !== true) return false; state.live = true; return true; }
    if (!state.live) { notice('Enable a configured live Muse session in Muse settings first.', true); return false; }
    if (!state.readiness?.provider_key_configured) { notice('This server has no Muse key configured. Starter drafts still work.', true); return false; }
    if (state.readiness.default_mode !== 'live' && !state.key) { notice('Enter the demo unlock key in Muse settings.', true); return false; } return true;
  }
  async function museImage() {
    const ownerEpoch = draftEpoch;
    if (state.busy || !liveReady()) return; if (!state.original) { notice('Add your original photo first.', true); return; }
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
  $('markPosted').addEventListener('click', () => { if (state.busy || !reviewed()) return; state.posted[postIdentity()] = new Date().toISOString(); persist(); render(); notice('Marked posted on this device. You’re done for today. Add results when you have them.'); });
  $('downloadPlan').addEventListener('click', () => { const plan = currentPlan(); if (!plan || state.busy) return; const rows = plan.posts.map((post, i) => { const edited = state.edits[`${state.channel}:${i}:${post.format}`]; return `${post.day_offset === 0 ? 'Today' : `In ${post.day_offset} days`} · ${names[post.channel]} · ${post.format}\n${edited?.hook || post.hook}\n${edited?.caption || post.caption}\n${post.visual_direction}\n${post.posting_tip}`; }); saveBlob(new Blob([`${state.product.title}\n${plan.mode === 'muse' ? 'Muse Spark plan' : 'Starter plan'} · manual posting\n\n${rows.join('\n\n')}\n\nDestination: ${safeURL(state.product.destination_url)}\nSuggested days, not scheduled posts. Add only offers you can fulfill.`], { type: 'text/plain' }), 'posting-plan.txt'); });
  $('resultsForm').addEventListener('submit', async event => { event.preventDefault(); if (state.busy) return; const values = {}; for (const key of ['views', 'clicks', 'inquiries', 'sales']) values[key] = Number($(key).value) || 0; if (Object.values(values).some(value => !Number.isSafeInteger(value) || value < 0)) { notice('Use whole, non-negative counts.', true); return; } state.performance = values; state.plans = {}; invalidate(); await buildPlan(false, true); persist(); $('resultsDetails').open = false; });
  $('clearResults').addEventListener('click', async () => { if (state.busy) return; state.performance = null; for (const key of ['views', 'clicks', 'inquiries', 'sales']) $(key).value = ''; state.plans = {}; invalidate(); await buildPlan(false, true); persist(); $('resultsDetails').open = false; });
  $('unlockKey').addEventListener('input', () => { state.key = $('unlockKey').value.trim(); }); $('liveMode').addEventListener('change', () => { state.live = $('liveMode').checked; });
  $('musePlan').addEventListener('click', () => buildPlan(true, true)); $('museImage').addEventListener('click', museImage);
  $('useOriginal').addEventListener('click', () => { if (state.busy) return; state.image = state.original; state.imageMode = 'original'; invalidate(); render(); persist(); });
  populateSetup(); render(); initDrafts();
  if (window.museAccount?.ready) window.museAccount.ready().then(() => buildPlan()); else buildPlan();
  fetch('/api/v1/readiness').then(response => response.json()).then(data => { state.readiness = data; syncAccountLive(); $('readinessNote').textContent = data.provider_key_configured ? 'Muse configured, not yet verified here. Starter plans use no credits. Live image uses one Muse Image request; this flow does not run SAM.' : 'No Muse provider key configured. Starter posts and downloads work without it.'; }).catch(() => { $('readinessNote').textContent = 'Could not check server configuration. Your draft is still available.'; });
  window.museDailySnapshot = () => JSON.parse(JSON.stringify({ product: state.product, channel: state.channel, format: state.format, copy: currentCopy(), plan: currentPlan(), performance: state.performance, imageMode: state.imageMode, source: state.source }));
})();
