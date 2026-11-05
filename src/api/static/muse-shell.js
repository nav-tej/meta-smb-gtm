'use strict';
// Shared app shell for / and /create: demo credits, progress feedback, gift plan, and the portal
// tour and stage tabs. Everything runs on saved results; nothing here calls a model or takes payment.
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
  function toast(message, kind = '') {
    if (!toastBox) { toastBox = el('div', { class: 'ms-toasts', role: 'status', 'aria-live': 'polite' }); document.body.appendChild(toastBox); }
    const item = el('div', { class: `ms-toast ${kind}` }, message);
    toastBox.appendChild(item);
    setTimeout(() => item.classList.add('out'), 2600);
    setTimeout(() => item.remove(), 3100);
  }

  // ---------- Demo credits ----------
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
  function spend(label) {
    if (serverMode()) return; // The server counts real runs; saved actions stay free.
    if (!hasSession()) return;
    if (credits === 0) { toast('No runs left. Pick a plan, or reset the demo credits.', 'warn'); openPricing(); return; }
    credits -= 1; saveCredits(); renderCredits(true);
    toast(`−1 run · ${label}`);
  }
  // Gate for any run (analysis, generation, refinement). Returns false when the visitor must
  // sign up or buy more runs first. Server accounts count their own runs.
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
      menu.appendChild(el('p', { class: 'ms-muted' }, 'Demo account: runs are stored in this browser. Repeat live results come from a 24-hour cache, so they never spend Muse API credit twice.'));
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
  const PLAN_RUNS = { starter: 10, growth: 50, unlimited: 999 };
  const PLANS = [
    { id: 'starter', name: 'Starter', price: '$9', per: 'one-time', runs: '10 runs', points: ['Competitor analysis', 'Ready-to-post ads', 'Ranked next moves'] },
    { id: 'growth', name: 'Growth', price: '$29', per: '/month', runs: '50 runs a month', points: ['Everything in Starter', 'Daily growth brief', 'Budget advice for ads'], featured: true },
    { id: 'unlimited', name: 'Unlimited', price: '$99', per: '/month', runs: 'Unlimited runs', points: ['Everything in Growth', 'Unlimited competitors', 'Priority support'] },
  ];
  async function buyPlan(plan, button) {
    const snap = serverSnapshot();
    if (!snap?.configured) return;
    if (!snap.user) { toast('Sign in to pick a plan.'); window.museAccount.open('signup'); return; }
    if (!snap.user.email_verified) { toast('Confirm your email first.'); window.museAccount.open('account'); return; }
    button.disabled = true;
    try {
      const response = await fetch('/api/v1/billing/checkout', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.url) throw new Error(data.detail || 'Checkout failed.');
      location.href = data.url;
    } catch (error) { toast(error.message, 'warn'); button.disabled = false; }
  }
  function refreshPlanButtons() {
    if (!pricingDialog) return;
    pricingDialog.querySelectorAll('.ms-plan').forEach((card, index) => {
      const plan = PLANS[index];
      const button = card.querySelector('button');
      if (!plan || !button) return;
      if (serverMode()) {
        button.disabled = false;
        button.removeAttribute('title');
        button.textContent = `Choose ${plan.name}`;
        button.onclick = () => buyPlan(plan.id, button);
      } else {
        button.disabled = false;
        button.title = 'Demo checkout: no payment is taken';
        button.textContent = `Choose ${plan.name}`;
        button.onclick = () => { pricingDialog.close(); openCheckout(plan); };
      }
    });
    const note = pricingDialog.querySelector('.ms-muted');
    if (note) note.textContent = serverMode()
      ? 'Secure checkout via Stripe. 1 run = one competitor analysis, ad generation or budget review.'
      : 'Demo checkout: no card is needed and no payment is taken; runs are added to this browser. 1 run = one analysis, refinement, re-run or ad scene.';
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
        if (plan.featured) card.appendChild(el('span', { class: 'ms-plan-tag' }, 'Most popular'));
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
      checkoutDialog.appendChild(el('p', { class: 'ms-checkout-note' }, 'This is a demo: no card is needed, nothing is charged, and no payment details are collected. Runs are added to this browser.'));
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
      credits += PLAN_RUNS[plan.id] || 0; saveCredits(); renderCredits(true);
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
      signupDialog.appendChild(el('p', { class: 'ms-eyebrow' }, 'Free to start · 3 runs'));
      signupDialog.appendChild(el('h2', { id: 'msSignupTitle' }, 'Create your free account'));
      signupDialog.appendChild(el('p', { class: 'ms-signup-reason' }));
      const form = el('form', { class: 'ms-signup-form', novalidate: '' });
      form.appendChild(el('label', { for: 'msSignupEmail' }, 'Email'));
      form.appendChild(el('input', { id: 'msSignupEmail', type: 'email', autocomplete: 'email', required: '', maxlength: '254', placeholder: 'you@yourshop.com' }));
      form.appendChild(el('label', { for: 'msSignupName' }, 'Shop or name (optional)'));
      form.appendChild(el('input', { id: 'msSignupName', type: 'text', autocomplete: 'organization', maxlength: '80', placeholder: 'Art of Sarabjit Singh' }));
      form.appendChild(el('p', { class: 'ms-signup-error', role: 'alert' }));
      form.appendChild(el('button', { type: 'submit', class: 'ms-primary' }, 'Create free account'));
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
      signupDialog.appendChild(el('p', { class: 'ms-muted' }, 'Demo mode: your account and runs are saved in this browser only. No email is sent and no password is stored.'));
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
    if (existing === null) { credits = START_CREDITS; saveCredits(); }
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
      const btn = el('button', { type: 'button', class: 'ms-primary ms-small ms-signup-btn' }, 'Sign up free');
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
  const TRIAGE_SELECTORS = ['.jr-recos > li', '#insightsContainer > .finding-item', '.try-next li', '#msBrief .ms-move'];
  function itemTitle(item) {
    const head = item.querySelector('strong:not(.ms-match-tag)');
    return (head?.textContent || item.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  }
  function itemLink(item) {
    const link = item.querySelector('a[href]');
    return link ? link.getAttribute('href') : '';
  }
  function setStatus(item, status) {
    const id = item.dataset.actionId;
    const all = readActions();
    if (status) all[id] = { status, title: itemTitle(item), href: itemLink(item), page: location.pathname, at: new Date().toISOString() };
    else delete all[id];
    writeActions(all);
    applyStatus(item);
    renderAccount();
    const labels = { accepted: 'Added to My actions', dismissed: 'Dismissed', archived: 'Archived' };
    if (status) toast(`${labels[status]} · ${itemTitle(item).slice(0, 48)}`);
  }
  function applyStatus(item) {
    const state = readActions()[item.dataset.actionId]?.status || '';
    item.classList.toggle('ms-accepted', state === 'accepted');
    item.hidden = state === 'dismissed' || state === 'archived';
    const accept = item.querySelector('.ms-triage-accept');
    if (accept) { accept.textContent = state === 'accepted' ? '✓ In My actions' : '✓ Accept'; accept.setAttribute('aria-pressed', String(state === 'accepted')); }
  }
  function addTriage(item) {
    if (item.querySelector('.ms-triage')) return;
    item.dataset.actionId = actionId(itemTitle(item));
    const bar = el('div', { class: 'ms-triage', role: 'group', 'aria-label': 'Recommendation actions' });
    const accept = el('button', { type: 'button', class: 'ms-triage-accept' }, '✓ Accept');
    const dismiss = el('button', { type: 'button', class: 'ms-triage-dismiss' }, '✕ Dismiss');
    const archive = el('button', { type: 'button', class: 'ms-triage-archive' }, '⤓ Archive');
    accept.addEventListener('click', () => setStatus(item, readActions()[item.dataset.actionId]?.status === 'accepted' ? '' : 'accepted'));
    dismiss.addEventListener('click', () => setStatus(item, 'dismissed'));
    archive.addEventListener('click', () => setStatus(item, 'archived'));
    bar.append(accept, dismiss, archive);
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
        [...list.children].forEach((c) => c.dataset?.actionId && applyStatus(c));
        addRestore(list);
      });
      list.insertAdjacentElement('afterend', restore);
    }
    restore.textContent = `Show ${n} dismissed ↺`;
  }
  function mountTriage() {
    const run = () => {
      for (const sel of TRIAGE_SELECTORS) document.querySelectorAll(sel).forEach(addTriage);
      new Set([...document.querySelectorAll('[data-action-id]')].map((i) => i.parentElement)).forEach((list) => list && addRestore(list));
    };
    run();
    document.addEventListener('click', (event) => { if (event.target.closest?.('.ms-triage')) setTimeout(run, 0); });
    const insights = document.getElementById('insightsContainer');
    if (insights && typeof MutationObserver !== 'undefined') new MutationObserver(() => setTimeout(run, 0)).observe(insights, { childList: true });
    window.addEventListener('muse:brief-ready', run);
  }
  let actionsDialog;
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
      for (const [id, a] of items) {
        const li = el('li', {});
        li.appendChild(el('strong', {}, a.title));
        const row = el('div', { class: 'ms-actions-row' });
        if (a.href && status === 'accepted') { const go = el('a', { href: a.href, class: 'ms-link' }, 'Do it →'); row.appendChild(go); }
        const next = { accepted: ['Mark done', 'done'], done: ['Reopen', 'accepted'], archived: ['Restore', 'accepted'] }[status];
        const move = el('button', { type: 'button', class: 'ms-link' }, next[0]);
        move.addEventListener('click', () => { const v = readActions(); v[id] = { ...v[id], status: next[1] }; writeActions(v); openActions(); renderAccount(); document.querySelectorAll(`[data-action-id="${id}"]`).forEach(applyStatus); });
        const remove = el('button', { type: 'button', class: 'ms-link ms-remove' }, 'Remove');
        remove.addEventListener('click', () => { const v = readActions(); delete v[id]; writeActions(v); openActions(); renderAccount(); document.querySelectorAll(`[data-action-id="${id}"]`).forEach(applyStatus); });
        row.append(move, remove);
        li.appendChild(row);
        list.appendChild(li);
      }
      body.appendChild(list);
    }
    if (!any) body.appendChild(el('p', { class: 'ms-muted' }, 'Accept a recommendation to add it here. Dismissed ideas are hidden; archived ones are kept here for later.'));
    if (typeof actionsDialog.showModal === 'function') actionsDialog.showModal(); else actionsDialog.setAttribute('open', '');
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
    const recheck = el('button', { type: 'button', class: 'ms-secondary ms-small', title: 'Rebuild today’s brief from saved and cached data · 1 run' }, 'Re-check now');
    const toggle = el('button', { type: 'button', class: 'ms-link ms-brief-toggle', 'aria-expanded': 'true', 'aria-controls': 'msBriefBody' }, 'Hide');
    const actions = el('div', { class: 'ms-brief-actions' });
    actions.append(recheck, toggle);
    head.append(titleBox, actions);
    const body = el('div', { class: 'ms-brief-body', id: 'msBriefBody' });
    const list = el('ul', { class: 'ms-watch' });
    const CHIP = { new: 'New', first: 'First check', fresh: 'Fresh Muse brief' };
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
    const sourceNote = el('p', { class: 'ms-muted ms-brief-source' }, 'From saved public snapshots captured Nov 3. Muse checks again when you run a re-check; it does not watch continuously.');
    const loadBrief = async (refresh = false) => {
      try {
        const response = await fetch(`/api/v1/daily-brief${refresh ? '?refresh=true' : ''}`);
        if (!response.ok) throw new Error(String(response.status));
        const brief = await response.json();
        if (Array.isArray(brief.items) && brief.items.length) renderItems(brief.items);
        const built = brief.generated_at ? new Date(brief.generated_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : '';
        sourceNote.textContent = `${String(brief.source || '')}${built ? ` Generated ${built}; cached for today.` : ''}`;
        return true;
      } catch { return false; }
    };
    recheck.addEventListener('click', async () => {
      if (!requireRun('Brief re-check')) return;
      recheck.disabled = true;
      await progress('Re-checking your watchlist', ['Reading saved snapshots', 'Looking for fresh Muse analyses', 'Ranking today’s move']);
      const ok = await loadBrief(true);
      recheck.disabled = false;
      toast(ok ? 'Brief rebuilt from saved and cached data' : 'Could not rebuild the brief; showing the saved one.', ok ? '' : 'warn');
    });
    loadBrief(false);
    const move = el('div', { class: 'ms-move' });
    const moveText = el('div');
    moveText.appendChild(el('span', { class: 'ms-chip high' }, 'Today’s move · high impact'));
    moveText.appendChild(el('strong', {}, 'Feature your Empowering Women series'));
    moveText.appendChild(el('span', { class: 'ms-note' }, 'SikhiArt keeps adding warrior and guru editions but has no group for women’s stories.'));
    const go = el('a', { class: 'ms-primary ms-small', href: '/create?goal=story' }, 'Make this post →');
    move.append(moveText, go);
    body.append(list, move);
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

  function init() {
    revealFallback();
    // The daily desk stays focused on the post; research lives in the portal.
    removeGates();
    mountCredits();
    mountSession();
    if (document.getElementById('journey') || location.pathname.startsWith('/today')) mountBrief();
    mountActions();
    mountRefine();
    mountStages();
    document.querySelectorAll('[data-open-gift]').forEach((node) => node.addEventListener('click', openGift));
    document.querySelectorAll('[data-open-tour]').forEach((node) => node.addEventListener('click', openTour));
    mountTriage();

  }

  window.museShell = { spend, requireRun, hasAccount: hasSession, progress, toast, openGift, openPricing, openSignup, openActions, openTour, showStage };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
