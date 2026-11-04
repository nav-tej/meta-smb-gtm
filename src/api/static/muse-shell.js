'use strict';
// Shared app shell for / and /create: demo credits, progress feedback, gift plan, and the portal
// tour and stage tabs. Everything runs on saved results; nothing here calls a model or takes payment.
(() => {
  const CREDIT_KEY = 'muse.demoCredits';
  const TOUR_KEY = 'muse.tourSeen';
  const START_CREDITS = 12;
  const store = {
    get(key) { try { return window.localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch { /* private mode */ } },
  };
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const el = (tag, attrs = {}, text = '') => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text) node.textContent = text;
    return node;
  };

  // ---------- Toasts ----------
  let toastBox;
  function toast(message, kind = '') {
    if (!toastBox) { toastBox = el('div', { class: 'ms-toasts', role: 'status', 'aria-live': 'polite' }); document.body.appendChild(toastBox); }
    const item = el('div', { class: `ms-toast ${kind}` }, message);
    toastBox.appendChild(item);
    setTimeout(() => item.classList.add('out'), 2600);
    setTimeout(() => item.remove(), 3100);
  }

  // ---------- Demo credits ----------
  let credits = Number.parseInt(store.get(CREDIT_KEY) ?? '', 10);
  if (!Number.isFinite(credits) || credits < 0) credits = START_CREDITS;
  let countNode;
  let pill;
  function renderCredits(bump = false) {
    if (!countNode) return;
    countNode.textContent = String(credits);
    pill.classList.toggle('empty', credits === 0);
    pill.setAttribute('aria-label', `${credits} demo credits remaining`);
    if (bump && !reducedMotion) { pill.classList.remove('bump'); void pill.offsetWidth; pill.classList.add('bump'); }
  }
  function spend(label) {
    if (credits === 0) { toast('Out of demo credits. Open the credits menu to reset; saved results still work.', 'warn'); return; }
    credits -= 1; store.set(CREDIT_KEY, String(credits)); renderCredits(true);
    toast(`−1 credit · ${label}`);
  }
  function mountCredits() {
    const header = document.querySelector('header.topbar') || document.querySelector('body > header');
    if (!header) return;
    const existing = header.querySelector('.ms-credits');
    pill = existing || el('div', { class: 'ms-credits' });
    let button = pill.querySelector('.ms-credits-btn');
    if (!button) {
      button = el('button', { type: 'button', class: 'ms-credits-btn', 'aria-haspopup': 'dialog', 'aria-expanded': 'false' });
      button.appendChild(el('span', { class: 'ms-coin', 'aria-hidden': 'true' }, '🪙'));
      countNode = el('strong', {}, String(credits));
      button.appendChild(countNode);
      button.appendChild(el('span', { class: 'ms-credits-label' }, ' credits'));
      pill.appendChild(button);
    } else {
      countNode = button.querySelector('strong');
      const coin = button.querySelector('.ms-coin');
      if (coin) coin.textContent = '🪙';
    }
    let menu = pill.querySelector('.ms-credits-menu');
    if (!menu) {
      menu = el('div', { class: 'ms-credits-menu', hidden: '' });
      menu.appendChild(el('strong', {}, 'Demo credits'));
      menu.appendChild(el('p', {}, '1 credit per run: competitor analysis, ad generation or budget recommendations.'));
      menu.appendChild(el('p', { class: 'ms-muted' }, 'This demo uses saved Muse results and takes no payment. Credits are stored in this browser only.'));
      const reset = el('button', { type: 'button', class: 'ms-link' }, `Reset to ${START_CREDITS} credits`);
      reset.addEventListener('click', () => { credits = START_CREDITS; store.set(CREDIT_KEY, String(credits)); renderCredits(true); toast('Demo credits reset.'); });
      menu.appendChild(reset);
      const gift = el('button', { type: 'button', class: 'ms-link' }, 'Gift a growth plan →');
      gift.addEventListener('click', () => { closeMenu(); openGift(); });
      menu.appendChild(gift);
      pill.appendChild(menu);
    }
    const closeMenu = () => { menu.hidden = true; button.setAttribute('aria-expanded', 'false'); };
    button.addEventListener('click', (event) => { event.stopPropagation(); menu.hidden = !menu.hidden; button.setAttribute('aria-expanded', String(!menu.hidden)); });
    document.addEventListener('click', (event) => { if (!pill.contains(event.target)) closeMenu(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenu(); });
    if (!existing) {
      const anchor = header.querySelector('.mode, .status-pill, #saveStatus');
      if (anchor) anchor.insertAdjacentElement('afterend', pill); else header.appendChild(pill);
    }
    renderCredits();
    // Any control marked data-credit costs one credit when used.
    document.addEventListener('click', (event) => {
      const target = event.target.closest?.('[data-credit]');
      if (target && !target.disabled) spend(target.dataset.credit);
    }, true);
  }

  // ---------- Progress card ----------
  let progressBusy = false;
  function progress(title, steps, total = 1600) {
    if (progressBusy) return Promise.resolve();
    progressBusy = true;
    const duration = reducedMotion ? 300 : total;
    const card = el('div', { class: 'ms-progress', role: 'status', 'aria-live': 'polite' });
    card.appendChild(el('strong', {}, title));
    const list = el('ol', {});
    const items = steps.map((step) => { const li = el('li', {}, step); list.appendChild(li); return li; });
    card.appendChild(list);
    const bar = el('div', { class: 'ms-bar' }); const fill = el('i', {}); bar.appendChild(fill); card.appendChild(bar);
    card.appendChild(el('small', {}, 'Loading saved Muse results · no live call'));
    document.body.appendChild(card);
    // A timer, not requestAnimationFrame: background and throttled tabs may never run rAF callbacks.
    setTimeout(() => { card.classList.add('in'); fill.style.transitionDuration = `${duration}ms`; fill.style.width = '100%'; }, 20);
    return new Promise((resolve) => {
      items.forEach((li, i) => setTimeout(() => { items.forEach((x, j) => x.classList.toggle('active', j === i)); if (i) items[i - 1].classList.add('done'); }, (duration / items.length) * i));
      setTimeout(() => {
        items.forEach((x) => { x.classList.remove('active'); x.classList.add('done'); });
        card.classList.add('out');
        setTimeout(() => { card.remove(); progressBusy = false; resolve(); }, 250);
      }, duration);
    });
  }

  // ---------- Gift plan dialog ----------
  let giftDialog;
  function openGift() {
    if (!giftDialog) {
      giftDialog = el('dialog', { class: 'ms-dialog ms-gift', 'aria-labelledby': 'msGiftTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => giftDialog.close());
      giftDialog.appendChild(close);
      giftDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Planned pricing'));
      giftDialog.appendChild(el('h2', { id: 'msGiftTitle' }, 'Gift a growth plan to a maker you love'));
      giftDialog.appendChild(el('p', { class: 'ms-price' }, '$29 / month'));
      const list = el('ul', {});
      ['A daily brief on the competitors they choose', 'Ready-to-post Muse images and captions', 'Ranked next moves after every post', 'Budget advice if they run ads'].forEach((item) => list.appendChild(el('li', {}, item)));
      giftDialog.appendChild(list);
      giftDialog.appendChild(el('p', { class: 'ms-muted' }, 'Not on sale yet. Gift plans are planned for after the beta; this demo takes no payment and collects no details.'));
      const ok = el('button', { type: 'button', class: 'ms-primary' }, 'Got it');
      ok.addEventListener('click', () => giftDialog.close());
      giftDialog.appendChild(ok);
      giftDialog.addEventListener('click', (event) => { if (event.target === giftDialog) giftDialog.close(); });
      document.body.appendChild(giftDialog);
    }
    if (typeof giftDialog.showModal === 'function') giftDialog.showModal(); else giftDialog.setAttribute('open', '');
  }

  // ---------- Portal: one stage at a time ----------
  const STAGES = ['loop-research', 'loop-create', 'loop-improve', 'loop-iterate'];
  function showStage(id, focus = false) {
    if (!STAGES.includes(id) || !document.getElementById(id)) return false;
    for (const stage of STAGES) {
      const node = document.getElementById(stage);
      if (node) { node.hidden = stage !== id; node.classList.toggle('ms-enter', stage === id && !reducedMotion); }
      // Scroll-reveal styling must never leave a shown stage invisible.
      if (node && stage === id) [node, ...node.querySelectorAll('.reveal-on-scroll')].forEach((x) => x.classList.add('revealed'));
    }
    document.querySelectorAll('.jr-loop a').forEach((link) => {
      const active = link.getAttribute('href') === `#${id}`;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current');
    });
    if (focus) document.querySelector('.jr-loop')?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
    return true;
  }
  function mountStages() {
    if (!document.getElementById('journey')) return;
    document.body.classList.add('ms-staged');
    document.addEventListener('click', (event) => {
      const link = event.target.closest?.('a[href^="#loop-"], a[href^="/#loop-"]');
      if (!link) return;
      const id = link.getAttribute('href').split('#')[1];
      if (showStage(id, true)) { event.preventDefault(); history.replaceState(null, '', `#${id}`); }
    });
    window.addEventListener('hashchange', () => showStage(location.hash.slice(1), true));
    const fromHash = location.hash.slice(1);
    showStage(STAGES.includes(fromHash) ? fromHash : 'loop-research', STAGES.includes(fromHash));
  }

  // ---------- Portal: first-visit tour ----------
  const TOUR = [
    { stage: null, kicker: 'Welcome back', title: 'Art of Sarabjit Singh', body: 'Muse is your growth loop: research similar sellers, create a post, improve with ranked ideas, then go again. This tour takes 20 seconds.', art: '✦' },
    { stage: 'loop-research', kicker: 'Step 1 · Research', title: 'See who sells similar art', body: 'Four competitors are on your watchlist, with what they charge next to your $14–$22 Pixels prints, and what is new at each shop.', art: '1' },
    { stage: 'loop-create', kicker: 'Step 2 · Create', title: 'Start from ads Muse already made', body: 'Muse Image staged your paintings in collector rooms. Open one, then make your own ready-to-post image and caption.', art: '2' },
    { stage: 'loop-improve', kicker: 'Step 3 · Improve', title: 'Pick the next move', body: 'Muse Spark ranks five ideas by impact, like featuring your Empowering Women series, which competitors don’t have.', art: '3' },
    { stage: 'loop-iterate', kicker: 'Step 4 · Iterate', title: 'Learn, then go again', body: 'Log how a post did in the daily desk, try the next idea and re-check competitors. Each run uses 1 credit.', art: '4' },
  ];
  let tourDialog;
  let tourIndex = 0;
  function renderTour() {
    const step = TOUR[tourIndex];
    tourDialog.querySelector('.ms-tour-art').textContent = step.art;
    tourDialog.querySelector('.ms-tour-art').className = `ms-tour-art s${tourIndex}`;
    tourDialog.querySelector('.ms-eyebrow').textContent = step.kicker;
    tourDialog.querySelector('h2').textContent = step.title;
    tourDialog.querySelector('.ms-tour-body').textContent = step.body;
    tourDialog.querySelectorAll('.ms-dots span').forEach((dot, i) => dot.classList.toggle('on', i === tourIndex));
    tourDialog.querySelector('.ms-back').hidden = tourIndex === 0;
    const last = tourIndex === TOUR.length - 1;
    tourDialog.querySelector('.ms-next').hidden = last;
    tourDialog.querySelector('.ms-finish').hidden = !last;
    if (step.stage) showStage(step.stage);
  }
  function openTour() {
    if (!tourDialog) {
      tourDialog = el('dialog', { class: 'ms-dialog ms-tour', 'aria-labelledby': 'msTourTitle' });
      const skip = el('button', { type: 'button', class: 'ms-skip' }, 'Skip tour');
      skip.addEventListener('click', () => endTour());
      tourDialog.appendChild(skip);
      tourDialog.appendChild(el('div', { class: 'ms-tour-art', 'aria-hidden': 'true' }));
      tourDialog.appendChild(el('p', { class: 'ms-eyebrow' }));
      tourDialog.appendChild(el('h2', { id: 'msTourTitle' }));
      tourDialog.appendChild(el('p', { class: 'ms-tour-body' }));
      const dots = el('div', { class: 'ms-dots', 'aria-hidden': 'true' });
      TOUR.forEach(() => dots.appendChild(el('span')));
      tourDialog.appendChild(dots);
      const nav = el('div', { class: 'ms-tour-nav' });
      const back = el('button', { type: 'button', class: 'ms-secondary ms-back' }, '← Back');
      const next = el('button', { type: 'button', class: 'ms-primary ms-next' }, 'Next →');
      const finish = el('a', { class: 'ms-primary ms-finish', href: '/create' }, 'Create your next post →');
      const explore = el('button', { type: 'button', class: 'ms-secondary ms-explore' }, 'Explore the plan');
      back.addEventListener('click', () => { tourIndex = Math.max(0, tourIndex - 1); renderTour(); });
      next.addEventListener('click', () => { tourIndex = Math.min(TOUR.length - 1, tourIndex + 1); renderTour(); });
      finish.addEventListener('click', () => store.set(TOUR_KEY, '1'));
      explore.addEventListener('click', () => endTour('loop-research'));
      nav.append(back, explore, next, finish);
      tourDialog.appendChild(nav);
      tourDialog.addEventListener('cancel', () => store.set(TOUR_KEY, '1'));
      document.body.appendChild(tourDialog);
    }
    tourIndex = 0; renderTour();
    if (typeof tourDialog.showModal === 'function') tourDialog.showModal(); else tourDialog.setAttribute('open', '');
  }
  function endTour(stage) {
    store.set(TOUR_KEY, '1');
    tourDialog?.close();
    if (stage) showStage(stage, true);
  }


  // ---------- /today: daily brief from the latest saved snapshot ----------
  const WATCH = [
    { name: 'SikhiArt.com', where: 'Own shop · 300 pages', status: 'new', note: '2 new listings in the 30 days before Nov 3: new editions of Mai Bhago ji and Hari Singh Nalwa' },
    { name: 'Gurinderpreet Kaur', where: 'Fine Art America · 70 listings', status: 'first', note: 'Prints $14–$50. First check, so nothing to compare yet' },
    { name: 'Manjot Singh Sachdeva', where: 'Fine Art America / Pixels · 105 listings', status: 'first', note: 'Prints $14–$24. First check, so nothing to compare yet' },
    { name: 'Gurdish Pannu', where: 'Saatchi Art · originals', status: 'first', note: 'Originals, no USD prices listed. First check' },
  ];
  function mountBrief() {
    if (!location.pathname.startsWith('/today')) return;
    const main = document.querySelector('main');
    if (!main || document.getElementById('msBrief')) return;
    const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
    const section = el('section', { class: 'ms-brief', id: 'msBrief', 'aria-labelledby': 'msBriefTitle' });
    const head = el('div', { class: 'ms-brief-head' });
    const titleBox = el('div');
    titleBox.appendChild(el('p', { class: 'ms-eyebrow' }, `Today’s brief · ${today}`));
    titleBox.appendChild(el('h2', { id: 'msBriefTitle' }, 'What changed at the shops you watch'));
    const meta = el('p', { class: 'ms-brief-meta' });
    meta.appendChild(el('span', { class: 'ms-dot', 'aria-hidden': 'true' }));
    meta.appendChild(document.createTextNode('Watchlist: 4 competitors · 6 shop pages · last checked Nov 3 · social accounts not checked yet'));
    titleBox.appendChild(meta);
    const recheck = el('button', { type: 'button', class: 'ms-secondary ms-small', disabled: '', title: 'Re-checking needs a live server' }, 'Re-check now');
    const toggle = el('button', { type: 'button', class: 'ms-link ms-brief-toggle', 'aria-expanded': 'true', 'aria-controls': 'msBriefBody' }, 'Hide');
    const actions = el('div', { class: 'ms-brief-actions' });
    actions.append(recheck, toggle);
    head.append(titleBox, actions);
    const body = el('div', { class: 'ms-brief-body', id: 'msBriefBody' });
    const list = el('ul', { class: 'ms-watch' });
    for (const item of WATCH) {
      const li = el('li', { class: item.status });
      li.appendChild(el('span', { class: `ms-chip ${item.status}` }, item.status === 'new' ? 'New' : 'First check'));
      li.appendChild(el('strong', {}, item.name));
      li.appendChild(el('span', { class: 'ms-where' }, item.where));
      li.appendChild(el('span', { class: 'ms-note' }, item.note));
      list.appendChild(li);
    }
    const move = el('div', { class: 'ms-move' });
    const moveText = el('div');
    moveText.appendChild(el('span', { class: 'ms-chip high' }, 'Today’s move · high impact'));
    moveText.appendChild(el('strong', {}, 'Feature your Empowering Women series'));
    moveText.appendChild(el('span', { class: 'ms-note' }, 'SikhiArt keeps adding warrior and guru editions but has no group for women’s stories.'));
    const go = el('a', { class: 'ms-primary ms-small', href: '/create?goal=story' }, 'Make this post →');
    move.append(moveText, go);
    body.append(list, move);
    body.appendChild(el('p', { class: 'ms-muted' }, 'From saved public snapshots captured Nov 3. Muse checks again when you run a re-check on a live server; it does not watch continuously.'));
    section.append(head, body);
    toggle.addEventListener('click', () => {
      const open = body.hidden;
      body.hidden = !open;
      toggle.textContent = open ? 'Hide' : 'Show brief';
      toggle.setAttribute('aria-expanded', String(open));
      store.set('muse.briefHidden', open ? '' : '1');
    });
    if (store.get('muse.briefHidden') === '1') { body.hidden = true; toggle.textContent = 'Show brief'; toggle.setAttribute('aria-expanded', 'false'); }
    main.insertBefore(section, main.firstChild);
  }

  function revealFallback() {
    // Throttled or background tabs may never fire IntersectionObserver; reveal anything still hidden.
    setTimeout(() => document.querySelectorAll('.reveal-on-scroll:not(.revealed)').forEach((x) => x.classList.add('revealed')), 900);
  }

  function init() {
    revealFallback();
    mountCredits();
    mountBrief();
    mountStages();
    document.querySelectorAll('[data-open-gift]').forEach((node) => node.addEventListener('click', openGift));
    document.querySelectorAll('[data-open-tour]').forEach((node) => node.addEventListener('click', openTour));
    if (document.getElementById('journey') && !store.get(TOUR_KEY) && !location.hash) setTimeout(openTour, 500);
  }

  window.museShell = { spend, progress, toast, openGift, openTour, showStage };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
