// node --test card-change.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { cardChange } from './server.mjs';

const items = [{ name: 'memos', test: { files: 'sha256:bbbb2364c27f7866', tested: '2026-11-21' } }, { name: 'untested', test: null }];

test('an app on an older version of its card is told so', () => {
  assert.match(cardChange({ labels: { card: 'memos', 'card-files': 'aaaa2364c27f7866' } }, items), /newer tested version of the memos card.*2026-11-21/);
});

test('the same version, no tag, or no test.yml says nothing', () => {
  assert.equal(cardChange({ labels: { card: 'memos', 'card-files': 'bbbb2364c27f7866' } }, items), '');
  assert.equal(cardChange({ labels: { card: 'memos' } }, items), '');
  assert.equal(cardChange({}, items), '');
  assert.equal(cardChange({ labels: { card: 'untested', 'card-files': 'aaaa' } }, items), '');
});
