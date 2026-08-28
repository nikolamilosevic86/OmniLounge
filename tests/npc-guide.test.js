import { describe, it, expect } from 'vitest';
import {
  MAX_WAYPOINT_LABEL_LENGTH,
  applyNpcMove,
  characterOffersTour,
  formatTourStatus,
  isFollowingTour,
  normalizeWaypointLabel,
  tourButtonState,
} from '../src/npc-guide.js';

const character = (overrides = {}) => ({
  objectId: 'npc-1',
  objectType: 'ai_character',
  x: 100,
  y: 100,
  waypoints: [{ waypointId: 'wp-1', x: 200, y: 200, label: 'Library' }],
  tour: null,
  ...overrides,
});

describe('characterOffersTour', () => {
  it('is true for an AI character with at least one stop', () => {
    expect(characterOffersTour(character())).toBe(true);
  });

  it('is false for an AI character with no stops', () => {
    expect(characterOffersTour(character({ waypoints: [] }))).toBe(false);
  });

  it('is false when waypoints are missing entirely', () => {
    expect(characterOffersTour(character({ waypoints: undefined }))).toBe(false);
  });

  it('is false for a non-character object that somehow carries waypoints', () => {
    expect(characterOffersTour(character({ objectType: 'table' }))).toBe(false);
  });

  it('is false for null', () => {
    expect(characterOffersTour(null)).toBe(false);
  });
});

describe('isFollowingTour', () => {
  it('is true when the player is in the follower list', () => {
    const obj = character({ tour: { status: 'walking', followers: ['p1', 'p2'] } });
    expect(isFollowingTour(obj, 'p2')).toBe(true);
  });

  it('is false when the player is not following', () => {
    const obj = character({ tour: { status: 'walking', followers: ['p1'] } });
    expect(isFollowingTour(obj, 'p2')).toBe(false);
  });

  it('is false when no tour is running', () => {
    expect(isFollowingTour(character(), 'p1')).toBe(false);
  });

  it('is false without a player id', () => {
    const obj = character({ tour: { status: 'walking', followers: ['p1'] } });
    expect(isFollowingTour(obj, null)).toBe(false);
  });
});

describe('tourButtonState', () => {
  it('offers "follow" for a guide you are not yet following', () => {
    expect(tourButtonState(character(), 'p1')).toEqual({ follow: true, stop: false });
  });

  it('offers "stop" once you are following', () => {
    const obj = character({ tour: { status: 'walking', followers: ['p1'] } });
    expect(tourButtonState(obj, 'p1')).toEqual({ follow: false, stop: true });
  });

  it('offers neither button for a character with no route', () => {
    expect(tourButtonState(character({ waypoints: [] }), 'p1')).toEqual({ follow: false, stop: false });
  });

  it('never offers both buttons at once', () => {
    const cases = [character(), character({ tour: { status: 'walking', followers: ['p1'] } }), character({ waypoints: [] })];
    for (const obj of cases) {
      const { follow, stop } = tourButtonState(obj, 'p1');
      expect(follow && stop).toBe(false);
    }
  });

  it('still offers "follow" to a second visitor while someone else follows', () => {
    const obj = character({ tour: { status: 'walking', followers: ['p1'] } });
    expect(tourButtonState(obj, 'p2')).toEqual({ follow: true, stop: false });
  });
});

describe('formatTourStatus', () => {
  it('is empty when no tour is running', () => {
    expect(formatTourStatus(null)).toBe('');
    expect(formatTourStatus({})).toBe('');
  });

  it('reports walking progress as a 1-based stop number', () => {
    expect(formatTourStatus({ status: 'walking', waypointIndex: 0, waypointCount: 3 })).toBe('Walking (stop 1 of 3)');
  });

  it('reports a pause as explaining', () => {
    expect(formatTourStatus({ status: 'paused', waypointIndex: 1, waypointCount: 3 })).toBe('Explaining (stop 2 of 3)');
  });

  it('clamps the stop number to the route length past the last stop', () => {
    expect(formatTourStatus({ status: 'walking', waypointIndex: 3, waypointCount: 3 })).toBe('Walking (stop 3 of 3)');
  });

  it('describes the walk home', () => {
    expect(formatTourStatus({ status: 'returning', waypointIndex: 2, waypointCount: 3 })).toBe('Heading back...');
  });

  it('describes a completed tour', () => {
    expect(formatTourStatus({ status: 'finished' })).toBe('Tour complete');
  });
});

describe('applyNpcMove', () => {
  const objects = () => [
    { objectId: 'npc-1', objectType: 'ai_character', x: 100, y: 100, tour: { status: 'walking', followers: ['p1'] } },
    { objectId: 'table-1', objectType: 'table', x: 10, y: 10 },
  ];

  const payload = (overrides = {}) => ({
    objectId: 'npc-1',
    position: { x: 150, y: 120 },
    status: 'walking',
    waypointIndex: 0,
    finished: false,
    ...overrides,
  });

  it('updates the moving character position', () => {
    const next = applyNpcMove(objects(), payload());
    expect(next[0].x).toBe(150);
    expect(next[0].y).toBe(120);
  });

  it('leaves other objects untouched', () => {
    const next = applyNpcMove(objects(), payload());
    expect(next[1]).toEqual({ objectId: 'table-1', objectType: 'table', x: 10, y: 10 });
  });

  it('does not mutate the input array or its objects', () => {
    const input = objects();
    applyNpcMove(input, payload());
    expect(input[0].x).toBe(100);
  });

  it('returns the same array reference when nothing matched, so callers can skip re-rendering', () => {
    const input = objects();
    expect(applyNpcMove(input, payload({ objectId: 'ghost' }))).toBe(input);
  });

  it('preserves the follower list while updating tour status', () => {
    const next = applyNpcMove(objects(), payload({ status: 'paused', waypointIndex: 1 }));
    expect(next[0].tour).toEqual({ status: 'paused', waypointIndex: 1, followers: ['p1'] });
  });

  it('clears the tour once it finishes', () => {
    const next = applyNpcMove(objects(), payload({ finished: true, status: 'finished' }));
    expect(next[0].tour).toBeNull();
  });

  it('ignores malformed payloads rather than throwing', () => {
    const input = objects();
    expect(applyNpcMove(input, null)).toBe(input);
    expect(applyNpcMove(input, { objectId: 'npc-1' })).toBe(input);
    expect(applyNpcMove(null, payload())).toBeNull();
  });
});

describe('normalizeWaypointLabel', () => {
  it('trims surrounding whitespace', () => {
    expect(normalizeWaypointLabel('  The library  ')).toBe('The library');
  });

  it('returns null for an empty note, since a silent stop is allowed', () => {
    expect(normalizeWaypointLabel('')).toBeNull();
    expect(normalizeWaypointLabel('   ')).toBeNull();
    expect(normalizeWaypointLabel(undefined)).toBeNull();
  });

  it('accepts a note exactly at the length limit', () => {
    const label = 'x'.repeat(MAX_WAYPOINT_LABEL_LENGTH);
    expect(normalizeWaypointLabel(label)).toBe(label);
  });

  it('rejects an over-long note', () => {
    expect(() => normalizeWaypointLabel('x'.repeat(MAX_WAYPOINT_LABEL_LENGTH + 1)))
      .toThrow(/characters or fewer/);
  });
});
