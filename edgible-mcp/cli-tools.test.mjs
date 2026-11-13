// The pass-through to `edgible mcp` (cli-tools.mjs) must follow the CLI's sign-in. The real child reads
// it when it starts, so one started before the server was signed in kept answering "Not signed in"
// while the server's own tools (whoami, whats_running) saw the sign-in. This uses a fake `edgible`
// whose `mcp` child decides at start, as the real one does.

import test from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const sdk = (p) => import.meta.resolve(`@modelcontextprotocol/sdk/${p}`);

const dir = mkdtempSync(path.join(tmpdir(), 'cli-tools-test-'));
const state = path.join(dir, 'signed-in');
writeFileSync(path.join(dir, 'edgible'), `#!/usr/bin/env node
const { existsSync } = require('node:fs');
const signedIn = existsSync(process.env.FAKE_EDGIBLE_STATE); // decided once, at start
(async () => {
  const { McpServer } = await import(${JSON.stringify(sdk('server/mcp.js'))});
  const { StdioServerTransport } = await import(${JSON.stringify(sdk('server/stdio.js'))});
  const server = new McpServer({ name: 'fake-edgible', version: '1' });
  server.registerTool('list_devices', { description: 'Devices', inputSchema: {}, annotations: { readOnlyHint: true } },
    async () => signedIn
      ? { content: [{ type: 'text', text: 'devices: lggram17-wsl2-ubuntu26' }] }
      : { isError: true, content: [{ type: 'text', text: 'Not signed in. Run: edgible auth login' }] });
  await server.connect(new StdioServerTransport());
})();
`);
chmodSync(path.join(dir, 'edgible'), 0o755);
process.env.PATH = `${dir}${path.delimiter}${process.env.PATH}`;
process.env.FAKE_EDGIBLE_STATE = state;

const { closeCliTools, loadCliTools, registerCliTools } = await import('./cli-tools.mjs');
const { McpServer } = await import(sdk('server/mcp.js'));
const { Client } = await import(sdk('client/index.js'));
const { InMemoryTransport } = await import(sdk('inMemory.js'));

test('a pass-through child started before sign-in is replaced once the server is signed in', async (t) => {
  t.after(async () => { await closeCliTools(); rmSync(dir, { recursive: true, force: true }); });
  assert.ok(!existsSync(state));
  assert.deepEqual(await loadCliTools(false), ['list_devices']);

  const server = registerCliTools(new McpServer({ name: 'edgible-mcp', version: 'test' }), false);
  const [a, b] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'test', version: '1' });
  await Promise.all([server.connect(a), client.connect(b)]);
  const text = (r) => r.content.map((c) => c.text).join('\n');

  // Not signed in yet: an accurate hint for a hosted server, not "run edgible auth login" locally.
  const before = await client.callTool({ name: 'list_devices', arguments: {} });
  assert.equal(before.isError, true);
  assert.match(text(before), /sign_in/);
  assert.doesNotMatch(text(before), /^Not signed in\. Run/);

  // The server is signed in now (sign_in was approved); the next call must see it.
  writeFileSync(state, 'yes');
  const after = await client.callTool({ name: 'list_devices', arguments: {} });
  assert.notEqual(after.isError, true);
  assert.match(text(after), /lggram17-wsl2-ubuntu26/);

  await client.close();
  await server.close();
});
