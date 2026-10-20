// edgible-mcp's write tools, offered only with --allow-write (see edgible-mcp.mjs): deploy, move
// and remove Edgible app cards on any device in the organisation, without a shell on that device. A card becomes one
// self-contained Compose file (its card.env settings written in, the small files it mounts
// carried inside as configs), and Edgible runs it on the device as a managed docker-compose
// app. Moves use `edgible app move`. Every change asks the person first ("needs confirmation"),
// and every action is written to a record that `activity` reads back.
//
// App cards with one published app. Secrets: a card that declares them (card.yml secrets:) makes
// its internal ones on the device itself, in its <card>-secrets service, so no value is ever in
// the Compose file. A human one, such as an admin's password, the person needs once: deploy_card
// makes a first-use password, hands it to that service through an Edgible organisation secret
// (<app>-first-use), and shows it once in its result, for the person to change at first sign-in.
// Cards with secrets still in card.env, and cards needing a key the person brings, are refused.
// Runs where the `edgible` CLI is logged in, and needs `docker compose` to resolve a card.

import { AsyncLocalStorage } from 'node:async_hooks';
import { execFile, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
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
// The card-secrets image that takes a seed, used when deploy_card hands it a first-use password.
const CARD_SECRETS_IMAGE = 'ghcr.io/edgible-org/card-secrets:0.1.2';
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

async function selfContained({ dir, card }, { app, device, choices, seeds = [], port }) {
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
  // `docker compose config` already writes every literal "$" as "$$", ready for Compose to read again.
  const out = resolved;
  if (seeds.length) {
    // The service that makes the card's secrets takes each seed from Edgible, by ${NAME}. Edgible's
    // agent can start an app once before it has the secret's value; :? makes that start fail, so
    // the service never makes its own value in place of the seed.
    const maker = Object.values(out.services || {}).find((s) => s.environment?.CARD_SECRETS);
    if (!maker) return refused(`${card.metadata.name} declares secrets but has no card-secrets service to make them`);
    maker.image = CARD_SECRETS_IMAGE;
    for (const name of seeds) maker.environment[name] = `\${${name}:?the first-use value from Edgible}`;
  }
  // The host port Edgible forwards to: the one the card's app port is published on.
  const hostPort = Object.values(out.services || {}).flatMap((s) => s.ports || [])
    .map((p) => String(p).match(/(?:^|:)(\d+):(\d+)(?:\/tcp)?$/)).find((m) => m && Number(m[2]) === Number(port));
  if (!hostPort) return refused(`${card.metadata.name}'s Compose file does not publish its app port ${port}`);
  return { status: 'ok', compose: YAML.stringify(out, { lineWidth: 0 }), port: Number(hostPort[1]) };
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
    const declared = Object.entries(meta.secrets || {});
    const brought = declared.filter(([, s]) => s.kind === 'external' || s.kind === 'shared').map(([n]) => n);
    if (brought.length) return refused(`${card} needs ${brought.join(', ')}, which this version cannot take yet: a key the person brings, or one shared between machines`);
    const human = declared.filter(([, s]) => s.kind === 'human');
    const auth = (published[0].authModes || ['org']).join(',');
    const reasons = [];
    if (auth.split(',').includes('none')) reasons.push({ token: 'public', reason: `${app} will be open to anyone on the internet (auth mode none), as the card intends${hostnames.length ? `, at ${hostnames.join(', ')}` : ''}.` });
    const missing = reasons.filter((r) => !confirm.includes(r.token));
    if (missing.length) return needs(missing);

    const built = await selfContained(fetched, { app, device: target.name, choices, seeds: human.map(([n]) => n), port: published[0].port });
    if (built.status !== 'ok') return built;
    // Each human secret's first-use value, made here and kept by Edgible only until the app's
    // first start makes it on the device; the person changes it at first sign-in.
    const firstUse = human.map(([name, s]) => ({ name, for: s.for || 'a person', value: randomBytes(18).toString('base64url') }));
    const envFrom = [];
    if (firstUse.length) {
      const tmp = await mkdtemp(path.join(tmpdir(), 'edgible-first-use-'));
      try {
        const fromFiles = [];
        for (const f of firstUse) {
          const file = path.join(tmp, f.name);
          await writeFile(file, f.value, { mode: 0o600 });
          fromFiles.push('--from-file', `${f.name}=${file}`);
        }
        const s = await run('edgible', ['secret', 'set', `${app}-first-use`, ...fromFiles], { timeout: 120000 });
        if (s.code) return { status: 'failed', reason: `could not keep the first-use password with Edgible: ${cliError(s)}` };
      } finally {
        await rm(tmp, { recursive: true, force: true });
      }
      for (const f of firstUse) envFrom.push({ name: f.name, secretRef: { secret: `${app}-first-use`, key: f.name } });
    }
    const home = path.join(STATE, 'apps', app);
    await mkdir(home, { recursive: true });
    const file = path.join(home, 'docker-compose.yml');
    await writeFile(file, `# ${card} card as one self-contained file, deployed by edgible-mcp. Do not edit by hand.\n${built.compose}`);

    // A declaration for `edgible stack deploy`, not `edgible app create docker-compose`: the
    // create command first runs `docker compose up` on the machine the CLI runs on, whichever
    // device was chosen, and without the app's organisation secrets.
    const { organization } = await edgibleJson(['whoami', '--json']);
    const access = (hostnames.length ? hostnames : [null]).map((custom, i) => ({
      type: 'https', name: i ? `main-${i + 1}` : 'main', target: { workload: 'main', port: 'main' }, publish: true,
      policies: { auth: { modes: auth.split(',') } }, hostname: custom ? { generated: true, custom } : { generated: true },
    }));
    const declaration = {
      apiVersion: 'v3', kind: 'Application',
      metadata: { name: app, organization: organization.id, description: `The ${card} card, deployed by edgible-mcp`, labels: { card, by: 'edgible-mcp' } },
      spec: {
        placement: { strategy: 'serving-device', deviceSelector: { deviceId: target.id }, migrationPolicy: 'manual' },
        workloads: [{ name: 'main', type: 'compose', ports: [{ name: 'main', containerPort: built.port, protocol: 'tcp' }],
          composeFile: `base64:${Buffer.from(await readFile(file)).toString('base64')}`, ...(envFrom.length ? { envFrom } : {}) }],
        access,
      },
    };
    const stackFile = path.join(home, 'edgible.yml');
    await writeFile(stackFile, YAML.stringify(declaration, { lineWidth: 0 }));
    const r = await run('edgible', ['stack', 'deploy', '-f', stackFile, '--no-wait'], { timeout: 180000 });
    if (r.code) {
      if (firstUse.length) await run('edgible', ['secret', 'delete', `${app}-first-use`, '--yes'], { timeout: 120000 });
      await record({ tool: 'deploy_card', card, app, device: target.name, result: 'failed', detail: cliError(r) });
      return { status: 'failed', reason: cliError(r) };
    }
    const created = (await apps()).find((a) => a.name === app);
    await record({ tool: 'deploy_card', card, app, device: target.name, auth, hostnames: created?.hostnames || hostnames, choices: Object.keys(choices), firstUse: firstUse.map((f) => f.name), confirmed: confirm, result: 'created' });
    const result = { status: 'created', app, device: target.name, auth, hostnames: created?.hostnames || [], next: 'Edgible is starting it on the device; card_status reports when it answers, usually within two minutes.' };
    if (firstUse.length) {
      result.firstUse = firstUse;
      result.next += ' Give the person each first-use password once, now: it is not shown again. They sign in with it and change it at once; the card made every other secret on the device, and nobody knows those.';
    }
    return result;
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
    return needs([{ token: 'remove', reason: `Removing ${app}: it stops answering at ${(mine[app].hostnames || []).join(', ') || 'its address'}, and Edgible removes it from ${mine[app].device}. Its data volumes stay on that device (Edgible does not delete them), so they are there if it is deployed again under the same name.` }]);
  }
  const r = await run('edgible', ['app', 'delete', app, '--yes'], { timeout: 300000 });
  if (!r.code && mine[app].firstUse?.length) await run('edgible', ['secret', 'delete', `${app}-first-use`, '--yes'], { timeout: 120000 });
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
    description: 'Deploy an Edgible app card (from edgible-org/cards) on any online device in the organisation. The card becomes one self-contained Compose file, and Edgible runs it on that device as a managed app and publishes it with the card\'s auth mode. It handles app cards with one published app. A card that declares its secrets makes them on the device; a password a person needs comes back once as firstUse, to give them now. Cards with secrets in card.env, or needing a key the person brings, are refused with the reason. Returns "needs confirmation" before publishing anything open to anyone.',
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
