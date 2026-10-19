// edgible-mcp's write tools, offered only with --allow-write (see edgible-mcp.mjs): deploy, move
// and remove Edgible app cards on any device in the organisation, without a shell on that device. A card becomes one
// self-contained Compose file (its card.env settings written in, the small files it mounts
// carried inside as configs), and Edgible runs it on the device as a managed docker-compose
// app. Moves use `edgible app move`. Every change asks the person first ("needs confirmation"),
// and every action is written to a record that `activity` reads back.
//
// First slice: app cards with one published app and no secrets. Cards with secrets wait for
// a design that keeps them out of the Compose file (Edgible's organisation secrets).
// Runs where the `edgible` CLI is logged in, and needs `docker compose` to resolve a card.

import { AsyncLocalStorage } from 'node:async_hooks';
import { execFile, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { appendFile, mkdir, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import path from 'node:path';
import YAML from 'yaml';
import { z } from 'zod';

const STATE = process.env.EDGIBLE_MCP_STATE || path.join(homedir(), '.edgible-mcp');
const RECORD = path.join(STATE, 'activity.jsonl');
// Who is calling, for the record: over HTTP, each request runs inside actor.run(name, ...).
export const actor = new AsyncLocalStorage();
const REPO = 'edgible-org/cards';
const NAME = /^[a-z][a-z0-9-]{0,62}$/;
const PATH_ENV = [...new Set([
  '/opt/homebrew/bin', '/usr/local/bin', path.join(homedir(), '.local/bin'),
  ...(process.env.PATH || '').split(':'), '/usr/bin', '/bin', '/usr/sbin', '/sbin',
].filter(Boolean))].join(':');
const ENV = { ...process.env, PATH: PATH_ENV, NO_COLOR: '1', EDGIBLE_NO_UPDATE_NOTIFIER: '1', EDGIBLE_NO_INTERACTIVE: '1' };

// ---------- Helpers ----------

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { env: ENV, maxBuffer: 32 << 20, timeout: opts.timeout || 10 * 60 * 1000, cwd: opts.cwd },
      (err, stdout, stderr) => resolve({ code: err ? (typeof err.code === 'number' ? err.code : 1) : 0, stdout: String(stdout), stderr: String(stderr) }));
  });
}

async function edgibleJson(args, timeout = 120000) {
  const r = await run('edgible', args, { timeout });
  try { return JSON.parse(r.stdout); } catch { throw new Error(`edgible ${args.join(' ')} failed: ${(r.stderr || r.stdout).trim().slice(0, 400)}`); }
}

const text = (obj) => ({ content: [{ type: 'text', text: typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2) }] });

const needs = (reasons) => ({
  status: 'needs confirmation',
  reasons,
  how: `Ask the person, in their words. Only if they agree, call again with the same arguments and confirm: [${reasons.map((r) => JSON.stringify(r.token)).join(', ')}].`,
});

const refused = (reason) => ({ status: 'refused', reason });

// The error an edgible command reports, without its banners and warnings.
function cliError(r) {
  const out = `${r.stdout}\n${r.stderr}`;
  const m = out.match(/"message":\s*"((?:[^"\\]|\\.)*)"/);
  if (m) return m[1];
  return out.split('\n').filter((l) => l.trim() && !/^\s*(⚠|Using )/.test(l)).join(' ').trim().slice(-300);
}

// The record: one JSON line per action, so a person (or `activity`) can read what happened.
async function record(entry) {
  await mkdir(STATE, { recursive: true });
  await appendFile(RECORD, JSON.stringify({ at: new Date().toISOString(), by: actor.getStore() || process.env.EDGIBLE_MCP_AGENT || 'assistant', ...entry }) + '\n');
}

async function readRecord() {
  const lines = existsSync(RECORD) ? (await readFile(RECORD, 'utf8')).trim().split('\n').filter(Boolean) : [];
  return lines.map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}

// What these tools deployed, from the record: app name -> its latest deploy entry, unless removed since.
async function ours() {
  const mine = {};
  for (const e of await readRecord()) {
    if (e.tool === 'deploy_card' && e.result === 'created') mine[e.app] = e;
    if (e.tool === 'remove_card' && e.result === 'removed') delete mine[e.app];
  }
  return mine;
}

async function devices() {
  const list = await edgibleJson(['device', 'list', '--json']);
  return Array.isArray(list) ? list : list.devices || [];
}

