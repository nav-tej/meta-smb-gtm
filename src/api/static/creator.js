'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { step: 0, presets: null, workspace: 'sarabjit_singh', custom: false, copyEdited: false, sceneEdited: false, goal: 'story', original: '', image: '', imageKind: 'original', sampleImage: '', key: '', live: false, defaultLive: false, readiness: null, busy: false, revision: 0, paint: 0, product: {}, headline: '', caption: '', scene: '', provenance: 'Original-photo layout. No new image generated.' };
  const fields = { productName: 'name', productPrice: 'price', sellerName: 'seller', productDescription: 'description', productLink: 'link', productCollection: 'collection' };
  const destinations = { pixels: 'Pixels', fineartamerica: 'Fine Art America', saatchi: 'Saatchi Art', website: 'Artist website', other: 'My shop / inquiry page' };
  let offers = {};
  function postingChannels() { return [['postInstagram', 'instagram'], ['postFacebook', 'facebook']].filter(([id]) => $(id).checked).map(([, name]) => name); }
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
  const validInline = (value) => typeof value === 'string' && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value) && value.length < 4000000;
  function notify(message, kind = '') { $('notice').hidden = false; $('notice').textContent = message; $('notice').className = `notice ${kind}`; }
  function sync() {
    for (const [id, key] of Object.entries(fields)) state.product[key] = $(id).value.trim();
    if (state.product.destination) offers[state.product.destination] = { price: state.product.price, link: state.product.link };
    state.headline = $('headline').value.trim(); state.caption = $('caption').value.trim(); state.scene = $('scene').value.trim();
  }
  function changed(event) {
    if (['headline', 'caption'].includes(event?.target?.id)) state.copyEdited = true;
    if (event?.target?.id === 'scene') state.sceneEdited = true;
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
    state.workspace = workspace; state.custom = false; state.copyEdited = false; state.sceneEdited = false; state.revision += 1; state.artwork = null;
    const ws = state.presets?.workspaces?.[workspace]; const art = ws?.artworks_showcase?.[0];
    state.product = workspace === 'sarabjit_singh' ? { name: 'Ek Onkar · artwork promotion', price: '', seller: 'Art of Sarabjit Singh', description: 'Ek Onkar by Sarabjit Singh explores connection and equality. Check the selected shop for the matching artwork, available formats and current offer.', link: '', collection: '' } : { name: 'Stoneware & brass chai set', price: '$54', seller: 'Saffron & Clay', description: 'Illustrative product example: a stoneware and brass chai set.', link: '', collection: '' };
    resetOffers(workspace === 'sarabjit_singh');
    state.original = samplePath(art?.original_image) || (workspace === 'sarabjit_singh' ? '/samples/ek_onkar_original.jpg' : '/samples/etsy_chai_set_product_visual_live.webp');
    state.sampleImage = samplePath(art?.staged_image) || (workspace === 'sarabjit_singh' ? '/samples/ek_onkar_collector_room_live.webp' : '/samples/etsy_chai_set_product_visual_live.webp');
    originalLayout(); setProductFields(); starter(); $('reviewed').checked = false; $('moreDetails').open = false;
    $('productFactNote').textContent = workspace === 'sarabjit_singh' ? 'Confirm the matching artwork and offer at your chosen destination. Frame is staging only. Preview image is not a print master.' : 'Illustrative shop and sample pricing. These are saved examples, not a connected shop.';
    $('productImageCaption').textContent = workspace === 'sarabjit_singh' ? 'Ek Onkar · original artwork preview. Source: Art of Sarabjit Singh.' : 'Illustrative product image generated for the example shop.';
    updateChoices(); refreshPreview();
  }
  function updateChoices() { $('artistExample').classList.toggle('selected', !state.custom && state.workspace === 'sarabjit_singh'); $('ceramicsExample').classList.toggle('selected', !state.custom && state.workspace === 'etsy_ceramics'); $('customProduct').classList.toggle('selected', state.custom); }
  function originalLayout() { state.image = state.original; state.imageKind = 'original'; state.provenance = state.custom ? 'Original-photo layout. No personalized image generated.' : state.workspace === 'etsy_ceramics' ? 'Original example layout using a saved AI product image.' : 'Layout using the original artwork preview. No new image generated.'; refreshPreview(); }
  function newProduct() {
    if (state.busy) return;
    state.custom = true; state.copyEdited = false; state.sceneEdited = false; state.revision += 1; state.product = { name: '', price: '', seller: '', description: '', link: '', collection: '' }; resetOffers(false); state.original = ''; state.image = ''; state.sampleImage = ''; state.provenance = 'Add a photo to create your own product layout.';
    setProductFields(); starter(); updateChoices(); $('reviewed').checked = false; $('productFactNote').textContent = 'Your photo stays in this tab. A live request sends it to Muse only when you choose to generate.'; $('productImageCaption').textContent = 'Your product photo will appear here.'; $('moreDetails').open = true; refreshPreview(); $('productName').focus();
  }
  function imageElement(src) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('We could not open that image. Try a JPEG, PNG or WebP photo.')); image.src = src; }); }
  async function upload(file) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('Choose a JPEG, PNG or WebP photo smaller than 10 MB.');
    const url = URL.createObjectURL(file);
    try {
      const image = await imageElement(url); const scale = Math.min(1, 1400 / Math.max(image.width, image.height)); const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale)); const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      let quality = .88; let data = canvas.toDataURL('image/jpeg', quality); while (data.length > 1300000 && quality > .35) { quality -= .1; data = canvas.toDataURL('image/jpeg', quality); }
      if (data.length > 1300000) throw new Error('This photo is still too large. Please choose a smaller image.');
      if (!state.custom) newProduct(); state.original = data; state.revision += 1; originalLayout(); $('reviewed').checked = false; notify('Photo ready. Add your product details, then choose an idea.');
    } finally { URL.revokeObjectURL(url); }
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
        newProduct(); $('productName').value = listingName.slice(0, 180); $('productLink').value = safeLink(item.url) || '';
        $('sellerName').value = (businessName || '').slice(0, 120); $('productPrice').value = (item.price_hint || '').slice(0, 40);
        $('productDescription').value = '';
        sync(); starter(); changed(); $('productImageCaption').textContent = 'Add the product photo that matches this listing.';
        notify('Listing details added. Check them, then add a matching product photo.'); $('productName').focus();
      }); box.append(button);
    }
    box.hidden = false; $('importHint').textContent = 'Choose a listing to fill its title, price hint, and link. Review every detail and add the matching photo.';
  }
  async function importProducts() {
    if (state.busy) return;
    const url = safeLink($('shopUrl').value.trim());
    if (!url) { notify('Enter your shop website starting with https://.', 'error'); $('shopUrl').focus(); return; }
    setBusy(true); $('importResults').hidden = true; notify('Looking for public product listings… This can take a little while.', 'busy');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch('/api/v1/ingest-storefront', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_name: ((state.custom ? $('sellerName').value.trim() : '') || new URL(url).hostname.replace(/^www\./, '')).slice(0, 160), website_url: url, max_urls_per_source: 30 }), signal: controller.signal });
      let data = {}; try { data = await response.json(); } catch { /* Gateways may return an HTML timeout page. */ }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'We could not read that shop website. You can still enter the details below.');
      const items = data.discovered_catalog_items || []; showImportedItems(items, data.business_name || 'your shop');
      const fetched = (data.channels || []).some((channel) => channel.status === 'fetched');
      notify(items.length ? `Found ${items.length} public listing${items.length === 1 ? '' : 's'}. Choose one to bring its details into your post.` : fetched ? 'We reached your website but did not find product listings. You can enter details below.' : 'This site did not allow automatic reading. You can still enter details below or try your own website.');
    } catch (error) { notify(error.name === 'AbortError' ? 'This shop is taking too long to respond. Try again later or enter the details below.' : `${error.message} Your work is still here.`, 'error'); }
    finally { clearTimeout(timer); setBusy(false); }
  }
  function validateProduct() { sync(); if (!state.product.name) { notify('Give your product a name first.', 'error'); $('productName').focus(); return false; } if (!state.original) { $('moreDetails').open = true; notify('Add a product photo first. Open “More details” to upload it.', 'error'); return false; } if (state.product.link && !safeLink(state.product.link)) { $('moreDetails').open = true; notify('Use a complete http:// or https:// product link, or leave it empty.', 'error'); $('productLink').focus(); return false; } return true; }
  function go(step) {
    if (state.busy || (step > 0 && !validateProduct())) return;
    if (step === 3 && !postingChannels().length) { notify('Choose Instagram or Facebook for this post before sharing.', 'error'); go(0); return; }
    if (step === 3 && (!$('reviewed').checked || !state.headline || !state.caption)) { notify('Check your wording and product details, then tick the review box before sharing.', 'error'); go(2); return; }
    state.step = step;
    document.querySelectorAll('[data-panel]').forEach((el) => { el.hidden = Number(el.dataset.panel) !== step; });
    document.querySelectorAll('[data-step]').forEach((el) => { if (Number(el.dataset.step) === step) el.setAttribute('aria-current', 'step'); else el.removeAttribute('aria-current'); });
    $('backButton').disabled = step === 0; $('nextButton').hidden = step === 3; $('nextButton').textContent = ['Choose an idea →', 'Make it yours →', 'Ready to share →'][step] || 'Continue'; $('stepCount').textContent = `Step ${step + 1} of 4`; $('tryNext').hidden = state.custom || state.workspace !== 'sarabjit_singh';
    refreshPreview(); const h = document.querySelector(`[data-panel="${step}"] h2`); h.tabIndex = -1; h.focus({ preventScroll: true }); h.scrollIntoView({ behavior: 'auto', block: 'start' });
  }
  function refreshPreview() {
    for (const id of ['productImage', 'originalCompare']) { if (state.original) { $(id).src = state.original; $(id).hidden = false; } else { $(id).removeAttribute('src'); $(id).hidden = true; } }
    if (state.image) { $('sceneCompare').src = state.image; $('sceneCompare').hidden = false; } else { $('sceneCompare').removeAttribute('src'); $('sceneCompare').hidden = true; }
    $('sceneLabel').textContent = state.imageKind === 'original' ? 'Original-photo layout' : state.imageKind === 'saved' ? 'Saved AI scene' : 'New AI scene';
    $('previewShop').textContent = state.product.seller || 'Your shop'; $('previewHeadline').textContent = state.headline; $('previewCaption').textContent = state.caption; $('imageProvenance').textContent = state.provenance; $('shareTitle').textContent = state.product.name || 'Your product'; $('shareProvenance').textContent = state.provenance;
    const link = safeLink(state.product.link); $('listingLink').hidden = !link; if (link) $('listingLink').href = link;
    $('destinationNote').textContent = destinationNote();
    $('productPrice').placeholder = `Optional ${destinations[state.product.destination]} price`;
    $('postingSummary').textContent = `${postingChannels().map((c) => c === 'instagram' ? 'Instagram' : 'Facebook').join(' + ') || 'Choose a posting channel'} → ${destinations[state.product.destination]}${state.product.collection ? ` · ${state.product.collection}` : ''}. ${state.product.price ? `Selected offer: ${state.product.price}.` : 'No price included.'}`;
    $('postingSteps').replaceChildren(); for (const line of postingChecklist()) { const li = document.createElement('li'); li.textContent = line; $('postingSteps').append(li); }
    $('listingLink').textContent = `Check ${destinations[state.product.destination]} destination ↗`;
    const paint = ++state.paint; drawLayout(1350).then((canvas) => { if (paint !== state.paint) return; const preview = $('previewCanvas'); preview.getContext('2d').clearRect(0, 0, 1080, 1350); preview.getContext('2d').drawImage(canvas, 0, 0); }).catch(() => {});
  }
  function wrap(ctx, text, x, y, maxWidth, lineHeight, maxLines = 3) {
    const words = String(text).split(/\s+/); let line = ''; let count = 0;
    for (const word of words) { const next = line ? `${line} ${word}` : word; if (ctx.measureText(next).width > maxWidth && line) { ctx.fillText(line, x, y); y += lineHeight; count += 1; line = word; if (count >= maxLines - 1) break; } else line = next; }
    if (line) ctx.fillText(line, x, y); return y;
  }
  async function drawLayout(height) {
    const canvas = document.createElement('canvas'); canvas.width = 1080; canvas.height = height; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#f6f3eb'; ctx.fillRect(0, 0, 1080, height); ctx.fillStyle = '#263d35'; ctx.font = '24px sans-serif'; ctx.fillText((state.product.seller || 'Made with care').slice(0, 55), 80, 90);
    if (state.image) { const img = await imageElement(state.image); const area = { x: 80, y: 150, w: 920, h: height - 510 }; const scale = Math.min(area.w / img.width, area.h / img.height); const w = img.width * scale, h = img.height * scale; ctx.fillStyle = '#e9e7dc'; ctx.fillRect(area.x, area.y, area.w, area.h); ctx.drawImage(img, area.x + (area.w - w) / 2, area.y + (area.h - h) / 2, w, h); }
    ctx.fillStyle = '#263d35'; ctx.font = '46px Georgia'; wrap(ctx, state.headline || state.product.name || 'Your next shop post', 80, height - 280, 920, 55, 3); ctx.font = '25px sans-serif'; ctx.fillText((state.product.price || '').slice(0, 45), 80, height - 90); ctx.textAlign = 'right'; ctx.fillText('Discover the story', 1000, height - 90); return canvas;
  }
  function spendLive(label) {
    try { if (window.museShell?.spend) window.museShell.spend(label); } catch {}
    try { if (window.museAccount?.refresh) window.museAccount.refresh().catch(() => {}); } catch {}
  }
  function setBusy(busy) { state.busy = busy; document.querySelectorAll('button').forEach((b) => { b.disabled = busy; }); for (const id of [...Object.keys(fields), 'promotionDestination', 'postInstagram', 'postFacebook', 'shopUrl', 'headline', 'caption', 'scene', 'productPhoto', 'liveMode', 'unlockKey', 'reviewed']) $(id).disabled = busy; $('backButton').disabled = busy || state.step === 0; $('draftButton').setAttribute('aria-busy', String(busy)); $('generateButton').setAttribute('aria-busy', String(busy)); }
  async function request(payload) {
    const encoded = JSON.stringify(payload); if (new TextEncoder().encode(encoded).length > 3500000) throw new Error('This photo and text are too large together. Choose a smaller image.');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 285000);
    try { const response = await fetch('/api/v1/generate-ads' + (state.live ? '?live=true' : ''), { method: 'POST', headers: { 'Content-Type': 'application/json', ...(state.live ? { 'X-Demo-Key': state.key } : {}) }, body: encoded, signal: controller.signal }); if (!response.ok) { let detail = ''; try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail.slice(0, 350) : body.detail?.error === 'media_response_too_large' ? 'Muse finished, but the image was too large to send to this tab. Your original photo is still here. Ask the presenter to check saved output before trying again; do not rerun yet.' : ''; } catch {} throw new Error(detail || `Muse could not complete this request (${response.status}). Your edits are still here.`); } return await response.json(); }
    catch (error) { if (error.name === 'AbortError') throw new Error('This request timed out. It may still be processing and may be billed. Your edits are safe; check completion before generating again.'); throw error; } finally { clearTimeout(timer); }
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
    if (state.busy || !validateProduct()) return;
    if (!state.live) { notify('Saved mode uses editable starter copy. Enable a configured live presenter session to write a new Muse draft.'); return; }
    setBusy(true); notify('Muse is writing your draft. Your current words are kept until the new draft is ready…', 'busy');
    try { const result = await request({ draft: true, product: productPayload(), competitor_brief: promotionResearchContext(), placements: ['instagram_feed'], variants_per_placement: 1, use_comfyui: false }); const variant = result.variants?.[0]; if (!variant) throw new Error('Muse returned no editable draft. Your previous copy is still here.'); state.copyEdited = true; state.sceneEdited = true; state.headline = variant.headline; state.caption = variant.primary_text; state.scene = variant.image_prompt; $('headline').value = state.headline; $('caption').value = state.caption; $('scene').value = state.scene; $('reviewed').checked = false; refreshPreview(); spendLive('Fresh Muse draft'); notify('Fresh Muse draft ready. Read it through and make it sound like you.'); } catch (error) { try { window.museAccount?.refresh?.().catch(() => {}); } catch {} notify(error.message, 'error'); } finally { setBusy(false); }
  }
  async function generate() {
    if (state.busy || !validateProduct()) return;
    if (!state.live && !state.custom && typeof window !== 'undefined' && window.museShell) { setBusy(true); try { await window.museShell.progress('Staging your painting', ['Reading the saved Muse Image result', 'Fitting it to the feed layout', 'Adding your words']); } finally { setBusy(false); } }
    if (!state.live) { if (state.custom) { originalLayout(); notify('Your original-photo layout is ready. Saved mode does not generate personalized AI scenes.'); } else { state.image = state.sampleImage; state.imageKind = 'saved'; state.provenance = 'Saved Muse image from this example. No new image generated; compare details against the original. Frame and room are staging only.'; refreshPreview(); notify('Saved scene loaded. Your edited copy stays yours.'); } $('reviewed').checked = false; return; }
    if (!state.scene || !state.headline || !state.caption) { notify('Add your headline, caption and setting before creating an image.', 'error'); return; }
    setBusy(true); notify('Muse is creating your scene. This can take a few minutes. Please keep this tab open…', 'busy');
    try {
      const product = { ...productPayload(), image_base64: await sourceData() };
      const result = await request({ product, draft: false, placements: ['instagram_feed'], variants_per_placement: 1, use_comfyui: false, muse_workflow_mode: 'product_visuals', brief: { product_title: state.product.name, positioning_hook: goals[state.goal][0], preserve_product_note: 'Compare generated product details against the original before publishing.', estimated_paid_calls: 1, variants: [{ variant_id: 'v1', include: true, placement: 'instagram_feed', headline: state.headline, primary_text: state.caption, image_prompt: state.scene, target_audience: 'People interested in this product and the maker’s story', angle_rationale: 'Seller-selected promotion goal' }] } });
      const creative = result.creatives?.[0]; if (!creative) throw new Error('Muse returned no image. Your original-photo layout is still available.');
      if (String(creative.produced_by).startsWith('demo-cache')) throw new Error('The server returned a saved example, not a new image. Live mode was not confirmed. Your original is still available.');
      if (!validInline(creative.media_data_url)) throw new Error('Muse completed the request, but this server has not delivered a usable inline image. Do not generate again yet; ask the presenter to check image delivery.');
      await imageElement(creative.media_data_url); state.image = creative.media_data_url; state.imageKind = 'live'; state.provenance = `Generated with ${creative.produced_by || 'Muse'}. Review the artwork against the original. Product details can change; room and frame are staging only.`; $('reviewed').checked = false; refreshPreview(); spendLive('Live Muse scene'); notify('Your new scene is ready. Compare details with the original, or choose “Use original photo”. Download before refreshing; generated images are kept only in this tab.');
    } catch (error) { try { window.museAccount?.refresh?.().catch(() => {}); } catch {} notify(error.message, 'error'); } finally { setBusy(false); }
  }
  function saveBlob(blob, suffix) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${(state.product.name || 'promotion').replace(/[^a-z0-9]+/gi, '-').slice(0, 60)}-${suffix}`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  async function download(height) { if (state.busy || !validateProduct()) return; if (!$('reviewed').checked) { notify('Review your image and wording before downloading.', 'error'); go(2); return; } setBusy(true); try { sync(); const canvas = await drawLayout(height); const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png')); if (!blob) throw new Error('Could not create the download.'); saveBlob(blob, height === 1350 ? 'feed.png' : 'story.png'); notify('Image downloaded using your current headline. Copy the matching caption before posting.'); } catch (e) { notify(e.message, 'error'); } finally { setBusy(false); } }
  function campaignPack() { sync(); return { product: { ...state.product, link: safeLink(state.product.link) }, goal: state.goal, headline: state.headline, caption: state.caption, scene_prompt: state.scene, image_provenance: state.provenance, mode: state.imageKind, posting_channels: postingChannels(), note: 'Download the image separately. This pack does not launch ads or publish posts. Destination details are kept only in this tab; prices are not synced.', posting_checklist: postingChecklist() }; }
  for (const id of [...Object.keys(fields), 'headline', 'caption', 'scene']) $(id).addEventListener('input', changed);
  $('artistExample').addEventListener('click', () => selectExample('sarabjit_singh')); $('ceramicsExample').addEventListener('click', () => selectExample('etsy_ceramics')); $('customProduct').addEventListener('click', newProduct);
  $('importProducts').addEventListener('click', importProducts);
  $('promotionDestination').addEventListener('change', switchDestination);
  for (const id of ['postInstagram', 'postFacebook']) $(id).addEventListener('change', changed);
  $('downloadInstructions').addEventListener('click', () => { if (state.busy || !$('reviewed').checked || !postingChannels().length) { notify('Review your post and choose a posting channel before downloading instructions.', 'error'); return; } const pack = campaignPack(); saveBlob(new Blob([`${pack.product.name}\n${$('postingSummary').textContent}\n\n${pack.headline}\n\n${pack.caption}\n\n${pack.posting_checklist.map((line, i) => `${i + 1}. ${line}`).join('\n\n')}`], { type: 'text/plain' }), 'posting-instructions.txt'); });
  $('productPhoto').addEventListener('change', async (event) => { if (state.busy) return; try { await upload(event.target.files?.[0]); } catch (e) { notify(e.message, 'error'); } });
  document.querySelectorAll('[data-step]').forEach((el) => el.addEventListener('click', () => go(Number(el.dataset.step))));
  document.querySelectorAll('[data-goal]').forEach((el) => el.addEventListener('click', () => { state.goal = el.dataset.goal; document.querySelectorAll('[data-goal]').forEach((b) => b.classList.toggle('selected', b === el)); $('ideaTitle').textContent = goals[state.goal][0]; $('ideaReason').textContent = goals[state.goal][1]; if (!state.copyEdited) starter(); sync(); refreshPreview(); $('reviewed').checked = false; }));
  $('nextButton').addEventListener('click', () => go(Math.min(3, state.step + 1))); $('backButton').addEventListener('click', () => go(Math.max(0, state.step - 1))); $('originalButton').addEventListener('click', () => { originalLayout(); $('reviewed').checked = false; }); $('draftButton').addEventListener('click', draft); $('generateButton').addEventListener('click', generate);
  $('downloadFeed').addEventListener('click', () => download(1350)); $('downloadStory').addEventListener('click', () => download(1920)); $('downloadPack').addEventListener('click', () => { if (state.busy) return; if (!$('reviewed').checked) { notify('Review your product details and wording before downloading.', 'error'); return; } saveBlob(new Blob([JSON.stringify(campaignPack(), null, 2)], { type: 'application/json' }), 'campaign.json'); });
  $('copyCaption').addEventListener('click', async () => { sync(); try { await navigator.clipboard.writeText(`${state.headline}\n\n${state.caption}${safeLink(state.product.link) ? '\n\n' + safeLink(state.product.link) : ''}`); notify('Your current caption and link are copied.'); } catch { notify('Clipboard access is unavailable. Select and copy your caption from the edit screen.', 'error'); } });
  $('unlockKey').addEventListener('input', () => { state.key = $('unlockKey').value.trim(); });
  $('liveMode').addEventListener('change', () => { if ($('liveMode').checked && state.readiness && !state.readiness.provider_key_configured) { $('liveMode').checked = false; notify('The server has no Muse provider key configured. Saved examples still work.', 'error'); } if ($('liveMode').checked && !state.key && !state.defaultLive) { $('liveMode').checked = false; notify('Enter the configured demo unlock key first.', 'error'); } state.live = $('liveMode').checked; updateMode(); });
  function updateMode() { const live = state.live; $('modeBadge').textContent = live ? 'Live requests selected · billed Muse calls' : 'Saved example · no API cost'; $('modeBadge').classList.toggle('live', live); $('generateButton').textContent = live ? 'Create my image' : 'Preview a room scene'; $('draftHint').textContent = live ? 'A live draft uses your product details. Check every claim before sharing.' : 'Saved mode starts with editable example copy. Live mode writes a new draft.'; }
  selectExample('sarabjit_singh');
  Promise.allSettled([fetch('/api/v1/demo-presets').then((r) => { if (!r.ok) throw new Error(); return r.json(); }), fetch('/api/v1/readiness').then((r) => { if (!r.ok) throw new Error(); return r.json(); })]).then(([presets, readiness]) => {
    if (presets.status === 'fulfilled') state.presets = presets.value; else notify('Example product loaded. Research context is unavailable; live drafting may need the server connection restored.', 'error');
    if (readiness.status === 'fulfilled') { state.readiness = readiness.value; state.defaultLive = readiness.value.default_mode === 'live'; if (state.defaultLive) notify('This local server supports live requests. Turn on live mode in presenter settings before making billed Muse calls.'); }
    updateMode();
    // The portal's saved-ad gallery links here with ?artwork=<id>; only ids in the saved presets are used.
    const requestedArt = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('artwork') : null;
    const art = requestedArt && !state.custom ? state.presets?.workspaces?.sarabjit_singh?.artworks_showcase?.find((a) => a && a.id === requestedArt) : null;
    if (art && samplePath(art.staged_image)) applyArtwork(art);
  });
  function applyArtwork(art) {
    const names = { ek_onkar: 'Ek Onkar', diptych_combine: 'Ek Onkar + Kirat Karo diptych', naam_japo: 'Naam Japo', kirat_karo: 'Kirat Karo' };
    const name = names[art.id] || String(art.title || 'Artwork').replace(/^\d+\.\s*[^:]*:\s*/, '').slice(0, 80);
    state.artwork = { id: art.id, name, series: String(art.series || '').slice(0, 80) };
    state.product.name = name;
    state.product.description = `${name} by Sarabjit Singh. Check the selected shop for the matching artwork, available formats and current offer.`;
    state.original = samplePath(art.original_image) || state.original;
    state.sampleImage = samplePath(art.staged_image) || state.sampleImage;
    state.revision += 1;
    originalLayout(); setProductFields(); starter(); $('reviewed').checked = false; refreshPreview();
    $('productImageCaption').textContent = `${name} · original artwork preview. Source: Art of Sarabjit Singh.`;
    notify(`Loaded from the saved Muse ad: ${name}. Choose “Preview a room scene” in step 3 to use its saved Muse image.`);
  }
  // Ranked ideas on the portal link here with ?goal=story|gift|visit; only known goals are accepted.
  const requestedGoal = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('goal') : null;
  if (requestedGoal && Object.hasOwn(goals, requestedGoal)) document.querySelector?.(`[data-goal="${requestedGoal}"]`)?.click();
  // Expose a read-only snapshot for focused offline contract checks; never expose the unlock key.
  window.museCreatorSnapshot = () => JSON.parse(JSON.stringify(campaignPack()));
})();
