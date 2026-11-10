'use strict';
// Email digest sign-up on /digest. Shown only when the server can send email; double opt-in.
// Revision 4: Account required to subscribe; frequency and topic controls.
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
    if (node) {
      node.textContent = notice[0];
      node.className = `dg-status dg-email-notice ${notice[1]}`.trim();
      node.hidden = false;
      params.delete('email');
      try { history.replaceState(null, '', location.pathname + (params.size ? `?${params}` : '')); } catch {}
      try { window.museTrack?.('digest_email_link', { result }); } catch {}
    }
  }

  const section = $('digestSignup');
  const form = $('digestSignupForm');
  const status = $('digestSignupStatus');
  const gate = $('digestAccountGate');
  const info = $('digestAccountInfo');
  const signInBtn = $('digestSignInBtn');
  if (!section || !form) return;

  let currentUser = null;

  function updateAccountState(snap) {
    currentUser = snap?.user || null;
    if (!currentUser) {
      if (gate) gate.hidden = false;
      if (info) info.hidden = true;
      form.hidden = true;
    } else {
      if (gate) gate.hidden = true;
      if (info) info.hidden = false;
      form.hidden = false;

      const userEmailEl = $('digestUserEmail');
      const hiddenEmail = $('digestHiddenEmail');
      if (userEmailEl) userEmailEl.textContent = currentUser.email;
      if (hiddenEmail) hiddenEmail.value = currentUser.email;

      const remaining = Number.isFinite(snap?.usage?.remaining) ? snap.usage.remaining : 3;
      const runsNotice = $('digestRunsNotice');
      if (runsNotice) {
        if (remaining <= 0) {
          runsNotice.innerHTML = '0 runs remaining this month. <a href="/#pricing">Get more runs</a>. (Digest paused until runs return)';
        } else if (remaining === 1) {
          runsNotice.innerHTML = '1 run remaining this month. <a href="/#pricing">Get more runs</a>. (Digest pauses automatically at 0 runs)';
        } else {
          runsNotice.textContent = `${remaining} runs remaining this month. (Digest pauses automatically at 0 runs)`;
        }
      }

      // Prefill competitor shop inputs from workspace if available
      try {
        const competitors = snap?.workspace?.competitors || snap?.workspace?.onboarding?.competitors || [];
        const shopInputs = form.querySelectorAll('input[name="shop"]');
        if (Array.isArray(competitors) && competitors.length > 0) {
          shopInputs.forEach((inp, idx) => {
            if (!inp.value.trim() && competitors[idx]) {
              const compUrl = typeof competitors[idx] === 'string' ? competitors[idx] : competitors[idx].url || '';
              if (compUrl) inp.value = compUrl;
            }
          });
        }
      } catch (_) {}
    }
  }

  if (signInBtn) {
    signInBtn.addEventListener('click', () => {
      try {
        window.museAccount?.open?.('signup', 'Sign in or create a free account to subscribe to your weekly competitor digest.');
      } catch (_) {}
    });
  }

  window.addEventListener('account-change', (e) => updateAccountState(e.detail));
  window.addEventListener('muse:account-change', (e) => updateAccountState(e.detail));

  fetch('/api/v1/digest/subscription', { credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : { available: false }))
    .then(async (data) => {
      if (data?.available !== true && !location.search.includes('preview_digest')) return;
      section.hidden = false;
      try { window.museTrack?.('digest_prompt_shown', { surface: 'digest' }); } catch {}
      try {
        const snap = await window.museAccount?.ready?.();
        updateAccountState(snap);
      } catch {
        updateAccountState(null);
      }
    })
    .catch(() => {});

  const say = (text, error = false) => {
    if (!status) return;
    status.textContent = text;
    status.className = `dg-sub-status${error ? ' error' : ''}`;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!currentUser) {
      say('A free Muse account is required to subscribe.', true);
      try { window.museAccount?.open?.('signup'); } catch (_) {}
      return;
    }

    const email = (currentUser.email || '').trim();
    const competitors = [...form.querySelectorAll('input[name="shop"]')]
      .map((i) => i.value.trim())
      .filter(Boolean);

    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      say('Please ensure your account has a valid email address.', true);
      return;
    }
    if (!competitors.length) {
      say('Add at least one competitor shop link.', true);
      const firstShop = form.querySelector('input[name="shop"]');
      if (firstShop) firstShop.focus();
      return;
    }

    const frequency = form.frequency?.value || 'weekly';
    const topics = [...form.querySelectorAll('input[name="topic"]:checked')].map((i) => i.value);

    try {
      localStorage.setItem('muse.digest_preferences', JSON.stringify({ frequency, topics }));
    } catch (_) {}

    const button = form.querySelector('button[type="submit"]') || form.querySelector('button');
    if (button) button.disabled = true;
    say('Sending your confirmation email…');

    try {
      const response = await fetch('/api/v1/digest/subscribe', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, competitors }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'We could not sign you up right now. Try again later.');
      }
      say(data.message || 'Check your inbox to confirm.');
      try {
        window.museTrack?.('digest_subscribed', {
          surface: 'digest',
          frequency: frequency,
          topics: topics.join(','),
          shops: competitors.length,
        });
      } catch (_) {}
    } catch (error) {
      say(error.message, true);
    } finally {
      if (button) button.disabled = false;
    }
  });
})();
