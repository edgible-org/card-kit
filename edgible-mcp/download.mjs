// What the first start of a card downloads, so deploy_card and card_status can tell the person the
// wait is the app's images arriving, once, and about how long. The size is the images' size on
// disk that test-card measured (test.yml measured: images:), so the download itself is smaller.
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

// What deploy_card's `next` says about the wait.
export function startNext(download) {
  if (!download) {
    return 'Edgible has handed the app to the device, which now downloads its images from their registry: how long that takes depends on the device\'s connection, and it happens once. Tell the person now. card_status reports when it answers.';
  }
  return `Edgible has handed the app to the device, which now downloads the app's images from their registry: about ${download.size} once unpacked, ${download.time} on a typical home connection. That time is the download, not Edgible, and it happens once: later starts and upgrades reuse the images. Tell the person this now, before they wait. card_status reports when it answers; until then "starting" is normal, so do not redeploy.`;
}

// What card_status adds for an app these tools deployed that does not answer yet.
export function startingNote(download, minutesAgo, answering) {
  if (answering || minutesAgo === undefined || minutesAgo > 60) return undefined;
  const mins = Math.max(1, Math.round(minutesAgo));
  const what = download ? `about ${download.size} of images, ${download.time} on a typical home connection` : 'its images';
  return `Deployed ${mins} min ago and not answering yet: the device is most likely still downloading ${what}. That is the app's registry and the device's connection, not Edgible. Wait and check again; do not redeploy.`;
}
