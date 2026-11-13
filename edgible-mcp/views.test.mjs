import { test } from 'node:test';
import assert from 'node:assert/strict';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { registerReadTools, viewsEnabled } from './server.mjs';

async function connect(opts) {
  const server = registerReadTools(new McpServer({ name: 't', version: '0' }), opts);
  const [a, b] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 't', version: '0' });
  await Promise.all([server.connect(a), client.connect(b)]);
  return client;
}

test('EDGIBLE_MCP_VIEWS reads off, 0, false and no as off', () => {
  for (const v of ['off', '0', 'false', 'NO', ' off ']) assert.equal(viewsEnabled({ EDGIBLE_MCP_VIEWS: v }), false, v);
  for (const v of [undefined, '', 'on', '1']) assert.equal(viewsEnabled({ EDGIBLE_MCP_VIEWS: v }), true, String(v));
});

test('with views, the panel tools name their resource and the resources are listed', async () => {
  const client = await connect({ views: true });
  const { tools } = await client.listTools();
  for (const name of ['find', 'describe', 'whats_running']) {
    assert.match(tools.find((t) => t.name === name)._meta?.ui?.resourceUri ?? '', /^ui:\/\/edgible\//, name);
  }
  const { resources } = await client.listResources();
  assert.equal(resources.length, 2);
});

test('with views off, no tool names a panel and no resource is listed', async () => {
  const client = await connect({ views: false });
  const { tools } = await client.listTools();
  for (const t of tools) assert.equal(t._meta?.ui, undefined, t.name);
  assert.ok(tools.some((t) => t.name === 'whats_running'));
  await assert.rejects(client.listResources());
});
