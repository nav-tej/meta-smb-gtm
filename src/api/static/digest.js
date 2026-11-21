(() => {
  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === false || v === null || v === undefined) continue;
      if (k === 'class') node.className = v;
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
    for (const child of children) {
      if (child !== null && child !== undefined) {
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
      }
    }
    return node;
  };
  const write = (id, text) => {
    const node = document.getElementById(id);
    if (node) node.textContent = text;
  };
  const shortDate = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };
  const safeHref = (href, asSample = false) => {
    if (typeof href !== 'string' || !/^\/(?!\/)/.test(href)) {
      return asSample ? '/create?workspace=sample' : '/create';
    }
    if (asSample && href.startsWith('/create') && !href.includes('workspace=sample')) {
      return href.includes('?') ? `${href}&workspace=sample` : `${href}?workspace=sample`;
    }
    return href;
  };

  async function loadDirect() {
    const get = async (url) => {
      try {
        const r = await fetch(url, { credentials: 'same-origin' });
        return r.ok ? await r.json() : null;
      } catch {
        return null;
      }
    };
    const [log, digest, brief] = await Promise.all([
      get('/api/v1/monitor?limit=1'),
      get('/api/v1/weekly-digest'),
      get('/api/v1/daily-brief'),
    ]);
    return { run: Array.isArray(log?.runs) ? log.runs[0] || null : null, log, digest, brief };
  }

  function renderSampleHero(digest, brief) {
    const week = shortDate(digest?.week_end);
    write('digestWeek', week ? `Sample digest · week of ${week}` : 'Sample digest · This week');
    const focus = brief?.focus || brief?.move;
    const total = Number(digest?.total_changes) || 0;
    const checks = Number(digest?.checks) || 0;
    if (checks && total) {
      write('dgHeroTitle', `${total} competitor ${total === 1 ? 'change' : 'changes'} logged across ${checks} ${checks === 1 ? 'check' : 'checks'}.`);
    } else {
      write('dgHeroTitle', focus?.title || 'Sample seller digest (Art of Sarabjit Singh example)');
    }
    const body = [];
    if (Array.isArray(digest?.highlights) && digest.highlights.length) body.push(`Highlights: ${digest.highlights.join('. ')}.`);
    if (focus?.reason) body.push(`Suggested sample move: ${focus.reason}`);
    if (!body.length && digest?.note) body.push(digest.note);
    write('dgHeroBody', body.join(' ') || 'Illustrative digest from saved competitor snapshots captured Nov 3.');
    const link = document.getElementById('dgHeroLink');
    if (link) {
      link.setAttribute('href', safeHref(focus?.href || '/create?idea=idea-1-empowering-women', true));
      link.textContent = focus?.title ? `Make “${focus.title}” →` : 'Make this sample post →';
      link.hidden = false;
    }
    write('dgHeroSource', digest?.source || 'Sample digest · Art of Sarabjit Singh (saved Nov 3 snapshot)');
  }

  function renderStats(digest) {
    const box = document.getElementById('dgStats');
    if (!box) return;
    box.replaceChildren();
    const checks = Number(digest?.checks) || 0;
    const total = Number(digest?.total_changes) || 0;
    const cards = [
      [checks ? String(checks) : '1', checks ? 'monitor checks this week' : 'saved snapshot on file'],
      [String(total), `competitor ${total === 1 ? 'change' : 'changes'} found`],
      ['0 runs', 'used to read this sample digest'],
    ];
    for (const [value, label] of cards) {
      box.appendChild(el('li', { class: 'dg-stat' }, el('strong', {}, value), el('span', {}, label)));
    }
  }

  function renderSampleCompetitors(shell, digest) {
    const grid = document.getElementById('dgCompetitors');
    if (!grid) return;
    grid.replaceChildren();
    const list = Array.isArray(shell?.watchlist) ? shell.watchlist : [
      { name: 'SikhiArt.com', where: 'Own shop · 300 pages', note: 'New editions of Mai Bhago ji and Hari Singh Nalwa (Nov 3 sample).' },
      { name: 'Gurinderpreet Kaur', where: 'Fine Art America · 70 listings', note: 'Baseline $14–$50 prints.' },
      { name: 'Manjot Singh Sachdeva', where: 'Fine Art America / Pixels · 105 listings', note: 'Golden Temple series $14–$24.' },
      { name: 'Gurdish Pannu', where: 'Saatchi Art · originals', note: 'Original canvas works.' },
    ];
    const counts = digest?.by_competitor || {};
    const statusOf = shell?.competitorStatus || ((name) => ({ badges: [['first', 'Sample snapshot']], detail: list.find((w) => w.name === name)?.note || '', when: 'Nov 3' }));
    for (const w of list) {
      const card = el('article', { class: 'dg-card' });
      const head = el('div', { class: 'dg-card-head' }, el('h3', {}, w.name));
      const weekCount = Number(counts[w.name]) || 0;
      const status = statusOf(w.name, null);
      const badges = weekCount > 0 ? [['new', `${weekCount} this week`]] : status.badges;
      const chipRow = el('div', { class: 'dg-chips' });
      for (const [tone, label] of badges) chipRow.appendChild(el('span', { class: `ms-chip ${tone}` }, label));
      head.appendChild(chipRow);
      card.appendChild(head);
      card.appendChild(el('p', { class: 'dg-where' }, w.where));
      card.appendChild(el('p', { class: 'dg-detail' }, status.detail));
      card.appendChild(el('p', { class: 'dg-when' }, `Sample snapshot: ${status.when || 'Nov 3'}`));
      grid.appendChild(card);
    }
  }

  function renderSampleRecos(brief) {
    const list = document.getElementById('dgRecos');
    if (!list) return;
    list.replaceChildren();
    const items = Array.isArray(brief?.action_items) ? brief.action_items.slice(0, 3) : [];
    if (!items.length) {
      list.appendChild(el('li', {}, el('p', { class: 'ms-muted' }, 'No sample recommendations available right now.')));
      return;
    }
    for (const item of items) {
      const li = el('li', { class: `dg-reco ${item.impact || ''}` });
      li.appendChild(el('span', { class: `ms-chip ${item.impact || 'medium'}` }, `${item.impact || 'medium'} impact`));
      li.appendChild(el('strong', {}, String(item.title || '')));
      li.appendChild(el('p', {}, String(item.reason || '')));
      li.appendChild(el('a', { href: safeHref(item.href, true) }, 'Make this post in Sample shop →'));
      list.appendChild(li);
    }
    write('dgRecoSource', 'Recommendations from the Art of Sarabjit Singh sample shop · Reading never uses a run.');
  }

  function clearBody(heroTitle, heroBody, statusText) {
    write('digestWeek', 'Account check');
    write('digestStatus', statusText);
    write('dgHeroTitle', heroTitle);
    write('dgHeroBody', heroBody);
    write('dgHeroSource', '');
    write('dgRecoSource', '');
    const link = document.getElementById('dgHeroLink');
    if (link) link.hidden = true;
    document.getElementById('dgStats')?.replaceChildren();
    document.getElementById('dgCompetitors')?.replaceChildren();
    document.getElementById('dgRecos')?.replaceChildren();
  }

  function renderOwnWorkspaceDigest(wsDoc) {
    const onboarding = wsDoc?.onboarding || {};
    const competitors = Array.isArray(onboarding.competitors) ? onboarding.competitors : [];
    const shopUrls = Array.isArray(onboarding.shop_urls) ? onboarding.shop_urls : [];
    const shopName = onboarding.business_name || (shopUrls[0] ? shopUrls[0] : 'My workspace');

    write('digestWeek', `My workspace · ${shopName}`);
    const status = document.getElementById('digestStatus');
    if (status) {
      status.textContent = competitors.length
        ? `Showing your personal watchlist for ${shopName}.`
        : `Personal digest for ${shopName} starts once you add your shop website or watched competitors.`;
      status.hidden = false;
    }

    if (competitors.length) {
      write('dgHeroTitle', `Watching ${competitors.length} ${competitors.length === 1 ? 'competitor' : 'competitors'} for ${shopName}`);
      write('dgHeroBody', 'Your personal automated digest runs on your chosen schedule below and emails you changes in your own market. Sample artist data is kept separate.');
      const link = document.getElementById('dgHeroLink');
      if (link) {
        link.setAttribute('href', '/create');
        link.textContent = 'Open My workspace in Studio →';
        link.hidden = false;
      }
      write('dgHeroSource', 'Personal workspace · 0 runs used to inspect');
    } else {
      write('dgHeroTitle', 'Your personal digest starts empty until you add competitors');
      write('dgHeroBody', 'Connect your shop website and pick up to 3 competitors to track price changes, new listings, and personalized next moves, or view the sample digest.');
      const link = document.getElementById('dgHeroLink');
      if (link) {
        link.setAttribute('href', '/welcome?step=3');
        link.textContent = 'Add competitors in setup →';
        link.hidden = false;
      }
      write('dgHeroSource', 'My workspace · Sample artist examples stay separate');
    }

    const stats = document.getElementById('dgStats');
    if (stats) {
      stats.replaceChildren(
        el('li', { class: 'dg-stat' }, el('strong', {}, String(competitors.length)), el('span', {}, 'personal competitors watched')),
        el('li', { class: 'dg-stat' }, el('strong', {}, shopUrls.length ? 'Connected' : 'Not added'), el('span', {}, 'your shop website')),
        el('li', { class: 'dg-stat' }, el('strong', {}, '0 runs'), el('span', {}, 'used to view your digest'))
      );
    }

    const grid = document.getElementById('dgCompetitors');
    if (grid) {
      grid.replaceChildren();
      if (competitors.length) {
        for (const comp of competitors) {
          const name = typeof comp === 'string' ? comp : (comp.name || comp.url || 'Competitor');
          const url = typeof comp === 'string' ? comp : (comp.url || '');
          const card = el('article', { class: 'dg-card' });
          const head = el('div', { class: 'dg-card-head' }, el('h3', {}, String(name)));
          head.appendChild(el('div', { class: 'dg-chips' }, el('span', { class: 'ms-chip first' }, 'My watchlist')));
          card.appendChild(head);
          card.appendChild(el('p', { class: 'dg-where' }, url ? String(url) : 'Configured in setup'));
          card.appendChild(el('p', { class: 'dg-detail' }, 'Queued for your scheduled digest updates.'));
          grid.appendChild(card);
        }
      } else {
        const emptyCard = el('article', { class: 'dg-card' });
        emptyCard.appendChild(el('h3', {}, 'No personal competitors watched yet'));
        emptyCard.appendChild(el('p', { class: 'dg-detail' }, 'Add competitors you want to track, or open the Sample shop digest to see how weekly summaries look.'));
        emptyCard.appendChild(el('p', { class: 'dg-when' }, el('a', { href: '/digest?workspace=sample' }, 'View Sample shop digest →')));
        grid.appendChild(emptyCard);
      }
    }

    const recos = document.getElementById('dgRecos');
    if (recos) {
      recos.replaceChildren();
      const li = el('li', { class: 'dg-reco high' });
      li.appendChild(el('span', { class: 'ms-chip high' }, 'My workspace'));
      li.appendChild(el('strong', {}, shopUrls.length ? 'Draft a post from your shop website' : 'Add your shop website in My workspace'));
      li.appendChild(el('p', {}, shopUrls.length
        ? 'Jump straight to Studio to create an ad or social post using your own products and photos.'
        : 'Paste your shop URL or product photo in Studio to generate custom creatives for your own store.'));
      li.appendChild(el('a', { href: '/create' }, 'Open Studio in My workspace →'));
      const sampleLi = el('li', { class: 'dg-reco medium' });
      sampleLi.appendChild(el('span', { class: 'ms-chip first' }, 'Sample example'));
      sampleLi.appendChild(el('strong', {}, 'See how a filled sample digest looks'));
      sampleLi.appendChild(el('p', {}, 'Browse the Sample shop weekly digest separately without mixing it into your account.'));
      sampleLi.appendChild(el('a', { href: '/digest?workspace=sample' }, 'Open Sample shop digest →'));
      recos.appendChild(li);
      recos.appendChild(sampleLi);
    }
    write('dgRecoSource', 'Personal recommendations never mix with Sample shop data.');
  }

  async function applyMode(modeState) {
    const s = modeState || (await window.museModes?.resolve?.()) || {
      state: 'guest_entry',
      isSample: true,
      isLoading: false,
      isError: false,
      isExpired: false,
    };

    if (s.isLoading) {
      clearBody('Checking your account…', 'Verifying your workspace before showing your digest.', 'Checking your account…');
      return;
    }
    if (s.isError || s.isExpired) {
      clearBody(
        s.isExpired ? 'Session expired' : 'Account check unavailable',
        s.authError || 'Could not verify your account right now. Sample digest stays separate until your account loads.',
        s.isExpired ? 'Sign in again to load your personal digest.' : 'Retry checking your account above.'
      );
      return;
    }

    if (s.state === 'account_own') {
      const guard = window.museModes?.bindAsyncGuard?.() || { isCurrent: () => true };
      write('digestStatus', 'Loading your personal workspace…');
      let wsDoc = {};
      try {
        if (window.museAccount && typeof window.museAccount.loadWorkspace === 'function') {
          const loaded = await window.museAccount.loadWorkspace(s.ownerId);
          if (!guard.isCurrent()) return;
          wsDoc = loaded?.document || {};
        }
      } catch {
        if (!guard.isCurrent()) return;
        wsDoc = {};
      }
      renderOwnWorkspaceDigest(wsDoc);
      return;
    }

    // Guest or explicit Sample shop view -> render clearly labeled Sample digest
    const guard = window.museModes?.bindAsyncGuard?.() || { isCurrent: () => true };
    const status = document.getElementById('digestStatus');
    const shell = window.museShell;
    const loaded = shell?.signals ? await shell.signals() : await loadDirect();
    if (!guard.isCurrent()) return;
    if (status) {
      status.textContent = loaded?.digest
        ? 'Showing the Sample shop weekly digest (Art of Sarabjit Singh example).'
        : 'Showing the saved Sample shop digest (Art of Sarabjit Singh example).';
    }
    renderSampleHero(loaded?.digest || {}, loaded?.brief || {});
    renderStats(loaded?.digest || {});
    renderSampleCompetitors(shell, loaded?.digest || {});
    renderSampleRecos(loaded?.brief || {});
  }

  async function start() {
    if (window.museModes?.subscribe) window.museModes.subscribe(applyMode);
    if (window.museModes?.resolve) await applyMode(await window.museModes.resolve());
    else await applyMode();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
