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

  const safeExternalHref = (raw) => {
    try {
      const u = new URL(String(raw || ''));
      return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : '';
    } catch {
      return '';
    }
  };
  const normalizeCompetitorUrl = (raw) => {
    const cleaned = String(raw || '').trim();
    if (!cleaned) return '';
    const withScheme = cleaned.includes('://') ? cleaned : `https://${cleaned.replace(/^@+/, '')}`;
    try {
      const u = new URL(withScheme);
      const path = u.pathname.replace(/\/+$/, '');
      return `${u.protocol.toLowerCase()}//${u.host.toLowerCase()}${path}${u.search}`;
    } catch {
      return cleaned;
    }
  };
  const AD_PAGE_ID_RE = /^[0-9]{5,20}$/;
  const validAdPageId = (raw) => {
    const cleaned = String(raw || '').trim();
    return AD_PAGE_ID_RE.test(cleaned) ? cleaned : '';
  };
  const adLibraryQuery = (name, url) => {
    const n = String(name || '').trim();
    if (n && !/^https?:\/\//i.test(n) && n.split(/\s+/).length <= 2 && !n.includes('.')) return n;
    const raw = String(url || (n.includes('.') ? n : '') || '').trim();
    try {
      const host = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`).hostname.replace(/^www\./i, '');
      const label = host.split('.')[0];
      if (label) return label.charAt(0).toUpperCase() + label.slice(1);
    } catch {}
    return n || raw;
  };
  const adLibraryPageUrl = (pageId) => (
    `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=${encodeURIComponent(pageId)}&search_type=page&media_type=all`
  );
  const adLibrarySearchUrl = (query) => (
    `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q=${encodeURIComponent(query)}&search_type=keyword_unordered&media_type=all`
  );
  const extractWatchlist = (wsDoc) => {
    const prefs = wsDoc?.preferences && typeof wsDoc.preferences === 'object' ? wsDoc.preferences : {};
    const onb = wsDoc?.onboarding && typeof wsDoc.onboarding === 'object' ? wsDoc.onboarding : {};
    const prefEntries = Array.isArray(prefs.competitor_entries) ? prefs.competitor_entries : [];
    const onbEntries = Array.isArray(onb.competitors) ? onb.competitors : [];
    const rawList = prefEntries.length ? prefEntries : onbEntries;
    const supplemental = new Map();
    for (const item of (prefEntries.length ? onbEntries : prefEntries)) {
      if (!item || typeof item !== 'object') continue;
      const norm = normalizeCompetitorUrl(item.url);
      if (norm && !supplemental.has(norm)) supplemental.set(norm, item);
    }
    const seen = new Set();
    const out = [];
    for (const item of rawList) {
      const isSelected = typeof item === 'string' ? true : item?.selected !== false;
      const rawUrl = typeof item === 'string' ? item.trim() : String(item?.url || '').trim();
      const rawName = typeof item === 'string' ? '' : String(item?.name || '').trim();
      if (!isSelected || !rawUrl) continue;
      const norm = normalizeCompetitorUrl(rawUrl);
      if (!norm || seen.has(norm)) continue;
      seen.add(norm);
      let host = norm;
      try { host = new URL(norm).hostname.replace(/^www\./i, ''); } catch {}
      const extra = supplemental.get(norm) || {};
      const obj = typeof item === 'object' && item ? item : {};
      const adPageId = validAdPageId(obj.ad_library_page_id || extra.ad_library_page_id);
      const note = String(
        obj.rationale || extra.rationale || obj.reason || extra.reason || ''
      ).trim();
      const analyzedAt = String(obj.analyzed_at || extra.analyzed_at || '').trim();
      out.push({
        name: rawName || host,
        url: norm,
        ad_library_page_id: adPageId,
        note,
        analyzed_at: analyzedAt,
      });
      if (out.length >= 6) break;
    }
    return out;
  };
  const prefillDraftShops = (watchlist) => {
    const urls = watchlist.slice(0, 3).map((c) => c.url).filter(Boolean);
    window.__museWatchlistUrls = urls;
    const inputs = [...document.querySelectorAll('#digestDraftForm input[name="draftShop"]')];
    if (!inputs.length || !urls.length) return;
    const anyFilled = inputs.some((inp) => inp.value.trim());
    if (!anyFilled) {
      inputs.forEach((inp, idx) => { inp.value = urls[idx] || ''; });
    }
  };

  let ownState = {
    ownerId: null,
    wsDoc: {},
    version: 0,
    busy: false,
    autoCheck: null,
    checksMap: null,
  };

  function formatNextCheckDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    });
  }

  function clearAutoCheckBar() {
    document.getElementById('dgAutoCheckBar')?.remove();
  }

  function renderAutoCheckBar(autoCheck) {
    clearAutoCheckBar();
    if (!autoCheck || autoCheck.enabled !== true) return;
    const grid = document.getElementById('dgCompetitors');
    if (!grid || !grid.parentNode) return;

    const bar = el('div', {
      id: 'dgAutoCheckBar',
      class: 'dg-note',
      style: 'display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0.5rem 1rem;margin:0.35rem 0 0.75rem;padding:0.6rem 0.75rem;border:1px solid var(--border,#e5e1d8);border-radius:10px;max-width:100%;box-sizing:border-box;',
    });

    const nextStr = formatNextCheckDate(autoCheck.next_check_at);
    const noteText = autoCheck.paused
      ? 'Automatic weekly checks are paused. Press Check now (free) whenever you want an update.'
      : (nextStr
        ? `Muse checks your watchlist once a week. Next check: about ${nextStr}.`
        : 'Muse checks your watchlist once a week.');
    bar.appendChild(el('span', { id: 'dgAutoCheckNote', style: 'overflow-wrap:anywhere;' }, noteText));

    const label = el('label', {
      for: 'dgAutoCheckToggle',
      style: 'display:inline-flex;align-items:center;gap:0.45rem;cursor:pointer;font-weight:500;',
    });
    const checkbox = el('input', {
      type: 'checkbox',
      id: 'dgAutoCheckToggle',
    });
    checkbox.checked = !autoCheck.paused;
    checkbox.addEventListener('change', async () => {
      const wantPaused = !checkbox.checked;
      checkbox.disabled = true;
      try {
        const resp = await fetch('/api/v1/competitors/auto-check', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paused: wantPaused }),
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.auto_check) {
          ownState.autoCheck = data.auto_check;
          renderAutoCheckBar(ownState.autoCheck);
          return;
        }
        checkbox.checked = !wantPaused;
      } catch {
        checkbox.checked = !wantPaused;
      } finally {
        checkbox.disabled = false;
      }
    });
    label.append(checkbox, document.createTextNode('Check my watchlist automatically each week'));
    bar.appendChild(label);
    grid.parentNode.insertBefore(bar, grid);
  }

  function setCheckControls(visible, statusText = '') {
    const btn = document.getElementById('dgCheckNowBtn');
    const st = document.getElementById('dgCheckStatus');
    if (btn) btn.hidden = !visible;
    if (st) {
      st.textContent = statusText;
      st.hidden = !statusText;
    }
  }

  function clearBody(heroTitle, heroBody, statusText) {
    setCheckControls(false, '');
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

  function computeOwnTopInsight(watchlist, checksMap) {
    const checkedItems = watchlist
      .map((c) => ({ comp: c, check: checksMap[c.url] || null }))
      .filter((x) => x.check && typeof x.check === 'object');

    let best = null;
    let bestTotal = 0;
    for (const item of checkedItems) {
      const counts = item.check.counts || {};
      const total = (Number(counts.new_listing) || 0) + (Number(counts.price_change) || 0) + (Number(counts.removed_listing) || 0);
      if (total > bestTotal) {
        bestTotal = total;
        best = item;
      }
    }
    if (best && bestTotal > 0) {
      const counts = best.check.counts || {};
      const nNew = Number(counts.new_listing) || 0;
      const nPrice = Number(counts.price_change) || 0;
      const nRem = Number(counts.removed_listing) || 0;
      let title;
      if (nNew >= nPrice && nNew >= nRem && nNew > 0 && best.check.partial) {
        title = `${best.comp.name} has ${nNew} new or updated ${nNew === 1 ? 'page' : 'pages'}`;
      } else if (nNew >= nPrice && nNew >= nRem && nNew > 0) {
        title = `${best.comp.name} added ${nNew} ${nNew === 1 ? 'page' : 'pages'}`;
      } else if (nPrice >= nRem && nPrice > 0) {
        title = `${best.comp.name} updated ${nPrice} ${nPrice === 1 ? 'price' : 'prices'}`;
      } else {
        title = `${best.comp.name} removed ${nRem} ${nRem === 1 ? 'page' : 'pages'}`;
      }
      return {
        title,
        body: best.check.summary || 'Review the changes below and decide if you want to respond with a post.',
      };
    }

    const unchanged = checkedItems.filter((x) => x.check.status === 'unchanged');
    if (unchanged.length) {
      const sinceIso = unchanged.find((x) => x.check.compared_with)?.check.compared_with || unchanged[0].check.checked_at;
      const since = shortDate(sinceIso);
      return {
        title: since ? `No changes at the competitors you watch since ${since}` : 'No changes at the competitors you watch since your last check',
        body: 'Muse checked their public pages and found no new, removed, or repriced pages.',
      };
    }

    const firstChecks = checkedItems.filter((x) => x.check.status === 'first_check');
    if (firstChecks.length) {
      const totalPages = firstChecks.reduce((acc, x) => acc + (Number(x.check.page_count) || 0), 0);
      return {
        title: `Baseline saved for ${firstChecks.length} ${firstChecks.length === 1 ? 'competitor' : 'competitors'}`,
        body: `Muse now knows ${totalPages} public pages across your watchlist. Changes show from the next check.`,
      };
    }

    if (checkedItems.length && checkedItems.every((x) => x.check.status === 'error')) {
      return {
        title: 'Could not read your watched competitors right now',
        body: 'See each competitor card below for details, or try Check now (free) again later.',
      };
    }

    return {
      title: 'Your watchlist has not been checked yet',
      body: 'Click Check now (free) below to scan your watched competitors and save a baseline. No Muse runs are used.',
    };
  }

  function renderOwnWorkspaceDigest(wsDoc, wsVersion = ownState.version) {
    ownState.wsDoc = wsDoc || {};
    ownState.version = Number.isFinite(Number(wsVersion)) ? Number(wsVersion) : 0;

    const onboarding = wsDoc?.onboarding || {};
    const prefs = wsDoc?.preferences || {};
    const autoCheck = ownState.autoCheck && ownState.autoCheck.enabled === true ? ownState.autoCheck : null;
    const checksMap = autoCheck && ownState.checksMap && typeof ownState.checksMap === 'object'
      ? ownState.checksMap
      : (prefs.competitor_checks && typeof prefs.competitor_checks === 'object' ? prefs.competitor_checks : {});
    const watchlist = extractWatchlist(wsDoc);
    const shopUrls = Array.isArray(onboarding.shop_urls) ? onboarding.shop_urls : [];
    const shopName = onboarding.business_name || (shopUrls[0] ? shopUrls[0] : 'My workspace');
    const isSvc = onboarding.business_type === 'services';
    if (typeof document !== 'undefined') {
      document.title = isSvc
        ? 'Weekly competitor digest | Muse Growth Studio'
        : 'Weekly competitor digest for small shops | Muse Growth Studio';
      const listingCb = document.querySelector('#digestDraftForm input[name="draftTopic"][value="listing_changes"]');
      const listingLabel = listingCb?.parentElement;
      if (listingLabel && listingLabel.lastChild && listingLabel.lastChild.nodeType === 3) {
        listingLabel.lastChild.textContent = isSvc ? ' New and removed pages' : ' New and removed listings or pages';
      }
    }

    prefillDraftShops(watchlist);
    setCheckControls(watchlist.length > 0, document.getElementById('dgCheckStatus')?.textContent || '');
    renderAutoCheckBar(autoCheck);

    write('digestWeek', `My workspace · ${shopName}`);
    const status = document.getElementById('digestStatus');
    if (status) {
      status.textContent = watchlist.length
        ? `Showing your personal watchlist for ${shopName}.`
        : `Personal digest for ${shopName} starts once you add your website or watched competitors.`;
      status.hidden = false;
    }

    if (watchlist.length) {
      const insight = computeOwnTopInsight(watchlist, checksMap);
      write('dgHeroTitle', insight.title);
      write('dgHeroBody', insight.body);
      const link = document.getElementById('dgHeroLink');
      if (link) {
        link.setAttribute('href', '/create');
        link.textContent = 'Open My workspace in Studio →';
        link.hidden = false;
      }
      write('dgHeroSource', 'Personal workspace · 0 runs used to check or inspect');
    } else {
      write('dgHeroTitle', 'Your personal digest starts empty until you add competitors');
      write('dgHeroBody', 'Connect your website and pick competitors to track price changes, new pages, and next moves, or view the sample digest.');
      const link = document.getElementById('dgHeroLink');
      if (link) {
        link.setAttribute('href', '/welcome?step=3');
        link.textContent = 'Add competitors in setup →';
        link.hidden = false;
      }
      write('dgHeroSource', 'My workspace · Sample artist examples stay separate');
    }

    const totalChanges = watchlist.reduce((sum, c) => {
      const counts = checksMap[c.url]?.counts || {};
      return sum + (Number(counts.new_listing) || 0) + (Number(counts.price_change) || 0) + (Number(counts.removed_listing) || 0);
    }, 0);
    const checkedCount = watchlist.filter((c) => Boolean(checksMap[c.url]?.checked_at)).length;

    const stats = document.getElementById('dgStats');
    if (stats) {
      stats.replaceChildren(
        el('li', { class: 'dg-stat' }, el('strong', {}, `${checkedCount}/${watchlist.length}`), el('span', {}, 'watched competitors checked')),
        el('li', { class: 'dg-stat' }, el('strong', {}, String(totalChanges)), el('span', {}, `competitor ${totalChanges === 1 ? 'change' : 'changes'} found`)),
        el('li', { class: 'dg-stat' }, el('strong', {}, '0 runs'), el('span', {}, 'used to check or view'))
      );
    }

    const grid = document.getElementById('dgCompetitors');
    if (grid) {
      grid.replaceChildren();
      if (watchlist.length) {
        for (const comp of watchlist) {
          const check = checksMap[comp.url] || null;
          const card = el('article', { class: 'dg-card' });
          const head = el('div', { class: 'dg-card-head' }, el('h3', {}, String(comp.name)));
          const chipRow = el('div', { class: 'dg-chips' });

          if (!check) {
            chipRow.appendChild(el('span', { class: 'ms-chip first' }, 'Not checked yet'));
          } else if (check.status === 'error') {
            chipRow.appendChild(el('span', { class: 'ms-chip error' }, 'Could not check'));
          } else if (check.status === 'first_check') {
            chipRow.appendChild(el('span', { class: 'ms-chip first' }, 'First check'));
          } else {
            const counts = check.counts || {};
            const nNew = Number(counts.new_listing) || 0;
            const nPrice = Number(counts.price_change) || 0;
            const nRem = Number(counts.removed_listing) || 0;
            const newWord = check.partial ? 'new or updated' : 'new';
            if (nNew > 0) chipRow.appendChild(el('span', { class: 'ms-chip new' }, `${nNew} ${newWord} ${nNew === 1 ? 'page' : 'pages'}`));
            if (nPrice > 0) chipRow.appendChild(el('span', { class: 'ms-chip price' }, `${nPrice} price ${nPrice === 1 ? 'change' : 'changes'}`));
            if (nRem > 0) chipRow.appendChild(el('span', { class: 'ms-chip removed' }, `${nRem} removed`));
            if (!nNew && !nPrice && !nRem) chipRow.appendChild(el('span', { class: 'ms-chip none' }, 'No changes'));
          }
          head.appendChild(chipRow);
          card.appendChild(head);
          card.appendChild(el('p', { class: 'dg-where' }, String(comp.url)));

          if (comp.note) {
            card.appendChild(el('p', { class: 'dg-detail dg-comp-note' }, comp.note));
          }
          if (comp.analyzed_at) {
            const analyzedDate = shortDate(comp.analyzed_at);
            const analysisLabel = analyzedDate ? `From your analysis, ${analyzedDate}` : 'From your analysis';
            card.appendChild(el(
              'p',
              { class: 'dg-when dg-analysis-meta', style: 'display:flex;flex-wrap:wrap;gap:0.25rem 0.6rem;align-items:baseline;margin:0.15rem 0 0;' },
              el('span', {}, analysisLabel),
              el('a', { href: '/#loop-research', class: 'dg-view-analysis' }, 'View analysis')
            ));
          }

          if (!check) {
            card.appendChild(el('p', { class: 'dg-detail' }, 'Not checked yet. Click Check now (free) above to save a baseline of their public pages.'));
          } else {
            card.appendChild(el('p', { class: 'dg-detail' }, String(check.summary || check.error || 'Checked.')));
            const newPages = Array.isArray(check.new_pages) ? check.new_pages.slice(0, 5) : [];
            if (newPages.length) {
              const ul = el('ul', { class: 'dg-detail', style: 'margin:0.35rem 0 0;padding-left:1.1rem;' });
              for (const p of newPages) {
                const href = safeExternalHref(p.loc);
                const label = String(p.title || p.loc || 'New page');
                ul.appendChild(el('li', {}, href ? el('a', { href, target: '_blank', rel: 'noopener noreferrer' }, label) : label));
              }
              card.appendChild(ul);
            }
            const priceChanges = Array.isArray(check.price_changes) ? check.price_changes.slice(0, 5) : [];
            if (priceChanges.length) {
              const ul = el('ul', { class: 'dg-detail', style: 'margin:0.35rem 0 0;padding-left:1.1rem;' });
              for (const pc of priceChanges) {
                const label = `${pc.title || 'Page'}: ${pc.old_price || 'none'} to ${pc.new_price || 'none'}`;
                ul.appendChild(el('li', {}, label));
              }
              card.appendChild(ul);
            }
            const whenStr = shortDate(check.checked_at);
            if (autoCheck) {
              const sourceLabel = check.source === 'auto' ? 'Automatic check' : 'Checked by you';
              card.appendChild(el('p', { class: 'dg-when' }, whenStr ? `${sourceLabel} · ${whenStr}` : sourceLabel));
            } else {
              card.appendChild(el('p', { class: 'dg-when' }, whenStr ? `Checked ${whenStr}` : 'Checked'));
            }
          }

          const adLinksRow = el('p', {
            class: 'dg-when dg-ad-links',
            style: 'display:flex;flex-wrap:wrap;gap:0.25rem 0.75rem;align-items:baseline;margin:0.3rem 0 0;overflow-wrap:anywhere;',
          });
          if (comp.ad_library_page_id) {
            adLinksRow.appendChild(el(
              'a',
              {
                href: adLibraryPageUrl(comp.ad_library_page_id),
                target: '_blank',
                rel: 'noopener noreferrer',
                class: 'dg-meta-ad-link',
              },
              'See their ads on Meta ↗'
            ));
          } else {
            const query = adLibraryQuery(comp.name, comp.url);
            adLinksRow.appendChild(el(
              'a',
              {
                href: adLibrarySearchUrl(query),
                target: '_blank',
                rel: 'noopener noreferrer',
                class: 'dg-meta-ad-link',
              },
              `Search Meta ads for “${query}” (all advertisers) ↗`
            ));
            adLinksRow.appendChild(el(
              'a',
              { href: '/#loop-research', class: 'dg-link-exact-page' },
              'Link their exact page'
            ));
          }
          card.appendChild(adLinksRow);
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
      li.appendChild(el('strong', {}, shopUrls.length ? 'Draft a post from your website' : 'Add your website in My workspace'));
      li.appendChild(el('p', {}, shopUrls.length
        ? 'Jump straight to Studio to create an ad or social post with your own photos and words.'
        : 'Paste your website URL or photo in Studio to generate custom posts for your business.'));
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

  async function runOwnWatchlistCheck() {
    if (ownState.busy) return;
    const btn = document.getElementById('dgCheckNowBtn');
    const st = document.getElementById('dgCheckStatus');
    ownState.busy = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Checking…'; }
    if (st) { st.textContent = 'Checking public pages across your watchlist (free, 0 runs)…'; st.hidden = false; }
    try {
      const resp = await fetch('/api/v1/competitors/check', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_version: ownState.version,
          expected_owner: ownState.ownerId || undefined,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = typeof data.detail === 'string'
          ? data.detail
          : (resp.status === 409 ? 'Your workspace changed in another tab. Reloading…' : 'Could not check your watchlist right now.');
        if (st) { st.textContent = msg; st.hidden = false; }
        if (resp.status === 409 && ownState.ownerId && window.museAccount?.loadWorkspace) {
          const fresh = await window.museAccount.loadWorkspace(ownState.ownerId).catch(() => null);
          if (fresh) renderOwnWorkspaceDigest(fresh.document || {}, fresh.version || 0);
        }
        return;
      }
      if (data.auto_check && data.auto_check.enabled === true) {
        ownState.autoCheck = data.auto_check;
        ownState.checksMap = data.competitor_checks || {};
      }
      const nextDoc = {
        ...(ownState.wsDoc || {}),
        preferences: {
          ...((ownState.wsDoc && ownState.wsDoc.preferences) || {}),
          competitor_checks: data.competitor_checks || {},
        },
      };
      if (st) { st.textContent = 'Watchlist checked. 0 runs used.'; st.hidden = false; }
      renderOwnWorkspaceDigest(nextDoc, data.version);
      try { window.museSellerMemory?.reload?.(); } catch {}
    } catch {
      if (st) { st.textContent = 'Could not reach Muse right now. Try again shortly.'; st.hidden = false; }
    } finally {
      ownState.busy = false;
      if (btn) { btn.disabled = false; btn.textContent = 'Check now (free)'; }
    }
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
      ownState.ownerId = s.ownerId || null;
      ownState.autoCheck = null;
      ownState.checksMap = null;
      write('digestStatus', 'Loading your personal workspace…');
      let wsDoc = {};
      let wsVersion = 0;
      try {
        const wsPromise = (window.museAccount && typeof window.museAccount.loadWorkspace === 'function')
          ? window.museAccount.loadWorkspace(s.ownerId).catch(() => null)
          : Promise.resolve(null);
        const checksPromise = fetch('/api/v1/competitors/checks', { credentials: 'same-origin' })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null);
        const [loaded, checksResp] = await Promise.all([wsPromise, checksPromise]);
        if (!guard.isCurrent()) return;
        wsDoc = loaded?.document || {};
        wsVersion = Number(loaded?.version || 0);
        if (checksResp && checksResp.auto_check && checksResp.auto_check.enabled === true) {
          ownState.autoCheck = checksResp.auto_check;
          ownState.checksMap = checksResp.competitor_checks || {};
        }
      } catch {
        if (!guard.isCurrent()) return;
        wsDoc = {};
        wsVersion = 0;
      }
      renderOwnWorkspaceDigest(wsDoc, wsVersion);
      return;
    }

    // Guest or explicit Sample shop view -> render clearly labeled Sample digest
    if (typeof document !== 'undefined') {
      document.title = 'Weekly competitor digest for small shops | Muse Growth Studio';
      const listingCb = document.querySelector('#digestDraftForm input[name="draftTopic"][value="listing_changes"]');
      const listingLabel = listingCb?.parentElement;
      if (listingLabel && listingLabel.lastChild && listingLabel.lastChild.nodeType === 3) {
        listingLabel.lastChild.textContent = ' New and removed listings or pages';
      }
    }
    ownState.autoCheck = null;
    ownState.checksMap = null;
    clearAutoCheckBar();
    setCheckControls(false, '');
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
    document.getElementById('dgCheckNowBtn')?.addEventListener('click', runOwnWatchlistCheck);
    if (window.museModes?.subscribe) window.museModes.subscribe(applyMode);
    if (window.museModes?.resolve) await applyMode(await window.museModes.resolve());
    else await applyMode();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
