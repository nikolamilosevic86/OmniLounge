// Phase G: TV/music media pure logic helpers.
// Kept dependency-free from the DOM so they can be unit tested with vitest's
// node environment, and duplicated verbatim into client/js/media.js per the
// project convention for pure-logic modules used from browser code.

const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function isValidYoutubeVideoId(id) {
  return typeof id === 'string' && YOUTUBE_ID_RE.test(id);
}

export function extractYoutubeVideoId(input) {
  if (!input) return null;
  const trimmed = input.trim();
  if (isValidYoutubeVideoId(trimmed)) return trimmed;

  try {
    const url = new URL(trimmed);
    if (url.hostname.replace(/^www\./, '') === 'youtu.be') {
      const candidate = url.pathname.slice(1);
      return isValidYoutubeVideoId(candidate) ? candidate : null;
    }
    if (url.hostname.replace(/^www\./, '').endsWith('youtube.com')) {
      const watchId = url.searchParams.get('v');
      if (watchId && isValidYoutubeVideoId(watchId)) return watchId;
      const embedMatch = url.pathname.match(/^\/embed\/([^/?]+)/);
      if (embedMatch && isValidYoutubeVideoId(embedMatch[1])) return embedMatch[1];
    }
  } catch {
    // not a valid URL at all
  }
  return null;
}

export function computeSyncPosition(session, nowMs) {
  if (!session) return 0;
  if (!session.isPlaying) return session.positionSeconds;
  const elapsedSeconds = Math.max(0, (nowMs - session.asOfMs) / 1000);
  return session.positionSeconds + elapsedSeconds;
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '';
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

export function sessionAppliesToItem(session, itemId) {
  if (!session || !itemId) return false;
  return session.itemId === itemId;
}

/** Live validation/preview state for a YouTube URL/ID input field (design doc
 * build_mode_ui_redesign_feature_design.md §8.7): 'empty' for blank input (no
 * feedback needed yet), 'invalid' for non-empty input that doesn't resolve to
 * a video id, or 'valid' with the resolved videoId and its public YouTube
 * thumbnail URL. Reuses `extractYoutubeVideoId` so the live-preview check is
 * always the exact same rule as the on-submit validation. */
export function youtubeLinkPreviewState(input) {
  const trimmed = (input || '').trim();
  if (!trimmed) {
    return { status: 'empty', videoId: null, thumbnailUrl: null };
  }
  const videoId = extractYoutubeVideoId(trimmed);
  if (!videoId) {
    return { status: 'invalid', videoId: null, thumbnailUrl: null };
  }
  return { status: 'valid', videoId, thumbnailUrl: `https://img.youtube.com/vi/${videoId}/mqdefault.jpg` };
}

/** Client-side pre-check for the TV video / music track add-edit form (design
 * doc build_mode_ui_redesign_feature_design.md §8.7, Gap 1): a title and a
 * resolvable YouTube URL/ID are both required. Shared by the Add and
 * Save-Changes (edit) paths so an edit can never be submitted with less
 * validation than a fresh add -- this is what lets Gap 1's remove-then-add
 * edit flow safely run the remove only after this passes. */
export function validateMediaItemInput({ title, youtubeInput } = {}) {
  const trimmedTitle = (title || '').trim();
  const youtubeVideoId = trimmedTitle ? extractYoutubeVideoId(youtubeInput) : null;
  if (!trimmedTitle || !youtubeVideoId) {
    return { valid: false, error: 'Enter a title and a valid YouTube URL or video ID.', youtubeVideoId: null };
  }
  return { valid: true, error: null, youtubeVideoId };
}
