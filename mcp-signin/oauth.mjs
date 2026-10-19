// OAuth for mcp-signin: a remote connector (Claude on the web and phone, or any MCP client
// that follows the MCP authorization spec) signs in before it reaches the MCP server behind.
// mcp-signin is its own OAuth authorization server, as MCP expects: the client registers
// itself (dynamic client registration), sends the person here, and gets a token. The person
// signs in with Edgible itself: no other account or app to set up.
//
// The sign-in page is on its own port, published only behind Edgible's org sign-in. Edgible
// signs the person in first and tells the page who they are (X-Auth-Email,
// X-Auth-Organization-Id), deleting any X-Auth-* header a client sent itself. The page asks
// the person to allow the client, naming where it will send them, so a link from someone
// else's client cannot sign them in silently.
//
// Who may sign in: members of one Edgible organisation, narrowed to listed email addresses
// when there are any. Tokens are kept hashed in a file, so a restart signs no one out.

import { createHash, randomBytes } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { InvalidGrantError, InvalidTokenError } from '@modelcontextprotocol/sdk/server/auth/errors.js';

const ACCESS_SECONDS = 3600;
const REFRESH_DAYS = 30;
const token = () => randomBytes(32).toString('base64url');
const hash = (t) => createHash('sha256').update(t).digest('hex');
const now = () => Math.floor(Date.now() / 1000);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const page = (title, body) => `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(title)}</title><body style="font:16px system-ui;max-width:32em;margin:3em auto;padding:0 1em;line-height:1.5"><h1>${esc(title)}</h1>${body}`;