async function apps() {
  const list = await edgibleJson(['app', 'list', '--json']);
  return (Array.isArray(list) ? list : list.applications || []).filter((a) => a.subtype !== 'ingest');
}

// EDGIBLE_MCP_DEVICES (names, comma separated) limits every change to those devices, such as a
// test machine while the tools are reachable from outside. Unset, any device in the organisation.
const ALLOWED = (process.env.EDGIBLE_MCP_DEVICES || '').split(',').map((s) => s.trim()).filter(Boolean);
function notAllowed(...names) {
  const out = ALLOWED.length ? names.filter((n) => !ALLOWED.includes(n)) : [];
  return out.length ? `this server may only change apps on ${ALLOWED.join(', ')}, not ${out.join(', ')}` : null;
}
const appDevices = (a) => (a.devices || []).map((d) => d.name);

async function findDevice(nameOrId) {
  const d = (await devices()).find((x) => x.name === nameOrId || x.id === nameOrId);
  if (!d) throw new Error(`no device named ${nameOrId} in this organisation`);
  return d;
}

// ---------- A card, as one self-contained Compose file ----------

async function fetchCard(card) {
  const dir = await mkdtemp(path.join(tmpdir(), 'edgible-mcp-'));
  const res = await fetch(`https://codeload.github.com/${REPO}/tar.gz/refs/heads/main`);
  if (!res.ok) throw new Error(`fetching ${REPO}: HTTP ${res.status}`);
  const tar = spawn('tar', ['-xz', '--strip-components=2', '-C', dir, `cards-main/${card}`], { env: ENV });
  const done = new Promise((ok) => tar.on('close', ok));
  for await (const chunk of res.body) tar.stdin.write(chunk);
  tar.stdin.end();
  await done;
  const yml = await readFile(path.join(dir, 'card.yml'), 'utf8').catch(() => null);
  if (!yml) { await rm(dir, { recursive: true, force: true }); return null; }
  return { dir, card: YAML.parse(yml) };
}

function parseEnv(textIn) {
  const values = {};
  const generated = new Set();
  let comment = '';
  for (const line of textIn.split('\n')) {
    if (/^\s*#/.test(line)) { comment += line; continue; }
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m) {
      values[m[1]] = m[2].replace(/^"(.*)"$/, '$1').replace(/^'(.*)'$/, '$1');
      if (/Generate with:/i.test(comment)) generated.add(m[1]);
    }
    comment = '';
  }
  return { values, generated };
}

function setEnvLines(textIn, changes) {
  const done = new Set();
  const out = textIn.split('\n').map((line) => {
    const m = line.match(/^([A-Z0-9_]+)=/);
    if (m && m[1] in changes) { done.add(m[1]); return `${m[1]}=${changes[m[1]]}`; }
    return line;
  });
  const missing = Object.keys(changes).filter((k) => !done.has(k));
  if (missing.length) throw new Error(`card.env has no setting called ${missing.join(', ')}`);
  return out.join('\n');
}

const isSecretKey = (key, generated) => generated.has(key) || /(PASSWORD|SECRET|TOKEN|KEY|SALT)/.test(key);

// Compose interpolates "$" in the file it runs, so every literal "$" is written as "$$".
const escapeDollars = (v) => (typeof v === 'string' ? v.replaceAll('$', '$$$$')
  : Array.isArray(v) ? v.map(escapeDollars)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, escapeDollars(x)])) : v);

