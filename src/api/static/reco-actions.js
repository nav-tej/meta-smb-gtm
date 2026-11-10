// Home page "Improve" list: makes each ranked idea show what it would look like, and
// shows progress across the list.
//  - a preview thumbnail per idea that opens the saved sample ad dialog (no dead-end click)
//  - a progress strip that reads the Accept / Done / Dismiss / Archive state muse-shell.js
//    already saves under `muse.actions`. This file does not write that state.
// Device-local, read-only. No network calls, no model runs.
// Per-idea generated previews and ROI are specified in docs/launch/ANTIGRAVITY_HERMES_PRD_RESEARCH.md.
(function () {
  'use strict';
  var ACTIONS_KEY = 'muse.actions';

  function readActions() {
    try { var v = JSON.parse(localStorage.getItem(ACTIONS_KEY) || '{}'); return v && typeof v === 'object' ? v : {}; } catch (e) { return {}; }
  }
  function track(name, props) {
    try { if (window.posthog && window.posthog.capture) window.posthog.capture(name, props); } catch (e) { /* never break the page */ }
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function init() {
    var list = document.querySelector('#loop-improve .jr-recos');
    if (!list || list.dataset.recoReady) return;
    list.dataset.recoReady = '1';
    var items = Array.prototype.slice.call(list.children);

    var strip = el('div', 'jr-moves');
    strip.setAttribute('role', 'status');
    var stripText = el('strong');
    var bar = el('div', 'jr-moves-bar');
    var fill = el('span');
    bar.appendChild(fill);
    var stripNote = el('small');
    strip.appendChild(stripText); strip.appendChild(bar); strip.appendChild(stripNote);
    list.parentNode.insertBefore(strip, list);

    function refreshStrip() {
      var all = readActions();
      var done = 0, todo = 0, aside = 0;
      items.forEach(function (li) {
        var rec = all[li.dataset.actionId];
        var status = rec && rec.status;
        if (status === 'done') done += 1;
        else if (status === 'accepted') todo += 1;
        else if (status === 'dismissed' || status === 'archived') aside += 1;
      });
      var open = items.length - aside;
      stripText.textContent = done + ' of ' + open + ' moves done' +
        (todo ? ' · ' + todo + ' on your to-do list' : '') +
        (aside ? ' · ' + aside + ' set aside' : '');
      fill.style.width = (open ? Math.round((done / open) * 100) : 0) + '%';
      stripNote.textContent = done || todo
        ? 'Saved on this device. Mark a move done in My actions once you have posted it.'
        : 'Accept an idea to start tracking. Saved on this device.';
    }
    refreshStrip();
    // muse-shell.js writes the state on click; read it back after its handler has run.
    list.addEventListener('click', function () { setTimeout(refreshStrip, 60); });
    document.addEventListener('click', function (event) {
      if (event.target && event.target.closest && event.target.closest('.ms-drawer, .ms-actions, dialog')) setTimeout(refreshStrip, 60);
    });
    window.addEventListener('storage', function (event) { if (event.key === ACTIONS_KEY) refreshStrip(); });
    window.addEventListener('focus', refreshStrip);

    // Preview thumbnails: reuse the saved ads the gallery already loaded, and its dialog.
    var gallery = document.getElementById('adGallery');
    function attachThumbs() {
      if (!gallery) return;
      var cards = gallery.querySelectorAll('.jr-ad');
      if (!cards.length) return;
      items.forEach(function (li, index) {
        if (li.querySelector('.jr-reco-thumb') || !li.querySelector('a[href^="/create"]')) return;
        var card = cards[index % cards.length];
        var src = card.querySelector('img');
        if (!src || !src.src) return;
        var btn = el('button', 'jr-reco-thumb'); btn.type = 'button';
        btn.setAttribute('aria-label', 'Preview a saved sample ad for this idea');
        var img = document.createElement('img'); img.src = src.src; img.alt = ''; img.loading = 'lazy';
        btn.appendChild(img); btn.appendChild(el('span', '', 'Sample preview'));
        btn.addEventListener('click', function (event) {
          event.stopPropagation();
          card.click();
          track('reco_preview_open', { reco_id: li.dataset.actionId || '', rank: index + 1 });
        });
        li.classList.add('has-thumb');
        li.appendChild(btn);
      });
      refreshStrip();
    }
    attachThumbs();
    if (gallery && window.MutationObserver) {
      new MutationObserver(attachThumbs).observe(gallery, { childList: true });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
