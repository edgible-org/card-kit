// node --test generate.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { declarationFor, healthCheckFor, seconds } from './generate.mjs';

test('Compose durations become whole seconds', () => {
  assert.equal(seconds(undefined), 0);
  assert.equal(seconds('45s'), 45);
  assert.equal(seconds('1m30s'), 90);
  assert.equal(seconds('2m0s'), 120);
  assert.equal(seconds('500ms'), 1);
  assert.equal(seconds(30e9), 30);
});

test('the declared check is TCP on the published port, with at least a minute of grace', () => {
  assert.deepEqual(healthCheckFor(), { type: 'tcp', port: 'main', intervalSeconds: 30, timeoutSeconds: 5, failureThreshold: 3, startupGraceSeconds: 60 });
  assert.equal(healthCheckFor(180).startupGraceSeconds, 180);
});

test('every declaration carries the check', () => {
  const d = declarationFor({ app: 'a', card: 'memos', organizationId: 'o', deviceId: 'd', port: 5230, auth: 'org', compose: 'services: {}', startPeriod: 90 });
  assert.deepEqual(d.spec.workloads[0].healthChecks, [healthCheckFor(90)]);
});

test('the card version is the test.yml files fingerprint, without "sha256:"', async () => {
  const { cardFilesOf } = await import('./generate.mjs');
  assert.equal(cardFilesOf('tested: 2026-11-20\nfiles: sha256:3b182ed31ee4510a\n'), '3b182ed31ee4510a');
  assert.equal(cardFilesOf(''), '');
  assert.equal(cardFilesOf('files: something-else\n'), '');
  const d = declarationFor({ app: 'a', card: 'memos', organizationId: 'o', deviceId: 'd', port: 5230, auth: 'org', compose: 'services: {}', cardFiles: 'ac5e2364c27f7866' });
  assert.deepEqual(d.metadata.labels, { card: 'memos', by: 'edgible-mcp', 'card-files': 'ac5e2364c27f7866' });
  assert.equal(declarationFor({ app: 'a', card: 'memos', organizationId: 'o', deviceId: 'd', port: 1, auth: 'org', compose: '' }).metadata.labels['card-files'], undefined);
});
