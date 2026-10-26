// What the first start of a card downloads, so deploy_card and card_status can tell the person the
// wait is the app's images arriving, once, and about how long. The size is what test-card measured
// (test.yml measured: images:, from docker image inspect): the compressed download on Docker's
// containerd image store, the unpacked size on the classic one, and a little different by CPU. So
// it is only ever "about", never "unpacked" or "compressed".
// The same buckets are in card-kit's card-readme.py: change them together.
import YAML from 'yaml';

const UNITS = { KB: 1e3, MB: 1e6, GB: 1e9 };

// "1.1 GB", "147 MB", "10 KB" -> bytes; anything else -> null.
export function bytesOf(text) {
  const m = String(text ?? '').trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*(KB|MB|GB)$/i);
  return m ? Math.round(parseFloat(m[1]) * UNITS[m[2].toUpperCase()]) : null;
}

export function sizeWords(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`.replace('.0 ', ' ');
  if (bytes >= 1e6) return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} KB`;
}

// How long that takes on a typical home connection, in words and never as a promise.
export function timeWords(bytes) {
  if (bytes < 100e6) return 'under a minute';
  if (bytes < 500e6) return 'a minute or two';
  if (bytes < 1.5e9) return 'a few minutes';
  return 'ten minutes or more';
}

// The images' size from a card's test.yml text: every place's measured images together, or null.
export function imageDownload(testYml) {
  let measured;
  try { measured = YAML.parse(testYml || '')?.measured; } catch { return null; }
  const sizes = Object.values(measured || {}).map((p) => bytesOf(p?.images)).filter((b) => b !== null);
  if (!sizes.length) return null;
  const bytes = sizes.reduce((a, b) => a + b, 0);
  return { bytes, size: sizeWords(bytes), time: timeWords(bytes) };
}

// What deploy_card's `next` says about the wait. Two things take time and neither is Edgible being
// slow: the device downloading the images (once), and Edgible issuing the new address's certificate
// (usually under a minute, on its own). The server cannot push a message into the chat, so the
// assistant asks card_status, which can hold the call open (wait_seconds) until the address answers.
export function startNext(download) {
  const images = download
    ? `now downloads the app's images from their registry: about ${download.size}, ${download.time} on a typical home connection. That time is the download, not Edgible, and it happens once: later starts and upgrades reuse the images.`
    : 'now downloads its images from their registry: how long that takes depends on the device\'s connection, and it happens once.';
  return `Edgible has handed the app to the device, which ${images} A new address also needs its certificate, which Edgible issues on its own, usually within a minute. Tell the person this now, before they wait. Then call card_status with wait_seconds (up to 60) until it answers; until then "starting" is normal, so do not redeploy.`;
}

// The certificate state from `edgible app status --json` certificates: [{hostname, status}].
// "issued" when every one is, "pending" when one is on its way, the raw status for anything else
// (an error, say), undefined when the app reports none.
export function certificateState(certs) {
  const states = (Array.isArray(certs) ? certs : []).map((c) => String(c?.status || '').toLowerCase()).filter(Boolean);
  if (!states.length) return undefined;
  if (states.every((s) => s === 'issued')) return 'issued';
  const other = states.find((s) => s !== 'issued' && s !== 'pending');
  return other || 'pending';
}

// What card_status adds for an app these tools deployed that does not answer yet. While Edgible
// still says "deploying" the device is most likely downloading images. Once it says "deployed" the
// images are down. A pending certificate is named whenever it is, because it is real, and an issued
// one that has not started answering is DNS, which can take a minute more.
export function startingNote(download, minutesAgo, answering, status, certificate) {
  if (answering || minutesAgo === undefined || minutesAgo > 60) return undefined;
  const mins = Math.max(1, Math.round(minutesAgo));
  const parts = [];
  if (status !== 'deployed') {
    const what = download ? `about ${download.size} of images, ${download.time} on a typical home connection` : 'its images';
    parts.push(`the device is most likely still downloading ${what}`);
  }
  if (certificate === 'pending') {
    parts.push('Edgible is still issuing the address\'s certificate, which it does on its own, usually within a minute');
  } else if (status === 'deployed' && certificate && certificate !== 'issued') {
    parts.push(`the address's certificate shows "${certificate}", which Edgible needs to resolve`);
  } else if (status === 'deployed') {
    parts.push(certificate === 'issued'
      ? 'its certificate is issued, and the address can take a minute more to start answering (DNS)'
      : 'a new address needs its certificate and DNS, which can take a minute or two');
  }
  if (!parts.length) return undefined;
  return `Deployed ${mins} min ago and not answering yet: ${parts.join('; ')}. That is the app's registry, the device's connection and Edgible's usual set-up, not a fault. Wait and check again; do not redeploy.`;
}

// Call check() until it says done or the time is up: { done, tries, value }. sleep is a parameter so a
// test does not wait.
export async function pollUntil(check, { seconds, everyMs = 5000, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), now = Date.now } = {}) {
  const deadline = now() + seconds * 1000;
  let tries = 0;
  for (;;) {
    tries += 1;
    const value = await check();
    if (value.done) return { done: true, tries, value };
    if (now() + everyMs > deadline) return { done: false, tries, value };
    await sleep(everyMs);
  }
}
