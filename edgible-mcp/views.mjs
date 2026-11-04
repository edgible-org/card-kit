// MCP Apps views: small HTML pages that hosts supporting the MCP Apps extension (Claude, Claude
// Desktop, VS Code Copilot, and others) show inside the chat, beside a tool's text answer. Hosts
// without it ignore them and show the text, which stays complete on its own.
// Spec: https://modelcontextprotocol.io/extensions/apps/overview (protocol 2026-01-26).
// Each view is one self-contained page: no external scripts, styles or fonts, so it needs no CSP.

export const UI_MIME = 'text/html;profile=mcp-app';
export const WHATS_RUNNING_URI = 'ui://edgible/whats-running.html';

export const WHATS_RUNNING_HTML = String.raw`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What's running</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #e5e5ea; --card: #f7f7f9;
    --ok: #1f9d55; --bad: #d64545; --warn: #c27c0e; --idle: #8e8e93; --chip: #ececf1; --link: #0a66c2;
  }
  :root[data-theme="dark"] {
    --bg: #1c1c1e; --fg: #f2f2f7; --muted: #a1a1a6; --line: #38383a; --card: #2c2c2e;
    --ok: #34c37a; --bad: #ff6b6b; --warn: #f0b13c; --idle: #8e8e93; --chip: #3a3a3c; --link: #64a8ff;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #1c1c1e; --fg: #f2f2f7; --muted: #a1a1a6; --line: #38383a; --card: #2c2c2e;
      --ok: #34c37a; --bad: #ff6b6b; --warn: #f0b13c; --idle: #8e8e93; --chip: #3a3a3c; --link: #64a8ff;
    }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--fg); }
  body { font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 14px 16px 16px; }
  header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 16px; margin: 0; }
  .sub { color: var(--muted); font-size: 12px; }
  .summary { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0 12px; }
  .pill { background: var(--chip); border-radius: 999px; padding: 3px 10px; font-size: 12px; }
  .pill b { font-weight: 600; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 14px 0 6px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 8px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; min-width: 0; }
  .row { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--idle); }
  .dot.ok { background: var(--ok); } .dot.bad { background: var(--bad); } .dot.warn { background: var(--warn); }
  .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .state { margin-left: auto; font-size: 12px; color: var(--muted); white-space: nowrap; }
  .meta { color: var(--muted); font-size: 12px; margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { background: var(--chip); border-radius: 6px; padding: 1px 6px; color: var(--fg); }
  a.host { display: block; margin-top: 6px; color: var(--link); font-size: 12px; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
  a.host:hover { text-decoration: underline; }
  .why { margin-top: 6px; font-size: 12px; color: var(--bad); overflow-wrap: anywhere; }
  .devices { display: flex; gap: 8px; flex-wrap: wrap; }
  .device { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 6px 10px; display: flex; align-items: center; gap: 8px; }
  .empty, .wait { color: var(--muted); padding: 8px 0; }
  footer { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; color: var(--muted); font-size: 12px; gap: 8px; flex-wrap: wrap; }
  button { font: inherit; font-size: 12px; background: var(--chip); color: var(--fg); border: 1px solid var(--line); border-radius: 8px; padding: 4px 10px; cursor: pointer; }
  button:disabled { opacity: .6; cursor: default; }
</style>
</head>
<body>
<div id="root"><p class="wait">Checking your apps…</p></div>
<script>
(function () {
  var nextId = 1, pending = {}, last = null;
  var root = document.getElementById('root');

  function send(msg) { window.parent.postMessage(msg, '*'); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: '2.0', id: id, method: method, params: params || {} });
    return new Promise(function (ok, fail) { pending[id] = { ok: ok, fail: fail }; });
  }
  function notify(method, params) { send({ jsonrpc: '2.0', method: method, params: params || {} }); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function theme(ctx) { if (ctx && ctx.theme) document.documentElement.setAttribute('data-theme', ctx.theme); }
  function resize() {
    var r = document.documentElement.getBoundingClientRect();
    notify('ui/notifications/size-changed', { width: Math.ceil(r.width), height: Math.ceil(document.body.scrollHeight) });
  }
  function open(url) {
    request('ui/open-link', { url: url }).catch(function () { window.open(url, '_blank', 'noopener'); });
  }

  function appDot(a) {
    if (a.deviceOffline || a.works === 'no') return 'bad';
    if (a.works === 'yes') return 'ok';
    return 'warn';
  }
  function appState(a) {
    if (a.deviceOffline) return 'device offline';
    if (a.works === 'yes') return 'working';
    if (a.works === 'no') return 'needs attention';
    return a.status || 'not checked';
  }
  var AUTH = { none: 'open to anyone', org: 'your organisation', 'api-key': 'API key' };

  function render(v) {
    last = v;
    root.textContent = '';
    if (!v || !v.apps) { root.appendChild(el('p', 'empty', 'Nothing to show: see the text answer.')); resize(); return; }
    var head = el('header');
    head.appendChild(el('h1', null, 'What’s running in ' + (v.organization || 'your organisation')));
    head.appendChild(el('span', 'sub', 'signed in as ' + (v.account || '?') + (v.connector ? ', via ' + v.connector : '')));
    root.appendChild(head);

    var ok = v.apps.filter(function (a) { return appDot(a) === 'ok'; }).length;
    var bad = v.apps.filter(function (a) { return appDot(a) === 'bad'; }).length;
    var online = v.devices.filter(function (d) { return d.status === 'online'; }).length;
    var sum = el('div', 'summary');
    [[v.apps.length, v.apps.length === 1 ? 'app' : 'apps'], [ok, 'working'], [bad, 'need attention'],
     [online + ' of ' + v.devices.length, 'devices online']].forEach(function (p) {
      var s = el('span', 'pill'); s.appendChild(el('b', null, String(p[0]))); s.appendChild(document.createTextNode(' ' + p[1])); sum.appendChild(s);
    });
    root.appendChild(sum);

    root.appendChild(el('h2', null, 'Apps'));
    if (!v.apps.length) root.appendChild(el('p', 'empty', 'No apps published yet.'));
    var grid = el('div', 'grid');
    v.apps.forEach(function (a) {
      var c = el('div', 'card');
      var r = el('div', 'row');
      r.appendChild(el('span', 'dot ' + appDot(a)));
      r.appendChild(el('span', 'name', a.name));
      r.appendChild(el('span', 'state', appState(a)));
      c.appendChild(r);
      var m = el('div', 'meta');
      if (a.device) m.appendChild(el('span', 'tag', a.device));
      (a.auth || []).forEach(function (x) { m.appendChild(el('span', 'tag', AUTH[x] || x)); });
      c.appendChild(m);
      (a.hostnames || []).forEach(function (h) {
        var link = el('a', 'host', h);
        if (a.protocol === 'https') { link.href = 'https://' + h; link.addEventListener('click', function (e) { e.preventDefault(); open('https://' + h); }); }
        c.appendChild(link);
      });
      if (appDot(a) !== 'ok' && a.evidence) c.appendChild(el('div', 'why', a.evidence));
      grid.appendChild(c);
    });
    root.appendChild(grid);

    root.appendChild(el('h2', null, 'Devices'));
    var devs = el('div', 'devices');
    v.devices.forEach(function (d) {
      var x = el('div', 'device');
      x.appendChild(el('span', 'dot ' + (d.status === 'online' ? 'ok' : d.status === 'offline' ? 'bad' : '')));
      x.appendChild(el('span', 'name', d.name));
      x.appendChild(el('span', 'sub', d.status + (d.agentVersion ? ', agent ' + d.agentVersion : '')));
      devs.appendChild(x);
    });
    if (!v.devices.length) devs.appendChild(el('p', 'empty', 'No devices yet.'));
    root.appendChild(devs);

    var foot = el('footer');
    foot.appendChild(el('span', null, 'Checked ' + new Date(v.checkedAt || Date.now()).toLocaleTimeString() +
      (v.system ? ' · ' + v.system + ' Edgible system apps not shown' : '')));
    var btn = el('button', null, 'Check again');
    btn.addEventListener('click', function () {
      btn.disabled = true; btn.textContent = 'Checking…';
      request('tools/call', { name: 'whats_running', arguments: last && last.filter ? last.filter : {} })
        .then(function (res) { render(res && res.structuredContent ? res.structuredContent : last); })
        .catch(function () { btn.disabled = false; btn.textContent = 'Check again'; });
    });
    foot.appendChild(btn);
    root.appendChild(foot);
    resize();
  }

  window.addEventListener('message', function (ev) {
    var m = ev.data;
    if (!m || m.jsonrpc !== '2.0') return;
    if (m.id != null && pending[m.id] && !m.method) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.fail(m.error); else p.ok(m.result);
      return;
    }
    if (m.method === 'ui/notifications/tool-result') {
      var r = m.params || {};
      if (r.structuredContent) render(r.structuredContent);
      else { root.textContent = ''; root.appendChild(el('p', 'empty', 'See the text answer.')); resize(); }
    } else if (m.method === 'ui/notifications/host-context-changed') {
      theme(m.params);
    }
  });

  request('ui/initialize', {
    protocolVersion: '2026-01-26',
    appInfo: { name: 'edgible-whats-running', version: '1' },
    appCapabilities: {},
  }).then(function (res) {
    theme(res && res.hostContext);
    notify('ui/notifications/initialized');
    resize();
  });
})();
</script>
</body>
</html>`;
