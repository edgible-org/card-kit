#!/usr/bin/env node
// The one generator (J-45): an Edgible card plus one person's values become an Edgible stack file,
// an Application declaration for `edgible stack deploy`. deploy_card uses it, and so can the README
// and test-card, so every path deploys the same thing.
//
//   node generate.mjs <card directory> --device <name> [--app <name>] [--set KEY=VALUE ...]
//                     [--key NAME=<secret>:<key> ...] [--hostname <own domain> ...] [--out <dir>]
//
// The inputs are the card (its Compose file and card.yml), card.env with --set choices, and what
// the signed-in Edgible CLI knows: the organisation and the device's id. It writes
// docker-compose.yml (the card as one self-contained file) and edgible.yml (the declaration) to
// --out, the card directory when left out, and changes nothing in Edgible. Deploy with
// `edgible stack deploy -f <out>/edgible.yml`. The file holds no secret values: passwords are made
// on the device by card-secrets, and keys are references to Edgible organisation secrets.
// This version handles cards that publish one app, on one machine.
// A card's data stays in Compose named volumes. Edgible's platform storage (spec.storage, which
// snapshot, restore and `app move --storage` use) takes over once the platform gives it what a
// named volume has and carries an app's entries in one move: platform findings 70, 71 and 75.
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { cp, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import YAML from 'yaml';

// The card-secrets image that takes a seed, used when deploy_card hands it a first-use password.
export const CARD_SECRETS_IMAGE = 'ghcr.io/edgible-org/card-secrets:0.1.3';

const PATH_ENV = [...new Set([
  '/opt/homebrew/bin', '/usr/local/bin', path.join(homedir(), '.local/bin'),
  ...(process.env.PATH || '').split(':'), '/usr/bin', '/bin', '/usr/sbin', '/sbin',
].filter(Boolean))].join(':');
const ENV = { ...process.env, PATH: PATH_ENV, NO_COLOR: '1', EDGIBLE_NO_UPDATE_NOTIFIER: '1', EDGIBLE_NO_INTERACTIVE: '1' };

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { env: ENV, maxBuffer: 32 << 20, timeout: opts.timeout || 10 * 60 * 1000, cwd: opts.cwd },
      (err, stdout, stderr) => resolve({ code: err ? (typeof err.code === 'number' ? err.code : 1) : 0, stdout: String(stdout), stderr: String(stderr) }));
  });
}

// A refusal, in the shape the MCP tools use; deploy_card adds how to tell the person.
const refused = (reason) => ({ status: 'refused', reason });

