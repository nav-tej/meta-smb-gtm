'use strict';
// Weekly Market Digest: renders the weekly digest, monitor log and daily brief that muse-shell.js
// loads once per page. Every value is written with textContent; nothing here calls a model.
(() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, className = '', text = null) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== null && text !== undefined) node.textContent = String(text);
    return node;
  };
  const safeHref = (href, fallback) => (typeof href === 'string' && /^\/(?!\/)/.test(href) ? href : fallback);
  const fmtDay = (iso) => {
    const d = new Date(`${String(iso || '').slice(0, 10)}T12:00:00Z`);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };
  const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

  async function loadDirect() {
    const get = async (url) => { try { const r = await fetch(url, { credentials: 'same-origin' }); return r.ok ? await r.json() : null; } catch { return null; } };
    const [log, digest, brief] = await Promise.all([get('/api/v1/monitor?limit=1'), get('/api/v1/weekly-digest'), get('/api/v1/daily-brief')]);
    return { run: log?.runs?.[0] || null, log, digest, brief };
  }

  function renderHero(digest, brief) {
    const link = $('dgHeroLink');
    const checks = Number(digest?.checks) || 0;
    const top = Array.isArray(digest?.highlights) ? digest.highlights[0] : '';
    const focus = brief?.focus || brief?.move;
    link.hidden = true;
    if (top) {
      $('dgHeroTitle').textContent = top;
      $('dgHeroBody').textContent = digest.highlights[1] ? `Also this week: ${digest.highlights[1]}.` : 'See what else changed below.';
      $('dgHeroSource').textContent = `From ${plural(checks, 'competitor check')} this week.`;
      link.href = '/portal#loop-research';
      link.textContent = 'See your watchlist →';
      link.hidden = false;
    } else if (focus?.title) {
      $('dgHeroTitle').textContent = String(focus.title);
      $('dgHeroBody').textContent = String(focus.reason || '');
      $('dgHeroSource').textContent = checks
        ? 'No competitor changes were logged this week, so this is the top-ranked move from your daily brief.'
        : 'No competitor checks ran this week, so this is the top-ranked move from your daily brief.';
      const href = safeHref(focus.href, '/create');
      link.href = href;
      link.textContent = href.startsWith('/create') ? 'Make this post →' : 'Open →';
      link.hidden = false;
    } else {
      $('dgHeroTitle').textContent = 'No insight available yet';
      $('dgHeroBody').textContent = 'Run a competitor check from the portal to start this week’s change log.';
      $('dgHeroSource').textContent = '';
    }
  }

  function renderStats(digest) {
    const kinds = digest?.by_kind || {};
    const rows = [
      [Number(digest?.checks) || 0, 'competitor checks'],
      [Number(digest?.total_changes) || 0, 'changes found'],
      [Number(kinds.new_listing) || 0, 'new listings'],
      [Number(kinds.price_change) || 0, 'price changes'],
    ];
    $('dgStats').replaceChildren(...rows.map(([value, label]) => {
      const li = el('li');
      li.append(el('strong', '', value), el('span', '', label));
      return li;
    }));
  }

  function renderCompetitors(shell, digest) {
    const watch = Array.isArray(shell?.watchlist) ? shell.watchlist : [];
    const fromDigest = Array.isArray(digest?.competitors) ? digest.competitors : [];
    const names = [...new Set([...watch.map((w) => w.name), ...fromDigest.map((c) => c.name)])];
    const paused = shell?.pausedCompetitors ? shell.pausedCompetitors() : {};
    const checks = Number(digest?.checks) || 0;
    const grid = $('dgCompetitors');
    grid.replaceChildren();
    for (const name of names) {
      const saved = watch.find((w) => w.name === name);
      const week = fromDigest.find((c) => c.name === name);
      let badges;
      let lines;
      let source;
      if (week && week.changes > 0) {
        badges = shell?.changeBadges ? shell.changeBadges(week.counts) : [['new', plural(week.changes, 'change')]];
        lines = week.highlights || [];
        source = 'From this week’s competitor checks';
      } else if (checks) {
        badges = [['none', 'No changes this week']];
        lines = [];
        source = `Compared in ${plural(checks, 'check')} this week`;
      } else {
        badges = saved ? [[saved.status === 'new' ? 'new' : 'first', saved.badge]] : [];
        lines = saved?.note ? [saved.note] : [];
        source = 'From the saved Nov 3 snapshot';
      }
      if (paused[name]) badges = [...badges, ['paused', 'Alerts paused']];
      const card = el('article', `dg-card${paused[name] ? ' paused' : ''}`);
      const head = el('div', 'dg-card-head');
      const badgeBox = el('span', 'dg-badges');
      badges.forEach(([tone, label]) => badgeBox.appendChild(el('span', `ms-badge ${tone}`, label)));
      head.append(el('h3', '', name), badgeBox);
      card.appendChild(head);
      if (saved?.where) card.appendChild(el('p', 'dg-where', saved.where));
      if (lines.length) {
        const ul = el('ul', 'dg-lines');
        lines.slice(0, 3).forEach((line) => ul.appendChild(el('li', '', line)));
        card.appendChild(ul);
      }
      card.appendChild(el('p', 'dg-source', source));
      grid.appendChild(card);
    }
    if (!names.length) grid.appendChild(el('p', 'dg-note', 'No competitors on your watchlist yet.'));
  }

  function renderRecos(brief) {
    const list = $('dgRecos');
    list.replaceChildren();
    const moves = Array.isArray(brief?.action_items) ? brief.action_items.slice(0, 3) : [];
    if (!moves.length) {
      list.hidden = true;
      $('dgRecoSource').textContent = 'Today’s ideas could not be loaded. The ranked ideas in your portal still work.';
      return;
    }
    list.hidden = false;
    for (const move of moves) {
      const li = el('li', `dg-reco ${move.impact || ''}`);
      li.appendChild(el('span', `ms-chip ${move.impact === 'high' ? 'high' : ''}`, `${move.impact || 'medium'} impact`));
      li.appendChild(el('strong', '', move.title));
      if (move.reason) li.appendChild(el('p', '', move.reason));
      const href = safeHref(move.href, '/create');
      const go = el('a', 'dg-reco-go', href.startsWith('/create') ? 'Make this post →' : 'Open →');
      go.href = href;
      li.appendChild(go);
      if (move.source) li.appendChild(el('span', 'dg-reco-source', move.source));
      list.appendChild(li);
    }
    $('dgRecoSource').textContent = String(brief.source || '');
    // Lets muse-shell add Accept / Dismiss / Archive / Adjust to each idea.
    window.dispatchEvent(new CustomEvent('muse:brief-ready'));
  }

  async function start() {
    const shell = window.museShell;
    const status = $('digestStatus');
    const loaded = shell?.signals ? await shell.signals() : await loadDirect();
    const { digest, brief, log } = loaded;
    if (digest?.week_start && digest?.week_end) $('digestWeek').textContent = `Week of ${fmtDay(digest.week_start)} – ${fmtDay(digest.week_end)}`;
    renderHero(digest, brief);
    renderStats(digest);
    renderCompetitors(shell, digest);
    renderRecos(brief);
    $('dgNote').textContent = [digest?.note, log?.note].filter(Boolean).join(' ');
    if (!digest && !brief) status.textContent = 'Couldn’t reach the server, so this shows the saved Nov 3 snapshot. Reload to try again.';
    else status.hidden = true;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