async function selfContained({ dir, card }, { app, device, choices }) {
  const composeFiles = ['docker-compose.yml', 'compose.yml', 'compose.yaml', 'docker-compose.yaml'].filter((f) => existsSync(path.join(dir, f)));
  if (composeFiles.length !== 1) return refused(`this first version handles cards with one Compose file; ${card.metadata.name} has ${composeFiles.length}`);
  const envText = await readFile(path.join(dir, 'card.env'), 'utf8').catch(() => '');
  const { values, generated } = parseEnv(envText);
  const secretKeys = Object.keys(values).filter((k) => isSecretKey(k, generated));
  if (secretKeys.length) return refused(`${card.metadata.name} has secrets (${secretKeys.join(', ')}). This first version only deploys cards without secrets, so no password ever sits in a Compose file; secrets need Edgible's organisation secrets, which come next.`);
  const changes = { ...choices };
  if ('DEVICE' in values) changes.DEVICE = device;
  await writeFile(path.join(dir, 'card.env'), setEnvLines(envText, changes));
  const r = await run('docker', ['compose', '--env-file', 'card.env', '-f', composeFiles[0], 'config', '--format', 'json'], { cwd: dir });
  if (r.code) {
    const missing = [...r.stderr.matchAll(/set ([A-Z0-9_]+) in card\.env/g)].map((m) => m[1]);
    return refused(missing.length ? `the card needs these settings in choices: ${[...new Set(missing)].join(', ')}` : `the card's Compose file did not resolve: ${r.stderr.trim().slice(0, 300)}`);
  }
  const resolved = JSON.parse(r.stdout);
  const configs = {};
  const real = await realpath(dir);   // macOS reports /var/folders as /private/var/folders
  for (const [svcName, svc] of Object.entries(resolved.services || {})) {
    const keep = [];
    for (const v of svc.volumes || []) {
      if (v.type !== 'bind') { keep.push(v); continue; }
      const src = v.source;
      const inside = src.startsWith(real + path.sep) || src.startsWith(dir + path.sep);
      const isFile = inside && existsSync(src) && (await stat(src)).isFile();
      if (!isFile) return refused(`service ${svcName} mounts ${inside ? path.relative(real, src) : src} from the machine, which a remote deploy cannot carry`);
      const key = `${svcName}-${path.basename(src)}`.replace(/[^a-zA-Z0-9_.-]/g, '-');
      configs[key] = { content: await readFile(src, 'utf8') };
      svc.configs = [...(svc.configs || []), { source: key, target: v.target }];
    }
    svc.volumes = keep;
    if (!svc.volumes.length) delete svc.volumes;
    // `docker compose config` writes ports in the long form; Edgible's CLI reads the short one.
    if (svc.ports) {
      svc.ports = svc.ports.map((p) => (typeof p !== 'object' ? String(p)
        : `${p.host_ip ? `${p.host_ip}:` : ''}${p.published ? `${p.published}:` : ''}${p.target}${p.protocol && p.protocol !== 'tcp' ? `/${p.protocol}` : ''}`));
    }
  }
  // Names follow the new project, so nothing collides with the card's own project on the device.
  for (const group of ['volumes', 'networks']) {
    for (const v of Object.values(resolved[group] || {})) { if (v && typeof v === 'object') delete v.name; }
  }
  resolved.name = app;
  if (Object.keys(configs).length) resolved.configs = { ...(resolved.configs || {}), ...configs };
  return { status: 'ok', compose: YAML.stringify(escapeDollars(resolved), { lineWidth: 0 }) };
}

// ---------- Tools ----------

async function deployCard({ card, app, device, choices = {}, hostnames = [], confirm = [] }) {
  app = app || card;
  if (!NAME.test(card) || !NAME.test(app)) return refused('card and app names are lowercase letters, digits and dashes');
  const target = await findDevice(device);
  if (notAllowed(target.name)) return refused(notAllowed(target.name));
  if (target.status !== 'online') return refused(`device ${target.name} is ${target.status}`);
  if ((await apps()).some((a) => a.name === app)) return refused(`an app called ${app} already exists in this organisation`);
  const fetched = await fetchCard(card);
  if (!fetched) return refused(`no card called ${card} in ${REPO}`);
  try {
    const { card: meta } = fetched;
    if (meta.metadata?.type !== 'app') return refused(`${card} is a pattern card; this first version deploys app cards`);
    const published = (meta.applications || []).filter((a) => a.published !== false);
    if (published.length !== 1) return refused(`${card} publishes ${published.length} apps; this first version handles cards with one`);
    if ((meta.applications || []).some((a) => a.native)) return refused(`${card} installs on the machine itself (native), which these tools never do`);
    const auth = (published[0].authModes || ['org']).join(',');
    const reasons = [];
    if (auth.split(',').includes('none')) reasons.push({ token: 'public', reason: `${app} will be open to anyone on the internet (auth mode none), as the card intends${hostnames.length ? `, at ${hostnames.join(', ')}` : ''}.` });
    const missing = reasons.filter((r) => !confirm.includes(r.token));
    if (missing.length) return needs(missing);

    const built = await selfContained(fetched, { app, device: target.name, choices });
    if (built.status !== 'ok') return built;
    const home = path.join(STATE, 'apps', app);
    await mkdir(home, { recursive: true });
    const file = path.join(home, 'docker-compose.yml');
    await writeFile(file, `# ${card} card as one self-contained file, deployed by edgible-mcp. Do not edit by hand.\n${built.compose}`);

    const args = ['app', 'create', 'docker-compose', '--non-interactive', '--name', app, '--compose-file', file,
      '--device-id', target.id, '--auth-modes', auth, '--tag', `card=${card}`, '--tag', 'by=edgible-mcp', '--no-wait'];
    if (hostnames.length) args.push('--hostnames', hostnames.join(','));
    const r = await run('edgible', args, { timeout: 180000 });
    if (r.code) {
      await record({ tool: 'deploy_card', card, app, device: target.name, result: 'failed', detail: cliError(r) });
      return { status: 'failed', reason: cliError(r) };
    }
    const created = (await apps()).find((a) => a.name === app);
    await record({ tool: 'deploy_card', card, app, device: target.name, auth, hostnames: created?.hostnames || hostnames, choices: Object.keys(choices), confirmed: confirm, result: 'created' });
    return { status: 'created', app, device: target.name, auth, hostnames: created?.hostnames || [], next: 'Edgible is starting it on the device; card_status reports when it answers, usually within two minutes.' };
  } finally {
    await rm(fetched.dir, { recursive: true, force: true });
  }
}