export function parseEnv(textIn) {
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

export function setEnvLines(textIn, changes) {
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
export const DECLARED_AUTH = { org: 'edgible-login' };

const keyMark = (name) => `__edgible_key_${name}__`;
const duringMark = (name) => `__edgible_during_${name}__`;

export async function selfContained({ dir, card }, { app, device, choices, seeds = [], port, keys = [], user = '', published = '' }) {
  const composeFiles = ['docker-compose.yml', 'compose.yml', 'compose.yaml', 'docker-compose.yaml'].filter((f) => existsSync(path.join(dir, f)));
  if (composeFiles.length !== 1) return refused(`this first version handles cards with one Compose file; ${card.metadata.name} has ${composeFiles.length}`);
  const envText = await readFile(path.join(dir, 'card.env'), 'utf8').catch(() => '');
  const { values, generated } = parseEnv(envText);
  const external = new Set(Object.entries(card.secrets || {}).filter(([, s]) => s?.kind === 'external').map(([n]) => n));
  const secretKeys = Object.keys(values).filter((k) => isSecretKey(k, generated) && !external.has(k));
  if (secretKeys.length) return refused(`${card.metadata.name} has secrets (${secretKeys.join(', ')}). This first version only deploys cards without secrets, so no password ever sits in a Compose file; secrets need Edgible's organisation secrets, which come next.`);
  const changes = { ...choices };
  for (const name of keys) changes[name] = keyMark(name);
  // setup.during: values the app runs with until its own setup is done, such as sign-up on. They
  // become the app's Edgible environment, and the Compose file reads them as ${NAME:-<card.env's
  // value>}, so \`edgible app update --unset-env NAME\` puts card.env's value back in one release.
  const during = Object.assign({}, ...(card.applications || []).filter((a) => a.published !== false).map((a) => a.setup?.during || {}));
  const finals = {};
  for (const name of Object.keys(during)) {
    if (!(name in values)) return refused(`setup.during sets ${name}, which card.env does not have`);
    finals[name] = name in choices ? choices[name] : values[name];
    changes[name] = duringMark(name);
  }
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
  let secretsVolume = '';
  for (const name of keys) out = JSON.parse(JSON.stringify(out).replaceAll(keyMark(name), `\${${name}}`));
  for (const [name, value] of Object.entries(finals)) {
    out = JSON.parse(JSON.stringify(out).replaceAll(duringMark(name), `\${${name}:-${String(value).replaceAll('$', '$$$$')}}`));
  }
  if (seeds.length) {
    // The service that makes the card's secrets takes each seed from Edgible, by ${NAME}. Edgible's
    // agent can start an app once before it has the secret's value; :? makes that start fail, so
    // the service never makes its own value in place of the seed.
    const maker = Object.values(out.services || {}).find((s) => s.environment?.CARD_SECRETS);
    if (!maker) return refused(`${card.metadata.name} declares secrets but has no card-secrets service to make them`);
    maker.image = CARD_SECRETS_IMAGE;
    for (const name of seeds) maker.environment[name] = `\${${name}:?the first-use value from Edgible}`;
    const vol = (maker.volumes || []).find((v) => (typeof v === 'string' ? v.split(':')[1] : v.target) === '/run/card-secrets');
    const source = vol && (typeof vol === 'string' ? vol.split(':')[0] : vol.source);
    // Compose names a project's volumes <project>_<volume>, and the project is the app.
    if (source) secretsVolume = `${app}_${source}`;
  }
  // The host port Edgible forwards to: the one the card's app port is published on.
  // card.yml's port is the host port, the <APP>_PORT line in card.env, which the choices may move.
  // Some cards map it to another port inside (otter-wiki: 8080 to 80), so match the host side.
  const portKey = Object.keys(values).find((k) => /_PORT$/.test(k) && Number(values[k]) === Number(port));
  const wantHost = Number(portKey && changes[portKey] ? changes[portKey] : port);
  const mapped = Object.values(out.services || {}).flatMap((s) => s.ports || [])
    .map((p) => String(p).match(/(?:^|:)(\d+):(\d+)(?:\/tcp)?$/)).filter(Boolean);
  const hostPort = mapped.find((m) => Number(m[1]) === wantHost) || mapped.find((m) => Number(m[2]) === Number(port));
  if (!hostPort) return refused(`${card.metadata.name}'s Compose file does not publish its app port ${port}`);
  // The app's own healthcheck start_period, so the declared check below waits as long as Docker's.
  const appService = Object.values(out.services || {}).find((s) => (s.ports || []).some((p) => String(p).match(/(?:^|:)(\d+):(\d+)(?:\/tcp)?$/)?.[1] === hostPort[1]));
  const startPeriod = seconds(appService?.healthcheck?.start_period);
  return { status: 'ok', compose: YAML.stringify(out, { lineWidth: 0 }), port: Number(hostPort[1]), secretsVolume, during, startPeriod };
}

// Seconds in a Compose duration as `docker compose config` writes it ("1m30s", "45s", "500ms").
export function seconds(duration) {
  if (duration == null) return 0;
  if (typeof duration === 'number') return Math.ceil(duration / 1e9);
  let total = 0;
  for (const [, n, unit] of String(duration).matchAll(/([\d.]+)(h|ms|m|s|us|ns)/g)) {
    total += Number(n) * { h: 3600, m: 60, s: 1, ms: 1e-3, us: 1e-6, ns: 1e-9 }[unit];
  }
  return Math.ceil(total);
}

// Edgible's health check for a card: only that its published port accepts connections. When the
// port is closed the app is down, so this check cannot fail a working app. The card's detailed
// check stays its Compose healthcheck, which Docker runs and Edgible reads. Edgible stores declared
// checks on a compose app but does not run them yet (platform finding 76); this one is ready when
// it does. Grace is the app's own start_period, at least a minute.
export function healthCheckFor(startPeriod = 0) {
  return { type: 'tcp', port: 'main', intervalSeconds: 30, timeoutSeconds: 5, failureThreshold: 3,
    startupGraceSeconds: Math.max(60, startPeriod) };
}

// The version of a card an app came from: the files fingerprint test-card wrote in its test.yml
// (files: sha256:<hex>), as the hex alone, since Edgible's label values allow no ":". Kept as the
// app's card-files tag, so an app can be matched to a newer version of its card. "" without one.
export function cardFilesOf(testYml = '') {
  return (String(testYml).match(/^files:\s*sha256:([0-9a-f]{8,63})\s*$/m) || [])[1] || '';
}

// The auth mode an app is published on, and the one it goes to after. An app with setup: in
// card.yml waits behind setup.behind (org) while the person finishes its own setup, such as an
// install wizard, then is switched to its authModes with their yes. A public app (none) without
// setup: starts behind org too (staged): the person signs in to it first, so nobody else can take
// its admin, and it goes public only when they say so.
export function deployAuth(application) {
  const modes = (application.authModes || ['org']).join(',');
  if (!application.setup) {
    if (modes.split(',').includes('none')) return { auth: 'org', after: modes, setup: false, staged: true };
    return { auth: modes, after: null, setup: false };
  }
  // An app whose authModes is [setup.behind] stays there: nothing to switch after setup.
  return { auth: application.setup.behind, after: modes === application.setup.behind ? null : modes, setup: true };
}


// The Application declaration for one published app of a card on one device. hostnames are the
// person's own domains; the generated hostname is always there. envFrom names organisation
// secrets by reference, never their values.
// card.yml's appPaths as Edgible's path policies: each set of paths left to the app's own login
// (app-native), with its for as the reason Edgible records. Only behind Edgible's sign-in: on
// none the whole app is already the app's own, and api-key has no browser sign-in to step past.
export function pathPoliciesFor(appPaths = [], modes = []) {
  if (!appPaths?.length || !modes.includes('edgible-login')) return [];
  return appPaths.map((p) => ({ paths: p.paths, modes: ['app-native'], justification: p.for }));
}

export function declarationFor({ app, card, organizationId, deviceId, port, auth, hostnames = [], compose, envFrom = [], env = {}, startPeriod = 0, cardFiles = '', appPaths = [], by = 'edgible-mcp' }) {
  const modes = auth.split(',').map((m) => DECLARED_AUTH[m] || m);
  const pathPolicies = pathPoliciesFor(appPaths, modes);
  const access = (hostnames.length ? hostnames : [null]).map((custom, i) => ({
    type: 'https', name: i ? `main-${i + 1}` : 'main', target: { workload: 'main', port: 'main' }, publish: true,
    policies: { auth: { modes, ...(pathPolicies.length ? { pathPolicies } : {}) } }, hostname: custom ? { generated: true, custom } : { generated: true },
  }));
  return {
    apiVersion: 'v3', kind: 'Application',
    metadata: { name: app, organization: organizationId, description: `The ${card} card, deployed by ${by}`, labels: { card, by, ...(cardFiles ? { 'card-files': cardFiles } : {}) } },
    spec: {
      placement: { strategy: 'serving-device', deviceSelector: { deviceId }, migrationPolicy: 'manual' },
      workloads: [{ name: 'main', type: 'compose', ports: [{ name: 'main', containerPort: port, protocol: 'tcp' }],
        healthChecks: [healthCheckFor(startPeriod)],
        composeFile: `base64:${Buffer.from(compose).toString('base64')}`, ...(envFrom.length ? { envFrom } : {}),
        ...(Object.keys(env).length ? { env } : {}) }],
      access,
    },
  };
}

// ---------- From the command line ----------

async function edgibleJson(args) {
  const r = await run('edgible', args, { timeout: 120000 });
  if (r.code) throw new Error(`edgible ${args.join(' ')}: ${(r.stderr || r.stdout).trim().slice(0, 300)}`);
  return JSON.parse(r.stdout);
}

function parseArgs(argv) {
  const o = { set: {}, keys: {}, hostnames: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], v = () => { if (i + 1 >= argv.length) throw new Error(`${a} needs a value`); return argv[++i]; };
    if (a === '--device') o.device = v();
    else if (a === '--app') o.app = v();
    else if (a === '--out') o.out = v();
    else if (a === '--hostname') o.hostnames.push(v());
    else if (a === '--set' || a === '--key') {
      const pair = v(), at = pair.indexOf('=');
      if (at < 1) throw new Error(`${a} takes NAME=value`);
      const [name, value] = [pair.slice(0, at), pair.slice(at + 1)];
      if (a === '--set') o.set[name] = value;
      else { const [secret, key] = value.split(':'); o.keys[name] = { secret, key: key || name }; }
    } else if (a.startsWith('--')) throw new Error(`unknown option ${a}`);
    else if (!o.dir) o.dir = a;
    else throw new Error(`one card directory, not ${a}`);
  }
  if (!o.dir || !o.device) throw new Error('usage: node generate.mjs <card directory> --device <name> [--app <name>] [--set KEY=VALUE] [--key NAME=<secret>:<key>] [--hostname <domain>] [--out <dir>]');
  return o;
}

async function main(argv) {
  const o = parseArgs(argv);
  const dir = path.resolve(o.dir);
  const card = YAML.parse(await readFile(path.join(dir, 'card.yml'), 'utf8'));
  const name = card.metadata.name;
  const published = (card.applications || []).filter((a) => a.published !== false);
  if (published.length !== 1) throw new Error(`${name} publishes ${published.length} apps; this version handles cards that publish one (J-45)`);
  if (Object.keys(card.places || {}).length > 1) throw new Error(`${name} runs on ${Object.keys(card.places).length} machines; this version handles cards on one`);
  if ((card.applications || []).some((a) => a.native)) throw new Error(`${name} installs on the machine itself (native); it keeps its README's own path`);
  const app = o.app || name;
  const me = await edgibleJson(['whoami', '--json']);
  const list = await edgibleJson(['device', 'list', '--json']);
  const devices = Array.isArray(list) ? list : list.devices || [];
  const found = devices.filter((d) => d.name === o.device || d.id === o.device);
  if (found.length !== 1) throw new Error(`need exactly one device named ${o.device} (found ${found.length})`);
  const { auth } = deployAuth(published[0]);
  // The generator writes the choices into card.env, so it works on a copy and leaves the card as it is.
  const work = await mkdtemp(path.join(tmpdir(), 'edgible-generate-'));
  try {
    await cp(dir, work, { recursive: true });
    const built = await selfContained({ dir: work, card }, { app, device: found[0].name, choices: o.set, port: published[0].port,
      keys: Object.keys(o.keys), user: me.account || '', published: published[0].name });
    if (built.status !== 'ok') throw new Error(built.reason);
    const envFrom = Object.entries(o.keys).map(([n, secretRef]) => ({ name: n, secretRef }));
    const compose = `# ${name} card as one self-contained file, made by generate.mjs. Do not edit by hand: change card.env and generate again.\n${built.compose}`;
    const declaration = declarationFor({ app, card: name, organizationId: me.organization.id, deviceId: found[0].id, port: built.port, auth,
      hostnames: o.hostnames, compose, envFrom, env: built.during, startPeriod: built.startPeriod, cardFiles: cardFilesOf(await readFile(path.join(dir, 'test.yml'), 'utf8').catch(() => '')), appPaths: published[0].setup ? [] : published[0].appPaths, by: 'generate.mjs' });
    const out = path.resolve(o.out || dir);
    await writeFile(path.join(out, 'docker-compose.generated.yml'), compose);
    await writeFile(path.join(out, 'edgible.yml'), `# ${app}: the ${name} card on ${found[0].name}, made by generate.mjs. Regenerate rather than edit.\n${YAML.stringify(declaration, { lineWidth: 0 })}`);
    const duringKeys = Object.keys(built.during);
    console.log(`wrote ${path.join(out, 'edgible.yml')}: ${app} on ${found[0].name}, auth ${auth}${duringKeys.length ? `, until setup is done ${duringKeys.map((k) => `${k}=${built.during[k]}`).join(' ')}` : ''}. Deploy with: edgible stack deploy -f ${path.join(out, 'edgible.yml')}`);
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(await realpath(process.argv[1])).href) {
  main(process.argv.slice(2)).catch((err) => { console.error(`generate.mjs: ${err.message}`); process.exit(1); });
}
