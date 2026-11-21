// node --test generate.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { declarationFor, healthCheckFor, pathPoliciesFor, seconds } from './generate.mjs';

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

test('appPaths become app-native path policies behind Edgible sign-in only', () => {
  const appPaths = [{ paths: ['/api/*', '/icons/*'], for: "the Bitwarden apps' vault calls" }];
  const base = { app: 'a', card: 'vaultwarden', organizationId: 'o', deviceId: 'd', port: 8222, compose: 'services: {}', appPaths };
  const org = declarationFor({ ...base, auth: 'org' }).spec.access[0].policies.auth;
  assert.deepEqual(org, { modes: ['edgible-login'], pathPolicies: [{ paths: ['/api/*', '/icons/*'], modes: ['app-native'], justification: "the Bitwarden apps' vault calls" }] });
  assert.deepEqual(declarationFor({ ...base, auth: 'none' }).spec.access[0].policies.auth, { modes: ['none'] });
  assert.deepEqual(declarationFor({ ...base, auth: 'org', appPaths: undefined }).spec.access[0].policies.auth, { modes: ['edgible-login'] });
  assert.deepEqual(pathPoliciesFor([], ['edgible-login']), []);
});

test('finish_setup sets path policies only on accesses behind Edgible sign-in', async () => {
  const { withPathPolicies } = await import('./write.mjs');
  const doc = { spec: { access: [{ policies: { auth: { modes: ['edgible-login'] } } }, { policies: { auth: { modes: ['none'] } } }] } };
  withPathPolicies(doc, [{ paths: ['/api/*'], for: 'the apps' }]);
  assert.deepEqual(doc.spec.access[0].policies.auth.pathPolicies, [{ paths: ['/api/*'], modes: ['app-native'], justification: 'the apps' }]);
  assert.equal(doc.spec.access[1].policies.auth.pathPolicies, undefined);
});

test('signInPaths keep paths behind sign-in inside appPaths', () => {
  assert.deepEqual(pathPoliciesFor([{ paths: ['/*'], for: 'the apps' }], ['edgible-login'], [{ paths: ['/web/*'], for: 'the web app' }]), [
    { paths: ['/*'], modes: ['app-native'], justification: 'the apps' },
    { paths: ['/web/*'], modes: ['edgible-login'], justification: 'the web app' }]);
});
