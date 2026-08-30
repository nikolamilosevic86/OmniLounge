import { describe, it, expect } from 'vitest';
import {
  buildBookEntries,
  buildPlaylistEntries,
  filterEntries,
  formatReadingStatus,
  pickInitialEntryId,
  summarizeLibrary,
} from '../src/library.js';

const BOOKS = [
  { bookId: 'b1', title: 'Vinci, 1452', author: 'Curator', estReadMinutes: 3, summary: 'Birth and family.', progress: 0 },
  { bookId: 'b2', title: 'The Bottega', author: 'Curator', estReadMinutes: 4, progress: 0.5 },
  { bookId: 'b3', title: 'Amboise, 1519', progress: 1 },
];

const VIDEOS = [
  { videoId: 'v1', title: 'Decoding da Vinci', description: 'A documentary.', youtubeVideoId: 'NGsUFvwgvCo' },
  { videoId: 'v2', title: 'Flying Machines', youtubeVideoId: 'Y0_htkvCVpE' },
];

const TRACKS = [
  { trackId: 't1', title: 'The Italian Lute', artist: 'Brilliant Classics', durationSeconds: 3725 },
  { trackId: 't2', title: 'Ave Maria', youtubeVideoId: 'LUAgAF4Khmg' },
];

describe('formatReadingStatus', () => {
  it('reports an untouched book as not started', () => {
    expect(formatReadingStatus(0)).toBe('Not started');
  });

  it('treats a missing progress value as not started', () => {
    expect(formatReadingStatus(undefined)).toBe('Not started');
    expect(formatReadingStatus(null)).toBe('Not started');
  });

  it('reports a partially read book as a rounded percentage', () => {
    expect(formatReadingStatus(0.5)).toBe('50% read');
    expect(formatReadingStatus(0.426)).toBe('43% read');
  });

  it('reports a fully read book as finished', () => {
    expect(formatReadingStatus(1)).toBe('Finished');
  });

  it('treats all-but-the-last-pixel as finished so the label is reachable', () => {
    expect(formatReadingStatus(0.999)).toBe('Finished');
  });

  it('clamps nonsense values instead of rendering them', () => {
    expect(formatReadingStatus(-3)).toBe('Not started');
    expect(formatReadingStatus(42)).toBe('Finished');
  });

  it('never rounds an in-progress book up to a misleading 100%', () => {
    expect(formatReadingStatus(0.9994)).toBe('Finished');
    expect(formatReadingStatus(0.97)).toBe('97% read');
  });
});

describe('buildBookEntries', () => {
  it('maps each book to a sidebar entry keyed by book id', () => {
    const entries = buildBookEntries(BOOKS);
    expect(entries.map((e) => e.id)).toEqual(['b1', 'b2', 'b3']);
    expect(entries[0].title).toBe('Vinci, 1452');
  });

  it('joins author and read time into one meta line', () => {
    expect(buildBookEntries(BOOKS)[0].meta).toBe('Curator \u00b7 3 min read');
  });

  it('omits missing meta fields rather than leaving empty separators', () => {
    expect(buildBookEntries(BOOKS)[2].meta).toBe('');
  });

  it('truncates long summaries for the sidebar', () => {
    const long = 'x'.repeat(400);
    const [entry] = buildBookEntries([{ bookId: 'b', title: 'T', summary: long }]);
    expect(entry.summary.length).toBeLessThan(long.length);
    expect(entry.summary.endsWith('\u2026')).toBe(true);
  });

  it('carries a clamped progress fraction and a human status', () => {
    const entries = buildBookEntries(BOOKS);
    expect(entries[1].progress).toBe(0.5);
    expect(entries[1].status).toBe('50% read');
    expect(entries[2].status).toBe('Finished');
  });

  it('marks the active entry so the sidebar can highlight it', () => {
    const entries = buildBookEntries(BOOKS, { activeId: 'b2' });
    expect(entries.map((e) => e.isActive)).toEqual([false, true, false]);
  });

  it('marks nothing active when no book is open', () => {
    expect(buildBookEntries(BOOKS).every((e) => e.isActive === false)).toBe(true);
  });

  it('drops entries with no usable id instead of rendering dead rows', () => {
    expect(buildBookEntries([{ title: 'Orphan' }, ...BOOKS])).toHaveLength(3);
  });

  it('returns an empty list for missing input', () => {
    expect(buildBookEntries(undefined)).toEqual([]);
    expect(buildBookEntries(null)).toEqual([]);
  });
});