async function moveCard({ app, to, confirm = [] }) {
  const current = (await apps()).find((a) => a.name === app);
  if (!current) return refused(`no app called ${app}`);
  if (current.subtype !== 'docker-compose') return refused(`${app} is a "${current.subtype}" app, which Edgible cannot move by itself: it needs the app started on the new machine first`);
  const target = await findDevice(to);
  if (notAllowed(target.name, ...appDevices(current))) return refused(notAllowed(target.name, ...appDevices(current)));
  if (target.status !== 'online') return refused(`device ${target.name} is ${target.status}`);
  if (!confirm.includes('move')) {
    return needs([{ token: 'move', reason: `Moving ${app} to ${target.name}: Edgible starts it there, switches traffic over, then stops the old copy. Expect up to half a minute when it does not answer.` }]);
  }
  const started = Date.now();
  const r = await run('edgible', ['app', 'move', app, '--to', target.id, '--wait-timeout', '600'], { timeout: 660000 });
  const seconds = Math.round((Date.now() - started) / 1000);
  const ok = r.code === 0 && /"completed"|completed/.test(r.stdout);
  await record({ tool: 'move_card', app, to: target.name, confirmed: confirm, result: ok ? 'moved' : 'failed', seconds, detail: ok ? undefined : cliError(r) });
  return ok ? { status: 'moved', app, to: target.name, seconds, next: 'card_status checks it answers from the new device.' }
    : { status: 'failed', reason: cliError(r) };
}

async function removeCard({ app, confirm = [] }) {
  const mine = await ours();
  if (!mine[app]) return refused(`${app} was not deployed by these tools, so they will not remove it`);
  const live = (await apps()).find((a) => a.name === app);
  const where = live ? appDevices(live) : [mine[app].device];
  if (notAllowed(...where)) return refused(notAllowed(...where));
  if (!confirm.includes('remove')) {
    return needs([{ token: 'remove', reason: `Removing ${app}: it stops answering at ${(mine[app].hostnames || []).join(', ') || 'its address'}, and Edgible removes it from ${mine[app].device}. Its data on that device goes with it.` }]);
  }
  const r = await run('edgible', ['app', 'delete', app, '--yes'], { timeout: 300000 });
  await record({ tool: 'remove_card', app, confirmed: confirm, result: r.code ? 'failed' : 'removed', detail: r.code ? cliError(r) : undefined });
  return r.code ? { status: 'failed', reason: cliError(r) } : { status: 'removed', app };
}

async function cardStatus({ app }) {
  const list = await apps();
  const pick = app ? list.filter((a) => a.name === app) : list.filter((a) => a.subtype === 'docker-compose');
  if (!pick.length) return app ? refused(`no app called ${app}`) : 'No managed apps in this organisation.';
  const out = [];
  for (const a of pick) {
    const device = (a.devices || []).map((d) => d.name).join(', ') || 'unknown';
    const host = (a.hostnames || [])[0];
    let answers = null;
    if (host && (a.status === 'deployed')) {
      const c = await run('curl', ['-s', '-o', '/dev/null', '-m', '10', '-w', '%{http_code}', `https://${host}/`], { timeout: 20000 });
      answers = c.stdout || 'no answer';
    }
    out.push({ app: a.name, status: a.status, device, hostnames: a.hostnames, https: answers, kind: a.subtype });
  }
  return out;
}

