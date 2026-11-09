'use strict';
// PostHog product analytics. Off unless the server returns a project key (/api/v1/analytics/config).
// Privacy: no session recordings, Do Not Track honoured, profiles only for signed-in users (by
// account ID, never email), and URL fragments/queries are stripped because Supabase email links
// carry sign-in tokens there. Typed text is never sent; autocapture records clicks, not inputs.
(() => {
  if (window.museTrack) return;
  const queue = [];
  let ready = false;
  let enabled = null;

  const cleanUrl = (value) => {
    if (typeof value !== 'string' || !value) return value;
    try {
      const url = new URL(value, location.origin);
      const billing = url.searchParams.get('billing');
      url.hash = '';
      url.search = billing ? `?billing=${encodeURIComponent(billing)}` : '';
      return url.toString();
    } catch { return value.split(/[?#]/)[0]; }
  };
  const URL_PROPS = ['$current_url', '$referrer', '$initial_current_url', '$initial_referrer', '$pathname'];
  function scrub(event) {
    if (!event?.properties) return event;
    for (const key of URL_PROPS) if (key in event.properties) event.properties[key] = cleanUrl(event.properties[key]);
    if (event.$set) for (const key of URL_PROPS) if (key in event.$set) event.$set[key] = cleanUrl(event.$set[key]);
    if (event.$set_once) for (const key of URL_PROPS) if (key in event.$set_once) event.$set_once[key] = cleanUrl(event.$set_once[key]);
    return event;
  }

  function send(name, props) {
    if (enabled === false) return;
    if (!ready) { if (queue.length < 50) queue.push([name, props]); return; }
    try { window.posthog.capture(name, props || {}); } catch { /* analytics never breaks the app */ }
  }
  window.museTrack = (name, props = {}) => send(String(name).slice(0, 80), props);

  function loadPostHog(key, host) {
    // Official PostHog loader stub: queues calls until /static/array.js arrives.
    /* eslint-disable */
    !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once unregister identify setPersonProperties group reset get_distinct_id alias set_config opt_in_capturing opt_out_capturing has_opted_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
    /* eslint-enable */
    window.posthog.init(key, {
      api_host: host,
      person_profiles: 'identified_only',
      capture_pageview: true,
      capture_pageleave: true,
      autocapture: { dom_event_allowlist: ['click', 'submit'] },
      disable_session_recording: true,
      respect_dnt: true,
      before_send: scrub,
      sanitize_properties: (props) => scrub({ properties: props }).properties,
    });
    window.posthog.register({ app: 'muse-growth-studio', page: location.pathname });
    ready = true;
    queue.splice(0).forEach(([name, props]) => send(name, props));
  }

  // Identify by account ID only; forget the person on sign-out.
  let identified = null;
  window.addEventListener('account-change', (event) => {
    if (!ready) return;
    const user = event.detail?.user;
    try {
      if (user?.id && user.id !== identified) { window.posthog.identify(user.id, { email_verified: !!user.email_verified }); identified = user.id; }
      else if (!user && identified) { window.posthog.reset(); identified = null; }
    } catch { /* ignore */ }
  });

  // Any element with data-track="name" reports a named click (CTAs, plan buttons).
  document.addEventListener('click', (event) => {
    const target = event.target.closest?.('[data-track]');
    if (target) send('cta_clicked', { cta: target.getAttribute('data-track'), page: location.pathname });
  }, true);

  fetch('/api/v1/analytics/config', { credentials: 'same-origin' })
    .then((response) => (response.ok ? response.json() : { enabled: false }))
    .then((config) => {
      enabled = config?.enabled === true && typeof config.key === 'string' && typeof config.host === 'string';
      if (!enabled) { queue.length = 0; return; }
      loadPostHog(config.key, config.host);
      const billing = new URLSearchParams(location.search).get('billing');
      if (billing === 'success' || billing === 'cancelled') send('checkout_returned', { result: billing });
    })
    .catch(() => { enabled = false; queue.length = 0; });
})();
