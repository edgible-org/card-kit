// node --test download.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { bytesOf, imageDownload, sizeWords, startNext, startingNote, timeWords } from './download.mjs';

test('sizes read and print the way test-card writes them', () => {
  assert.equal(bytesOf('1.1 GB'), 1.1e9);
  assert.equal(bytesOf('147 MB'), 147e6);
  assert.equal(bytesOf('10 KB'), 10e3);
  assert.equal(bytesOf('lots'), null);
  assert.equal(bytesOf(undefined), null);
  assert.equal(sizeWords(2.1e9), '2.1 GB');
  assert.equal(sizeWords(2e9), '2 GB');
  assert.equal(sizeWords(854e6), '854 MB');
});

test('the time is a bucket for a typical home connection', () => {
  assert.equal(timeWords(10e6), 'under a minute');
  assert.equal(timeWords(147e6), 'a minute or two');
  assert.equal(timeWords(854e6), 'a few minutes');
  assert.equal(timeWords(2.1e9), 'ten minutes or more');
});

test('a card\'s test.yml gives the images of every place together', () => {
  const one = 'measured:\n  bloglite:\n    memory: 3 MB\n    images: 10 MB\n    data: 147 KB\n';
  assert.deepEqual(imageDownload(one), { bytes: 10e6, size: '10 MB', time: 'under a minute' });
  const two = 'measured:\n  app:\n    images: 700 MB\n  helper:\n    images: 900 MB\n';
  assert.equal(imageDownload(two).size, '1.6 GB');
});

test('no measurement, or a test.yml that does not parse, gives null', () => {
  assert.equal(imageDownload(''), null);
  assert.equal(imageDownload(undefined), null);
  assert.equal(imageDownload('result: pass\n'), null);
  assert.equal(imageDownload(': : [\n'), null);
});

test('deploy_card says what the wait is, with and without a size', () => {
  const d = imageDownload('measured:\n  p:\n    images: 854 MB\n');
  assert.match(startNext(d), /about 854 MB.*a few minutes.*not Edgible.*do not redeploy/);
  assert.match(startNext(null), /downloads its images.*connection/);
  assert.doesNotMatch(startNext(d), /two minutes/);
});

test('card_status explains a recent app that does not answer, and stays quiet otherwise', () => {
  const d = imageDownload('measured:\n  p:\n    images: 2100 MB\n');
  assert.match(startingNote(d, 3, false), /3 min ago.*2\.1 GB.*ten minutes or more.*not Edgible/);
  assert.match(startingNote(null, 0.2, false), /1 min ago.*its images/);
  assert.equal(startingNote(d, 3, true), undefined);
  // Once Edgible says deployed, the images are down: the wait is the address, not a download.
  assert.match(startingNote(d, 2, false, 'deployed'), /reports it deployed.*certificate and DNS.*do not redeploy/);
  assert.doesNotMatch(startingNote(d, 2, false, 'deployed'), /downloading/);
  assert.match(startingNote(d, 2, false, 'deploying'), /still downloading/);
  assert.equal(startingNote(d, 90, false), undefined);
  assert.equal(startingNote(d, undefined, false), undefined);
});
