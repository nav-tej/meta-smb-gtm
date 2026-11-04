'use strict';
// Shared app shell for / and /create: demo credits, progress feedback, gift plan, and the portal
// tour and stage tabs. Everything runs on saved results; nothing here calls a model or takes payment.
(() => {
  const CREDIT_KEY = 'muse.demoCredits';
  const TOUR_KEY = 'muse.tourSeen';
  const START_CREDITS = 3;
  const SESSION_KEY = 'muse.demoSession';
  const hasSession = () => store.get(SESSION_KEY) === '1';
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
    pill.setAttribute('aria-label', credits === 0 ? 'No demo runs left. Get more runs' : `${credits} demo credits remaining`);
    const label = pill.querySelector('.ms-credits-label');
    if (label) label.textContent = credits === 0 ? ' · Get more runs' : ' credits';
    if (bump && !reducedMotion) { pill.classList.remove('bump'); void pill.offsetWidth; pill.classList.add('bump'); }
  }
  function spend(label) {
    if (!hasSession()) return;
    if (credits === 0) { toast('No runs left. Pick a plan, or reset the demo credits.', 'warn'); openPricing(); return; }
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
      let coin = button.querySelector('.ms-coin');
      if (!coin) {
        coin = el('span', { class: 'ms-coin', 'aria-hidden': 'true' }, '🪙');
        button.prepend(coin);
      } else {
        coin.textContent = '🪙';
      }
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
      const more = el('button', { type: 'button', class: 'ms-link ms-more' }, 'Get more runs →');
      more.addEventListener('click', () => { closeMenu(); openPricing(); });
      menu.appendChild(more);
      const gift = el('button', { type: 'button', class: 'ms-link' }, 'Gift a subscription →');
      gift.addEventListener('click', () => { closeMenu(); openPricing('gift'); });
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

  // ---------- Pricing (planned) ----------
  const PLANS = [
    { name: 'Starter', price: '$9', per: 'one-time', runs: '10 runs', points: ['Competitor analysis', 'Ready-to-post ads', 'Ranked next moves'] },
    { name: 'Growth', price: '$29', per: '/month', runs: '50 runs a month', points: ['Everything in Starter', 'Daily growth brief', 'Budget advice for ads'], featured: true },
    { name: 'Unlimited', price: '$99', per: '/month', runs: 'Unlimited runs', points: ['Everything in Growth', 'Unlimited competitors', 'Priority support'] },
  ];
  let pricingDialog;
  function openPricing(mode = '') {
    if (!pricingDialog) {
      pricingDialog = el('dialog', { class: 'ms-dialog ms-pricing', 'aria-labelledby': 'msPricingTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => pricingDialog.close());
      pricingDialog.appendChild(close);
      pricingDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Planned pricing'));
      pricingDialog.appendChild(el('h2', { id: 'msPricingTitle' }, 'Get more runs'));
      pricingDialog.appendChild(el('p', { class: 'ms-pricing-gift' }));
      const grid = el('div', { class: 'ms-plans' });
      for (const plan of PLANS) {
        const card = el('div', { class: `ms-plan${plan.featured ? ' featured' : ''}` });
        if (plan.featured) card.appendChild(el('span', { class: 'ms-plan-tag' }, 'Most popular'));
        card.appendChild(el('strong', { class: 'ms-plan-name' }, plan.name));
        const price = el('p', { class: 'ms-plan-price' }, plan.price);
        price.appendChild(el('small', {}, ` ${plan.per}`));
        card.appendChild(price);
        card.appendChild(el('p', { class: 'ms-plan-runs' }, plan.runs));
        const list = el('ul', {});
        plan.points.forEach((point) => list.appendChild(el('li', {}, point)));
        card.appendChild(list);
        card.appendChild(el('button', { type: 'button', class: plan.featured ? 'ms-primary' : 'ms-secondary', disabled: '', title: 'Not on sale in this demo' }, 'Coming soon'));
        grid.appendChild(card);
      }
      pricingDialog.appendChild(grid);
      pricingDialog.appendChild(el('p', { class: 'ms-muted' }, 'Plans open after the beta. This demo takes no payment and collects no details. 1 run = one competitor analysis, ad generation or budget review.'));
      pricingDialog.addEventListener('click', (event) => { if (event.target === pricingDialog) pricingDialog.close(); });
      document.body.appendChild(pricingDialog);
    }
    pricingDialog.querySelector('h2').textContent = mode === 'gift' ? 'Gift a subscription' : 'Get more runs';
    const giftLine = pricingDialog.querySelector('.ms-pricing-gift');
    giftLine.textContent = mode === 'gift' ? 'Any plan can be sent as a gift to a maker you love.' : '';
    giftLine.hidden = mode !== 'gift';
    if (typeof pricingDialog.showModal === 'function') pricingDialog.showModal(); else pricingDialog.setAttribute('open', '');
  }
  const openGift = () => openPricing('gift');

  // ---------- Logged-out demo and free signup ----------
  let signupDialog;
  function openSignup() {
    if (!signupDialog) {
      signupDialog = el('dialog', { class: 'ms-dialog ms-signup', 'aria-labelledby': 'msSignupTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => signupDialog.close());
      signupDialog.appendChild(close);
      signupDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Free to start'));
      signupDialog.appendChild(el('h2', { id: 'msSignupTitle' }, '3 runs on us'));
      signupDialog.appendChild(el('p', { class: 'ms-tour-body' }, 'Analyze competitors, create ready-to-post ads and get ranked next moves for Art of Sarabjit Singh.'));
      const start = el('button', { type: 'button', class: 'ms-primary' }, 'Start free with 3 runs');
      start.addEventListener('click', () => { startSession(); signupDialog.close(); });
      signupDialog.appendChild(start);
      signupDialog.appendChild(el('p', { class: 'ms-muted' }, 'Accounts open after the beta. For now, your free demo runs are saved in this browser; no email or payment is needed.'));
      signupDialog.addEventListener('click', (event) => { if (event.target === signupDialog) signupDialog.close(); });
      document.body.appendChild(signupDialog);
    }
    if (typeof signupDialog.showModal === 'function') signupDialog.showModal(); else signupDialog.setAttribute('open', '');
  }
  function startSession() {
    store.set(SESSION_KEY, '1');
    if (store.get(CREDIT_KEY) === null) { credits = START_CREDITS; store.set(CREDIT_KEY, String(credits)); }
    document.body.classList.remove('ms-logged-out');
    document.querySelectorAll('.ms-gate').forEach((gate) => gate.remove());
    document.querySelectorAll('.ms-signup-btn').forEach((btn) => btn.remove());
    if (pill) { pill.hidden = false; renderCredits(true); }
    toast(`Welcome! ${credits} free runs are ready.`);
  }
  function mountSession() {
    if (hasSession()) return;
    document.body.classList.add('ms-logged-out');
    if (pill) pill.hidden = true;
    const header = document.querySelector('header.topbar') || document.querySelector('body > header');
    if (header) {
      const btn = el('button', { type: 'button', class: 'ms-primary ms-small ms-signup-btn' }, 'Sign up free');
      btn.addEventListener('click', openSignup);
      if (pill?.parentNode) pill.insertAdjacentElement('afterend', btn); else header.appendChild(btn);
    }
    // On the portal, frost the interactive stages and workspace until the visitor starts.
    const gated = [...document.querySelectorAll('.jr-stage'), document.querySelector('.ms-workspace-bar')].filter(Boolean);
    for (const area of gated) {
      area.classList.add('ms-gated');
      const gate = el('div', { class: 'ms-gate' });
      const card = el('div', { class: 'ms-gate-card' });
      card.appendChild(el('strong', {}, 'Sign up free — 3 runs on us'));
      card.appendChild(el('span', {}, 'Sample data shown. Start free to run analyses, open ads and use the tools.'));
      const cta = el('button', { type: 'button', class: 'ms-primary' }, 'Sign up free');
      cta.addEventListener('click', openSignup);
      card.appendChild(cta);
      gate.appendChild(card);
      area.appendChild(gate);
    }
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
    titleBox.appendChild(el('p', { class: 'ms-eyebrow' }, `Your daily growth brief · ${today}`));
    titleBox.appendChild(el('h2', { id: 'msBriefTitle' }, 'What changed at the shops you watch'));
    titleBox.appendChild(el('p', { class: 'ms-brief-plan' }, 'Planned: a fresh brief delivered every morning. Today’s is built from the Nov 3 snapshot.'));
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


  // ---------- Portal workspace: every item gets a next step ----------
  const PIXELS_SHOP = 'https://sarabjit-singh.pixels.com/';
  const ROUTES = [
    { test: /checkout|contact form|1-click/i, label: 'Get the checkout template →', to: 'tab:tab-export' },
    { test: /starter|cheap|under \$25|\$1\d/i, label: 'Promote your prints →', to: '/create?goal=visit' },
    { test: /women|goddess|empower|mai bhago|mata gujri|shop group/i, label: 'Feature it in a post →', to: '/create?goal=story' },
    { test: /gift|holiday|housewarming|wedding/i, label: 'Make a gift post →', to: '/create?goal=gift' },
    { test: /story|blog|meaning|village/i, label: 'Make a story post →', to: '/create?goal=story' },
    { test: /home|title|seo|metadata|series tag|omit|listing/i, label: 'Open your Pixels shop ↗', to: PIXELS_SHOP },
  ];
  const CONTAINER_DEFAULTS = {
    metaAdsContainer: { label: 'Make an ad like this →', to: '/create', first: true },
    reallocationsContainer: { label: 'Add to campaign pack →', to: 'tab:tab-export', first: true },
    audiencesContainer: { label: 'Export for Ads Manager →', to: 'tab:tab-export', first: true },
  };
  function routeFor(containerId, text) {
    const fixed = CONTAINER_DEFAULTS[containerId];
    if (fixed?.first) return fixed;
    const title = text.split('\n').map((t) => t.trim()).find(Boolean) || '';
    return ROUTES.find((r) => r.test.test(title)) || ROUTES.find((r) => r.test.test(text)) || { label: 'Create a post for this →', to: '/create' };
  }
  function go(to) {
    if (to.startsWith('tab:')) {
      const tab = document.querySelector(`.step-tab[data-tab="${to.slice(4)}"]`);
      tab?.click();
      document.getElementById(to.slice(4))?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
    } else if (/^https:\/\//.test(to)) {
      window.open(to, '_blank', 'noopener');
    } else {
      location.href = to;
    }
  }
  function decorate(container) {
    container.querySelectorAll(':scope > .finding-item').forEach((item) => {
      if (item.querySelector('.ms-do')) return;
      const head = item.querySelector('.finding-head strong, strong');
      const route = routeFor(container.id, `${head ? head.textContent : ''}\n${item.textContent || ''}`);
      const row = el('div', { class: 'ms-do-row' });
      const btn = el('button', { type: 'button', class: 'ms-do' }, route.label);
      btn.addEventListener('click', () => go(route.to));
      row.appendChild(btn);
      item.appendChild(row);
    });
  }
  function mountActions() {
    const ids = ['findingsContainer', 'insightsContainer', 'diagnosticsContainer', 'metaAdsContainer', 'reallocationsContainer', 'audiencesContainer'];
    for (const id of ids) {
      const node = document.getElementById(id);
      if (!node) continue;
      decorate(node);
      if (typeof MutationObserver !== 'undefined') new MutationObserver(() => decorate(node)).observe(node, { childList: true });
    }
    document.getElementById('rerunDiagBtn')?.addEventListener('click', async () => {
      await progress('Re-running channel diagnostics', ['Re-reading the saved shop snapshot', 'Recounting listings and tags', 'Checking checkout friction']);
      const box = document.getElementById('diagnosticsContainer');
      box?.querySelectorAll('.finding-item').forEach((item) => { item.classList.remove('ms-flash'); void item.offsetWidth; item.classList.add('ms-flash'); });
      toast('Diagnostics recalculated from the Nov 3 snapshot · no changes');
    });
  }

  // ---------- Refine + memory ----------
  const MEMORY_KEY = 'muse.memory';
  const SYNONYMS = {
    pricing: ['price', 'priced', 'cheap', 'starter', '$', 'premium', 'under'], price: ['price', 'cheap', 'starter', '$'],
    gift: ['gift', 'holiday', 'housewarming', 'wedding'], instagram: ['instagram', 'social', 'post', 'story', 'reel', 'facebook'],
    women: ['women', 'goddess', 'empower', 'mai bhago', 'mata gujri'], story: ['story', 'blog', 'meaning'], home: ['home', 'title'],
  };
  const readMemory = () => { try { return JSON.parse(store.get(MEMORY_KEY) || '[]').filter((x) => typeof x === 'string').slice(0, 5); } catch { return []; } };
  function termsFor(text) {
    const words = text.toLowerCase().match(/[a-z$]+/g) || [];
    const terms = new Set();
    for (const word of words) {
      for (const [key, list] of Object.entries(SYNONYMS)) if (word.startsWith(key.slice(0, 5))) list.forEach((t) => terms.add(t));
      if (word.length > 4 && !['focus', 'analysis', 'about', 'their', 'strategy', 'frequency', 'posting', 'add'].includes(word)) terms.add(word);
    }
    return [...terms];
  }
  function applyFocus(text) {
    const terms = termsFor(text);
    const lists = ['insightsContainer', 'findingsContainer'].map((id) => document.getElementById(id)).filter(Boolean);
    let total = 0; let matched = 0;
    for (const list of lists) {
      const items = [...list.querySelectorAll(':scope > .finding-item')];
      total += items.length;
      const scored = items.map((item) => {
        const body = (item.textContent || '').toLowerCase();
        const score = terms.reduce((n, t) => n + (body.includes(t) ? 1 : 0), 0);
        item.classList.toggle('ms-match', score > 0);
        item.querySelector('.ms-match-tag')?.remove();
        if (score > 0) { matched += 1; item.insertBefore(el('span', { class: 'ms-match-tag' }, 'Matches your focus'), item.firstChild); }
        return { item, score };
      });
      scored.sort((a, b) => b.score - a.score).forEach(({ item }) => list.appendChild(item));
    }
    const banner = document.getElementById('focusBanner');
    if (banner) {
      banner.hidden = false;
      banner.textContent = matched
        ? `Focused on “${text}”: ${matched} of ${total} saved items match and are shown first. A fresh Muse Spark run with this focus needs a live server.`
        : `Nothing in the saved analysis covers “${text}” yet. It’s saved to memory, and a live Muse Spark run would analyse it.`;
    }
  }
  function renderMemory() {
    const strip = document.getElementById('memoryStrip');
    if (!strip) return;
    const memory = readMemory();
    strip.replaceChildren();
    if (!memory.length) { strip.hidden = true; return; }
    strip.hidden = false;
    strip.appendChild(el('span', { class: 'ms-memory-badge' }, '🧠 Remembered'));
    for (const item of memory) strip.appendChild(el('span', { class: 'ms-memory-item' }, item));
    const forget = el('button', { type: 'button', class: 'ms-link ms-forget' }, 'Forget');
    forget.addEventListener('click', () => { store.set(MEMORY_KEY, '[]'); renderMemory(); document.getElementById('focusBanner').hidden = true; document.querySelectorAll('.ms-match-tag').forEach((t) => t.remove()); document.querySelectorAll('.ms-match').forEach((m) => m.classList.remove('ms-match')); toast('Preferences forgotten.'); });
    strip.appendChild(forget);
  }
  function mountRefine() {
    const form = document.getElementById('refineForm');
    if (!form) return;
    const input = document.getElementById('refineInput');
    form.querySelectorAll('[data-refine]').forEach((chip) => chip.addEventListener('click', () => { input.value = chip.dataset.refine; input.focus(); }));
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const text = input.value.trim().replace(/\s+/g, ' ').slice(0, 140);
      if (!text) { input.focus(); return; }
      await progress('Refining your seller audit', ['Saving your preference to memory', 'Re-ranking the saved findings', 'Highlighting what matches']);
      const memory = [text, ...readMemory().filter((m) => m.toLowerCase() !== text.toLowerCase())].slice(0, 5);
      store.set(MEMORY_KEY, JSON.stringify(memory));
      renderMemory();
      applyFocus(text);
      toast('Your preferences saved');
      input.value = '';
    });
    renderMemory();
    // Re-apply the most recent preference once the saved analysis has rendered.
    const latest = readMemory()[0];
    const list = document.getElementById('insightsContainer');
    if (latest && list) {
      const reapply = () => { if (list.querySelector('.finding-item')) { applyFocus(latest); return true; } return false; };
      if (!reapply() && typeof MutationObserver !== 'undefined') {
        const obs = new MutationObserver(() => { if (reapply()) obs.disconnect(); });
        obs.observe(list, { childList: true });
      }
    }
  }

  function revealFallback() {
    // Throttled or background tabs may never fire IntersectionObserver; reveal anything still hidden.
    setTimeout(() => document.querySelectorAll('.reveal-on-scroll:not(.revealed)').forEach((x) => x.classList.add('revealed')), 900);
  }

  function init() {
    revealFallback();
    mountCredits();
    mountSession();
    mountBrief();
    mountActions();
    mountRefine();
    mountStages();
    document.querySelectorAll('[data-open-gift]').forEach((node) => node.addEventListener('click', openGift));
    document.querySelectorAll('[data-open-tour]').forEach((node) => node.addEventListener('click', openTour));
    if (document.getElementById('journey') && !store.get(TOUR_KEY) && !location.hash) setTimeout(openTour, 500);
  }

  window.museShell = { spend, progress, toast, openGift, openPricing, openSignup, openTour, showStage };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