async function activity({ limit = 20 }) {
  const entries = (await readRecord()).slice(-limit);
  if (!entries.length) return 'These tools have not done anything yet.';
  return entries.map((e) => {
    const when = e.at.replace('T', ' ').slice(0, 16) + ' UTC';
    const what = e.tool === 'deploy_card' ? `deployed the ${e.card} card as ${e.app} on ${e.device}`
      : e.tool === 'move_card' ? `moved ${e.app} to ${e.to}${e.seconds ? ` (${e.seconds}s)` : ''}`
      : e.tool === 'remove_card' ? `removed ${e.app}` : e.tool;
    const asked = e.confirmed?.length ? `, after the person agreed (${e.confirmed.join(', ')})` : '';
    return `${when}: ${e.by} ${what}${asked}: ${e.result}${e.detail ? ` (${e.detail})` : ''}`;
  }).join('\n');
}

export const WRITE_INSTRUCTIONS = 'Deploy, move and remove Edgible app cards on any device in the organisation, without a shell on that device: Edgible runs each card as a managed app. When a result says "needs confirmation", put each reason to the person in their own words, and call again with confirm only after they agree. Never confirm on their behalf. activity shows what these tools did. Use find and describe to choose a card.';

// The tools that change things, on any MCP server; the combined edgible server adds them with --allow-write.
export function registerWriteTools(server) {
  const wrap = (fn) => async (args) => {
    try { return text(await fn(args)); } catch (err) { return { isError: true, ...text(`Failed: ${err.message}`) }; }
  };
  server.registerTool('deploy_card', {
    title: 'Deploy an Edgible app card on a device',
    description: 'Deploy an Edgible app card (from edgible-org/cards) on any online device in the organisation. The card becomes one self-contained Compose file, and Edgible runs it on that device as a managed app and publishes it with the card\'s auth mode. This first version handles app cards with one published app and no secrets, and refuses others with the reason. Returns "needs confirmation" before publishing anything open to anyone.',
    inputSchema: {
      card: z.string().describe('The card, such as static-site'),
      device: z.string().describe('The Edgible device to run it on, by name'),
      app: z.string().optional().describe('The app name, which sets its address; defaults to the card name'),
      choices: z.record(z.string(), z.string()).optional().describe('card.env settings, such as {"STATIC_SITE_SOURCE": "https://…/main.tar.gz"}'),
      hostnames: z.array(z.string()).optional().describe('The person\'s own domain names to attach, such as ["www.example.com"]'),
      confirm: z.array(z.string()).optional().describe('Tokens from an earlier "needs confirmation" result, only after the person agreed'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }, wrap(deployCard));
  server.registerTool('move_card', {
    title: 'Move an app to another device',
    description: 'Move a managed app to another online device with `edgible app move`: Edgible starts it there, switches traffic, then stops the old copy, with up to half a minute of downtime. Always returns "needs confirmation" first.',
    inputSchema: {
      app: z.string().describe('The app to move'),
      to: z.string().describe('The device to move it to, by name'),
      confirm: z.array(z.string()).optional().describe('["move"], only after the person agreed'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }, wrap(moveCard));
  server.registerTool('remove_card', {
    title: 'Remove an app these tools deployed',
    description: 'Remove an app that deploy_card deployed: Edgible stops it and removes it from its device. Refuses anything else. Always returns "needs confirmation" first.',
    inputSchema: {
      app: z.string().describe('The app to remove'),
      confirm: z.array(z.string()).optional().describe('["remove"], only after the person agreed'),
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
  }, wrap(removeCard));
  server.registerTool('card_status', {
    title: 'Status of managed apps',
    description: 'Each managed app (or one, by name): its status, the device it runs on, its addresses, and whether its first address answers over HTTPS.',
    inputSchema: { app: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  }, wrap(cardStatus));
  server.registerTool('activity', {
    title: 'What these tools did',
    description: 'A plain record of every deploy, move and removal these tools made: when, which app and device, whether the person agreed first, and the result.',
    inputSchema: { limit: z.number().int().positive().max(200).optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, wrap(activity));
  return server;
}

export { ALLOWED, RECORD, STATE };
