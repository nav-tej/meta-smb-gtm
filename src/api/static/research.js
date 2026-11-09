'use strict';
(() => {
  const $ = id => document.getElementById(id);
  if (!$('researchForm')) return;
  let result = null;
  let busy = false;
  let readiness = null;
  const status = (text, isBusy = false) => {
    $('researchStatus').textContent = text;
    $('researchStatus').classList.toggle('busy', Boolean(isBusy));
  };
  const isOfflineNow = () => Boolean(window.museShell?.isOffline?.() || (typeof navigator !== 'undefined' && navigator.onLine === false));
  const safeURL = value => { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const node = (tag, text) => { const el = document.createElement(tag); el.textContent = text; return el; };
  const ownerKey = () => 'muse-research:' + (window.museAccount?.getSnapshot?.().user?.id || 'guest');
  function remember() { try { localStorage.setItem(ownerKey(), JSON.stringify({ website: $('researchWebsite').value, direction: $('researchDirection').value, result })); } catch {} }
  function restore() {
    result = null; $('researchWebsite').value = ''; $('researchDirection').value = 'Find smaller businesses serving similar customers. Focus on practical content ideas.';
    try { const saved = JSON.parse(localStorage.getItem(ownerKey()) || 'null'); if (saved) { $('researchWebsite').value = String(saved.website || '').slice(0,500); $('researchDirection').value = String(saved.direction || '').slice(0,1500); if (Array.isArray(saved.result?.targets)) result = saved.result; } } catch {}
    render(); status('Start with your own website. Suggestions run only when you ask.');
  }
  async function liveRequest(path, body) {
    if (isOfflineNow()) throw new Error('You appear to be offline. Your saved research is still here — reconnect and try again.');
    if (readiness?.accounts_required && !window.museAccount?.liveReady?.()) throw new Error('Sign in before running personalized research.');
    const key = $('unlockKey')?.value.trim();
    if (!readiness?.accounts_required && !readiness?.live_unlock_configured && readiness?.default_mode !== 'live') throw new Error('Live research is not enabled on this demo. Explore the saved research, or configure the server first.');
    if (!readiness?.accounts_required && readiness?.default_mode !== 'live' && !key) throw new Error('Open Muse settings below and enter the presenter unlock key to run live research.');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 285000);
    try {
      const response = await fetch('/api/v1/' + path + '?live=true', { method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json', ...(key ? {'X-Demo-Key':key} : {})}, body:JSON.stringify(body), signal:controller.signal });
      let data = {};
      try { data = await response.json(); } catch {}
      if (!response.ok) {
        const detail = typeof data.detail === 'string' && !/<html|traceback/i.test(data.detail) ? data.detail : '';
        if (response.status === 401 || response.status === 403) throw new Error(detail || 'Your session expired before Muse started, so no run was used. Sign in again; your research is still here.');
        if (response.status === 402 || response.status === 429) throw new Error(detail || 'You have reached your current run allowance. Check your plan or wait a moment — your research is still here.');
        if (response.status >= 500) throw new Error(detail || 'Muse is temporarily unavailable right now. No run was used and your previous results are kept.');
        throw new Error(detail || 'Research could not finish. Your previous results are kept.');
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Research timed out and may still be processing. Check completion before running again.');
      if (isOfflineNow() || /failed to fetch|networkerror/i.test(error?.message || '')) throw new Error('You appear to be offline or the server could not be reached. Your previous results are kept.');
      throw error;
    }
    finally { clearTimeout(timer); window.museAccount?.refresh?.().catch(() => {}); window.museShell?.syncCredits?.(); }
  }
  function render() {
    const list = $('researchTargets'); list.replaceChildren();
    if (!result) return;
    list.append(node('p', String(result.business_summary || '')));
    list.append(node('p', 'Research leads · review for relevance'));
    list.append(node('small', String(result.provenance || 'Suggested sites are unverified.')));
    for (const target of result.targets.slice(0,4)) {
      const url = safeURL(target.url); if (!url) continue;
      const card = node('article',''); card.className = 'research-target';
      const link = node('a', String(target.name || url)); link.href=url; link.target='_blank'; link.rel='noopener noreferrer';
      const button = node('button','Research this site'); button.type='button'; button.className='quiet';
      button.addEventListener('click', async () => {
        if (busy) return; busy=true; button.disabled=true; button.setAttribute('aria-busy','true'); status('Reading this site and writing a fresh brief…', true);
        try { const brief=await liveRequest('analyze-competitors',{competitor_url:url,seller_context: String(result.business_summary || '') + '\nSeller direction: ' + $('researchDirection').value,max_urls:30,max_batches:1,batch_size:30});
          const output=$('researchBrief'); output.replaceChildren(node('h3',target.name),node('p',brief.summary || 'Research complete.'));
          const ideas=brief.actionable_insights || [];
          for (const idea of ideas.slice(0,3)) output.append(node('p',typeof idea==='string'?idea:idea.recommendation || idea.title || idea.action || JSON.stringify(idea)));
          status('Fresh brief ready. Review the source site before acting.');
        } catch(error) { status(error.message); } finally { busy=false; button.disabled=false; button.setAttribute('aria-busy','false'); }
      });
      card.append(link,node('p',String(target.reason || '')),button); list.append(card);
    }
    list.append(node('p',String(result.next_move || '')));
    list.append(node('small','Your website was read for these suggestions. Suggested sites are checked only when you choose “Research this site”. Each live action uses a run.'));
  }
  $('researchForm').addEventListener('submit',async event => {
    event.preventDefault(); if (busy) return; busy=true; $('discoverTargets').disabled=true; $('discoverTargets').setAttribute('aria-busy','true'); status('Reading your website and finding a relevant shortlist…', true);
    try { const next=await liveRequest('research-targets',{website:$('researchWebsite').value,direction:$('researchDirection').value,previous_targets:(result?.targets || []).map(t=>t.url).slice(0,8)}); result=next; render(); remember(); status('Shortlist ready. Refine the direction and run again whenever your focus changes.'); }
    catch(error) { status(error.message); } finally { busy=false; $('discoverTargets').disabled=false; $('discoverTargets').setAttribute('aria-busy','false'); }
  });
  async function loadExample() {
    if (busy) return; busy=true;
    try { const response=await fetch('/api/v1/research-example'); if(!response.ok) throw new Error('The example is unavailable.'); result=await response.json(); $('researchWebsite').value='https://nplusalpha.com'; render(); status('Saved live Muse example. No new call made. These are discovery directories, not verified direct competitors.'); }
    catch(error) {status(error.message);} finally {busy=false;}
  }
  $('researchExample').addEventListener('click', loadExample);
  $('researchWebsite').addEventListener('change',()=>{ result=null; render(); $('researchBrief').replaceChildren(); remember(); });
  $('researchDirection').addEventListener('change',remember);
  let owner=null; window.addEventListener('muse:account-change', event=>{ const next=event.detail?.user?.id || null; if(next!==owner){ owner=next; restore(); } });
  restore();
  if (new URLSearchParams(location.search).get('example') === 'nplusalpha') { $('researchWorkspace').open=true; loadExample(); }
  fetch('/api/v1/readiness').then(r=>r.json()).then(data=>{readiness=data;}).catch(()=>{});
})();
