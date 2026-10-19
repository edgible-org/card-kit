#!/usr/bin/env node
// mcp-signin: Sign in with Edgible in front of any MCP server, so Claude on the web and phone
// (or any MCP client that follows the MCP authorization spec) can use a server on your own
// machine as a remote connector, and only the people you allow get in.
//
// Two ports, published as two Edgible apps:
// - PUBLIC_PORT (auth mode none): /mcp, passed on to MCP_UPSTREAM_URL once the caller's token
//   checks out, plus the OAuth endpoints and metadata, which the client calls with no browser;
// - LOGIN_PORT (auth mode org): the sign-in page the client opens in the person's browser.
// Each call passed on carries X-MCP-User: the email of the person who signed in. Any
// X-MCP-User a caller sent is dropped, so the server behind can trust it, as long as nothing
// else reaches that server.
//
// Settings, from the environment (see the mcp-signin card's card.env):
//   MCP_UPSTREAM_URL        the MCP server behind, such as http://edgible-mcp:8000/mcp
//   MCP_SIGNIN_PUBLIC_URL   the public address, such as https://mcp.example.edgible.app
//   MCP_SIGNIN_LOGIN_URL    the sign-in address, such as https://mcp-login.example.edgible.app
//   EDGIBLE_ORGANIZATION_ID the Edgible organisation whose members may sign in
//   MCP_SIGNIN_USERS        optional: only these email addresses, comma separated
//   MCP_SIGNIN_NAME         what the consent page calls the server (default: this MCP server)
//   MCP_SIGNIN_PURPOSE      optional: what it lets the assistant do, for the consent page
//   MCP_SIGNIN_STATE        where tokens are kept (default /data)
//   PUBLIC_PORT, LOGIN_PORT (default 8000 and 8001)

import { mkdir } from 'node:fs/promises';
import { Readable } from 'node:stream';
import express from 'express';
import { getOAuthProtectedResourceMetadataUrl, mcpAuthRouter } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { edgibleProvider } from './oauth.mjs';

const version = '0.1.1';
const env = (k, d) => (process.env[k] ?? d ?? '').trim();
const need = (k) => env(k) || (() => { throw new Error(`mcp-signin needs ${k}`); })();
const trim = (u) => u.replace(/\/$/, '');
const upstream = new URL(need('MCP_UPSTREAM_URL'));
const publicUrl = trim(need('MCP_SIGNIN_PUBLIC_URL'));
const loginUrl = trim(need('MCP_SIGNIN_LOGIN_URL'));
const organizationId = need('EDGIBLE_ORGANIZATION_ID');
const users = env('MCP_SIGNIN_USERS').split(',').map((s) => s.trim()).filter(Boolean);
const name = env('MCP_SIGNIN_NAME', 'this MCP server');
const state = env('MCP_SIGNIN_STATE', '/data');
const publicPort = Number(env('PUBLIC_PORT', '8000'));
const loginPort = Number(env('LOGIN_PORT', '8001'));

await mkdir(state, { recursive: true });
const { provider, signinPage, signinAnswer } = await edgibleProvider({
  state, loginUrl, organizationId, users, name, purpose: env('MCP_SIGNIN_PURPOSE'),
});

// Headers passed on in each direction. Everything else stays here: the caller's token
// above all, which is for mcp-signin, not for the server behind.
const UP = ['content-type', 'accept', 'mcp-session-id', 'mcp-protocol-version', 'last-event-id'];
const DOWN = ['content-type', 'mcp-session-id', 'cache-control'];

async function pass(req, res) {
  const headers = { 'x-mcp-user': req.auth.extra.user };
  for (const h of UP) if (req.get(h)) headers[h] = req.get(h);
  const ctrl = new AbortController();
  res.on('close', () => ctrl.abort());
  try {
    const got = await fetch(upstream, {
      method: req.method, headers, signal: ctrl.signal,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : req.body,
    });
    res.status(got.status);
    for (const h of DOWN) if (got.headers.get(h)) res.set(h, got.headers.get(h));
    if (got.body) Readable.fromWeb(got.body).on('error', () => res.end()).pipe(res);
    else res.end();
  } catch (err) {
    if (ctrl.signal.aborted) return;
    console.error(`mcp-signin: ${upstream.host} did not answer: ${err.message}`);
    if (!res.headersSent) res.status(502).json({ jsonrpc: '2.0', error: { code: -32000, message: `The MCP server behind mcp-signin did not answer` }, id: null });
  }
}

const app = express();
// Edgible's web server on this machine forwards each request; the card publishes both ports on
// 127.0.0.1 only, so that server is the one proxy in front: trust exactly one hop.
app.set('trust proxy', 1);
app.get('/healthz', (req, res) => res.send('ok\n'));
// Someone who opens the address in a browser learns what it is for.
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
app.get('/', (req, res) => res.send(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(name)}</title><body style="font:16px system-ui;max-width:32em;margin:3em auto;padding:0 1em;line-height:1.5"><h1>${esc(name)}</h1><p>An MCP server, for AI assistants. To use it, add <code>${esc(publicUrl)}/mcp</code> to your assistant as a connector, such as in Claude: Settings, Connectors, Add custom connector. You sign in with Edgible when you connect.</p>`));
const resource = new URL(`${publicUrl}/mcp`);
app.use(mcpAuthRouter({ provider, issuerUrl: new URL(publicUrl), resourceServerUrl: resource, scopesSupported: ['mcp'], resourceName: name }));
app.all('/mcp', requireBearerAuth({ verifier: provider, resourceMetadataUrl: getOAuthProtectedResourceMetadataUrl(resource) }),
  express.raw({ type: () => true, limit: '4mb' }), pass);
app.use((req, res) => res.status(404).send('not found\n'));
app.listen(publicPort, () => console.error(`mcp-signin ${version}: ${name} at ${resource.href}, passed on to ${upstream.href}, for ${users.length ? users.join(', ') : `members of organisation ${organizationId}`}`));

// The sign-in page has its own port, published only behind Edgible's org sign-in.
const login = express();
login.set('trust proxy', 1);
login.get('/healthz', (req, res) => res.send('ok\n'));
login.get('/signin', signinPage);
login.post('/signin', express.urlencoded({ extended: false, limit: '4kb' }), signinAnswer);
login.use((req, res) => res.status(404).send('not found\n'));
login.listen(loginPort, () => console.error(`mcp-signin: sign-in page on port ${loginPort} for ${loginUrl}`));
