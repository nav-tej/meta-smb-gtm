'use strict';
// Shared app shell for /, /create, /today and /digest: demo credits, progress feedback, gift plan,
// the portal tour and stage tabs, recommendation triage, watchlist and notifications.
// Everything runs on saved results; nothing here calls a model or takes payment.
(() => {
  const CREDIT_KEY = 'muse.demoCredits';
  const TOUR_KEY = 'muse.tourSeen';
  const START_CREDITS = 3;
  const ACCOUNT_KEY = 'muse.demoAccount';
  const store = {
    get(key) { try { return window.localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch { /* private mode */ } },
    remove(key) { try { window.localStorage.removeItem(key); } catch { /* private mode */ } },
  };
  // Demo accounts live in this browser only (no auth backend in demo mode).
  const readAccount = () => { try { const a = JSON.parse(store.get(ACCOUNT_KEY) || 'null'); return a && typeof a.email === 'string' ? a : null; } catch { return null; } };
  const hasSession = () => !!readAccount();
  const creditKey = () => { const a = readAccount(); return a ? `${CREDIT_KEY}:${a.email}` : CREDIT_KEY; };
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  // Server accounts (Supabase + runs quota) replace browser-local demo credits when on.
  const serverSnapshot = () => window.museAccount?.getSnapshot?.() || null;
  const serverMode = () => serverSnapshot()?.configured === true;
  function removeGates() {
    document.body.classList.remove('ms-logged-out');
    document.querySelectorAll('.ms-gate').forEach((gate) => gate.remove());
    document.querySelectorAll('.ms-signup-btn').forEach((btn) => btn.remove());
  }
  const el = (tag, attrs = {}, text = '') => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text) node.textContent = text;
    return node;
  };

  // ---------- Toasts ----------
  let toastBox;
  // `action` ({ label, onClick }) adds one button, e.g. Undo, and keeps the toast up longer.
  function toast(message, kind = '', action = null) {
    if (!toastBox) { toastBox = el('div', { class: 'ms-toasts', role: 'status', 'aria-live': 'polite' }); document.body.appendChild(toastBox); }
    // Repeated clicks refresh the visible toast instead of stacking copies of it.
    for (const shown of toastBox.querySelectorAll('.ms-toast:not(.out)')) if (shown.firstChild?.nodeValue === message) shown.remove();
    const item = el('div', { class: `ms-toast ${kind}` }, message);
    let life = 2600;
    if (action && typeof action.onClick === 'function') {
      const button = el('button', { type: 'button', class: 'ms-toast-action' }, action.label || 'Undo');
      button.addEventListener('click', () => { item.remove(); action.onClick(); });
      item.append(' ', button);
      item.classList.add('has-action');
      life = 5000;
    }
    toastBox.appendChild(item);
    setTimeout(() => item.classList.add('out'), life);
    setTimeout(() => item.remove(), life + 500);
  }

  // ---------- Resilient fetch: friendly errors, retries only where it is safe ----------
  // Retries happen on network errors and 502/503/504, and only for GETs or requests marked
  // safe (saved-mode calls). Billed live calls (?live=true) are never retried automatically.
  const RETRY_STATUS = new Set([502, 503, 504]);
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const STATUS_MESSAGES = {
    401: 'Your session expired. Sign in again to continue — your work is safe on this device.',
    402: 'You are out of runs. Saved results are still free to view.',
    403: 'This needs a live session. Saved results still work.',
    408: 'Muse is taking longer than expected. Your inputs are safe; try again in a minute.',
    413: 'That upload is too large. Try a smaller image.',
    415: 'That request was not in the expected format. Please try again.',
    422: 'Some details need fixing before this can run.',
    429: 'Too many live runs this hour. Saved results still work; try again later.',
    500: 'Something went wrong on our side. Your work is safe; please try again.',
    502: 'Muse could not finish this right now. Your inputs are safe; try again in a minute.',
    503: 'This service is busy or not configured. Saved results still work.',
    504: 'This took too long. Your inputs are safe; try again in a minute.',
  };
  let forcedOffline = false;
  function isOffline() {
    if (forcedOffline) return true;
    return typeof navigator !== 'undefined' && navigator.onLine === false;
  }
  function friendlyError(errorOrMessage, status = 0, fallback = 'Something went wrong. Your work is safe; please try again.') {
    if (isOffline()) return 'You appear to be offline. Your work is saved on this device — reconnect and try again.';
    const raw = typeof errorOrMessage === 'string' ? errorOrMessage : (errorOrMessage?.message || '');
    if (errorOrMessage?.name === 'AbortError' || status === 504 || status === 408 || /timed?\s*out/i.test(raw)) {
      return STATUS_MESSAGES[504];
    }
    if (status === 401) return STATUS_MESSAGES[401];
    if (status && STATUS_MESSAGES[status] && (!raw || /traceback|exception|<html|<!doctype|http\s*\d{3}|failed to fetch|networkerror/i.test(raw))) {
      return STATUS_MESSAGES[status];
    }
    if (raw && raw.length <= 400 && !/traceback|exception|<html|<!doctype|failed to fetch|networkerror|load failed/i.test(raw)) {
      return raw;
    }
    if (status && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status];
    return fallback;
  }
  async function errorMessage(response, fallback = 'Something went wrong. Please try again.') {
    let detail = '';
    try { const body = await response.clone().json(); if (typeof body?.detail === 'string') detail = body.detail; else if (typeof body?.detail?.message === 'string') detail = body.detail.message; } catch { /* not JSON */ }
    // Never show stack traces or HTML error pages; keep server messages short and plain.
    if (detail && detail.length <= 400 && !/traceback|exception|<html|<!doctype/i.test(detail)) return detail;
    return STATUS_MESSAGES[response.status] || fallback;
  }
  async function museFetch(url, options = {}, { retries = 2, safe, timeoutMs = 30000 } = {}) {
    if (isOffline()) {
      const err = new Error('You appear to be offline. Your work is saved on this device — reconnect and try again.');
      err.code = 'OFFLINE';
      throw err;
    }
    const method = String(options.method || 'GET').toUpperCase();
    const billed = /[?&]live=(true|1)\b/.test(String(url));
    const canRetry = !billed && (safe ?? method === 'GET');
    const attempts = canRetry ? retries + 1 : 1;
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = typeof AbortController === 'function' ? new AbortController() : null;
      const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
      try {
        const response = await fetch(url, { credentials: 'same-origin', ...options, ...(controller && !options.signal ? { signal: controller.signal } : {}) });
        if (response.status === 401 && serverSnapshot()?.user) {
          window.museAccount?.open?.('signin', 'Your session expired. Sign in again — your work is still on this device.');
        }
        if (!RETRY_STATUS.has(response.status) || attempt === attempts - 1) return response;
        lastError = new Error(await errorMessage(response));
      } catch (error) {
        lastError = error?.name === 'AbortError'
          ? new Error(STATUS_MESSAGES[504])
          : new Error(isOffline() ? 'You appear to be offline. Your work is saved on this device — reconnect and try again.' : 'You seem to be offline or the server is unreachable. Your work is safe; try again.');
        if (attempt === attempts - 1) throw lastError;
      } finally { if (timer) clearTimeout(timer); }
      await wait(400 * 3 ** attempt);
    }
    throw lastError;
  }

  // ---------- Run credits: the server decides; localStorage is only an offline fallback ----------
  const loadCredits = () => { const n = Number.parseInt(store.get(creditKey()) ?? '', 10); return Number.isFinite(n) && n >= 0 ? n : START_CREDITS; };
  let credits = loadCredits();
  const saveCredits = () => store.set(creditKey(), String(credits));
  let countNode;
  let pill;
  function renderCredits(bump = false) {
    if (!countNode) return;
    countNode.textContent = String(credits);
    pill.classList.toggle('empty', credits === 0);
    pill.setAttribute('aria-label', credits === 0 ? 'No demo runs left. Get more runs' : `${credits} demo credits remaining`);
    const label = pill.querySelector('.ms-credits-label');
    if (label) label.textContent = credits === 0 ? ' · Get more runs' : (credits === 1 ? ' run' : ' runs');
    if (bump && !reducedMotion) { pill.classList.remove('bump'); void pill.offsetWidth; pill.classList.add('bump'); }
  }
  let serverCredits = false;
  let creditNote = '';
  function applyServerCredits(data) {
    if (!data || data.source !== 'server' || typeof data.balance !== 'number') return false;
    serverCredits = true;
    credits = Math.max(0, data.balance);
    creditNote = data.persistent === false ? String(data.note || '') : '';
    saveCredits();
    renderCredits();
    const noteNode = pill?.querySelector('.ms-credit-note');
    if (noteNode) noteNode.textContent = creditNote;
    return true;
  }
  async function syncCredits() {
    try {
      const response = await museFetch('/api/v1/credits', {}, { retries: 1, timeoutMs: 8000 });
      if (response.ok) return applyServerCredits(await response.json());
    } catch { /* offline: keep the browser's last known balance */ }
    return false;
  }
  async function spendOnServer(label) {
    try {
      const response = await museFetch('/api/v1/credits/spend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label: String(label).slice(0, 80) }) }, { safe: false, timeoutMs: 8000 });
      if (response.status === 402) { credits = 0; saveCredits(); renderCredits(true); toast(await errorMessage(response), 'warn'); openPricing(); return; }
      if (response.ok) applyServerCredits(await response.json());
    } catch { /* offline: the optimistic local count stands until the next sync */ }
  }
  function spend(label) {
    if (serverMode()) return; // The server counts real runs; saved actions stay free.
    if (!hasSession()) return;
    if (credits === 0) { toast('No runs left. Pick a plan, or reset the demo credits.', 'warn'); openPricing(); return; }
    credits -= 1; saveCredits(); renderCredits(true);
    toast(`−1 run · ${label}`);
    if (serverCredits) spendOnServer(label);
  }
  // A live Muse call is charged by the server's live gate (and refunded on cache hits or
  // failures), so the browser only re-reads the balance instead of spending again.
  function spendLive(label) {
    try { window.museTrack?.('live_run_completed', { label: String(label).slice(0, 60), accounts: serverMode() }); } catch {}
    if (serverMode()) return;
    if (serverCredits) { syncCredits().then(() => toast(`Live run · ${label} · ${credits} left`)); return; }
    spend(label);
  }
  // Gate for any run (analysis, generation, refinement). Returns false when the visitor must
  // sign up or buy more runs first. Server accounts count their own runs.
  // Check without spending: used before a paid live call, which spends only after it succeeds.
  function canRun(label) {
    if (serverMode()) return true;
    if (!hasSession()) { openSignup(`Create a free account to run ${label.toLowerCase()}.`); return false; }
    if (credits === 0) { toast('No runs left. Pick a plan to keep going.', 'warn'); openPricing(); return false; }
    return true;
  }
  function requireRun(label) {
    if (serverMode()) return true;
    if (!hasSession()) { openSignup(`Create a free account to run ${label.toLowerCase()}.`); return false; }
    if (credits === 0) { toast('No runs left. Pick a plan to keep going.', 'warn'); openPricing(); return false; }
    spend(label);
    return true;
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
      menu.appendChild(el('strong', {}, 'Runs'));
      menu.appendChild(el('p', {}, '1 run = one competitor analysis, refinement, re-run or ad scene. Viewing results you already have is free.'));
      menu.appendChild(el('p', { class: 'ms-muted' }, 'Runs are checked on the server before any live Muse call. Repeat live results come from a 24-hour cache and give the run back, so they never spend Muse API credit twice.'));
      menu.appendChild(el('p', { class: 'ms-muted ms-credit-note' }, creditNote));
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
      const anchor = header.querySelector('.mode, .status-pill, .topbar-nav, #saveStatus');
      if (anchor) anchor.insertAdjacentElement('afterend', pill); else header.appendChild(pill);
    }
    renderCredits();
    // Runs are spent only by explicit spend() calls after a live Muse request
    // succeeds. Viewing saved results is always free; no click auto-spends.
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

  // ---------- Pricing ----------
  // Starter is the only plan on sale; Growth/Unlimited return when they have Stripe prices.
  const PLAN_RUNS = { starter: 20, growth: 50, unlimited: 999 };
  const STARTER_POINTS = ['20 Muse runs every month', 'Competitor analysis and ready-to-post ads', 'Cancel anytime'];
  const PLANS = [
    { id: 'starter', interval: 'month', name: 'Starter · Monthly', price: '$12', per: '/month', runs: '20 runs a month', points: STARTER_POINTS },
    { id: 'starter', interval: 'year', name: 'Starter · Annual', price: '$9', per: '/month, billed $108 yearly', runs: '20 runs a month · save 25%', points: STARTER_POINTS, featured: true, tag: 'Best value' },
  ];
  async function buyPlan(plan, interval, button) {
    const snap = serverSnapshot();
    if (!snap?.configured) return;
    // Hand over to the account dialog (one message, no toast hidden behind two stacked modals).
    if (!snap.user) { pricingDialog?.close(); window.museAccount.open('signup', 'Create a free account or sign in, then pick your plan.'); return; }
    if (!snap.user.email_verified) { pricingDialog?.close(); window.museAccount.open('account', 'Confirm your email using the signup link, then pick your plan.'); return; }
    button.disabled = true;
    window.museTrack?.('checkout_started', { plan, interval });
    try {
      const response = await fetch('/api/v1/billing/checkout', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan, interval }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) { window.museTrack?.('checkout_failed', { plan, interval, status: response.status }); throw new Error(data.detail || 'Checkout failed.'); }
      location.href = data.url;
    } catch (error) { toast(error.message, 'warn'); button.disabled = false; }
  }
  // Real checkout is offered only when the server says payments can be taken and recorded.
  let billingStatus = null;
  async function loadBillingStatus() {
    if (billingStatus) return billingStatus;
    try {
      const response = await fetch('/api/v1/billing/status', { credentials: 'same-origin' });
      billingStatus = response.ok ? await response.json() : { available: false };
    } catch { billingStatus = { available: false }; }
    return billingStatus;
  }
  function refreshPlanButtons() {
    if (!pricingDialog) return;
    const comingSoon = serverMode() && billingStatus?.available !== true;
    pricingDialog.querySelectorAll('.ms-plan').forEach((card, index) => {
      const plan = PLANS[index];
      const button = card.querySelector('button');
      if (!plan || !button) return;
      if (comingSoon) {
        button.disabled = true;
        button.textContent = 'Coming soon';
        button.title = 'Paid plans open soon';
        button.onclick = null;
      } else if (serverMode()) {
        button.disabled = false;
        button.removeAttribute('title');
        button.textContent = `Choose ${plan.name}`;
        button.onclick = () => buyPlan(plan.id, plan.interval, button);
        button.setAttribute('data-track', `plan_${plan.interval}`);
      } else {
        button.disabled = false;
        button.title = 'Demo checkout: no payment is taken';
        button.textContent = `Choose ${plan.name}`;
        button.onclick = () => { pricingDialog.close(); openCheckout(plan); };
      }
    });
    const note = pricingDialog.querySelector('.ms-muted');
    if (note && comingSoon) { note.textContent = 'Paid plans open soon. Your 3 free Muse runs work now.'; return; }
    if (note) note.textContent = serverMode()
      ? 'Secure checkout via Stripe for n Plus Alpha LLC. Cancel anytime; runs reset monthly. 1 run = one competitor analysis, ad generation or budget review.'
      : 'Demo checkout: no card is needed and no payment is taken; runs are added to your demo balance on this server. 1 run = one analysis, refinement, re-run or ad scene.';
  }
  let pricingDialog;
  function openPricing(mode = '') {
    if (!pricingDialog) {
      pricingDialog = el('dialog', { class: 'ms-dialog ms-pricing', 'aria-labelledby': 'msPricingTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => pricingDialog.close());
      pricingDialog.appendChild(close);
      pricingDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Plans'));
      pricingDialog.appendChild(el('h2', { id: 'msPricingTitle' }, 'Get more runs'));
      pricingDialog.appendChild(el('p', { class: 'ms-pricing-gift' }));
      const grid = el('div', { class: 'ms-plans' });
      for (const plan of PLANS) {
        const card = el('div', { class: `ms-plan${plan.featured ? ' featured' : ''}` });
        if (plan.featured) card.appendChild(el('span', { class: 'ms-plan-tag' }, plan.tag || 'Most popular'));
        card.appendChild(el('strong', { class: 'ms-plan-name' }, plan.name));
        const price = el('p', { class: 'ms-plan-price' }, plan.price);
        price.appendChild(el('small', {}, ` ${plan.per}`));
        card.appendChild(price);
        card.appendChild(el('p', { class: 'ms-plan-runs' }, plan.runs));
        const list = el('ul', {});
        plan.points.forEach((point) => list.appendChild(el('li', {}, point)));
        card.appendChild(list);
        card.appendChild(el('button', { type: 'button', class: plan.featured ? 'ms-primary' : 'ms-secondary' }, ''));
        grid.appendChild(card);
      }
      pricingDialog.appendChild(grid);
      pricingDialog.appendChild(el('p', { class: 'ms-muted' }, ''));
      pricingDialog.addEventListener('click', (event) => { if (event.target === pricingDialog) pricingDialog.close(); });
      document.body.appendChild(pricingDialog);
    }
    refreshPlanButtons();
    if (serverMode() && !billingStatus) loadBillingStatus().then(refreshPlanButtons);
    window.museTrack?.('plans_viewed', { mode: mode || 'plans', accounts: serverMode(), signed_in: !!serverSnapshot()?.user });
    pricingDialog.querySelector('h2').textContent = mode === 'gift' ? 'Gift a subscription' : 'Get more runs';
    const giftLine = pricingDialog.querySelector('.ms-pricing-gift');
    giftLine.textContent = mode === 'gift' ? 'Any plan can be sent as a gift to a maker you love.' : '';
    giftLine.hidden = mode !== 'gift';
    if (typeof pricingDialog.showModal === 'function') pricingDialog.showModal(); else pricingDialog.setAttribute('open', '');
  }
  const openGift = () => openPricing('gift');

  // ---------- Demo checkout (adds runs; no payment) ----------
  let checkoutDialog;
  function openCheckout(plan) {
    if (!hasSession()) { openSignup('Create a free account before choosing a plan.'); return; }
    if (!checkoutDialog) {
      checkoutDialog = el('dialog', { class: 'ms-dialog ms-checkout', 'aria-labelledby': 'msCheckoutTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => checkoutDialog.close());
      checkoutDialog.appendChild(close);
      checkoutDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Demo checkout'));
      checkoutDialog.appendChild(el('h2', { id: 'msCheckoutTitle' }));
      const summary = el('div', { class: 'ms-checkout-summary' });
      checkoutDialog.appendChild(summary);
      checkoutDialog.appendChild(el('p', { class: 'ms-checkout-note' }, 'This is a demo: no card is needed, nothing is charged, and no payment details are collected. Runs are added to your demo balance on this server.'));
      const pay = el('button', { type: 'button', class: 'ms-primary ms-pay' });
      checkoutDialog.appendChild(pay);
      checkoutDialog.addEventListener('click', (event) => { if (event.target === checkoutDialog) checkoutDialog.close(); });
      document.body.appendChild(checkoutDialog);
    }
    const account = readAccount();
    checkoutDialog.querySelector('h2').textContent = `${plan.name} · ${plan.runs}`;
    const summary = checkoutDialog.querySelector('.ms-checkout-summary');
    summary.replaceChildren();
    [['Plan', plan.name], ['Price', `${plan.price} ${plan.per}`], ['Runs added', plan.id === 'unlimited' ? 'Unlimited (999 in this demo)' : String(PLAN_RUNS[plan.id])], ['Account', account.email]]
      .forEach(([k, v]) => { const row = el('div', {}); row.append(el('span', {}, k), el('strong', {}, v)); summary.appendChild(row); });
    const pay = checkoutDialog.querySelector('.ms-pay');
    pay.disabled = false;
    pay.textContent = `Complete demo purchase · ${plan.price}`;
    pay.onclick = async () => {
      pay.disabled = true;
      await progress('Completing demo purchase', ['Confirming the plan', 'Adding runs to your account']);
      let added = false;
      if (serverCredits) {
        try {
          const response = await museFetch('/api/v1/credits/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan: plan.id }) }, { safe: false, timeoutMs: 8000 });
          if (response.ok) added = applyServerCredits(await response.json());
          else { toast(await errorMessage(response), 'warn'); pay.disabled = false; return; }
        } catch (error) { toast(error.message, 'warn'); pay.disabled = false; return; }
      }
      if (!added) { credits += PLAN_RUNS[plan.id] || 0; saveCredits(); }
      renderCredits(true);
      const history = account.purchases || [];
      history.push({ plan: plan.id, runs: PLAN_RUNS[plan.id], at: new Date().toISOString() });
      store.set(ACCOUNT_KEY, JSON.stringify({ ...account, purchases: history.slice(-20) }));
      checkoutDialog.close();
      toast(`+${PLAN_RUNS[plan.id]} runs added · demo purchase, nothing charged`);
    };
    if (typeof checkoutDialog.showModal === 'function') checkoutDialog.showModal(); else checkoutDialog.setAttribute('open', '');
  }

  // ---------- Demo sign-up and account ----------
  const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[A-Za-z]{2,24}$/;
  let signupDialog;
  function openSignup(reason = '') {
    if (serverMode()) { window.museAccount.open('signup'); return; }
    if (hasSession()) { renderAccount(); return; }
    if (!signupDialog) {
      signupDialog = el('dialog', { class: 'ms-dialog ms-signup', 'aria-labelledby': 'msSignupTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => signupDialog.close());
      signupDialog.appendChild(close);
      signupDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Demo profile · this browser only'));
      signupDialog.appendChild(el('h2', { id: 'msSignupTitle' }, 'Try a demo profile'));
      signupDialog.appendChild(el('p', { class: 'ms-signup-reason' }));
      const form = el('form', { class: 'ms-signup-form', novalidate: '' });
      form.appendChild(el('label', { for: 'msSignupEmail' }, 'Email'));
      form.appendChild(el('input', { id: 'msSignupEmail', type: 'email', autocomplete: 'email', required: '', maxlength: '254', placeholder: 'you@yourshop.com' }));
      form.appendChild(el('label', { for: 'msSignupName' }, 'Shop or name (optional)'));
      form.appendChild(el('input', { id: 'msSignupName', type: 'text', autocomplete: 'organization', maxlength: '80', placeholder: 'Art of Sarabjit Singh' }));
      form.appendChild(el('p', { class: 'ms-signup-error', role: 'alert' }));
      form.appendChild(el('button', { type: 'submit', class: 'ms-primary' }, 'Create demo profile'));
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const email = form.querySelector('#msSignupEmail').value.trim().toLowerCase();
        const name = form.querySelector('#msSignupName').value.trim().replace(/\s+/g, ' ').slice(0, 80);
        if (!EMAIL_RE.test(email)) { form.querySelector('.ms-signup-error').textContent = 'Enter a valid email address.'; form.querySelector('#msSignupEmail').focus(); return; }
        createAccount(email, name);
        signupDialog.close();
      });
      signupDialog.appendChild(form);
      const demo = el('button', { type: 'button', class: 'ms-link ms-demo-user' }, 'Or continue as the demo user (Art of Sarabjit Singh) →');
      demo.addEventListener('click', () => { createAccount('demo@artofsarabjitsingh.example', 'Art of Sarabjit Singh'); signupDialog.close(); });
      signupDialog.appendChild(demo);
      signupDialog.appendChild(el('p', { class: 'ms-muted' }, 'Demo mode: your account is saved in this browser and your runs are counted on the server. No email is sent and no password is stored.'));
      signupDialog.addEventListener('click', (event) => { if (event.target === signupDialog) signupDialog.close(); });
      document.body.appendChild(signupDialog);
    }
    const reasonNode = signupDialog.querySelector('.ms-signup-reason');
    reasonNode.textContent = reason || 'Analyze competitors, create ready-to-post ads and get ranked next moves.';
    signupDialog.querySelector('.ms-signup-error').textContent = '';
    if (typeof signupDialog.showModal === 'function') signupDialog.showModal(); else signupDialog.setAttribute('open', '');
    setTimeout(() => signupDialog.querySelector('#msSignupEmail')?.focus(), 30);
  }
  function createAccount(email, name) {
    const existing = store.get(`${CREDIT_KEY}:${email}`);
    store.set(ACCOUNT_KEY, JSON.stringify({ email, name, created: new Date().toISOString(), purchases: [] }));
    credits = loadCredits();
    if (existing === null && !serverCredits) { credits = START_CREDITS; saveCredits(); }
    if (serverCredits) syncCredits();
    renderAccount();
    renderCredits(true);
    toast(existing === null ? `Welcome${name ? `, ${name}` : ''}! ${credits} free runs are ready.` : `Welcome back! ${credits} runs left.`);
    window.dispatchEvent(new CustomEvent('muse:demo-account', { detail: { email } }));
  }
  function signOut() {
    store.remove(ACCOUNT_KEY);
    credits = loadCredits();
    renderAccount();
    toast('Signed out. Your saved demo results stay in this browser.');
    window.dispatchEvent(new CustomEvent('muse:demo-account', { detail: { email: null } }));
  }
  let accountSlot;
  function renderAccount() {
    if (serverMode() || !accountSlot) return;
    const account = readAccount();
    accountSlot.replaceChildren();
    if (pill) pill.hidden = !account;
    if (!account) {
      const btn = el('button', { type: 'button', class: 'ms-primary ms-small ms-signup-btn' }, 'Try demo profile');
      btn.addEventListener('click', () => openSignup());
      accountSlot.appendChild(btn);
      return;
    }
    const chip = el('button', { type: 'button', class: 'ms-account-chip', 'aria-haspopup': 'menu', 'aria-expanded': 'false' });
    chip.appendChild(el('span', { class: 'ms-account-initial', 'aria-hidden': 'true' }, (account.name || account.email).trim().charAt(0).toUpperCase()));
    chip.appendChild(el('span', { class: 'ms-account-label' }, account.name || account.email));
    const queued = Object.values(readActions()).filter((a) => a.status === 'accepted').length;
    if (queued) chip.appendChild(el('span', { class: 'ms-account-count', title: 'Accepted actions' }, String(queued)));
    const menu = el('div', { class: 'ms-account-menu', hidden: '' });
    menu.appendChild(el('p', { class: 'ms-muted' }, `Signed in as ${account.email} (demo account)`));
    const actions = el('button', { type: 'button', class: 'ms-link' }, `My actions (${queued}) →`);
    actions.addEventListener('click', () => { menu.hidden = true; openActions(); });
    const plans = el('button', { type: 'button', class: 'ms-link' }, 'Get more runs →');
    plans.addEventListener('click', () => { menu.hidden = true; openPricing(); });
    const out = el('button', { type: 'button', class: 'ms-link ms-signout-link' }, 'Sign out');
    out.addEventListener('click', () => { menu.hidden = true; signOut(); });
    menu.append(actions, plans, out);
    chip.addEventListener('click', (event) => { event.stopPropagation(); menu.hidden = !menu.hidden; chip.setAttribute('aria-expanded', String(!menu.hidden)); });
    document.addEventListener('click', (event) => { if (!accountSlot.contains(event.target)) menu.hidden = true; });
    accountSlot.append(chip, menu);
  }
  function syncServerSession() {
    // Server accounts (when configured) own sign-in and count runs on the server.
    if (!serverMode()) return;
    if (pill) pill.hidden = true;
    if (accountSlot) accountSlot.replaceChildren();
    removeGates();
  }
  function mountSession() {
    const header = document.querySelector('header.topbar') || document.querySelector('body > header');
    if (!header) return;
    accountSlot = el('div', { class: 'ms-account' });
    if (pill?.parentNode) pill.insertAdjacentElement('afterend', accountSlot); else header.appendChild(accountSlot);
    renderAccount();
    syncServerSession();
    window.addEventListener('muse:account-change', () => { syncServerSession(); renderAccount(); });
  }

  // ---------- Recommendation triage: accept, dismiss, archive ----------
  const ACTIONS_KEY = 'muse.actions';
  const readActions = () => { try { const v = JSON.parse(store.get(ACTIONS_KEY) || '{}'); return v && typeof v === 'object' ? v : {}; } catch { return {}; } };
  const writeActions = (v) => store.set(ACTIONS_KEY, JSON.stringify(v));
  const actionId = (text) => { let h = 0; for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) | 0; return `a${(h >>> 0).toString(36)}`; };
  const TRIAGE_SELECTORS = ['.jr-recos > li', '#insightsContainer > .finding-item', '.try-next li', '#msBrief .ms-move', '.ms-digest-recos > li'];
  function itemTitle(item) {
    const head = item.querySelector('strong:not(.ms-match-tag)');
    return (head?.textContent || item.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  }
  function itemLink(item) {
    const link = item.querySelector('a[href]');
    return link ? link.getAttribute('href') : '';
  }
  // Relative app links and https only; anything else (javascript:, data:, //host) is dropped.
  const safeHref = (href, fallback = '') => (typeof href === 'string' && /^(\/(?!\/)|https:\/\/)/.test(href) ? href : fallback);
  function setStatus(item, status, { note, silent = false } = {}) {
    const id = item.dataset.actionId;
    const all = readActions();
    const previous = all[id] ? { ...all[id] } : null;
    if (status) {
      all[id] = { ...(previous || {}), status, title: itemTitle(item), href: itemLink(item), page: location.pathname, at: new Date().toISOString() };
      if (note !== undefined) all[id].note = note;
    } else delete all[id];
    writeActions(all);
    actionsChanged();
    if (!status || silent) return;
    const labels = { accepted: 'Added to My actions', dismissed: 'Dismissed', archived: 'Archived' };
    const undo = status === 'dismissed' || status === 'archived'
      ? { label: 'Undo', onClick: () => { const v = readActions(); if (previous) v[id] = previous; else delete v[id]; writeActions(v); actionsChanged(); } }
      : null;
    toast(`${labels[status]} · ${itemTitle(item).slice(0, 48)}`, '', undo);
  }
  function applyStatus(item) {
    const entry = readActions()[item.dataset.actionId];
    const state = entry?.status || '';
    item.classList.toggle('ms-accepted', state === 'accepted');
    item.hidden = state === 'dismissed' || state === 'archived';
    const accept = item.querySelector('.ms-triage-accept');
    if (accept) { accept.textContent = state === 'accepted' ? '✓ In My actions' : '✓ Accept'; accept.setAttribute('aria-pressed', String(state === 'accepted')); }
    let noteLine = item.querySelector('.ms-adjust-note');
    if (state && entry?.note) {
      if (!noteLine) { noteLine = el('p', { class: 'ms-adjust-note' }); item.querySelector('.ms-triage')?.insertAdjacentElement('beforebegin', noteLine); }
      noteLine.textContent = `Your tweak: ${entry.note}`;
    } else noteLine?.remove();
  }
  // Adjust: an inline note on the idea. It is saved with the action; no model call, no run.
  function toggleAdjust(item, button) {
    const open = item.querySelector('.ms-adjust');
    if (open) { open.remove(); button.setAttribute('aria-expanded', 'false'); return; }
    const id = item.dataset.actionId;
    const inputId = `msAdjust-${id}`;
    const form = el('form', { class: 'ms-adjust' });
    form.appendChild(el('label', { for: inputId }, 'How should this idea change for you?'));
    const row = el('div', { class: 'ms-adjust-row' });
    const input = el('input', { id: inputId, maxlength: '140', autocomplete: 'off', placeholder: 'e.g. Use my Abstracts series instead' });
    input.value = readActions()[id]?.note || '';
    const save = el('button', { type: 'submit', class: 'ms-primary ms-small' }, 'Save tweak');
    const cancel = el('button', { type: 'button', class: 'ms-secondary ms-small' }, 'Cancel');
    row.append(input, save, cancel);
    form.append(row, el('p', { class: 'ms-muted' }, 'Saved with this idea in My actions on this device. No run is used.'));
    const close = () => { form.remove(); button.setAttribute('aria-expanded', 'false'); button.focus(); };
    cancel.addEventListener('click', close);
    form.addEventListener('keydown', (event) => { if (event.key === 'Escape') { event.stopPropagation(); close(); } });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const note = input.value.trim().replace(/\s+/g, ' ').slice(0, 140);
      if (!note) { input.focus(); return; }
      setStatus(item, 'accepted', { note, silent: true });
      close();
      toast('Tweak saved · added to My actions');
    });
    item.querySelector('.ms-triage')?.insertAdjacentElement('afterend', form);
    button.setAttribute('aria-expanded', 'true');
    input.focus();
  }
  function addTriage(item) {
    if (item.querySelector('.ms-triage')) return;
    item.dataset.actionId = actionId(itemTitle(item));
    const bar = el('div', { class: 'ms-triage', role: 'group', 'aria-label': 'Recommendation actions' });
    const accept = el('button', { type: 'button', class: 'ms-triage-accept' }, '✓ Accept');
    const dismiss = el('button', { type: 'button', class: 'ms-triage-dismiss' }, '✕ Dismiss');
    const archive = el('button', { type: 'button', class: 'ms-triage-archive' }, '⤓ Archive');
    const adjust = el('button', { type: 'button', class: 'ms-triage-adjust', 'aria-expanded': 'false' }, '✎ Adjust');
    accept.addEventListener('click', () => setStatus(item, readActions()[item.dataset.actionId]?.status === 'accepted' ? '' : 'accepted'));
    dismiss.addEventListener('click', () => setStatus(item, 'dismissed'));
    archive.addEventListener('click', () => setStatus(item, 'archived'));
    adjust.addEventListener('click', () => toggleAdjust(item, adjust));
    bar.append(accept, dismiss, archive, adjust);
    item.appendChild(bar);
    applyStatus(item);
  }
  function hiddenCountFor(list) {
    const all = readActions();
    return [...list.children].filter((c) => c.dataset?.actionId && all[c.dataset.actionId]?.status === 'dismissed').length;
  }
  function addRestore(list) {
    let restore = list.nextElementSibling?.classList?.contains('ms-restore') ? list.nextElementSibling : null;
    const n = hiddenCountFor(list);
    if (!n) { restore?.remove(); return; }
    if (!restore) {
      restore = el('button', { type: 'button', class: 'ms-link ms-restore' });
      restore.addEventListener('click', () => {
        const all = readActions();
        [...list.children].forEach((c) => { const st = all[c.dataset?.actionId]?.status; if (st === 'dismissed') delete all[c.dataset.actionId]; });
        writeActions(all);
        actionsChanged();
      });
      list.insertAdjacentElement('afterend', restore);
    }
    restore.textContent = `Show ${n} dismissed ↺`;
  }
  function refreshTriage() {
    for (const sel of TRIAGE_SELECTORS) document.querySelectorAll(sel).forEach(addTriage);
    new Set([...document.querySelectorAll('[data-action-id]')].map((i) => i.parentElement)).forEach((list) => list && addRestore(list));
  }
  // One place that re-syncs every view of the queue after any change.
  function actionsChanged() {
    document.querySelectorAll('[data-action-id]').forEach(applyStatus);
    refreshTriage();
    renderAccount();
    renderMyActions();
    if (actionsDialog?.open) fillActions();
    renderNotifications();
  }
  function mountTriage() {
    refreshTriage();
    const insights = document.getElementById('insightsContainer');
    if (insights && typeof MutationObserver !== 'undefined') new MutationObserver(() => setTimeout(refreshTriage, 0)).observe(insights, { childList: true });
    window.addEventListener('muse:brief-ready', refreshTriage);
  }
  function actionRow(id, entry, status) {
    const li = el('li', {});
    li.appendChild(el('strong', {}, entry.title || 'Saved idea'));
    if (entry.note) li.appendChild(el('p', { class: 'ms-actions-note' }, `Your tweak: ${entry.note}`));
    const row = el('div', { class: 'ms-actions-row' });
    const href = safeHref(entry.href);
    if (href && status === 'accepted') {
      const external = href.startsWith('https://');
      row.appendChild(el('a', { href, class: 'ms-link', ...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {}) }, external ? 'Do it ↗' : 'Do it →'));
    }
    const next = { accepted: ['Mark done', 'done'], done: ['Reopen', 'accepted'], archived: ['Restore', 'accepted'] }[status];
    const move = el('button', { type: 'button', class: 'ms-link' }, next[0]);
    move.addEventListener('click', () => { const v = readActions(); if (v[id]) v[id] = { ...v[id], status: next[1] }; writeActions(v); actionsChanged(); });
    const remove = el('button', { type: 'button', class: 'ms-link ms-remove' }, 'Remove');
    remove.addEventListener('click', () => { const v = readActions(); delete v[id]; writeActions(v); actionsChanged(); });
    row.append(move, remove);
    li.appendChild(row);
    return li;
  }
  let actionsDialog;
  function fillActions() {
    const body = actionsDialog.querySelector('.ms-actions-body');
    body.replaceChildren();
    const all = readActions();
    const groups = [['accepted', 'To do'], ['done', 'Done'], ['archived', 'Archived']];
    let any = false;
    for (const [status, heading] of groups) {
      const items = Object.entries(all).filter(([, a]) => a.status === status);
      if (!items.length) continue;
      any = true;
      body.appendChild(el('h3', {}, `${heading} (${items.length})`));
      const list = el('ul', { class: 'ms-actions-list' });
      for (const [id, a] of items) list.appendChild(actionRow(id, a, status));
      body.appendChild(list);
    }
    if (!any) body.appendChild(el('p', { class: 'ms-muted' }, 'Accept a recommendation to add it here. Dismissed ideas are hidden; archived ones are kept here for later.'));
  }
  function openActions() {
    if (!actionsDialog) {
      actionsDialog = el('dialog', { class: 'ms-dialog ms-actions', 'aria-labelledby': 'msActionsTitle' });
      const close = el('button', { type: 'button', class: 'ms-close', 'aria-label': 'Close' }, '×');
      close.addEventListener('click', () => actionsDialog.close());
      actionsDialog.appendChild(close);
      actionsDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Your queue'));
      actionsDialog.appendChild(el('h2', { id: 'msActionsTitle' }, 'My actions'));
      actionsDialog.appendChild(el('div', { class: 'ms-actions-body' }));
      actionsDialog.addEventListener('click', (event) => { if (event.target === actionsDialog) actionsDialog.close(); });
      document.body.appendChild(actionsDialog);
    }
    fillActions();
    if (actionsDialog.open) return;
    if (typeof actionsDialog.showModal === 'function') actionsDialog.showModal(); else actionsDialog.setAttribute('open', '');
  }
  // Inline, collapsible queue above the portal's research stage (visible on every stage).
  let myActionsBox;
  function mountMyActions() {
    const anchor = document.getElementById('loop-research');
    if (!anchor || document.getElementById('myActions')) return;
    myActionsBox = el('details', { class: 'ms-myactions', id: 'myActions' });
    const summary = el('summary');
    summary.append(el('span', { class: 'ms-myactions-title' }, 'My actions'), el('span', { class: 'ms-myactions-count' }), el('span', { class: 'ms-myactions-hint' }));
    myActionsBox.append(summary, el('div', { class: 'ms-myactions-body' }));
    anchor.insertAdjacentElement('beforebegin', myActionsBox);
    renderMyActions();
    if (Object.values(readActions()).some((a) => a.status === 'accepted')) myActionsBox.open = true;
  }
  function renderMyActions() {
    if (!myActionsBox) return;
    const entries = Object.entries(readActions());
    const todo = entries.filter(([, a]) => a.status === 'accepted');
    const done = entries.filter(([, a]) => a.status === 'done').length;
    const archived = entries.filter(([, a]) => a.status === 'archived').length;
    const count = myActionsBox.querySelector('.ms-myactions-count');
    count.textContent = String(todo.length);
    count.hidden = !todo.length;
    myActionsBox.querySelector('.ms-myactions-hint').textContent = todo.length ? 'Saved on this device' : 'Accept an idea to queue it here';
    const body = myActionsBox.querySelector('.ms-myactions-body');
    body.replaceChildren();
    if (todo.length) {
      const list = el('ul', { class: 'ms-actions-list' });
      todo.forEach(([id, a]) => list.appendChild(actionRow(id, a, 'accepted')));
      body.appendChild(list);
    } else {
      body.appendChild(el('p', { class: 'ms-muted' }, 'Use ✓ Accept on a ranked idea in Improve (or in the full workspace) to add it here. Dismissed ideas are hidden; archived ones wait in the full list.'));
    }
    if (done || archived) {
      const foot = el('p', { class: 'ms-myactions-foot' }, `${done} done · ${archived} archived · `);
      const all = el('button', { type: 'button', class: 'ms-link' }, 'See full list →');
      all.addEventListener('click', openActions);
      foot.appendChild(all);
      body.appendChild(foot);
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
    { name: 'SikhiArt.com', where: 'Own shop · 300 pages', status: 'new', badge: '2 new listings', note: '2 new listings in the 30 days before Nov 3: new editions of Mai Bhago ji and Hari Singh Nalwa' },
    { name: 'Gurinderpreet Kaur', where: 'Fine Art America · 70 listings', status: 'first', badge: 'First check', note: 'Prints $14–$50. First check, so nothing to compare yet' },
    { name: 'Manjot Singh Sachdeva', where: 'Fine Art America / Pixels · 105 listings', status: 'first', badge: 'First check', note: 'Prints $14–$24. First check, so nothing to compare yet' },
    { name: 'Gurdish Pannu', where: 'Saatchi Art · originals', status: 'first', badge: 'First check', note: 'Originals, no USD prices listed. First check' },
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
    titleBox.appendChild(el('p', { class: 'ms-brief-plan' }, 'Built once a day from your watchlist, the competitor monitor and campaign trends. No Muse credit is used to read it.'));
    const meta = el('p', { class: 'ms-brief-meta' });
    meta.appendChild(el('span', { class: 'ms-dot', 'aria-hidden': 'true' }));
    meta.appendChild(document.createTextNode('Watchlist: 4 competitors · 6 shop pages · last checked Nov 3 · social accounts not checked yet'));
    titleBox.appendChild(meta);
    const recheck = el('button', { type: 'button', class: 'ms-secondary ms-small', title: 'Check competitors’ public pages and rebuild today’s brief · 1 run' }, 'Re-check now');
    const toggle = el('button', { type: 'button', class: 'ms-link ms-brief-toggle', 'aria-expanded': 'true', 'aria-controls': 'msBriefBody' }, 'Hide');
    const actions = el('div', { class: 'ms-brief-actions' });
    actions.append(recheck, toggle);
    head.append(titleBox, actions);
    const body = el('div', { class: 'ms-brief-body', id: 'msBriefBody' });
    const list = el('ul', { class: 'ms-watch' });
    const CHIP = { new: 'New', first: 'First check', fresh: 'Fresh Muse brief', changed: 'Changed' };
    const renderItems = (items) => {
      list.replaceChildren();
      for (const item of items) {
        const status = CHIP[item.status] ? item.status : 'first';
        const li = el('li', { class: status });
        li.appendChild(el('span', { class: `ms-chip ${status}` }, CHIP[status]));
        li.appendChild(el('strong', {}, String(item.name || '')));
        li.appendChild(el('span', { class: 'ms-where' }, String(item.where || '')));
        li.appendChild(el('span', { class: 'ms-note' }, String(item.note || '')));
        list.appendChild(li);
      }
    };
    renderItems(WATCH);
    const statusLine = el('p', { class: 'ms-brief-status', role: 'status', 'aria-live': 'polite' }, 'Loading today’s brief…');
    const retry = el('button', { type: 'button', class: 'ms-link ms-brief-retry', hidden: '' }, 'Try again');
    const statusRow = el('div', { class: 'ms-brief-statusrow' });
    statusRow.append(statusLine, retry);
    const sourceNote = el('p', { class: 'ms-muted ms-brief-source' }, 'From saved public snapshots captured Nov 3. Muse checks again when you run a re-check; it does not watch continuously.');
    // Focus of the day (server-ranked; the saved snapshot move is shown until the brief loads).
    const move = el('div', { class: 'ms-move' });
    const moveText = el('div');
    const moveChip = el('span', { class: 'ms-chip high' }, 'Focus of the day · high impact');
    const moveTitle = el('strong', {}, 'Feature your Empowering Women series');
    const moveReason = el('span', { class: 'ms-note' }, 'SikhiArt keeps adding warrior and guru editions but has no group for women’s stories.');
    moveText.append(moveChip, moveTitle, moveReason);
    const go = el('a', { class: 'ms-primary ms-small', href: '/create?goal=story' }, 'Make this post →');
    move.append(moveText, go);
    const safeHref = (href) => (typeof href === 'string' && /^\/(?!\/)/.test(href) ? href : '/create');
    const goLabel = (href) => (href.startsWith('/create') ? 'Make this post →' : 'Open →');
    const columns = el('div', { class: 'ms-brief-columns' });
    const overnightBox = el('section', { class: 'ms-brief-card', 'aria-label': 'Overnight competitor changes' });
    const actionsBox = el('section', { class: 'ms-brief-card', 'aria-label': 'Top 3 actions' });
    const trendsBox = el('section', { class: 'ms-brief-card', 'aria-label': 'Performance trends' });
    columns.append(actionsBox, overnightBox, trendsBox);
    const weekly = el('p', { class: 'ms-muted ms-weekly' });
    const card = (box, title, rows, empty, note = '') => {
      box.replaceChildren(el('h3', {}, title));
      if (!rows.length) box.appendChild(el('p', { class: 'ms-muted' }, empty));
      else { const ul = el('ul', {}); rows.forEach((row) => ul.appendChild(row)); box.appendChild(ul); }
      if (note) box.appendChild(el('p', { class: 'ms-muted ms-card-note' }, note));
    };
    const renderBrief = (brief) => {
      if (Array.isArray(brief.items) && brief.items.length) renderItems(brief.items);
      const focus = brief.focus || brief.move;
      if (focus?.title) {
        moveChip.textContent = `Focus of the day · ${focus.impact || 'high'} impact`;
        moveTitle.textContent = String(focus.title);
        moveReason.textContent = String(focus.reason || '');
        const href = safeHref(focus.href);
        go.setAttribute('href', href);
        go.textContent = goLabel(href);
      }
      const actions = Array.isArray(brief.action_items) ? brief.action_items.slice(0, 3) : [];
      card(actionsBox, 'Top 3 actions', actions.map((item, index) => {
        const li = el('li', { class: `ms-action ${item.impact || ''}` });
        const link = el('a', { href: safeHref(item.href) }, `${index + 1}. ${String(item.title || '')}`);
        li.append(link, el('span', { class: 'ms-note' }, String(item.reason || '')));
        if (item.source) li.appendChild(el('span', { class: 'ms-where' }, String(item.source)));
        return li;
      }), 'No actions today.');
      const changes = Array.isArray(brief.overnight_changes) ? brief.overnight_changes : [];
      card(overnightBox, 'Overnight changes', changes.map((change) => {
        const li = el('li', { class: `ms-change ${change.kind || ''}` });
        li.appendChild(el('span', { class: 'ms-note' }, String(change.text || '')));
        return li;
      }), String(brief.overnight_note || 'No competitor changes logged overnight.'), changes.length ? String(brief.overnight_note || '') : '');
      const trends = Array.isArray(brief.trends) ? brief.trends : [];
      card(trendsBox, 'Performance trends', trends.map((trend) => {
        const arrow = trend.direction === 'up' ? '▲' : trend.direction === 'down' ? '▼' : '•';
        const tone = trend.good === true ? 'good' : trend.good === false ? 'bad' : '';
        const li = el('li', { class: `ms-trend ${tone}` });
        li.append(el('strong', {}, `${arrow} ${String(trend.value || '')}`), el('span', {}, ` ${String(trend.label || '')}`));
        if (trend.note) li.appendChild(el('span', { class: 'ms-note' }, String(trend.note)));
        return li;
      }), 'Add campaign data to see trends.', String(brief.trends_source || ''));
      if (brief.overnight_note) meta.lastChild.textContent = `Watchlist: 4 competitors · ${brief.overnight_note}`;
      const built = brief.generated_at ? new Date(brief.generated_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : '';
      sourceNote.textContent = `${String(brief.source || '')}${built ? ` Generated ${built}; cached for today.` : ''}`;
    };
    const setLoading = (loading, message = '') => {
      section.classList.toggle('ms-loading', loading);
      body.setAttribute('aria-busy', String(loading));
      statusLine.textContent = message;
      statusLine.hidden = !message;
    };
    const loadBrief = async (refresh = false) => {
      setLoading(true, refresh ? 'Rebuilding today’s brief…' : 'Loading today’s brief…');
      retry.hidden = true;
      try {
        const response = await museFetch(`/api/v1/daily-brief${refresh ? '?refresh=true' : ''}`, {}, { retries: 2, timeoutMs: 15000 });
        if (!response.ok) throw new Error(await errorMessage(response, 'Could not load today’s brief.'));
        renderBrief(await response.json());
        setLoading(false);
        return true;
      } catch (error) {
        setLoading(false, `${error.message || 'Could not load today’s brief.'} Showing the saved brief.`);
        retry.hidden = false;
        return false;
      }
    };
    const loadWeekly = async () => {
      try {
        const response = await museFetch('/api/v1/weekly-digest', {}, { retries: 1, timeoutMs: 10000 });
        if (!response.ok) return;
        const digest = await response.json();
        const first = Array.isArray(digest.highlights) && digest.highlights[0] ? ` Biggest: ${digest.highlights[0]}.` : '';
        weekly.textContent = digest.checks ? `This week: ${digest.total_changes} competitor change(s) across ${digest.checks} check(s).${first}` : String(digest.note || '');
      } catch { /* the weekly line is optional */ }
    };
    retry.addEventListener('click', () => { loadBrief(false); loadWeekly(); });
    recheck.addEventListener('click', async () => {
      if (!requireRun('Brief re-check')) return;
      recheck.disabled = true;
      recheck.textContent = 'Checking…';
      let monitorNote = '';
      const monitorRun = (async () => {
        try {
          const response = await museFetch('/api/v1/monitor', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }, { safe: false, timeoutMs: 170000 });
          if (!response.ok) monitorNote = await errorMessage(response, 'The competitor check could not run.');
          else if (response.headers.get('X-Muse-Monitor') === 'cooldown') monitorNote = 'Competitors were checked recently, so the latest check was reused.';
        } catch (error) { monitorNote = error.message; }
      })();
      await Promise.all([monitorRun, progress('Re-checking your watchlist', ['Reading each competitor’s public pages', 'Comparing with the last snapshot', 'Ranking today’s actions'], 2400)]);
      const ok = await loadBrief(true);
      loadWeekly();
      recheck.disabled = false;
      recheck.textContent = 'Re-check now';
      toast(ok ? (monitorNote || 'Brief rebuilt with the latest competitor check') : 'Could not rebuild the brief; showing the saved one.', ok && !monitorNote ? '' : 'warn');
    });
    loadBrief(false);
    loadWeekly();
    body.append(statusRow, move, columns, list, weekly);
    body.appendChild(sourceNote);
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


  // ---------- Shared signals: monitor log, weekly digest, daily brief ----------
  // All three are free GETs: none crawls or calls a model, so reading them never uses a run.
  let signals = null;
  let signalsPromise;
  function loadSignals() {
    if (!signalsPromise) {
      const get = async (url) => {
        try { const response = await museFetch(url, {}, { retries: 1, timeoutMs: 10000 }); return response.ok ? await response.json() : null; } catch { return null; }
      };
      signalsPromise = Promise.all([get('/api/v1/monitor?limit=1'), get('/api/v1/weekly-digest'), get('/api/v1/daily-brief')])
        .then(([log, digest, brief]) => ({ run: Array.isArray(log?.runs) ? log.runs[0] || null : null, log, digest, brief }));
    }
    return signalsPromise;
  }
  const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
  const fmtWhen = (iso) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); };
  const KIND_BADGE = { new_listing: ['new', 'new listing'], price_change: ['price', 'price change'], removed_listing: ['removed', 'removed listing'], ad_new: ['ad', 'new ad'], ad_stopped: ['ad', 'stopped ad'] };
  // [[tone, label], ...] for one competitor's change counts, biggest first.
  function changeBadges(counts) {
    return Object.entries(counts || {})
      .filter(([kind, n]) => KIND_BADGE[kind] && Number(n) > 0)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .map(([kind, n]) => [KIND_BADGE[kind][0], plural(Number(n), KIND_BADGE[kind][1])]);
  }
  // One watched shop: the latest monitor check when there is one, else the saved Nov 3 snapshot.
  function competitorStatus(name, run) {
    const check = Array.isArray(run?.competitors) ? run.competitors.find((c) => c?.name === name) : null;
    if (check) {
      const badges = check.status === 'error' ? [['error', 'Couldn’t check']] : changeBadges(check.counts);
      if (!badges.length) badges.push(['none', 'No changes']);
      const note = check.error || (check.compared_with ? `Compared with ${check.compared_with}` : '');
      return { badges, when: `Checked ${fmtWhen(run.checked_at)}`, source: 'monitor', note };
    }
    const saved = WATCH.find((w) => w.name === name);
    if (saved) return { badges: [[saved.status === 'new' ? 'new' : 'first', saved.badge]], when: 'Saved snapshot · Nov 3', source: 'snapshot', note: saved.note };
    return { badges: [['added', 'Added by you']], when: 'Not checked yet', source: 'added', note: '' };
  }

  // ---------- Portal watchlist: alerts toggle, last checked, change badges ----------
  // Pausing is a per-device alert preference; the scheduled monitor still checks every shop.
  const PAUSE_KEY = 'muse.watchPaused';
  const readPaused = () => { try { const v = JSON.parse(store.get(PAUSE_KEY) || '{}'); return v && typeof v === 'object' ? v : {}; } catch { return {}; } };
  function setPaused(name, paused) { const v = readPaused(); if (paused) v[name] = true; else delete v[name]; store.set(PAUSE_KEY, JSON.stringify(v)); }
  const sellerPainters = new Map();
  function decorateSeller(li) {
    if (li.querySelector('.ms-watchmeta')) return;
    const info = li.querySelector(':scope > div');
    const name = (li.querySelector('strong, a')?.textContent || '').trim();
    if (!info || !name) return;
    li.querySelector('.jr-new')?.remove();
    const meta = el('div', { class: 'ms-watchmeta' });
    const toggle = el('label', { class: 'toggle-switch', title: 'Pausing mutes this shop’s alerts on this device. Scheduled checks still read its public pages.' });
    const input = el('input', { type: 'checkbox', 'aria-label': `Alerts for ${name}` });
    toggle.append(input, el('span', { class: 'slider', 'aria-hidden': 'true' }));
    const state = el('span', { class: 'ms-watch-state' });
    const when = el('span', { class: 'ms-watch-time' });
    const badges = el('span', { class: 'ms-watch-badges' });
    meta.append(toggle, state, when, badges);
    info.appendChild(meta);
    const paint = () => {
      const paused = !!readPaused()[name];
      input.checked = !paused;
      li.classList.toggle('ms-paused', paused);
      state.textContent = paused ? 'Paused' : 'Active';
      const status = competitorStatus(name, signals?.run);
      when.textContent = status.when;
      badges.title = status.note;
      badges.replaceChildren(...status.badges.map(([tone, label]) => el('span', { class: `ms-badge ${tone}` }, label)));
    };
    input.addEventListener('change', () => {
      setPaused(name, !input.checked);
      paint();
      toast(input.checked ? `Alerts on · ${name}` : `Alerts paused · ${name}`);
      renderNotifications();
    });
    sellerPainters.set(li, paint);
    paint();
  }
  function mountWatchlist() {
    const list = document.getElementById('sellerList');
    if (!list) return;
    const decorateAll = () => list.querySelectorAll(':scope > .jr-seller').forEach(decorateSeller);
    decorateAll();
    if (typeof MutationObserver !== 'undefined') new MutationObserver(decorateAll).observe(list, { childList: true });
    loadSignals().then((loaded) => {
      signals = loaded;
      sellerPainters.forEach((paint) => paint());
      const line = document.querySelector('.jr-watch');
      if (loaded.run && line) {
        for (const node of line.childNodes) {
          if (node.nodeType === 3 && /last checked/.test(node.textContent)) node.textContent = node.textContent.replace(/last checked .*$/, `last checked ${fmtWhen(loaded.run.checked_at)} `);
        }
      }
    });
  }

  // ---------- Phone header: one compact row plus a menu for everything else ----------
  // Only headers marked .ms-topbar (portal, digest) collapse; CSS decides which items stay in the row.
  let closeMobileNav = () => {};
  // ---------- Hero and nav: plans and sign-up are always one click away ----------
  function updateHeroCtas() {
    const primary = document.querySelector('[data-hero-primary]');
    const accountStep = document.querySelector('[data-hero-account]');
    if (!primary) return;
    const snap = serverSnapshot();
    const signedOut = serverMode() && !snap?.user;
    if (signedOut) {
      primary.textContent = 'Create free account →';
      primary.setAttribute('href', '#create-account');
      primary.dataset.action = 'signup';
    } else {
      primary.textContent = 'Make today’s post →';
      primary.setAttribute('href', '/today');
      delete primary.dataset.action;
    }
    const subtitle = document.querySelector('[data-hero-subtitle]');
    if (subtitle && !serverMode()) subtitle.textContent = 'Prepare a post, see what similar sellers do, and get your next best move. Everything here runs on saved Muse results, free.';
    if (accountStep) {
      const [, strong, detail] = accountStep.children;
      if (!serverMode()) { strong.textContent = 'Try a demo profile'; detail.textContent = 'Saved results, in this browser'; }
      else if (snap?.user && snap.usage && Number.isFinite(snap.usage.remaining)) { strong.textContent = `${Math.max(0, snap.usage.remaining)} of ${snap.usage.limit} runs left`; detail.textContent = 'Your account'; }
      else { strong.textContent = '3 live Muse runs'; detail.textContent = 'On your own products'; }
    }
  }
  function mountPlanLinks() {
    document.addEventListener('click', (event) => {
      const plans = event.target.closest('[data-open-pricing]');
      if (plans) { event.preventDefault(); openPricing(); return; }
      const primary = event.target.closest('[data-hero-primary][data-action="signup"]');
      if (primary && window.museAccount?.open) { event.preventDefault(); window.museAccount.open('signup'); }
    });
    window.addEventListener('account-change', updateHeroCtas);
    updateHeroCtas();
  }

  function mountMobileNav() {
    const header = document.querySelector('header.ms-topbar');
    const right = header?.querySelector('.topbar-right');
    if (!header || !right || header.querySelector('.ms-menu-btn')) return;
    const button = el('button', { type: 'button', class: 'ms-menu-btn', 'aria-expanded': 'false', 'aria-label': 'Open menu' });
    button.appendChild(el('span', { class: 'ms-menu-icon', 'aria-hidden': 'true' }));
    right.appendChild(button);
    const setOpen = (open) => {
      header.classList.toggle('ms-nav-open', open);
      button.setAttribute('aria-expanded', String(open));
      button.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      if (open) toggleNotifications(false);
    };
    closeMobileNav = () => { if (header.classList.contains('ms-nav-open')) setOpen(false); };
    button.addEventListener('click', (event) => { event.stopPropagation(); setOpen(!header.classList.contains('ms-nav-open')); });
    document.addEventListener('click', (event) => { if (!header.contains(event.target)) closeMobileNav(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && header.classList.contains('ms-nav-open')) { setOpen(false); button.focus(); } });
    // Choosing something in the menu closes it (dialogs and links take over from there).
    header.addEventListener('click', (event) => { if (event.target.closest('.topbar-link, #openLocalEngineBtn, .workspace-btn, .ma-account-button')) closeMobileNav(); });
    window.matchMedia?.('(min-width: 641px)').addEventListener?.('change', (event) => { if (event.matches) closeMobileNav(); });
  }

  // ---------- Notifications: competitor changes, new ideas, weekly digest ----------
  const READ_KEY = 'muse.notifRead';
  const readSeen = () => { try { const v = JSON.parse(store.get(READ_KEY) || '[]'); return new Set(Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []); } catch { return new Set(); } };
  const writeSeen = (seen) => store.set(READ_KEY, JSON.stringify([...seen].slice(-200)));
  // Monday of the digest's week, so "digest ready" is one notification per week, not per day.
  const weekOf = (isoDate) => {
    const d = new Date(`${String(isoDate).slice(0, 10)}T00:00:00Z`);
    if (Number.isNaN(d.getTime())) return String(isoDate);
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  };
  // Pure: the notification list for loaded signals. Ids are stable so read state survives reloads.
  function notificationItems({ run = null, digest = null, brief = null } = {}, { paused = {}, actions = {} } = {}) {
    const items = [];
    if (run && Array.isArray(run.competitors)) {
      for (const check of run.competitors) {
        if (!check?.name || paused[check.name]) continue;
        const badges = changeBadges(check.counts);
        if (!badges.length) continue;
        const latest = Array.isArray(check.changes) && check.changes[0] ? String(check.changes[0].title || '') : '';
        items.push({ id: `change:${run.run_id}:${check.name}`, kind: 'change', label: 'Competitor change', title: `${check.name}: ${badges.map((b) => b[1]).join(', ')}`, body: latest ? `Latest: ${latest}` : '', when: fmtWhen(run.checked_at), href: '/#loop-research' });
      }
    } else {
      for (const w of WATCH) {
        if (w.status !== 'new' || paused[w.name]) continue;
        items.push({ id: `snapshot:2026-11-03:${w.name}`, kind: 'change', label: 'Competitor change', title: `${w.name}: ${w.badge}`, body: w.note, when: 'Saved snapshot · Nov 3', href: '/#loop-research' });
      }
    }
    const moves = Array.isArray(brief?.action_items) ? brief.action_items : [];
    for (const move of moves.slice(0, 3)) {
      const title = String(move?.title || '').trim();
      if (!title || actions[actionId(title)]) continue;
      items.push({ id: `idea:${actionId(title)}`, kind: 'idea', label: 'New recommendation', title, body: String(move.reason || ''), when: '', href: '/digest#digestRecos' });
    }
    if (digest?.week_end) {
      const checks = Number(digest.checks) || 0;
      const body = checks ? `${plural(Number(digest.total_changes) || 0, 'competitor change')} across ${plural(checks, 'check')}.` : 'This week’s competitor summary and strategy ideas.';
      items.push({ id: `digest:${weekOf(digest.week_end)}`, kind: 'digest', label: 'Weekly digest ready', title: 'Your weekly market digest is ready', body, when: '', href: '/digest' });
    }
    return items;
  }
  let bell = null;
  const currentNotifications = () => notificationItems(signals || {}, { paused: readPaused(), actions: readActions() });
  function toggleNotifications(force) {
    if (!bell) return;
    const open = typeof force === 'boolean' ? force : bell.menu.hidden;
    if (open) closeMobileNav();
    bell.menu.hidden = !open;
    bell.button.setAttribute('aria-expanded', String(open));
  }
  function markRead(id) {
    const seen = readSeen();
    seen.add(id);
    writeSeen(seen);
    renderNotifications();
  }
  function renderNotifications() {
    if (!bell || !signals) return;
    const items = currentNotifications();
    const seen = readSeen();
    const unread = items.filter((n) => !seen.has(n.id)).length;
    bell.badge.textContent = unread > 9 ? '9+' : String(unread);
    bell.badge.hidden = !unread;
    bell.button.setAttribute('aria-label', unread ? `Notifications, ${unread} unread` : 'Notifications');
    bell.markAll.hidden = !unread;
    bell.list.replaceChildren();
    if (!items.length) { bell.list.appendChild(el('li', { class: 'ms-notif-empty' }, 'You’re all caught up.')); return; }
    for (const n of items) {
      const li = el('li', { class: `ms-notif-item kind-${n.kind}${seen.has(n.id) ? '' : ' unread'}` });
      const link = el('a', { href: n.href, class: 'ms-notif-link' });
      link.appendChild(el('span', { class: 'ms-notif-kind' }, n.label));
      link.appendChild(el('strong', {}, n.title));
      if (n.body) link.appendChild(el('span', { class: 'ms-notif-body' }, n.body));
      if (n.when) link.appendChild(el('span', { class: 'ms-notif-when' }, n.when));
      link.addEventListener('click', () => { markRead(n.id); toggleNotifications(false); });
      li.appendChild(link);
      bell.list.appendChild(li);
    }
  }
  function mountNotifications() {
    const header = document.querySelector('header.topbar');
    if (!header || !(document.getElementById('journey') || document.getElementById('digest'))) return;
    const wrap = el('div', { class: 'ms-notif' });
    const button = el('button', { type: 'button', class: 'ms-bell', 'aria-haspopup': 'true', 'aria-expanded': 'false', 'aria-controls': 'msNotifMenu', 'aria-label': 'Notifications' });
    const badge = el('span', { class: 'ms-bell-badge', hidden: '' });
    button.append(el('span', { class: 'ms-bell-icon', 'aria-hidden': 'true' }, '🔔'), badge);
    const menu = el('div', { class: 'ms-notif-menu', id: 'msNotifMenu', hidden: '' });
    const head = el('div', { class: 'ms-notif-head' });
    const markAll = el('button', { type: 'button', class: 'ms-link' }, 'Mark all read');
    head.append(el('strong', {}, 'Notifications'), markAll);
    const list = el('ul', { class: 'ms-notif-list' });
    list.appendChild(el('li', { class: 'ms-notif-empty' }, 'Checking your watchlist…'));
    menu.append(head, list, el('p', { class: 'ms-muted ms-notif-foot' }, 'From your watchlist checks and daily brief. Reading these never uses a run.'));
    wrap.append(button, menu);
    bell = { wrap, button, badge, menu, list, markAll };
    button.addEventListener('click', (event) => { event.stopPropagation(); toggleNotifications(); });
    markAll.addEventListener('click', () => { const seen = readSeen(); currentNotifications().forEach((n) => seen.add(n.id)); writeSeen(seen); renderNotifications(); });
    document.addEventListener('click', (event) => { if (!wrap.contains(event.target)) toggleNotifications(false); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !menu.hidden) { toggleNotifications(false); button.focus(); } });
    if (pill?.parentNode) pill.insertAdjacentElement('afterend', wrap);
    else { const anchor = header.querySelector('.status-pill, .topbar-nav'); if (anchor) anchor.insertAdjacentElement('afterend', wrap); else header.appendChild(wrap); }
    loadSignals().then((loaded) => { signals = loaded; renderNotifications(); });
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
      if (!requireRun('Diagnostics re-run')) return;
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
      if (!requireRun('Refined analysis')) return;
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

  // ---------- Network Offline Banner ----------
  let offlineBannerNode = null;
  function setOfflineState(offline) {
    forcedOffline = Boolean(offline);
    updateOfflineBanner(forcedOffline);
  }
  function updateOfflineBanner(announceOnline = false) {
    const offline = isOffline();
    if (!offlineBannerNode && document.body) {
      offlineBannerNode = el(
        'div',
        {
          id: 'msOfflineBanner',
          class: 'ms-offline-banner',
          role: 'status',
          'aria-live': 'polite',
          hidden: '',
        },
        'You appear to be offline. Your work is saved on this device — reconnect to generate with Muse.'
      );
      document.body.prepend(offlineBannerNode);
    }
    if (!offlineBannerNode) return;
    if (offline) {
      offlineBannerNode.removeAttribute('hidden');
      offlineBannerNode.hidden = false;
    } else {
      offlineBannerNode.setAttribute('hidden', '');
      offlineBannerNode.hidden = true;
      if (announceOnline) toast('Back online. You can continue with Muse.');
    }
  }
  function mountOfflineBanner() {
    updateOfflineBanner(false);
    window.addEventListener('offline', () => updateOfflineBanner(false));
    window.addEventListener('online', () => { forcedOffline = false; updateOfflineBanner(true); });
  }

  // ---------- Universal Modal Focus Management & Keyboard Trap ----------
  const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';
  function focusableInside(dialog) {
    if (!dialog) return [];
    return [...dialog.querySelectorAll(FOCUSABLE_SELECTOR)].filter(
      (node) => !node.hidden && !node.closest('[hidden]') && node.getClientRects?.().length !== 0
    );
  }
  function bindDialogFocusReturn(dialog) {
    if (!dialog || dialog.__msFocusBound) return;
    dialog.__msFocusBound = true;
    dialog.addEventListener('close', () => {
      const opener = dialog.__msOpener;
      dialog.__msOpener = null;
      if (opener && typeof opener.focus === 'function' && document.contains(opener)) {
        try { opener.focus({ preventScroll: true }); } catch { try { opener.focus(); } catch {} }
      }
    });
  }
  function mountDialogAccessibility() {
    if (typeof HTMLDialogElement !== 'undefined' && HTMLDialogElement.prototype.showModal && !HTMLDialogElement.prototype.__msWrapped) {
      const origShowModal = HTMLDialogElement.prototype.showModal;
      const wrapped = function (...args) {
        if (!this.open) {
          this.__msOpener = document.activeElement;
        }
        this.setAttribute('aria-modal', 'true');
        bindDialogFocusReturn(this);
        const res = origShowModal.apply(this, args);
        queueMicrotask(() => {
          if (!this.open) return;
          if (!this.contains(document.activeElement) || document.activeElement === this) {
            const auto = this.querySelector('[autofocus]:not([disabled])');
            const items = focusableInside(this);
            const target = auto || items[0] || this;
            if (target === this && !this.hasAttribute('tabindex')) this.setAttribute('tabindex', '-1');
            try { target.focus({ preventScroll: true }); } catch { try { target.focus(); } catch {} }
          }
        });
        return res;
      };
      wrapped.__msWrapped = true;
      HTMLDialogElement.prototype.showModal = wrapped;
    }
    document.querySelectorAll('dialog').forEach((d) => {
      d.setAttribute('aria-modal', 'true');
      bindDialogFocusReturn(d);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const openDialogs = [...document.querySelectorAll('dialog[open]')];
      const topDialog = openDialogs[openDialogs.length - 1];
      if (!topDialog || topDialog.classList.contains('ma-dialog')) return;
      const items = focusableInside(topDialog);
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !topDialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !topDialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  function init() {
    revealFallback();
    // The daily desk stays focused on the post; research lives in the portal.
    removeGates();
    mountOfflineBanner();
    mountDialogAccessibility();
    mountCredits();
    mountSession();
    mountNotifications();
    mountMobileNav();
    mountPlanLinks();
    mountWatchlist();
    syncCredits();
    window.addEventListener('focus', () => { if (serverCredits) syncCredits(); });
    window.addEventListener('muse:credits-refresh', () => syncCredits());
    if (document.getElementById('journey') || location.pathname.startsWith('/today')) mountBrief();
    mountActions();
    mountRefine();
    mountStages();
    document.querySelectorAll('[data-open-gift]').forEach((node) => node.addEventListener('click', openGift));
    document.querySelectorAll('[data-open-tour]').forEach((node) => node.addEventListener('click', openTour));
    mountMyActions();
    mountTriage();
  }

  window.museShell = { spend, spendLive, canRun, requireRun, syncCredits, fetch: museFetch, errorMessage, friendlyError, isOffline, setOfflineState, hasAccount: hasSession, progress, toast, openGift, openPricing, openSignup, openActions, openTour, showStage, watchlist: WATCH, signals: loadSignals, competitorStatus, changeBadges, notificationItems, pausedCompetitors: readPaused, toggleNotifications, markRead };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
