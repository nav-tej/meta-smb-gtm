'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const names = { instagram: 'Instagram', facebook: 'Facebook', x: 'X', tiktok: 'TikTok' };
  const shops = { pixels: 'Pixels', fineartamerica: 'Fine Art America', saatchi: 'Saatchi Art', website: 'Artist website', other: 'Your shop' };
  const storageKey = 'muse-daily-v1';
  const originalSample = '/samples/ek_onkar_original.jpg';
  const initialProduct = () => ({ title: 'Ek Onkar', description: 'An artwork by Sarabjit Singh exploring connection and equality through color and form.', seller: 'Art of Sarabjit Singh', collection: '', price: '', destination_url: 'https://sarabjit-singh.pixels.com/', destination: 'pixels' });
  const state = { product: initialProduct(), original: originalSample, image: originalSample, imageMode: 'original', source: 'Suggested from the artist example', channel: 'instagram', format: 'image', goal: 'visits', salesGoal: null, performance: null, plans: {}, edits: {}, selected: 0, posted: {}, offers: {}, busy: false, revision: 0, paint: 0, live: false, key: '', readiness: null };
  let setupBackup = null;
  const safeURL = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const inline = value => typeof value === 'string' && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length <= 2100000;
  const imageSource = value => inline(value) || /^\/samples\/[a-zA-Z0-9_.-]+$/.test(value || '');
  function notice(message, error = false) { $('notice').hidden = false; $('notice').textContent = message; $('notice').className = error ? 'error' : ''; }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify({ product: state.product, original: state.original, image: state.image, imageMode: state.imageMode, source: state.source, channel: state.channel, format: state.format, goal: state.goal, salesGoal: state.salesGoal, performance: state.performance, plans: state.plans, edits: state.edits, posted: state.posted, offers: state.offers })); $('saveStatus').textContent = 'Saved on this device'; }
    catch { $('saveStatus').textContent = 'Download before closing this tab'; }
  }
  function restore() {
    try {
      const data = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (!data || typeof data.product?.title !== 'string' || (data.original !== '' && !imageSource(data.original))) return;
      for (const key of ['product', 'original', 'source', 'salesGoal', 'performance', 'posted', 'offers']) if (data[key] !== undefined) state[key] = data[key];
      state.channel = Object.hasOwn(names, data.channel) ? data.channel : 'instagram';
      state.format = ['image', 'video', 'text'].includes(data.format) ? data.format : 'image';
      state.goal = ['visits', 'inquiries', 'sales'].includes(data.goal) ? data.goal : 'visits';
      if (data.plans && typeof data.plans === 'object') state.plans = data.plans;
      if (data.edits && typeof data.edits === 'object') state.edits = data.edits;
      state.image = imageSource(data.image) ? data.image : state.original;
      state.imageMode = data.imageMode === 'live' ? 'live' : 'original';
      state.product.destination_url = safeURL(state.product.destination_url);
      if (!Object.hasOwn(shops, state.product.destination)) state.product.destination = 'other';
      $('saveStatus').textContent = 'Restored from this device';
    } catch { /* A blocked or full local store does not block the daily flow. */ }
  }
  function lock(busy) { state.busy = busy; document.querySelectorAll('button, input, select, textarea').forEach(el => { el.disabled = busy; }); document.body.classList.toggle('exporting', busy); }
  function invalidate() { state.revision += 1; $('reviewed').checked = false; }
  function currentPlan() { return state.plans[state.channel]; }
  function currentPost() { return currentPlan()?.posts?.[state.selected] || null; }
  const editKey = () => `${state.channel}:${state.selected}:${state.format}`;
  function currentCopy() { return { hook: $('postHook').value.trim(), caption: $('postCaption').value.trim() }; }
  function saveEdit() { state.edits[editKey()] = currentCopy(); invalidate(); $('copyCount').textContent = `${$('postCaption').value.length} characters`; persist(); paint(); }
  function formatCopy(post) {
    if (!post) return { hook: state.product.title, caption: state.product.description };
    const stored = state.edits[editKey()];
    if (stored) return stored;
    return { hook: post.hook, caption: post.caption };
  }
  function postIdentity() { return JSON.stringify([state.product.title, state.product.destination_url, state.channel, state.format, state.selected, currentCopy()]); }
  async function jsonRequest(path, payload, live = false) {
    const control = new AbortController(); const timer = setTimeout(() => control.abort(), live ? 285000 : 45000);
    try {
      const response = await fetch(path + (live ? '?live=true' : ''), { method: 'POST', headers: { 'Content-Type': 'application/json', ...(live ? { 'X-Demo-Key': state.key } : {}) }, body: JSON.stringify(payload), signal: control.signal });
      let data; try { data = await response.json(); } catch { throw new Error('The server could not finish. Your edits are still here.'); }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the item details and try again.');
      return data;
    } catch (error) { if (error.name === 'AbortError') throw new Error(live ? 'Muse timed out and may still be processing. Check completion before paying for another request.' : 'That site is taking too long. Enter your item below.'); throw error; }
    finally { clearTimeout(timer); }
  }
  function planPayload(live) { return { product: { title: state.product.title, description: state.product.description, price: state.product.price || undefined, destination_url: safeURL(state.product.destination_url) || undefined, seller: state.product.seller, collection: state.product.collection }, channels: [state.channel], goal: state.goal, sales_goal: state.salesGoal || undefined, performance: state.performance || undefined, use_muse: live }; }
  async function buildPlan(live = false, force = false) {
    if (state.busy) return;
    if (live && !liveReady()) return;
    if (!force && !live && currentPlan()) { render(); return; }
    const channel = state.channel; const revision = state.revision;
    lock(true); if (live) notice('Muse is writing three posts from your item and goal…');
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
    for (const [i, item] of (plan?.posts || []).entries()) {
      const button = document.createElement('button'); button.className = 'plan-card'; button.setAttribute('aria-pressed', String(i === state.selected));
      const timing = document.createElement('span'); timing.textContent = `${item.day_offset === 0 ? 'TODAY' : `IN ${item.day_offset} DAYS`} · ${names[item.channel]} · ${item.format.toUpperCase()}`;
      const title = document.createElement('strong'); title.textContent = state.edits[`${state.channel}:${i}:${item.format}`]?.hook || item.hook;
      const tip = document.createElement('span'); tip.textContent = item.posting_tip;
      button.append(timing, title, tip); button.addEventListener('click', () => { if (state.busy) return; state.selected = i; state.format = item.format; invalidate(); render(); persist(); }); $('planCards').append(button);
    }
    $('insightTitle').textContent = plan?.insight?.summary || 'Start with one clear invitation.';
    $('insightAction').textContent = plan?.insight?.next_action || 'Post once, then note the visits or inquiries it brings.';
    $('resultsSource').textContent = (state.performance ? 'Your last-7-days counts' : 'No performance data added') + (state.salesGoal ? ` · weekly goal: ${state.salesGoal} sales${plan?.insight?.sales_remaining != null ? ` · ${plan.insight.sales_remaining} to go` : ''}` : '');
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
    if (state.busy || !reviewed()) return; lock(true);
    try {
      if (state.format === 'text') { await copyText(); notice('Text ready. Paste it into your post.'); return; }
      notice(state.format === 'video' ? 'Preparing your six-second clip… Keep this tab open.' : 'Preparing your post…');
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
    const safe = safeURL(url); if (!safe) throw new Error('Enter a complete shop or listing link.');
    const data = await jsonRequest('/api/v1/product-reference', { url: safe });
    state.product = { title: data.title || new URL(safe).hostname, description: data.description || '', price: data.price_hint || '', seller: new URL(safe).hostname, destination_url: safeURL(data.url) || safe, destination: 'other', collection: '' };
    state.original = inline(data.image_data_url) ? data.image_data_url : ''; state.image = state.original; state.imageMode = 'original'; state.offers = {}; state.plans = {}; state.edits = {}; state.selected = 0; state.performance = null; state.source = `From ${new URL(safe).hostname} · check product facts`; invalidate(); populateSetup(); $('importStatus').textContent = data.source_note || 'Listing ready. Check the item and photo.';
  }
  async function readListing() { if (state.busy) return; lock(true); try { await useReference($('shopUrl').value); notice('Listing selected. Check its details, then use this item.'); } catch (error) { $('importStatus').textContent = error.message; } finally { lock(false); } }
  async function findItems() {
    if (state.busy) return; const url = safeURL($('shopUrl').value.trim()); if (!url) { $('importStatus').textContent = 'Enter a full shop URL.'; return; }
    lock(true); $('importStatus').textContent = 'Finding a product for your next post…'; $('importItems').replaceChildren();
    try {
      const data = await jsonRequest('/api/v1/ingest-storefront', { website_url: url, business_name: new URL(url).hostname, max_urls_per_source: 20 });
      const items = (data.discovered_catalog_items || []).filter(item => safeURL(item.url)); const products = items.filter(item => ['products', 'listings'].includes(item.bucket)); const choices = products.length ? products : items;
      if (!choices.length) { $('importStatus').textContent = 'No items found. Paste a product link or enter one below.'; return; }
      for (const [i, item] of choices.entries()) { const button = document.createElement('button'); button.type = 'button'; button.textContent = `${i === 0 ? 'Suggested: ' : ''}${item.title || 'View listing'}`; button.addEventListener('click', async () => { if (state.busy) return; lock(true); try { await useReference(item.url); } catch (error) { $('importStatus').textContent = error.message; } finally { lock(false); } }); $('importItems').append(button); }
      await useReference(choices[0].url); $('importStatus').textContent = 'First product listing selected. Change it below or use this item.';
    } catch (error) { $('importStatus').textContent = error.message; } finally { lock(false); }
  }
  async function upload(file) {
    if (!file || state.busy) return; if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10000000) { notice('Choose a JPEG, PNG or WebP under 10 MB.', true); return; }
    const url = URL.createObjectURL(file); lock(true);
    try { const image = await loadImage(url); const canvas = document.createElement('canvas'); const scale = Math.min(1, 1400 / Math.max(image.width, image.height)); canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale); const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height); const data = canvas.toDataURL('image/jpeg', .8); if (!inline(data)) throw new Error('Try a smaller photo.'); state.original = data; state.image = data; state.imageMode = 'original'; invalidate(); render(); persist(); notice('Photo ready. Check your post and take it with you.'); }
    catch (error) { notice(error.message, true); } finally { URL.revokeObjectURL(url); lock(false); }
  }
  function liveReady() {
    if (!state.live) { notice('Enable a configured live Muse session in Muse settings first.', true); return false; }
    if (!state.readiness?.provider_key_configured) { notice('This server has no Muse key configured. Starter drafts still work.', true); return false; }
    if (state.readiness.default_mode !== 'live' && !state.key) { notice('Enter the demo unlock key in Muse settings.', true); return false; } return true;
  }
  async function museImage() {
    if (state.busy || !liveReady()) return; if (!state.original) { notice('Add your original photo first.', true); return; }
    lock(true); notice('Muse is creating a new scene. This is a billed image request…');
    try {
      let data = state.original; if (!inline(data)) { const response = await fetch(data); if (!response.ok) throw new Error('Could not load your source photo.'); data = await new Promise((resolve, reject) => { response.blob().then(blob => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob); }).catch(reject); }); }
      const copy = currentCopy(); const prompt = $('scenePrompt').value.trim(); if (!prompt || !copy.hook || !copy.caption) throw new Error('Add a scene, opening line and caption first.');
      const response = await jsonRequest('/api/v1/generate-ads', { product: { title: state.product.title, description: state.product.description, price: state.product.price || undefined, image_base64: data }, draft: false, placements: ['instagram_feed'], variants_per_placement: 1, use_comfyui: false, muse_workflow_mode: 'product_visuals', brief: { product_title: state.product.title, positioning_hook: copy.hook, estimated_paid_calls: 1, preserve_product_note: 'Compare with original before posting.', variants: [{ variant_id: 'daily1', placement: 'instagram_feed', include: true, headline: copy.hook.slice(0, 120), primary_text: copy.caption.slice(0, 600), image_prompt: prompt }] } }, true);
      const creative = response.creatives?.[0]; if (!creative || String(creative.produced_by).startsWith('demo-cache') || !inline(creative.media_data_url)) throw new Error('No usable new image delivered. Check completion before regenerating. Your original is still here.');
      await loadImage(creative.media_data_url); state.image = creative.media_data_url; state.imageMode = 'live'; invalidate(); render(); persist(); notice('Muse scene ready. Compare the artwork with your original before using it.');
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
  document.querySelectorAll('[data-channel]').forEach(button => button.addEventListener('click', async () => { if (state.busy) return; state.channel = button.dataset.channel; state.selected = 0; state.format = state.channel === 'tiktok' ? 'video' : state.channel === 'x' ? 'text' : 'image'; invalidate(); await buildPlan(); persist(); }));
  $('format').addEventListener('change', () => { state.format = $('format').value; invalidate(); render(); persist(); });
  $('getPost').addEventListener('click', getPost);
  $('copyOnly').addEventListener('click', async () => { if (state.busy || !reviewed()) return; const copied = await copyText(); notice(copied ? 'Post copied. Paste it into your channel.' : 'Caption downloaded.'); });
  $('markPosted').addEventListener('click', () => { if (state.busy || !reviewed()) return; state.posted[postIdentity()] = new Date().toISOString(); persist(); render(); notice('Marked posted on this device. You’re done for today. Add results when you have them.'); });
  $('downloadPlan').addEventListener('click', () => { const plan = currentPlan(); if (!plan || state.busy) return; const rows = plan.posts.map((post, i) => { const edited = state.edits[`${state.channel}:${i}:${post.format}`]; return `${post.day_offset === 0 ? 'Today' : `In ${post.day_offset} days`} · ${names[post.channel]} · ${post.format}\n${edited?.hook || post.hook}\n${edited?.caption || post.caption}\n${post.visual_direction}\n${post.posting_tip}`; }); saveBlob(new Blob([`${state.product.title}\n${plan.mode === 'muse' ? 'Muse Spark plan' : 'Starter plan'} · manual posting\n\n${rows.join('\n\n')}\n\nDestination: ${safeURL(state.product.destination_url)}\nSuggested days, not scheduled posts. Add only offers you can fulfill.`], { type: 'text/plain' }), 'posting-plan.txt'); });
  $('resultsForm').addEventListener('submit', async event => { event.preventDefault(); if (state.busy) return; const values = {}; for (const key of ['views', 'clicks', 'inquiries', 'sales']) values[key] = Number($(key).value) || 0; if (Object.values(values).some(value => !Number.isSafeInteger(value) || value < 0)) { notice('Use whole, non-negative counts.', true); return; } state.performance = values; state.plans = {}; invalidate(); await buildPlan(false, true); persist(); $('resultsDetails').open = false; });
  $('unlockKey').addEventListener('input', () => { state.key = $('unlockKey').value.trim(); }); $('liveMode').addEventListener('change', () => { state.live = $('liveMode').checked; });
  $('musePlan').addEventListener('click', () => buildPlan(true, true)); $('museImage').addEventListener('click', museImage);
  $('useOriginal').addEventListener('click', () => { if (state.busy) return; state.image = state.original; state.imageMode = 'original'; invalidate(); render(); persist(); });
  restore(); populateSetup(); render(); buildPlan();
  fetch('/api/v1/readiness').then(response => response.json()).then(data => { state.readiness = data; $('readinessNote').textContent = data.provider_key_configured ? 'Muse configured, not yet verified here. Starter plans use no credits. Live image uses one Muse Image request; this flow does not run SAM.' : 'No Muse provider key configured. Starter posts and downloads work without it.'; }).catch(() => { $('readinessNote').textContent = 'Could not check server configuration. Your draft is still available.'; });
  window.museDailySnapshot = () => JSON.parse(JSON.stringify({ product: state.product, channel: state.channel, format: state.format, copy: currentCopy(), plan: currentPlan(), performance: state.performance, imageMode: state.imageMode, source: state.source }));
})();
