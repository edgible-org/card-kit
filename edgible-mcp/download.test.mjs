// node --test download.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { bytesOf, certificateState, imageDownload, pollUntil, sizeWords, startNext, startingNote, timeWords } from './download.mjs';

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

test('deploy_card says what the wait is, with and without a size, and that the certificate takes a minute', () => {
  const d = imageDownload('measured:\n  p:\n    images: 854 MB\n');
  assert.match(startNext(d), /about 854 MB, a few minutes.*not Edgible.*certificate.*usually within a minute.*wait_seconds.*do not redeploy/);
  assert.match(startNext(null), /downloads its images.*connection.*certificate/);
  assert.doesNotMatch(startNext(d), /two minutes|unpacked/);
});

test('the certificate state is issued, pending, or whatever else Edgible says', () => {
  assert.equal(certificateState([{ hostname: 'a', status: 'issued' }]), 'issued');
  assert.equal(certificateState([{ hostname: 'a', status: 'pending' }]), 'pending');
  assert.equal(certificateState([{ status: 'issued' }, { status: 'pending' }]), 'pending');
  assert.equal(certificateState([{ status: 'issued' }, { status: 'Failed' }]), 'failed');
  assert.equal(certificateState([]), undefined);
  assert.equal(certificateState(null), undefined);
});

test('card_status says the real reason an app does not answer, and stays quiet otherwise', () => {
  const d = imageDownload('measured:\n  p:\n    images: 2100 MB\n');
  // Deploying: images, and the certificate when it is pending too.
  assert.match(startingNote(d, 3, false, 'deploying', 'pending'), /3 min ago.*still downloading about 2\.1 GB.*ten minutes or more.*still issuing.*certificate.*do not redeploy/);
  assert.match(startingNote(null, 0.2, false, 'deploying'), /1 min ago.*its images/);
  // Deployed: the images are down, so never "downloading".
  assert.match(startingNote(d, 2, false, 'deployed', 'pending'), /still issuing the address's certificate.*usually within a minute/);
  assert.doesNotMatch(startingNote(d, 2, false, 'deployed', 'pending'), /downloading/);
  assert.match(startingNote(d, 2, false, 'deployed', 'issued'), /certificate is issued.*DNS/);
  assert.match(startingNote(d, 2, false, 'deployed', 'failed'), /certificate shows "failed"/);
  assert.match(startingNote(d, 2, false, 'deployed'), /certificate and DNS.*minute or two/);
  // Answering, too old, or never deployed by these tools: nothing to add.
  assert.equal(startingNote(d, 3, true, 'deployed', 'issued'), undefined);
  assert.equal(startingNote(d, 90, false, 'deploying'), undefined);
  assert.equal(startingNote(d, undefined, false, 'deploying'), undefined);
});

test('pollUntil returns as soon as the check is done, and gives up at the deadline', async () => {
  let clock = 0, sleeps = 0;
  const env = { everyMs: 5000, now: () => clock, sleep: async (ms) => { clock += ms; sleeps += 1; } };
  let n = 0;
  const ok = await pollUntil(async () => ({ done: ++n >= 3, n }), { seconds: 60, ...env });
  assert.equal(ok.done, true);
  assert.equal(ok.tries, 3);
  assert.equal(sleeps, 2);
  clock = 0; sleeps = 0;
  const never = await pollUntil(async () => ({ done: false }), { seconds: 20, ...env });
  assert.equal(never.done, false);
  assert.equal(never.tries, 5); // t = 0, 5, 10, 15 and 20 s: the last check is at the deadline
  assert.equal(sleeps, 4);
});
