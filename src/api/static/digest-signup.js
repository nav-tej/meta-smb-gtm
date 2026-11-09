'use strict';
// Email digest sign-up on /digest. Shown only when the server can send email; double opt-in.
(() => {
  const $ = (id) => document.getElementById(id);
  const NOTICES = {
    confirmed: ['Your weekly digest is confirmed. The first email arrives next Monday.', ''],
    unsubscribed: ['You are unsubscribed. No more digest emails will be sent.', ''],
    'link-invalid': ['That email link is no longer valid. Sign up again below if you still want the digest.', 'warn'],
  };
  const params = new URLSearchParams(location.search);
  const result = params.get('email');
  const notice = NOTICES[result];
  if (notice) {
    const node = $('digestEmailNotice');
    node.textContent = notice[0];
    node.className = `dg-status dg-email-notice ${notice[1]}`.trim();
    node.hidden = false;
    params.delete('email');
    try { history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '')); } catch {}
    try { window.museTrack?.('digest_email_link', { result }); } catch {}
  }

  const section = $('digestSignup');
  const form = $('digestSignupForm');
  const status = $('digestSignupStatus');
  if (!section || !form) return;
  fetch('/api/v1/digest/subscription', { credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : { available: false }))
    .then(async (data) => {
      if (data?.available !== true) return;
      section.hidden = false;
      try {
        const snap = await window.museAccount?.ready?.();
        if (snap?.user?.email && !form.email.value) form.email.value = snap.user.email;
      } catch {}
    })
    .catch(() => {});

  const say = (text, error = false) => { status.textContent = text; status.className = `dg-sub-status${error ? ' error' : ''}`; };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const email = form.email.value.trim();
    const competitors = [...form.querySelectorAll('input[name="shop"]')].map((i) => i.value.trim()).filter(Boolean);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { say('Enter a valid email address.', true); form.email.focus(); return; }
    if (!competitors.length) { say('Add at least one competitor shop link.', true); form.querySelector('input[name="shop"]').focus(); return; }
    const button = form.querySelector('button');
    button.disabled = true; say('Sending your confirmation email…');
    try {
      const response = await fetch('/api/v1/digest/subscribe', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, competitors }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'We could not sign you up right now. Try again later.');
      say(data.message || 'Check your inbox to confirm.');
      try { window.museTrack?.('digest_subscribe_submitted', { shops: competitors.length }); } catch {}
    } catch (error) { say(error.message, true); }
    finally { button.disabled = false; }
  });
})();
