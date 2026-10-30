// platform.js — Base44 platform SPA (login→dashboard→builder→publish) on tokens
(() => {
  'use strict';
  const $ = sel => document.querySelector(sel);
  const $app = () => document.getElementById('root');
  const LS_T = 'b44_token', LS_INC = 'b44_inbox';

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let ME = null, WS = null, CREDITS = null;
  const api = async (path, opts = {}) => {
    const res = await fetch(path, {
      ...opts,
      headers: Object.assign({ 'Content-Type': 'application/json' },
        localStorage.getItem(LS_T) ? { Authorization: 'Bearer ' + localStorage.getItem(LS_T) } : {}, opts.headers || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.message || res.statusText), { status: res.status, data });
    return data;
  };

  const icons = {
    home: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5"/></svg>',
    compass: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5z"/></svg>',
    settings: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v3m0 12.4v3M4.6 4.6l2.1 2.1m10.6 10.6 2.1 2.1M2.8 12h3m12.4 0h3M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1"/></svg>',
    plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 5v14M5 12h14"/></svg>',
    spark: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.5 13.6 8.4 19.5 10 13.6 11.6 12 17.5 10.4 11.6 4.5 10l5.9-1.6z"/></svg>',
    send: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12 20 4l-4 16-4-6-6-1z"/></svg>',
    code: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m8 7-5 5 5 5m8-10 5 5-5 5"/></svg>',
    globe: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.6 4 5.8 4 9s-1.3 6.4-4 9c-2.7-2.6-4-5.8-4-9s1.3-6.4 4-9z"/></svg>',
    copy: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/></svg>',
    back: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 5l-7 7 7 7"/></svg>',
  };

  let toastT;
  const toast = m => {
    let t = document.querySelector('.toast');
    if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); }
    t.textContent = m; t.classList.add('show');
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2400);
  };

  const fmtAgo = ts => {
    const s = (Date.now() - ts) / 1000;
    return s < 60 ? 'just now' : s < 3600 ? Math.round(s / 60) + 'm ago' : s < 86400 ? Math.round(s / 3600) + 'h ago' : Math.round(s / 86400) + 'd ago';
  };

  // ---------- shared chrome ----------
  const sidebar = active => `
    <aside class="sidebar">
      <div class="logo"><span class="mark">${icons.spark}</span>Base44</div>
      <div class="ws-box"><span class="ws-avatar">${esc((ME.name || 'R')[0].toUpperCase())}</span>
        <div><div class="ws-name">${esc(WS?.name || 'Workspace')}</div><div class="ws-plan">Free plan</div></div></div>
      <nav class="nav">
        <a href="#/" class="${active === 'home' ? 'active' : ''}">${icons.home} Home</a>
        <a href="#/explore" class="${active === 'explore' ? 'active' : ''}">${icons.compass} Explore</a>
        <a href="#/settings" class="${active === 'settings' ? 'active' : ''}">${icons.settings} Settings</a>
      </nav>
      <div class="credits"><b style="font-size:12.5px">Daily credits</b>
        <div style="color:var(--stone-500)" id="credit-line">${CREDITS ? CREDITS.used + ' / ' + CREDITS.total + ' used' : '…'}</div>
        <div class="bar"><i style="width:${CREDITS ? Math.min(100, CREDITS.used / CREDITS.total * 100) : 0}%"></i></div></div>
    </aside>`;

  const setCredits = c => {
    CREDITS = c;
    const line = $('#credit-line');
    if (line) line.textContent = `${c.used} / ${c.total} used`;
    const bar = $('.credits .bar i');
    if (bar) bar.style.width = Math.min(100, c.used / c.total * 100) + '%';
  };

  // ---------- login ----------
  const viewLogin = mode => `
    <div class="auth-wrap">
      <div class="auth-card">
        <div style="display:flex;justify-content:center;margin-bottom:14px"><span class="logo-mark" style="width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,var(--orange-400),var(--orange-600));color:#fff">${icons.spark}</span></div>
        <h1 class="auth-title">${mode === 'signup' ? 'Create your account' : 'Log in to Base44'}</h1>
        <p class="auth-sub">Build useful apps, fast with Base44.</p>
        <form class="login-form" data-mode="${esc(mode || 'login')}">
          <div class="field"><label class="label">Email</label>
            <input class="input" name="email" type="email" placeholder="you@company.com" required></div>
          <div class="field"><label class="label">Password</label>
            <input class="input" name="password" type="password" placeholder="••••••••" required minlength="4"></div>
          <button class="btn btn-primary btn-lg btn-full" style="margin-top:6px">${mode === 'signup' ? 'Create account' : 'Log in'}</button>
        </form>
        <div class="divider">or</div>
        <button class="btn btn-outline btn-lg btn-full" data-demo>${icons.spark} Try the demo workspace</button>
        <p class="auth-foot">${mode === 'signup' ? 'Already have an account?' : 'New here? It takes seconds —'} <a data-switch mode="${mode === 'signup' ? 'login' : 'signup'}"><b>${mode === 'signup' ? 'Log in' : 'Sign up'}</b></a></p>
      </div>
    </div>`;

  const doLogin = async form => {
    const fd = new FormData(form);
    const mode = form.dataset.mode;
    const email = (fd.get('email') || '').toString();
    const password = (fd.get('password') || '').toString();
    if (localStorage.getItem(LS_INC)) try { await api('/api/auth/logout', { method: 'POST' }); } catch {}
    const d = await api(mode === 'signup' ? '/api/auth/signup' : '/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    localStorage.setItem(LS_T, d.access_token);
    await boot();
    location.hash = '#/';
  };

  // ---------- dashboard ----------
  const viewHome = apps => `
    <div class="shell">${sidebar('home')}
      <div class="main">
        <div class="topbar"><b style="font-size:15px">${esc(WS?.name)}</b>
          <div style="margin-left:auto;display:flex;gap:8px">
            <a class="btn btn-ghost" href="#/explore">${icons.compass} Explore</a>
            <button class="btn btn-primary" data-empty-app>${icons.plus} New App</button>
          </div></div>
        <div class="content">
          <div class="hero"><h1>Build useful apps,<br><span style="font-family:var(--font-brand);font-weight:500">fast with Base44.</span></h1>
            <p>Describe what you want. The agent builds the full app — data, logic and UI — in minutes.</p>
            <form class="prompt" data-prompt><textarea name="prompt" placeholder="e.g. A CRM to track my clients…" required></textarea><button class="btn btn-brand send">${icons.spark} Create</button></form>
          </div>
          <h2 class="section-title" style="font-size:16px;margin-bottom:12px">Your apps <span class="wb-badge" style="margin-left:6px">${apps.length}</span></h2>
          <div class="grid">${apps.map(appCard).join('')}</div>
        </div>
      </div>
    </div>`;

  const appCard = a => `
    <button class="app-card" data-open="${a.id}">
      <div class="top"><span class="app-icon" style="background:${(a.theme && a.theme.accent) || '#4d33de'}">${esc((a.name || 'A')[0].toUpperCase())}</span>
        <span class="vis ${a.state === 'published' ? 'published' : ''}">${a.state === 'published' ? 'Live' : 'Preview'}</span></div>
      <div><div class="app-name">${esc(a.name)}</div><div class="app-desc">${esc((a.spec && a.spec.summary) || 'Empty app')}</div></div>
      <div class="app-meta"><span>${esc(a.visibility)}</span><span>${fmtAgo(a.updated * 1000)}</span></div>
    </button>`;

  // ---------- explore ----------
  const TPLS = [
    ['CRM', 'Track customers, deals and follow-ups in one clean pipeline.', 'A CRM to track my clients and deals', '#4d33de'],
    ['Task Manager', 'Projects, tasks, statuses and a daily focus view.', 'A task manager with kanban board', '#ff773c'],
    ['Blog', 'Write posts with a rich editor and share publicly.', 'A blog to publish articles', '#3b51e5'],
    ['Expense Tracker', 'Log spend, monthly budget charts and export.', 'An expense tracker with categories', '#a6c93b'],
    ['Notes', 'Fast notes with search and pinned items.', 'A notes app with pinned notes', '#f0c84d'],
  ];
  const viewExplore = () => `
    <div class="shell">${sidebar('explore')}
      <div class="main">
        <div class="topbar"><b style="font-size:15px">Explore templates</b></div>
        <div class="content">
          <div class="grid">${TPLS.map(([n, d, p, c]) => `
            <div class="tpl"><div class="card" data-tpl="${esc(p)}">
              <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px"><span class="app-icon" style="background:${c}">${n[0]}</span><b>${n}</b></div>
              <div style="font-size:12.5px;color:var(--fg-muted)">${d}</div></div></div>`).join('')}
          </div>
        </div>
      </div>
    </div>`;

  // ---------- builder ----------
  const TABS = [['preview', 'Preview'], ['code', 'Code'], ['data', 'Data'], ['logs', 'Logs'], ['publish', 'Publish']];
  let app = null, curTab = 'preview', chat = null, curFile = null;
  const viewApp = a => `
    <div class="main" style="height:100vh">
      <div class="work-head">
        <button class="btn btn-ghost" data-go="#/">${icons.back}</button>
        <b style="font-size:14px">${esc(a.name)}</b>
        <span class="vis ${a.state === 'published' ? 'published' : ''}" style="margin-left:4px">${a.state === 'published' ? 'Live' : 'Preview'}</span>
        <div class="tabs">${TABS.map(([k, l]) => `<button class="tab ${curTab === k ? 'active' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>
        <span class="credit-chip" id="credit-chip">${CREDITS ? CREDITS.used + ' / ' + CREDITS.total + ' credits' : ''}</span>
      </div>
      <div class="builder">
        <div class="chat">
          <div class="chat-head"><span class="logo-mark" style="width:22px;height:22px;border-radius:6px;display:grid;place-items:center;background:linear-gradient(135deg,var(--orange-400),var(--orange-600));color:#fff;font-size:11px">${icons.spark}</span>
            <b style="font-size:13px">Base44 agent</b><span class="wb-badge">beta</span></div>
          <div class="chat-body" id="chat-body"></div>
          <form class="chat-input" data-turn><textarea name="message" placeholder="Describe a change…" required></textarea>
            <button class="btn btn-brand">${icons.send}</button></form>
        </div>
        <div class="work">
          <div class="work-body">
            <div class="preview" id="pane-preview">${curTab === 'preview' ? previewIframe(a) : ''}</div>
            <div class="pane ${curTab === 'code' ? '' : 'hidden'}" id="pane-code">${curTab === 'code' ? codePane(a) : ''}</div>
            <div class="pane ${curTab === 'data' ? '' : 'hidden'}" id="pane-data">${curTab === 'data' ? dataPane(a) : ''}</div>
            <div class="pane ${curTab === 'logs' ? '' : 'hidden'}" id="pane-logs">${curTab === 'logs' ? logsPane(a) : ''}</div>
            <div class="pane ${curTab === 'publish' ? '' : 'hidden'}" id="pane-publish">${curTab === 'publish' ? publishPane(a) : ''}</div>
          </div>
        </div>
      </div>
    </div>`;

  const previewIframe = a => `<div class="frame-wrap"><iframe id="pv-frame" data-app="${a.id}" src="/runtime.html#app=${a.id}" title="preview"></iframe></div>`;
  const codePane = a => {
    const files = Object.keys(a.files || {});
    curFile = curFile && files.includes(curFile) ? curFile : files[0];
    return files.length ? `
      <div class="code-tabs">${files.map(f => `<button class="code-file ${f === curFile ? 'active' : ''}" data-file="${esc(f)}">${esc(f)}</button>`).join('')}</div>
      <pre class="code">${esc(a.files[curFile] || '')}</pre>` : '<div class="empty">No code yet — build the app first.</div>';
  };
  const dataPane = a => (a.spec.entities || []).map(e => `
    <div class="panel"><h3 style="font-size:14px">${esc(e.name)}</h3><p class="hint" style="color:var(--fg-muted);font-size:12px;margin-bottom:8px">${e.fields.map(f => esc(f.name) + ' (' + f.type + ')').join(' · ')}</p>
      ${(e.seed || []).map(r => `<div class="entity-row"><span>${r.map(c => esc(String(c))).join(' — ')}</span></div>`).join('') || '<div style="color:var(--stone-500);font-size:12.5px">No records (seed on build)</div>'}</div>`).join('') || '<div class="empty">No entities yet.</div>';
  const logsPane = a => (a.logs || []).map(l => `<div class="logline">${esc(l[1] || l[1])}</div>`).join('') || '<div class="empty">Empty logs.</div>';
  const publishPane = a => `
    <div class="panel publish-wrap">
      <h3 style="font-size:15px">Publish</h3><p class="hint" style="color:var(--fg-muted);font-size:12.5px;margin:4px 0 16px">Your app goes live on <span class="mono">${esc(a.sub_domain)}.base44.app</span></p>
      ${a.state === 'published' ? `
        <div class="pub-url"><span>/p/${esc(a.sub_domain)}</span><button class="btn btn-ghost" data-copy="${esc(a.sub_domain)}" style="height:26px">${icons.copy}</button></div>
        <p style="font-size:12.5px;color:var(--fg-muted);margin-top:10px">Live version v${esc(a.live_version)} — <a data-open="${a.id}">app preview</a></p>`
      : `<button class="btn btn-brand btn-lg" data-publish>${icons.globe} Publish to the web</button>`}
    </div>`;

  const bindApp = a => {
    document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { curTab = b.dataset.tab; renderApp(a); }));
    document.querySelectorAll('[data-file]').forEach(b => b.addEventListener('click', () => { curFile = b.dataset.file; renderApp(a, true); }));
    const p = document.querySelector('[data-publish]');
    if (p) p.addEventListener('click', async () => {
      try {
        const up = await api(`/api/apps/${a.id}/publish`, { method: 'POST' });
        app = up; curTab = 'publish'; toast('App published live 🎉'); renderApp(up);
      } catch (e) { toast(e.message || 'publish failed'); }
    });
    const form = document.querySelector('[data-turn]');
    if (form) form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const inp = form.querySelector('textarea'); const msg = inp.value.trim(); if (!msg) return;
      inp.value = '';
      const body = $('#chat-body');
      body.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(msg)}</div>`);
      chat.push({ role: 'user', text: msg });
      const el = document.createElement('div'); el.className = 'msg ai'; el.innerHTML = '<div class="steps"></div>';
      body.appendChild(el);
      try {
        const r = await api(`/api/apps/${a.id}/agent`, { method: 'POST', body: JSON.stringify({ message: msg }) });
        const steps = el.querySelector('.steps');
        r.steps.forEach((s, i) => {
          const li = document.createElement('div'); li.className = 'step'; li.textContent = s; li.style.animationDelay = (i * .12) + 's';
          steps.appendChild(li);
        });
        setTimeout(async () => {
          const c = await api('/api/credits'); 
          app = await api(`/api/apps/${a.id}`);
          if (curTab === 'code') { const pane = $('#pane-code'); if (pane) pane.innerHTML = codePane(app); }
          if (curTab === 'data') { const pane = $('#pane-data'); if (pane) pane.innerHTML = dataPane(app); }
          if (curTab === 'preview') { const pane = $('#pane-preview'); if (pane) pane.innerHTML = previewIframe(app); }
          const head = document.querySelector('.work-head b'); if (head) head.textContent = app.name;
          setCredits(c);
        }, r.steps.length * 120 + 250);
      } catch (e) { el.innerHTML = `<div>${esc(e.message || 'agent failed')}</div>`; }
    });
  };

  const renderApp = (a, keepChat) => {
    if (!keepChat) { chat = [{ role: 'ai', text: 'This is your app. Ask me for anything — entities, pages, theme, publish.' }]; }
    document.getElementById('root').innerHTML = viewApp(a);
    const body = $('#chat-body');
    (chat || []).forEach(m => body.insertAdjacentHTML('beforeend', `<div class="msg ${m.role === 'user' ? 'user' : 'ai'}">${esc(m.text)}</div>`));
    body.scrollTop = body.scrollHeight;
    bindApp(a);
  };

  // ---------- settings ----------
  const viewSettings = u => `
    <div class="shell">${sidebar('settings')}
      <div class="main"><div class="topbar"><b style="font-size:15px">Settings</b></div>
        <div class="content">
          <div class="panel"><h3 style="font-size:15px">Account</h3>
            <div class="row"><span style="color:var(--fg-muted)">Email</span><b>${esc(u.email)}</b></div>
            <div class="row"><span style="color:var(--fg-muted)">Name</span><b>${esc(u.name)}</b></div>
            <div class="row"><span style="color:var(--fg-muted)">Workspace</span><b>${esc(WS?.name)}</b></div>
            <div class="row"><span style="color:var(--fg-muted)">Plan</span><span class="wb-badge" style="font-size:11px">Free</span></div>
          </div>
          <div class="panel"><h3 style="font-size:15px">Session</h3>
            <div class="row"><span style="color:var(--fg-muted)">Signed in as</span><span class="mono">${esc(u.email)}</span></div>
            <div class="row"><span style="color:var(--fg-muted)">Log out</span><button class="btn btn-outline" data-logout>Log out</button></div>
          </div>
        </div></div></div>`;

  // ---------- router ----------
  const boot = async () => {
    if (!localStorage.getItem(LS_T)) { ME = null; return false; }
    try { ME = await api('/api/me'); const wss = await api('/api/workspaces'); WS = wss[0] || null; CREDITS = await api('/api/credits'); return true; }
    catch (e) { localStorage.removeItem(LS_T); return false; }
  };

  const fresh = async () => {
    if (!(await boot())) { renderLogin('login'); return; }
    const hash = (location.hash || '#/').slice(2);
    if (hash.startsWith('app/')) {
      const id = hash.slice(4);
      try { app = await api(`/api/apps/${id}`); renderApp(app); return; } catch (e) { toast('App not found'); location.hash = '#/'; }
    }
    if (hash === 'explore') { document.getElementById('root').innerHTML = viewExplore(); bindExplore(); return; }
    if (hash === 'settings') { document.getElementById('root').innerHTML = viewSettings(ME); bindSettings(); return; }
    const apps = await api('/api/workspace_apps');
    document.getElementById('root').innerHTML = viewHome(apps);
    bindChrome(apps);
  };
  const bindChrome = apps => {
    document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => { location.hash = '#/app/' + b.dataset.open; }));
    document.querySelectorAll('[data-empty-app]').forEach(b => b.addEventListener('click', async () => { const a = await api('/api/apps', { method: 'POST', body: JSON.stringify({ name: 'Untitled App' }) }); location.hash = '#/app/' + a.id; }));
    const form = document.querySelector('[data-prompt]');
    if (form) form.addEventListener('submit', async e => {
      e.preventDefault();
      const prompt = form.querySelector('textarea').value.trim(); if (!prompt) return;
      try {
        const a = await api('/api/apps', { method: 'POST', body: JSON.stringify({ prompt }) });
        toast('App created — agent is building ' + a.name); location.hash = '#/app/' + a.id;
      } catch (e2) { toast(e2.message || 'failed'); }
    });
  };
  const bindExplore = () => document.querySelectorAll('[data-tpl]').forEach(b => b.addEventListener('click', async () => {
    const a = await api('/api/apps', { method: 'POST', body: JSON.stringify({ prompt: b.dataset.tpl }) });
    location.hash = '#/app/' + a.id;
  }));
  const bindSettings = () => document.querySelectorAll('[data-logout]').forEach(b => b.addEventListener('click', async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch {}
    localStorage.removeItem(LS_T); toast('Logged out'); renderLogin('login');
  }));
  const renderLogin = mode => {
    document.getElementById('root').innerHTML = viewLogin(mode);
    bindLogin(mode);
  };
  const bindLogin = () => {
    document.querySelectorAll('.login-form').forEach(f => f.addEventListener('submit', e => { e.preventDefault(); doLogin(f); }));
    document.querySelectorAll('[data-switch]').forEach(a => a.addEventListener('click', () => renderLogin(a.getAttribute('mode'))));
    document.querySelectorAll('[data-demo]').forEach(b => b.addEventListener('click', async () => {
      const d = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: 'demo@base44.dev', password: 'demo1234' }) });
      localStorage.setItem(LS_T, d.access_token); await boot(); location.hash = '#/';
    }));
  };
  window.addEventListener('hashchange', fresh);
  fresh();
})();
