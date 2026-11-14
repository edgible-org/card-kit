// A device that is offline and has not been seen for PARKED_AFTER_HOURS counts as presumed parked:
// off on purpose, such as a test laptop with its lid closed. Its apps are then left out of the
// problems. Edgible has no parked state of its own yet (platform finding 56); when it has one,
// read it here instead. A device that checks in again is back in normal monitoring at once.
export const PARKED_AFTER_HOURS = Number(process.env.EDGIBLE_PARKED_AFTER_HOURS) || 24;

export function presumedParked(d, now = Date.now()) {
  if (!d || d.status !== 'offline') return false;
  const seen = Date.parse(d.lastSeen || '');
  return !Number.isFinite(seen) || now - seen > PARKED_AFTER_HOURS * 3600e3;
}

// "2026-11-09", or "an unknown time" for a device that never reported.
export function lastSeenDay(d) {
  const seen = Date.parse(d?.lastSeen || '');
  return Number.isFinite(seen) ? new Date(seen).toISOString().slice(0, 10) : 'an unknown time';
}

// One phrase for a device that is not online, for refusals and evidence.
export function offlineWords(d, now = Date.now()) {
  if (presumedParked(d, now)) return `offline since ${lastSeenDay(d)}, presumed parked (off for over ${PARKED_AFTER_HOURS} hours)`;
  return d?.status || 'unknown';
}
