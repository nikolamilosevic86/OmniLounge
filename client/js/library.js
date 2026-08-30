// View-model builders for the two-pane library UI shared by the bookshelf
// reader and the TV/music playlist: a persistent sidebar of entries beside a
// content pane, rather than a list screen you must leave to read anything.
// Pure and DOM-free so it can be unit tested under vitest's node environment;
// duplicated verbatim into client/js/library.js per the project convention.

import { clampProgress, truncateSummary } from './reader.js';
import { formatDuration } from './media.js';

const SEPARATOR = ' \u00b7 ';

// Anything this close to the end is "Finished": the last pixel of scroll is
// often unreachable, so requiring an exact 1 would strand readers at 99%.
const FINISHED_THRESHOLD = 0.999;

export function formatReadingStatus(progress) {
  const value = clampProgress(Number(progress) || 0);
  if (value >= FINISHED_THRESHOLD) return 'Finished';
  if (value <= 0) return 'Not started';
  return `${Math.round(value * 100)}% read`;
}

function joinMeta(parts) {
  return parts.filter(Boolean).join(SEPARATOR);
}

export function buildBookEntries(books, { activeId = null } = {}) {
  return (books || [])
    .filter((book) => book && book.bookId)
    .map((book, index) => {
      const progress = clampProgress(Number(book.progress) || 0);
      return {
        id: book.bookId,
        ordinal: index + 1,
        title: book.title || 'Untitled',
        meta: joinMeta([book.author, book.estReadMinutes ? `${book.estReadMinutes} min read` : null]),
        summary: book.summary ? truncateSummary(book.summary) : '',
        progress,
        status: formatReadingStatus(progress),
        isActive: book.bookId === activeId,
      };
    });
}

export function buildPlaylistEntries(objectType, items, { activeId = null } = {}) {
  const isTv = objectType === 'tv';
  return (items || [])
    .filter((item) => item && (isTv ? item.videoId : item.trackId))
    .map((item, index) => {
      const id = isTv ? item.videoId : item.trackId;
      const meta = isTv
        ? (item.description ? truncateSummary(item.description) : '')
        : joinMeta([item.artist, item.durationSeconds ? formatDuration(item.durationSeconds) : null]);
      return {
        id,
        ordinal: index + 1,
        title: item.title || 'Untitled',
        meta,
        summary: '',
        progress: 0,
        status: '',
        isActive: id === activeId,
      };
    });
}

/** Which entry the content pane should show on open: the caller's preferred
 * one (a resumed book, a synced video) if it is still there, else the top of
 * the list, else nothing. */
export function pickInitialEntryId(entries, preferredId) {
  if (!entries || entries.length === 0) return null;
  if (entries.some((entry) => entry.id === preferredId)) return preferredId;
  return entries[0].id;
}

export function filterEntries(entries, query) {
  const needle = (query || '').trim().toLowerCase();
  if (!needle) return entries || [];
  return (entries || []).filter((entry) => (
    `${entry.title} ${entry.meta} ${entry.summary}`.toLowerCase().includes(needle)
  ));
}

export function summarizeLibrary(noun, count, shown) {
  if (!count) return `No ${noun}s`;
  if (shown !== undefined && shown !== count) {
    return shown === 0 ? `No ${noun}s match` : `${shown} of ${count} ${noun}s`;
  }
  return count === 1 ? `1 ${noun}` : `${count} ${noun}s`;
}
