#!/usr/bin/env node
// edgible-mcp: one MCP server for Edgible cards and the apps of your Edgible organisation.
//
//   edgible-mcp                     read-only tools over stdio, for an AI app on this machine
//   edgible-mcp --allow-write       also the tools that deploy, move and remove apps
//   edgible-mcp --http 8000         the same over Streamable HTTP, at /mcp (and /healthz)
//
// Read-only by default: find, describe and whats_running (server.mjs). With --allow-write
// (or EDGIBLE_MCP_ALLOW_WRITE=1) it adds deploy_card, move_card, remove_card, card_status and
// activity (write.mjs): every change asks the person first and is recorded, and
// EDGIBLE_MCP_DEVICES can limit changes to some devices.
//
// The HTTP mode has no sign-in of its own. Put it behind the mcp-signin card, which signs
// people in with Edgible and tells this server who they are in X-MCP-User (written to the
// record), or publish it on Edgible's api-key auth. Never publish it on auth mode none.

import { createServer } from 'node:http';
import { mkdir } from 'node:fs/promises';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { READ_INSTRUCTIONS, VERSION, prepareSignIn, registerReadTools } from './server.mjs';
import { ALLOWED, RECORD, STATE, WRITE_INSTRUCTIONS, actor, keyPage, registerWriteTools } from './write.mjs';

const argv = process.argv.slice(2);
const allowWrite = argv.includes('--allow-write') || process.env.EDGIBLE_MCP_ALLOW_WRITE === '1';
const port = argv.includes('--http') ? Number(argv[argv.indexOf('--http') + 1]) : null;
const host = argv.includes('--host') ? argv[argv.indexOf('--host') + 1] : '127.0.0.1';

function buildServer() {
  const server = new McpServer({ name: 'edgible', version: VERSION }, {
    instructions: allowWrite ? `${READ_INSTRUCTIONS} ${WRITE_INSTRUCTIONS}` : READ_INSTRUCTIONS,
  });
  registerReadTools(server);
  if (allowWrite) registerWriteTools(server);
  return server;
}

const tools = allowWrite
  ? `read and write tools${ALLOWED.length ? ` (changes only on ${ALLOWED.join(', ')})` : ''}, record in ${RECORD}`
  : 'read-only tools';
if (allowWrite) await mkdir(STATE, { recursive: true });

if (!port) {
  await buildServer().connect(new StdioServerTransport());
  console.error(`edgible-mcp ${VERSION}: serving over stdio, ${tools}`);
} else {
  createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/healthz') { res.writeHead(200).end('ok\n'); return; }
    // The page where a person stores a key (write.mjs), reached through mcp-signin's /pages/.
    if (url.pathname === '/pages/key' && allowWrite) {
      const chunks = [];
      let size = 0;
      if (req.method === 'POST') for await (const c of req) { size += c.length; if (size > 16384) { res.writeHead(413).end('too large\n'); return; } chunks.push(c); }
      await keyPage(req, res, url, Buffer.concat(chunks).toString('utf8')).catch((err) => {
        console.error(`edgible-mcp: key page failed: ${err.message}`);
        if (!res.headersSent) res.writeHead(500).end('failed\n');
      });
      return;
    }
    if (url.pathname !== '/mcp') { res.writeHead(404).end('not found\n'); return; }
    try {
      let body;
      if (req.method === 'POST') {
        const chunks = [];
        for await (const c of req) chunks.push(c);
        body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : undefined;
      }
      // Stateless: a fresh server and transport per request, so nothing lingers between calls.
      const server = buildServer();
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
      res.on('close', () => { transport.close(); server.close(); });
      await server.connect(transport);
      const who = req.headers['x-mcp-user'];
      await actor.run(who ? `${who} via mcp-signin` : undefined, () => transport.handleRequest(req, res, body));
    } catch (err) {
      console.error(`edgible-mcp: request failed: ${err.message}`);
      if (!res.headersSent) res.writeHead(400).end('bad request\n');
    }
  }).listen(port, host, () => console.error(`edgible-mcp ${VERSION}: serving MCP over HTTP on ${host}:${port}/mcp, ${tools}`));
  prepareSignIn().catch(() => {});
}
