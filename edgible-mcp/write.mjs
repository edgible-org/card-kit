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
// A key the person brings (kind external, such as a model's API key) is an Edgible organisation
// secret they stored once with `edgible secret set`: deploy_card takes it by reference (keys) and
// Edgible hands the value to the device, so it never passes through the conversation. list_keys
// names the stored ones, never their values. Cards with secrets still in card.env are refused.
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
  // A stack deploy's own reason for each application comes first: its last line is only a summary,
  // such as "Deployment failed for 1 of 1 application(s)", which hid an account's app limit.
  const reasons = [...out.matchAll(/"error":\s*"((?:[^"\\]|\\.)*)"(?:,\s*"code":\s*"([A-Z_]+)")?/g)].map((x) => x[2] ? `${x[1]} (${x[2]})` : x[1]);
  if (reasons.length) return reasons.join('; ').slice(0, 600);
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

// A card.env value that stands for a key Edgible fills on the device, replaced by ${NAME} once
// the Compose file is resolved, wherever the card used it.
// A file's text inside the Compose file: Compose would substitute each $ in it, so it is written $$.
const literal = (text) => text.replaceAll('$', '$$$$');

// card.yml's auth modes as an Application declaration names them.
const DECLARED_AUTH = { org: 'edgible-login' };

const keyMark = (name) => `__edgible_key_${name}__`;