export async function edgibleProvider({ state, loginUrl, organizationId, users, name, purpose }) {
  const file = path.join(state, 'oauth.json');
  let db = { clients: {}, access: {}, refresh: {} };
  try { db = { ...db, ...JSON.parse(await readFile(file, 'utf8')) }; } catch {}
  const save = () => writeFile(file, JSON.stringify(db, null, 1), { mode: 0o600 });
  const pending = new Map(); // request key -> the client's authorize request, while the person signs in
  const codes = new Map();   // our authorization code -> the request and who signed in
  const listed = new Set(users.map((u) => u.toLowerCase()));
  const allowed = (email) => Boolean(email) && (!listed.size || listed.has(String(email).toLowerCase()));

  const issue = async (clientId, user, scopes, resource) => {
    const access = token(); const refresh = token();
    db.access[hash(access)] = { clientId, user, scopes, resource, expiresAt: now() + ACCESS_SECONDS };
    db.refresh[hash(refresh)] = { clientId, user, scopes, resource, expiresAt: now() + REFRESH_DAYS * 86400 };
    for (const kind of ['access', 'refresh']) for (const [k, v] of Object.entries(db[kind])) if (v.expiresAt < now()) delete db[kind][k];
    await save();
    return { access_token: access, token_type: 'bearer', expires_in: ACCESS_SECONDS, refresh_token: refresh, scope: scopes.join(' ') };
  };

  const provider = {
    clientsStore: {
      getClient: (id) => db.clients[id],
      registerClient: async (client) => {
        const full = { ...client, client_id: token(), client_id_issued_at: now() };
        db.clients[full.client_id] = full;
        await save();
        return full;
      },
    },
    async authorize(client, params, res) {
      const key = token();
      pending.set(key, { clientId: client.client_id, clientName: client.client_name, ...params, at: Date.now() });
      for (const [k, v] of pending) if (Date.now() - v.at > 600000) pending.delete(k);
      res.redirect(`${loginUrl}/signin?request=${key}`);
    },
    async challengeForAuthorizationCode(client, code) {
      const c = codes.get(code);
      if (!c || c.clientId !== client.client_id) throw new InvalidGrantError('unknown authorization code');
      return c.codeChallenge;
    },
    async exchangeAuthorizationCode(client, code) {
      const c = codes.get(code);
      codes.delete(code);
      if (!c || c.clientId !== client.client_id || Date.now() - c.at > 300000) throw new InvalidGrantError('unknown or expired authorization code');
      return issue(client.client_id, c.user, c.scopes || [], c.resource?.href);
    },
    async exchangeRefreshToken(client, refresh) {
      const r = db.refresh[hash(refresh)];
      if (!r || r.clientId !== client.client_id || r.expiresAt < now()) throw new InvalidGrantError('unknown or expired refresh token');
      if (!allowed(r.user)) throw new InvalidGrantError(`${r.user} is no longer allowed`);
      delete db.refresh[hash(refresh)];
      return issue(client.client_id, r.user, r.scopes, r.resource);
    },
    async verifyAccessToken(t) {
      const a = db.access[hash(t)];
      if (!a || a.expiresAt < now()) throw new InvalidTokenError('unknown or expired token');
      if (!allowed(a.user)) throw new InvalidTokenError(`${a.user} is no longer allowed`);
      return { token: t, clientId: a.clientId, scopes: a.scopes, expiresAt: a.expiresAt, resource: a.resource ? new URL(a.resource) : undefined, extra: { user: a.user } };
    },
    async revokeToken(client, { token: t }) {
      delete db.access[hash(t)]; delete db.refresh[hash(t)];
      await save();
    },
  };

  // The sign-in page, on the org-only port. Edgible has signed the person in before it gets here.
  function who(req) {
    const email = req.get('x-auth-email');
    if (req.get('x-auth-type') !== 'org' || !email) return { refuse: 'Edgible did not say who you are. Open this from Claude again.' };
    if (req.get('x-auth-organization-id') !== organizationId) return { refuse: `${email} is signed in to another Edgible organisation.` };
    if (!allowed(email)) return { refuse: `${email} may not use ${name}. Ask its owner to add you.` };
    return { email };
  }
  function signinPage(req, res) {
    const p = pending.get(String(req.query.request || ''));
    if (!p) return res.status(400).send(page('Sign-in expired', '<p>Start again from Claude.</p>'));
    const w = who(req);
    if (w.refuse) { console.error(`mcp-signin: refused sign-in: ${w.refuse}`); return res.status(403).send(page('Not allowed', `<p>${esc(w.refuse)}</p>`)); }
    const to = new URL(p.redirectUri).host;
    res.set('content-security-policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https:; frame-ancestors 'none'")
      .send(page(`Allow access to ${name}?`, `<p><b>${esc(p.clientName || 'An assistant')}</b> at <b>${esc(to)}</b> asks to use <b>${esc(name)}</b> as <b>${esc(w.email)}</b>${purpose ? `: ${esc(purpose)}` : ''}.</p>
<p>Allow it only if you started this from that assistant just now.</p>
<form method="post" action="signin"><input type="hidden" name="request" value="${esc(req.query.request)}"><button style="font:inherit;padding:.5em 1.2em" name="allow" value="yes">Allow</button> <button style="font:inherit;padding:.5em 1.2em" name="allow" value="no">Cancel</button></form>`));
  }
  function signinAnswer(req, res) {
    const key = String(req.body?.request || '');
    const p = pending.get(key);
    pending.delete(key);
    if (!p) return res.status(400).send(page('Sign-in expired', '<p>Start again from Claude.</p>'));
    const w = who(req);
    if (w.refuse) return res.status(403).send(page('Not allowed', `<p>${esc(w.refuse)}</p>`));
    const back = new URL(p.redirectUri);
    if (req.body.allow !== 'yes') {
      back.searchParams.set('error', 'access_denied');
    } else {
      const code = token();
      codes.set(code, { ...p, user: w.email, at: Date.now() });
      back.searchParams.set('code', code);
      console.error(`mcp-signin: ${w.email} signed in`);
    }
    if (p.state) back.searchParams.set('state', p.state);
    res.redirect(303, back.href);
  }

  return { provider, signinPage, signinAnswer };
}
