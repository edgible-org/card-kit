import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PARKED_AFTER_HOURS, lastSeenDay, offlineWords, presumedParked } from './parked.mjs';

const now = Date.parse('2026-11-15T12:00:00Z');
const hoursAgo = (h) => new Date(now - h * 3600e3).toISOString();

test('an online device is never parked, however long ago it was seen', () => {
  assert.equal(presumedParked({ status: 'online', lastSeen: hoursAgo(1000) }, now), false);
});

test('an offline device is parked only after the threshold', () => {
  assert.equal(PARKED_AFTER_HOURS, 24);
  assert.equal(presumedParked({ status: 'offline', lastSeen: hoursAgo(2) }, now), false);
  assert.equal(presumedParked({ status: 'offline', lastSeen: hoursAgo(25) }, now), true);
});

test('an offline device that never reported counts as parked', () => {
  assert.equal(presumedParked({ status: 'offline' }, now), true);
  assert.equal(lastSeenDay({}), 'an unknown time');
});

test('offlineWords says since when, or just the status', () => {
  assert.equal(offlineWords({ status: 'offline', lastSeen: '2026-11-09T12:10:19Z' }, now),
    'offline since 2026-11-09, presumed parked (off for over 24 hours)');
  assert.equal(offlineWords({ status: 'offline', lastSeen: hoursAgo(1) }, now), 'offline');
});