async function selfContained({ dir, card }, { app, device, choices, seeds = [], port, keys = [], user = '', published = '' }) {
  const composeFiles = ['docker-compose.yml', 'compose.yml', 'compose.yaml', 'docker-compose.yaml'].filter((f) => existsSync(path.join(dir, f)));
  if (composeFiles.length !== 1) return refused(`this first version handles cards with one Compose file; ${card.metadata.name} has ${composeFiles.length}`);
  const envText = await readFile(path.join(dir, 'card.env'), 'utf8').catch(() => '');
  const { values, generated } = parseEnv(envText);
  const external = new Set(Object.entries(card.secrets || {}).filter(([, s]) => s?.kind === 'external').map(([n]) => n));
  const secretKeys = Object.keys(values).filter((k) => isSecretKey(k, generated) && !external.has(k));
  if (secretKeys.length) return refused(`${card.metadata.name} has secrets (${secretKeys.join(', ')}). This first version only deploys cards without secrets, so no password ever sits in a Compose file; secrets need Edgible's organisation secrets, which come next.`);
  const changes = { ...choices };
  for (const name of keys) changes[name] = keyMark(name);
  if ('DEVICE' in values) changes.DEVICE = device;
  // Who may sign in: a card that names Edgible accounts, such as openclaw's OPENCLAW_USERS, is
  // locked to the person deploying it unless the choices say otherwise, never left open to its
  // own password.
  if ('OPENCLAW_USERS' in values && !values.OPENCLAW_USERS && !choices.OPENCLAW_USERS && user) changes.OPENCLAW_USERS = user;
  // A card that works out its own address from its app's usual name, such as
  // OPENCLAW_URL=https://openclaw.<org>…, gets the address it will really have when the app is
  // named otherwise (agent-vm), or its own page is refused as a foreign origin.
  const compose = await readFile(path.join(dir, composeFiles[0]), 'utf8');
  const label = choices.ORG_LABEL || values.ORG_LABEL;
  const domain = choices.EDGIBLE_DOMAIN || values.EDGIBLE_DOMAIN || 'edgible.app';
  if (published && app !== published && label) {
    for (const m of compose.matchAll(/([A-Z][A-Z0-9_]*_URL): \$\{\1:-https:\/\/([a-z0-9-]+)\.\$\{ORG_LABEL/g)) {
      if (m[2] === published && !values[m[1]] && !choices[m[1]]) changes[m[1]] = `https://${app}.${label}.${domain}`;
    }
  }
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
      configs[key] = { content: literal(await readFile(src, 'utf8')) };
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
  // A service a profile left out (such as a pattern's bundled gateway when it uses a shared one) is
  // not in the resolved file; drop depends_on entries naming it, which the device rejects even
  // when they are required: false.
  for (const svc of Object.values(resolved.services || {})) {
    if (svc?.depends_on && typeof svc.depends_on === 'object' && !Array.isArray(svc.depends_on)) {
      for (const dep of Object.keys(svc.depends_on)) if (!(dep in resolved.services)) delete svc.depends_on[dep];
      if (!Object.keys(svc.depends_on).length) delete svc.depends_on;
    }
  }
  // Names follow the new project, so nothing collides with the card's own project on the device.
  for (const group of ['volumes', 'networks']) {
    for (const v of Object.values(resolved[group] || {})) { if (v && typeof v === 'object') delete v.name; }
  }
  // A config the card's Compose file reads from a file of its own travels inside too.
  for (const [key, cfg] of Object.entries(resolved.configs || {})) {
    if (!cfg?.file) continue;
    const src = cfg.file;
    const inside = src.startsWith(real + path.sep) || src.startsWith(dir + path.sep);
    if (!inside || !existsSync(src)) return refused(`config ${key} reads ${src}, which a remote deploy cannot carry`);
    resolved.configs[key] = { content: literal(await readFile(src, 'utf8')) };
  }
  resolved.name = app;
  if (Object.keys(configs).length) resolved.configs = { ...(resolved.configs || {}), ...configs };
  // `docker compose config` already writes every literal "$" as "$$", ready for Compose to read again.
  let out = resolved;
  for (const name of keys) out = JSON.parse(JSON.stringify(out).replaceAll(keyMark(name), `\${${name}}`));
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

async function deployCard({ card, app, device, choices = {}, keys = {}, hostnames = [], confirm = [] }) {
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
    // An app card, or a pattern card that publishes one app from one machine, such as edgible-agent.
    const published = (meta.applications || []).filter((a) => a.published !== false);
    if (published.length !== 1) return refused(`${card} publishes ${published.length} apps; this version handles cards that publish one`);
    if (Object.keys(meta.places || {}).length > 1) return refused(`${card} runs on ${Object.keys(meta.places).length} machines; this version handles cards on one`);
    if ((meta.applications || []).some((a) => a.native)) return refused(`${card} installs on the machine itself (native), which these tools never do`);
    const declared = Object.entries(meta.secrets || {});
    const shared = declared.filter(([, s]) => s.kind === 'shared').map(([n]) => n);
    if (shared.length) return refused(`${card} needs ${shared.join(', ')}, shared between machines, which this version cannot take yet`);
    // Keys the person brings: each given in keys as an organisation secret, NAME -> "secret:key".
    const external = declared.filter(([, s]) => s.kind === 'external');
    const unknown = Object.keys(keys).filter((n) => !external.some(([e]) => e === n));
    if (unknown.length) return refused(`${card} takes no key called ${unknown.join(', ')}; it takes ${external.map(([n]) => n).join(', ') || 'none'}`);
    const needed = external.filter(([n, s]) => s.required !== false && !keys[n]);
    if (needed.length) {
      return refused(`${card} needs ${needed.map(([n, s]) => `${n}${s.from ? ` (from ${s.from})` : ''}`).join(', ')}. ` +
        'The person stores each once as an Edgible organisation secret, on a computer with the Edgible CLI: ' +
        '`edgible secret set <secret> --from-file key=<file holding the key>`. Or call request_key for a link where they paste it, from any device. Then pass keys, such as ' +
        `{"${needed[0][0]}": "<secret>:key"}. list_keys shows the secrets already stored. Never ask for the key itself in the conversation.`);
    }
    const refs = {};
    for (const [n, ref] of Object.entries(keys)) {
      const [secret, key] = String(ref).split(':');
      if (!/^[a-z0-9][a-z0-9-]*$/.test(secret || '')) return refused(`keys.${n} is "<secret>:<key>", such as "gemini:key"`);
      refs[n] = { secret, key: key || n };
    }
    const human = declared.filter(([, s]) => s.kind === 'human');
    const auth = (published[0].authModes || ['org']).join(',');
    const reasons = [];
    if (auth.split(',').includes('none')) reasons.push({ token: 'public', reason: `${app} will be open to anyone on the internet (auth mode none), as the card intends${hostnames.length ? `, at ${hostnames.join(', ')}` : ''}.` });
    // The AI gateway (the litellm card) also publishes its API as <app>-api on none, where every
    // call needs a key it issued, as the card's Share it step does, and this server keeps its
    // master key, so gateway_key and gateway_spend work with nothing copied by hand.
    const gateway = card === GATEWAY_CARD;
    if (gateway) reasons.push({ token: 'gateway-api', reason: `${app}'s API will also be published as ${app}-api, open to the internet (auth mode none) but answering only calls with a key the gateway issued. This server keeps the gateway's master key, so it can make each app's key and report spending; the person never needs to see it. The gateway is always deployed this way: if they say no, nothing is deployed. Don't offer another way.` });
    const missing = reasons.filter((r) => !confirm.includes(r.token));
    if (missing.length) return needs(missing);

    const signedIn = await edgibleJson(['whoami', '--json']).catch(() => ({}));
    const built = await selfContained(fetched, { app, device: target.name, choices, seeds: human.map(([n]) => n), port: published[0].port, keys: Object.keys(refs), user: signedIn.account || '', published: published[0].name });
    if (built.status !== 'ok') return built;
    // Each human secret's first-use value, made here and kept by Edgible only until the app's
    // first start makes it on the device; the person changes it at first sign-in.
    const firstUse = human.map(([name, s]) => ({ name, for: s.for || 'a person', value: randomBytes(18).toString('base64url') }));
    // A gateway deployed again under a name it had before reuses its kept master key: its old
    // secrets volume, which remove_card leaves on the device, still holds that key, and the
    // card never replaces a secret that exists.
    if (gateway) {
      const kept = await readFile(keptMaster(app), 'utf8').then((s) => s.trim()).catch(() => '');
      const master = firstUse.find((f) => f.name === GATEWAY_MASTER);
      if (kept && master) master.value = kept;
    }
    const envFrom = Object.entries(refs).map(([name, secretRef]) => ({ name, secretRef }));
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
      policies: { auth: { modes: auth.split(',').map((m) => DECLARED_AUTH[m] || m) } }, hostname: custom ? { generated: true, custom } : { generated: true },
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
    let api;
    if (gateway) {
      api = await publishGatewayApi({ app, deviceId: target.id, port: built.port, master: firstUse.find((f) => f.name === GATEWAY_MASTER) });
      if (api.status !== 'ok') return api;
    }
    const created = (await apps()).find((a) => a.name === app);
    await record({ tool: 'deploy_card', card, app, device: target.name, auth, hostnames: created?.hostnames || hostnames, ...(api ? { gateway: api.url } : {}), choices: Object.keys(choices), firstUse: firstUse.map((f) => f.name), keys: Object.fromEntries(Object.entries(refs).map(([n, r]) => [n, `${r.secret}:${r.key}`])), confirmed: confirm, result: 'created' });
    const result = { status: 'created', app, device: target.name, auth, hostnames: created?.hostnames || [], next: 'Edgible is starting it on the device; card_status reports when it answers, usually within two minutes.' };
    if (api) {
      result.gateway = `${api.url}/v1`;
      result.next += ` Its API is ${api.url}/v1. This server keeps the gateway's master key: gateway_key makes each app's key with a budget, and gateway_spend reports spending. Never show or ask for the master key.`;
    }
    const shown = firstUse.filter((f) => !(gateway && f.name === GATEWAY_MASTER));
    if (shown.length) {
      result.firstUse = shown;
      result.next += ' Give the person each first-use password once, now: it is not shown again. They sign in with it and change it at once; the card made every other secret on the device, and nobody knows those.';
      // remove_card leaves an app's volumes on its device, and a card never replaces a secret that
      // exists, so an app deployed again under its old name keeps its old passwords.
      const before = (await readRecord()).some((e) => e.tool === 'remove_card' && e.app === app && e.result === 'removed');
      if (before) result.next += ` ${app} was deployed and removed before, and its data stays on the device: if it is the same device, the old passwords still apply and these first-use ones may not work. Say so to the person.`;
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
  let r = await run('edgible', ['app', 'delete', app, '--yes'], { timeout: 300000 });
  // A delete can time out waiting for a device that already let the app go; it is gone if Edgible no longer lists it.
  if (r.code && !(await apps()).some((a) => a.name === app)) r = { code: 0, stdout: '', stderr: '' };
  if (!r.code && mine[app].firstUse?.length) await run('edgible', ['secret', 'delete', `${app}-first-use`, '--yes'], { timeout: 120000 });
  if (!r.code && mine[app].gateway) await forgetGateway(app);
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

// Key links: request_key makes a one-time link to a page where the person pastes a key, which is
// stored as an organisation secret and never passes through the assistant. The page is served by
// keyPage below, at EDGIBLE_MCP_PAGES_URL (mcp-signin's /pages/ on its sign-in address, behind
// Edgible's org sign-in), and each link works once, for KEY_LINK_MINUTES.
const PAGES_URL = (process.env.EDGIBLE_MCP_PAGES_URL || '').replace(/\/$/, '');
const KEY_LINK_MINUTES = 10;
const keyLinks = new Map(); // token -> { name, secret, key, by, at }
const SECRET_NAME = /^[a-z0-9][a-z0-9-]{0,62}$/;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// A key this server itself uses, such as the AI gateway's master key for gateway_key, is kept in
// its own state (KEYS_DIR, readable by it alone) rather than as an organisation secret.
const KEYS_DIR = path.join(STATE, 'keys');

async function requestKey({ name, secret, keep = 'edgible' }) {
  if (!/^[A-Z][A-Z0-9_]*$/.test(name || '')) return refused('name is the key\'s variable, such as GEMINI_API_KEY');
  if (keep === 'server') {
    if (!PAGES_URL) return { status: 'no link', reason: 'This server has no page for keys (EDGIBLE_MCP_PAGES_URL is not set).' };
    const token = randomBytes(24).toString('base64url');
    keyLinks.set(token, { name, keep, by: actor.getStore() || 'assistant', at: Date.now() });
    return { status: 'link', link: `${PAGES_URL}/key?t=${token}`, expires_in_minutes: KEY_LINK_MINUTES,
      next: `Give the person this link. They paste ${name} there, and this server keeps it for its own use; you never see it.` };
  }
  secret = secret || name.toLowerCase().replace(/_api_key$|_key$/, '').replace(/_/g, '-');
  if (!SECRET_NAME.test(secret)) return refused('secret is lower-case letters, digits and dashes, such as gemini');
  if (!PAGES_URL) {
    return { status: 'no link', reason: 'This server has no page for keys (EDGIBLE_MCP_PAGES_URL is not set).',
      next: `On a computer with the Edgible CLI: edgible secret set ${secret} --from-file key=<file holding the key>. Then deploy with keys {"${name}": "${secret}:key"}.` };
  }
  for (const [t, l] of keyLinks) if (Date.now() - l.at > KEY_LINK_MINUTES * 60000) keyLinks.delete(t);
  const token = randomBytes(24).toString('base64url');
  keyLinks.set(token, { name, secret, key: 'key', by: actor.getStore() || 'assistant', at: Date.now() });
  const exists = (await edgibleJson(['secret', 'list', '--json']).catch(() => [])).some((s) => s.name === secret);
  return { status: 'link', link: `${PAGES_URL}/key?t=${token}`, expires_in_minutes: KEY_LINK_MINUTES, secret, replaces: exists,
    next: `Give the person this link. They open it, sign in with Edgible, and paste the key there; it is stored as organisation secret ${secret}${exists ? ', replacing the one stored now' : ''}, and you never see it. When they say it is done, deploy with keys {"${name}": "${secret}:key"}.` };
}

const page = (title, body) => `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(title)}</title><body style="font:16px system-ui;max-width:32em;margin:3em auto;padding:0 1em;line-height:1.5"><h1>${esc(title)}</h1>${body}`;

// The key page, for edgible-mcp's HTTP mode: GET shows the form, POST stores the key. Only
// mcp-signin reaches this server, and it sets X-MCP-User once Edgible has signed the person in.
export async function keyPage(req, res, url, body) {
  const send = (code, title, html) => res.writeHead(code, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store',
    'content-security-policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'" }).end(page(title, html));
  const user = req.headers['x-mcp-user'];
  if (!user) return send(403, 'Not allowed', '<p>Open this link from your assistant, through Edgible\'s sign-in.</p>');
  const form = req.method === 'POST' ? new URLSearchParams(body || '') : null;
  const token = form ? form.get('t') : url.searchParams.get('t');
  const link = keyLinks.get(token || '');
  if (!link || Date.now() - link.at > KEY_LINK_MINUTES * 60000) {
    return send(410, 'This link has expired', '<p>Ask your assistant for a new one.</p>');
  }
  if (!form) {
    const where = link.keep === 'server' ? 'It is kept by this Edgible server, for its own use, where only it can read it'
      : `It is stored with Edgible as the organisation secret <b>${esc(link.secret)}</b>, and goes from this page to Edgible`;
    return send(200, `Store your ${link.name}`, `<p>Paste the key below. ${where}: your assistant never sees it.</p>
<form method="post" action="key"><input type="hidden" name="t" value="${esc(token)}"><input name="value" type="password" autocomplete="off" required style="font:inherit;width:100%;padding:.4em" aria-label="${esc(link.name)}"><p><button style="font:inherit;padding:.5em 1.2em">Store it</button></p></form>`);
  }
  const value = (form.get('value') || '').trim();
  if (!value) return send(400, 'Nothing to store', '<p>Paste the key, then press Store it.</p>');
  keyLinks.delete(token);
  if (link.keep === 'server') {
    await mkdir(KEYS_DIR, { recursive: true, mode: 0o700 });
    await writeFile(path.join(KEYS_DIR, link.name), value, { mode: 0o600 });
    await record({ tool: 'store_key', kept: 'by this server', for: link.name, by: `${user} on the key page`, asked: link.by, result: 'stored' });
    return send(200, 'Stored', `<p>Your ${esc(link.name)} is kept by this server. Go back to your assistant and tell it it is done.</p>`);
  }
  const tmp = await mkdtemp(path.join(tmpdir(), 'edgible-key-'));
  try {
    const file = path.join(tmp, 'key');
    await writeFile(file, value, { mode: 0o600 });
    const r = await run('edgible', ['secret', 'set', link.secret, '--from-file', `${link.key}=${file}`], { timeout: 120000 });
    await record({ tool: 'store_key', secret: link.secret, for: link.name, by: `${user} on the key page`, asked: link.by, result: r.code ? 'failed' : 'stored' });
    if (r.code) return send(500, 'Not stored', `<p>Edgible did not store it: ${esc(cliError(r))}</p><p>Ask your assistant for a new link and try again.</p>`);
    return send(200, 'Stored', `<p>Your ${esc(link.name)} is stored with Edgible as <b>${esc(link.secret)}</b>. Go back to your assistant and tell it it is done.</p>`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

async function whoami() {
  // The person, as mcp-signin passed them on (X-MCP-User), and the Edgible account these tools act as.
  const by = actor.getStore() || '';
  const person = (by.match(/[^\s@]+@[^\s@]+\.[^\s@]+/) || [])[0] || null;
  const me = await edgibleJson(['whoami', '--json']).catch(() => ({}));
  return {
    you: person ? { email: person, how: 'signed in to this server with Edgible' } : { email: null, how: 'not known: this server is not behind mcp-signin' },
    tools_act_as: { email: me.account || null, organisation: me.organization?.name || null },
    use: 'A card setting that takes Edgible accounts, such as OPENCLAW_USERS, takes you.email: the address the person signs in to Edgible with, which may differ from their other email addresses.',
  };
}

// gateway_key: a key for one app on the shared AI gateway (the litellm card, its API published as
// litellm-api), with a budget, stored as an organisation secret <app>-gateway, so deploy_card
// passes it to the app by reference and nobody sees it. It needs the gateway's address
// (deploy_card records it when it deploys the gateway, or EDGIBLE_MCP_GATEWAY_URL) and its master
// key, kept by this server (deploy_card keeps it, or request_key with keep server).
const GATEWAY_CARD = 'litellm';
// An app's key may only use models and read its own record: never others' spending or the admin.
const APP_KEY_ROUTES = ['/v1/chat/completions', '/chat/completions', '/v1/models', '/models', '/key/info'];
const GATEWAY_MASTER = 'LITELLM_MASTER_KEY';
const GATEWAY_FILE = path.join(STATE, 'gateway.json');

async function gatewayUrl() {
  const set = (process.env.EDGIBLE_MCP_GATEWAY_URL || '').replace(/\/v1\/?$/, '').replace(/\/$/, '');
  if (set) return set;
  return JSON.parse(await readFile(GATEWAY_FILE, 'utf8').catch(() => '{}')).url || '';
}

// After deploy_card starts the gateway: publish its API on none, then keep its address and master key here.
async function publishGatewayApi({ app, deviceId, port, master }) {
  const name = `${app}-api`;
  const r = await run('edgible', ['app', 'create', 'existing', '--non-interactive', '--name', name, '--port', String(port),
    '--protocol', 'https', '--auth-modes', 'none', '--device-id', deviceId], { timeout: 180000 });
  const made = (await apps()).find((a) => a.name === name);
  if (r.code && !made) return { status: 'failed', reason: `${app} is deploying, but its API could not be published as ${name}: ${cliError(r)}` };
  const host = (made?.hostnames || [])[0];
  if (!host) return { status: 'failed', reason: `${name} was published without an address` };
  const url = `https://${host}`;
  await mkdir(KEYS_DIR, { recursive: true });
  if (master) {
    await writeFile(path.join(KEYS_DIR, GATEWAY_MASTER), master.value, { mode: 0o600 });
    await writeFile(keptMaster(app), master.value, { mode: 0o600 });
  }
  await writeFile(GATEWAY_FILE, JSON.stringify({ app, api: name, url }, null, 2));
  return { status: 'ok', url };
}

// Kept after remove_card too, for a redeploy under the same name (see deploy_card).
const keptMaster = (app) => path.join(KEYS_DIR, `gateway-${app}.${GATEWAY_MASTER}`);

async function forgetGateway(app) {
  await run('edgible', ['app', 'delete', `${app}-api`, '--yes'], { timeout: 300000 });
  const kept = JSON.parse(await readFile(GATEWAY_FILE, 'utf8').catch(() => '{}'));
  if (kept.app === app) {
    await rm(GATEWAY_FILE, { force: true });
    await rm(path.join(KEYS_DIR, GATEWAY_MASTER), { force: true });
  }
}

async function gatewayKey({ app, budget = 5, period = '30d', confirm = [] }) {
  if (!NAME.test(app || '')) return refused('app is the name the app will have, such as agent-gw');
  const GATEWAY_URL = await gatewayUrl();
  if (!GATEWAY_URL) return refused('This server knows no AI gateway yet: deploy the litellm card with deploy_card, which wires it up, or set EDGIBLE_MCP_GATEWAY_URL to its API address.');
  const master = await readFile(path.join(KEYS_DIR, 'LITELLM_MASTER_KEY'), 'utf8').then((s) => s.trim()).catch(() => '');
  if (!master) return refused('This server does not have the gateway\'s master key yet: call request_key with name LITELLM_MASTER_KEY and keep "server", and give the person the link.');
  const secret = `${app}-gateway`;
  const exists = (await edgibleJson(['secret', 'list', '--json']).catch(() => [])).some((s) => s.name === secret);
  if (exists && !confirm.includes('replace')) return needs([{ token: 'replace', reason: `${app} already has a gateway key (${secret}); a new one replaces it, and the app needs redeploying to use it.` }]);
  let made;
  try {
    const res = await fetch(`${GATEWAY_URL}/key/generate`, { method: 'POST', headers: { authorization: `Bearer ${master}`, 'content-type': 'application/json' },
      body: JSON.stringify({ key_alias: app, max_budget: Number(budget), budget_duration: period, allowed_routes: APP_KEY_ROUTES, metadata: { made_by: 'edgible-mcp gateway_key', by: actor.getStore() || 'assistant' } }) });
    made = await res.json();
    if (!res.ok || !made.key) return { status: 'failed', reason: `the gateway did not make a key (${res.status}): ${JSON.stringify(made).slice(0, 200)}` };
  } catch (err) {
    return { status: 'failed', reason: `the gateway at ${GATEWAY_URL} did not answer: ${err.message}` };
  }
  const tmp = await mkdtemp(path.join(tmpdir(), 'edgible-gateway-key-'));
  try {
    await writeFile(path.join(tmp, 'key'), made.key, { mode: 0o600 });
    const s = await run('edgible', ['secret', 'set', secret, '--from-file', `key=${path.join(tmp, 'key')}`], { timeout: 120000 });
    await record({ tool: 'gateway_key', app, secret, budget: `${budget} per ${period}`, result: s.code ? 'failed' : 'made' });
    if (s.code) return { status: 'failed', reason: `the key was made but Edgible did not store it: ${cliError(s)}` };
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
  return { status: 'made', app, secret, budget: `$${budget} per ${period}`, gateway: `${GATEWAY_URL}/v1`,
    next: `Deploy the app with this key by reference, such as keys {"OPENCLAW_MODEL_KEY": "${secret}:key"} and the gateway address ${GATEWAY_URL}/v1 as its model address. Its spend shows in the gateway's admin under ${app}.` };
}

// gateway_budget: change an app's budget on the AI gateway, by the app's name (its key's alias),
// asked first. It also keeps the key to the app routes, for keys made before they were set.
async function gatewayBudget({ app, budget, period, confirm = [] }) {
  if (!NAME.test(app || '')) return refused('app is the app\'s name on the gateway, such as agent-vm');
  if (!(Number(budget) > 0)) return refused('budget is dollars per period, more than 0');
  const GATEWAY_URL = await gatewayUrl();
  if (!GATEWAY_URL) return refused('This server knows no AI gateway yet.');
  const master = await readFile(path.join(KEYS_DIR, GATEWAY_MASTER), 'utf8').then((s) => s.trim()).catch(() => '');
  if (!master) return refused('This server does not have the gateway\'s master key.');
  const call = async (method, p, body) => {
    const res = await fetch(`${GATEWAY_URL}${p}`, { method, headers: { authorization: `Bearer ${master}`, 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    if (!res.ok) throw new Error(`the gateway answered ${res.status} for ${p}`);
    return res.json();
  };
  const found = ((await call('GET', `/key/list?return_full_object=true&key_alias=${encodeURIComponent(app)}`)).keys || []).filter((k) => k.key_alias === app);
  if (!found.length) return refused(`no key for ${app} on the gateway; gateway_key makes one`);
  const k = found[0];
  const before = `$${k.max_budget ?? 'no limit'} per ${k.budget_duration || 'all time'}`;
  const after = `$${Number(budget)} per ${period || k.budget_duration || '30d'}`;
  if (!confirm.includes('budget')) return needs([{ token: 'budget', reason: `${app}'s budget on the AI gateway changes from ${before} to ${after}. It has spent $${Number(k.spend || 0).toFixed(2)} this period.` }]);
  await call('POST', '/key/update', { key: k.token, max_budget: Number(budget), budget_duration: period || k.budget_duration || '30d', allowed_routes: APP_KEY_ROUTES });
  await record({ tool: 'gateway_budget', app, from: before, to: after, confirmed: confirm, result: 'changed' });
  return { status: 'changed', app, from: before, to: after, spent: `$${Number(k.spend || 0).toFixed(2)}` };
}

// restart_card: re-create a wedged app from its current release on its device, asked first.
async function restartCard({ app, confirm = [] }) {
  const live = (await apps()).find((a) => a.name === app);
  if (!live) return refused(`no app called ${app}`);
  if (live.subtype !== 'docker-compose') return refused(`${app} is a "${live.subtype}" app, which Edgible cannot restart for you`);
  const where = appDevices(live);
  if (notAllowed(...where)) return refused(notAllowed(...where));
  if (!confirm.includes('restart')) return needs([{ token: 'restart', reason: `Restarting ${app}: Edgible re-creates it from its current release on ${where.join(', ') || 'its device'}. Its data stays; it does not answer for up to a minute or two, and a reply it is writing is cut off.` }]);
  const r = await run('edgible', ['app', 'redeploy', app], { timeout: 180000 });
  await record({ tool: 'restart_card', app, confirmed: confirm, result: r.code ? 'failed' : 'restarted', detail: r.code ? cliError(r) : undefined });
  return r.code ? { status: 'failed', reason: cliError(r) } : { status: 'restarting', app, next: 'card_status reports when it answers again, usually within two minutes.' };
}

// gateway_check: one tiny question through the gateway, to show it answers: which provider replied,
// how long it took and what it cost. It uses the master key this server keeps, and returns no key.
async function gatewayCheck({ model = 'fast' }) {
  if (!/^[a-z][a-z0-9-]{0,40}$/.test(model)) return refused('model is a label the gateway offers, such as fast or smart');
  const GATEWAY_URL = await gatewayUrl();
  if (!GATEWAY_URL) return refused('This server knows no AI gateway yet: deploy the litellm card with deploy_card, which wires it up, or set EDGIBLE_MCP_GATEWAY_URL.');
  const master = await readFile(path.join(KEYS_DIR, GATEWAY_MASTER), 'utf8').then((s) => s.trim()).catch(() => '');
  if (!master) return refused('This server does not have the gateway\'s master key.');
  const started = Date.now();
  let res, body;
  try {
    res = await fetch(`${GATEWAY_URL}/v1/chat/completions`, { method: 'POST', headers: { authorization: `Bearer ${master}`, 'content-type': 'application/json' },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: 'Reply with the single word: ready' }], max_tokens: 200 }) });
    body = await res.json().catch(() => ({}));
  } catch (err) {
    return { status: 'failed', reason: `the gateway at ${GATEWAY_URL} did not answer: ${err.message}` };
  }
  const seconds = Math.round((Date.now() - started) / 100) / 10;
  if (!res.ok) return { status: 'failed', model, seconds, reason: `the gateway answered ${res.status}: ${String(body?.error?.message || '').replace(/sk-[A-Za-z0-9_-]{6,}/g, 'sk-…').slice(0, 300)}` };
  const fallbacks = Number(res.headers.get('x-litellm-attempted-fallbacks') || 0);
  const cost = Number(res.headers.get('x-litellm-response-cost') || 0);
  // The provider, from the address the gateway called (absent for a local model's own name).
  const base = res.headers.get('x-litellm-model-api-base') || '';
  const host = (() => { try { return new URL(base).hostname; } catch { return ''; } })();
  const PROVIDERS = { 'api.deepseek.com': 'DeepSeek', 'generativelanguage.googleapis.com': 'Google Gemini', 'openrouter.ai': 'OpenRouter', 'api.anthropic.com': 'Anthropic', 'api.openai.com': 'OpenAI' };
  const provider = PROVIDERS[host] || (/^(localhost|127\.|host\.docker\.internal|10\.|192\.168\.)/.test(host) ? 'a model on your own machine' : host || (body.model && body.model !== model ? body.model : 'the gateway did not say'));
  return { status: 'answered', asked_for: model, answered_by: provider, used_backup: fallbacks > 0, seconds,
    cost: `$${cost.toFixed(6)}`, reply: String(body?.choices?.[0]?.message?.content || '').slice(0, 80) };
}

// gateway_spend: what the shared AI gateway spent, by app and by model, with each app's budget and
// the tokens used. Read-only. It names apps by their key's alias and never returns a key: the
// gateway's logs record the caller's raw key, so only aliases, models and numbers leave here.
async function gatewaySpend({ days = 30 }) {
  const GATEWAY_URL = await gatewayUrl();
  if (!GATEWAY_URL) return refused('This server knows no AI gateway yet: deploy the litellm card with deploy_card, which wires it up, or set EDGIBLE_MCP_GATEWAY_URL.');
  const master = await readFile(path.join(KEYS_DIR, 'LITELLM_MASTER_KEY'), 'utf8').then((s) => s.trim()).catch(() => '');
  if (!master) return refused('This server does not have the gateway\'s master key: request_key with name LITELLM_MASTER_KEY and keep "server".');
  const get = async (p) => {
    const res = await fetch(`${GATEWAY_URL}${p}`, { headers: { authorization: `Bearer ${master}` } });
    if (!res.ok) throw new Error(`the gateway answered ${res.status} for ${p.split('?')[0]}`);
    return res.json();
  };
  const round = (n) => Math.round((Number(n) || 0) * 10000) / 10000;
  const keys = (await get('/key/list?return_full_object=true')).keys || [];
  const byApp = keys.map((k) => ({ app: k.key_alias || 'unnamed key', spend: round(k.spend), budget: k.max_budget ?? null,
    period: k.budget_duration || null, resets: k.budget_reset_at || null }));
  const end = new Date(); const start = new Date(end - days * 86400000);
  const day = (d) => d.toISOString().slice(0, 10);
  // Per-day summaries for the period: each day's spend by provider model (names only, no keys).
  const days_ = await get(`/spend/logs?start_date=${day(start)}&end_date=${day(new Date(end.getTime() + 86400000))}`).catch(() => []);
  const models = {};
  for (const d of Array.isArray(days_) ? days_ : []) {
    for (const [m, s] of Object.entries(d.models || {})) {
      if (!m) continue;
      const e = models[m] || (models[m] = { model: m, spend: 0 });
      e.spend += Number(s) || 0;
    }
  }
  const byModel = Object.values(models).map((e) => ({ ...e, spend: round(e.spend) })).sort((a, b) => b.spend - a.spend);
  // Each app's spend by model over the period, from LiteLLM's daily activity (per model, split by
  // key, named by the key's alias). Calls made with no app key, such as the owner's own, are "owner".
  const activity = await get(`/user/daily/activity?start_date=${day(start)}&end_date=${day(end)}`).catch(() => ({}));
  const matrix = {};
  for (const d of activity.results || []) {
    for (const [model, m] of Object.entries((d.breakdown || {}).models || {})) {
      for (const k of Object.values(m.api_key_breakdown || {})) {
        const app = (k.metadata || {}).key_alias || 'owner';
        const row = matrix[app] || (matrix[app] = {});
        const cell = row[model] || (row[model] = { spend: 0, tokens: 0, calls: 0 });
        const x = k.metrics || {};
        cell.spend += Number(x.spend) || 0; cell.tokens += Number(x.total_tokens) || 0; cell.calls += Number(x.api_requests) || 0;
      }
    }
  }
  const byAppAndModel = Object.entries(matrix).map(([app, row]) => ({
    app, total: round(Object.values(row).reduce((s, c) => s + c.spend, 0)),
    models: Object.entries(row).map(([model, c]) => ({ model, spend: round(c.spend), tokens: c.tokens, calls: c.calls })).sort((a, b) => b.spend - a.spend),
  })).sort((a, b) => b.total - a.total);
  return { scope: 'All apps on your AI gateway: the owner\'s view, through the gateway\'s master key', period: `last ${days} days`, total: round(byModel.reduce((s, e) => s + e.spend, 0)), by_app: byApp, by_model: byModel, by_app_and_model: byAppAndModel,
    note: 'Spend is the gateway\'s own estimate at list prices. by_app covers each key since it was made (or its budget last reset); by_model covers the period.' };
}

async function listKeys() {
  const secrets = await edgibleJson(['secret', 'list', '--json']);
  if (!secrets.length) return 'No organisation secrets are stored yet. On a computer with the Edgible CLI: edgible secret set <secret> --from-file key=<file holding the key>.';
  return secrets.map((s) => ({ secret: s.name, keys: s.keys || s.keyNames || [], updated: s.updatedAt || s.createdAt }));
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
    description: 'Deploy an Edgible app card (from edgible-org/cards) on any online device in the organisation. The card becomes one self-contained Compose file, and Edgible runs it on that device as a managed app and publishes it with the card\'s auth mode. It handles app cards, and pattern cards that publish one app from one machine (such as edgible-agent). A card that declares its secrets makes them on the device; a password a person needs comes back once as firstUse, to give them now. A key the person brings, such as a model\'s API key, is an Edgible organisation secret they stored once with the CLI, passed in keys by reference; never ask for the key itself. Cards with secrets in card.env are refused with the reason. Returns "needs confirmation" before publishing anything open to anyone.',
    inputSchema: {
      card: z.string().describe('The card, such as static-site'),
      device: z.string().describe('The Edgible device to run it on, by name'),
      app: z.string().optional().describe('The app name, which sets its address; defaults to the card name'),
      choices: z.record(z.string(), z.string()).optional().describe('card.env settings, such as {"STATIC_SITE_SOURCE": "https://…/main.tar.gz"}'),
      keys: z.record(z.string(), z.string()).optional().describe('Keys the person brings, each an organisation secret by reference: {"GEMINI_API_KEY": "gemini:key"} (secret name, then key name). list_keys shows what is stored.'),
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
  server.registerTool('whoami', {
    title: 'Who is asking',
    description: 'The person using this server, by the email they sign in to Edgible with (from mcp-signin), and the Edgible account and organisation these tools act as. Use it to fill a card setting that names Edgible accounts, such as OPENCLAW_USERS, rather than guessing an email.',
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, wrap(whoami));
  server.registerTool('request_key', {
    title: 'A link to store a key',
    description: 'A one-time link, for 10 minutes, to a page where the person pastes a key they bring, such as a model\'s API key. Edgible stores it as an organisation secret; the key never passes through the conversation. Then deploy_card takes it in keys. Use it when a card needs a key that list_keys does not show; never ask for the key itself.',
    inputSchema: {
      name: z.string().describe('The key\'s variable, as the card names it, such as GEMINI_API_KEY'),
      secret: z.string().optional().describe('The organisation secret to store it as, such as gemini; defaults from the name'),
      keep: z.enum(['edgible', 'server']).optional().describe('edgible (default): an organisation secret for deploys; server: kept by this server for its own use, such as the AI gateway\'s LITELLM_MASTER_KEY for gateway_key'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }, wrap(requestKey));
  server.registerTool('gateway_key', {
    title: 'A key for an app on the shared AI gateway',
    description: 'Make a key for one app on the shared AI gateway (the litellm card), with a budget, and store it as the organisation secret <app>-gateway, so deploy_card passes it to the app by reference: nobody sees it. Then deploy the app pointing at the gateway with that key. Each app gets its own key; its spend shows in the gateway\'s admin.',
    inputSchema: {
      app: z.string().describe('The app the key is for, as it will be named, such as agent-gw'),
      budget: z.number().positive().optional().describe('Dollars it may spend per period; default 5'),
      period: z.string().optional().describe('30d (default), 7d or 1d'),
      confirm: z.array(z.string()).optional().describe('["replace"], only after the person agreed to replace an existing key'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }, wrap(gatewayKey));
  server.registerTool('gateway_budget', {
    title: 'Change an app\'s AI budget',
    description: 'Change an app\'s or agent\'s budget on the AI gateway: dollars per period, by the app\'s name. Shows the old and new budget and what it has spent, and asks first. Good for "raise my agent\'s budget to ten dollars a month".',
    inputSchema: {
      app: z.string().describe('The app\'s name on the gateway, such as agent-vm'),
      budget: z.number().positive().describe('Dollars it may spend per period'),
      period: z.string().optional().describe('30d, 7d or 1d; default its current period'),
      confirm: z.array(z.string()).optional().describe('["budget"], only after the person agreed'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  }, wrap(gatewayBudget));
  server.registerTool('restart_card', {
    title: 'Restart an app',
    description: 'Restart an app that is stuck or not answering: Edgible re-creates it from its current release on its device, data kept. Asks first. Good for "my agent seems stuck".',
    inputSchema: {
      app: z.string().describe('The app\'s name'),
      confirm: z.array(z.string()).optional().describe('["restart"], only after the person agreed'),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  }, wrap(restartCard));
  server.registerTool('gateway_check', {
    title: 'Check the AI gateway answers',
    description: 'Send one tiny question through the AI gateway with a model label (fast by default) and report which provider answered, whether a backup was used, how long it took and what it cost (a fraction of a cent). Good for "does my AI gateway work?" right after setting it up. Uses the key this server keeps; returns no key.',
    inputSchema: { model: z.string().optional().describe('The label to try: fast (default), smart, open, best or private') },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }, wrap(gatewayCheck));
  server.registerTool('gateway_spend', {
    title: 'AI spending, from the shared gateway',
    description: 'The owner\'s view of the shared AI gateway\'s spending, scoped to all apps: by app, by app and model, (each key\'s spend against its budget) and by provider model (spend) over the last days. Read-only; names apps, never keys. Good for "show me my AI spending".',
    inputSchema: { days: z.number().int().positive().max(365).optional().describe('How many days back for the by-model figures; default 30') },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  }, wrap(gatewaySpend));
  server.registerTool('list_keys', {
    title: 'Keys stored with Edgible',
    description: 'The organisation secrets stored with Edgible, by name and key name, never their values: the keys a person brings, such as a model\'s API key, that deploy_card can pass to a card by reference.',
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  }, wrap(listKeys));
  server.registerTool('activity', {
    title: 'What these tools did',
    description: 'A plain record of every deploy, move and removal these tools made: when, which app and device, whether the person agreed first, and the result.',
    inputSchema: { limit: z.number().int().positive().max(200).optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, wrap(activity));
  return server;
}

export { ALLOWED, RECORD, STATE };