describe('buildPlaylistEntries', () => {
  it('keys tv entries by video id and music entries by track id', () => {
    expect(buildPlaylistEntries('tv', VIDEOS).map((e) => e.id)).toEqual(['v1', 'v2']);
    expect(buildPlaylistEntries('music_player', TRACKS).map((e) => e.id)).toEqual(['t1', 't2']);
  });

  it('uses the description as tv meta and artist/duration as music meta', () => {
    expect(buildPlaylistEntries('tv', VIDEOS)[0].meta).toBe('A documentary.');
    expect(buildPlaylistEntries('music_player', TRACKS)[0].meta).toBe('Brilliant Classics \u00b7 62:05');
  });

  it('leaves meta empty when the item carries none', () => {
    expect(buildPlaylistEntries('tv', VIDEOS)[1].meta).toBe('');
    expect(buildPlaylistEntries('music_player', TRACKS)[1].meta).toBe('');
  });

  it('numbers entries so the playlist reads as an ordered list', () => {
    expect(buildPlaylistEntries('tv', VIDEOS).map((e) => e.ordinal)).toEqual([1, 2]);
  });

  it('marks the playing entry as active', () => {
    const entries = buildPlaylistEntries('music_player', TRACKS, { activeId: 't2' });
    expect(entries.map((e) => e.isActive)).toEqual([false, true]);
  });

  it('never reports reading progress for playlist entries', () => {
    expect(buildPlaylistEntries('tv', VIDEOS)[0].status).toBe('');
  });

  it('returns an empty list for missing input', () => {
    expect(buildPlaylistEntries('tv', undefined)).toEqual([]);
  });
});

describe('pickInitialEntryId', () => {
  const entries = buildBookEntries(BOOKS);

  it('prefers the requested entry when it is on the shelf', () => {
    expect(pickInitialEntryId(entries, 'b3')).toBe('b3');
  });

  it('falls back to the first entry when the request is unknown', () => {
    expect(pickInitialEntryId(entries, 'gone')).toBe('b1');
  });

  it('falls back to the first entry when nothing is requested', () => {
    expect(pickInitialEntryId(entries, null)).toBe('b1');
  });

  it('returns null for an empty shelf so callers can show the empty state', () => {
    expect(pickInitialEntryId([], 'b1')).toBeNull();
  });
});

describe('filterEntries', () => {
  const entries = buildBookEntries(BOOKS);

  it('returns everything for a blank query', () => {
    expect(filterEntries(entries, '')).toHaveLength(3);
    expect(filterEntries(entries, '   ')).toHaveLength(3);
    expect(filterEntries(entries, undefined)).toHaveLength(3);
  });

  it('matches titles case-insensitively', () => {
    expect(filterEntries(entries, 'bottega').map((e) => e.id)).toEqual(['b2']);
  });

  it('matches the meta line too, so an author search works', () => {
    expect(filterEntries(entries, 'curator').map((e) => e.id)).toEqual(['b1', 'b2']);
  });

  it('matches the summary text', () => {
    expect(filterEntries(entries, 'birth').map((e) => e.id)).toEqual(['b1']);
  });

  it('ignores surrounding whitespace in the query', () => {
    expect(filterEntries(entries, '  amboise ').map((e) => e.id)).toEqual(['b3']);
  });

  it('returns an empty list when nothing matches', () => {
    expect(filterEntries(entries, 'zzz')).toEqual([]);
  });
});

describe('summarizeLibrary', () => {
  it('pluralizes the shelf count', () => {
    expect(summarizeLibrary('book', 0)).toBe('No books');
    expect(summarizeLibrary('book', 1)).toBe('1 book');
    expect(summarizeLibrary('book', 7)).toBe('7 books');
  });

  it('works for videos and tracks as well', () => {
    expect(summarizeLibrary('video', 4)).toBe('4 videos');
    expect(summarizeLibrary('track', 1)).toBe('1 track');
    expect(summarizeLibrary('track', 0)).toBe('No tracks');
  });

  it('shows the visible count against the total while filtering', () => {
    expect(summarizeLibrary('book', 7, 1)).toBe('1 of 7 books');
    expect(summarizeLibrary('track', 4, 2)).toBe('2 of 4 tracks');
  });

  it('does not qualify the count when the filter matches everything', () => {
    expect(summarizeLibrary('book', 7, 7)).toBe('7 books');
  });

  it('reports an empty filter result plainly', () => {
    expect(summarizeLibrary('book', 7, 0)).toBe('No books match');
  });

  it('ignores a shown count on an empty shelf', () => {
    expect(summarizeLibrary('book', 0, 0)).toBe('No books');
  });
});
