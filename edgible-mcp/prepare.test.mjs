// node --test prepare.test.mjs
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { prepareStep } from './write.mjs';

async function card(prepare) {
  const dir = await mkdtemp(path.join(tmpdir(), 'prepare-test-'));
  if (prepare !== undefined) await writeFile(path.join(dir, 'prepare.sh'), prepare);
  return dir;
}

test('a card without prepare.sh has no prepare step', async () => {
  const dir = await card();
  assert.equal(await prepareStep(dir, 'linkding'), null);
  await rm(dir, { recursive: true });
});

test('the step is the header\'s first sentence, without its full stop', async () => {
  const dir = await card('#!/bin/sh\n# Prepare for the hedgedoc card: make the first account before HedgeDoc is published.\n# HedgeDoc has no admin role.\nset -eu\n');
  assert.equal(await prepareStep(dir, 'hedgedoc'), 'make the first account before HedgeDoc is published');
  await rm(dir, { recursive: true });
});

test('a header sentence that runs on over two lines is read whole', async () => {
  const dir = await card('#!/bin/sh\n# Prepare for the minecraft card: switch Geyser to Floodgate sign-in, so Bedrock players sign in with Xbox,\n# and to the RakNet transport. Run it after Start.\n');
  assert.equal(await prepareStep(dir, 'minecraft'), 'switch Geyser to Floodgate sign-in, so Bedrock players sign in with Xbox, and to the RakNet transport');
  await rm(dir, { recursive: true });
});

test('a prepare.sh without the usual header still counts', async () => {
  const dir = await card('#!/bin/sh\nset -eu\n');
  assert.match(await prepareStep(dir, 'odd'), /odd's prepare\.sh/);
  await rm(dir, { recursive: true });
});

test('an app with setup: is published behind org, and goes to its authModes after', async () => {
  const { deployAuth } = await import('./write.mjs');
  assert.deepEqual(deployAuth({ authModes: ['none'], setup: { behind: 'org', done: 'true' } }), { auth: 'org', after: 'none' });
  assert.deepEqual(deployAuth({ authModes: ['none'] }), { auth: 'none', after: null });
  assert.deepEqual(deployAuth({}), { auth: 'org', after: null });
});
