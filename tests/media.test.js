import { describe, it, expect } from 'vitest';
import {
  isValidYoutubeVideoId,
  extractYoutubeVideoId,
  computeSyncPosition,
  formatDuration,
  sessionAppliesToItem,
  youtubeLinkPreviewState,
  validateMediaItemInput,
} from '../src/media.js';

describe('isValidYoutubeVideoId', () => {
  it('accepts exactly 11 url-safe characters', () => {
    expect(isValidYoutubeVideoId('dQw4w9WgXcQ')).toBe(true);
  });

  it('rejects ids that are too short', () => {
    expect(isValidYoutubeVideoId('short')).toBe(false);
  });

  it('rejects ids with invalid characters', () => {
    expect(isValidYoutubeVideoId('abc def!!!!')).toBe(false);
  });
});

describe('extractYoutubeVideoId', () => {
  it('passes through a bare valid id', () => {
    expect(extractYoutubeVideoId('dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it('extracts the id from a watch url', () => {
    expect(extractYoutubeVideoId('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it('extracts the id from a watch url with extra query params', () => {
    expect(extractYoutubeVideoId('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s')).toBe('dQw4w9WgXcQ');
  });

  it('extracts the id from a youtu.be short url', () => {
    expect(extractYoutubeVideoId('https://youtu.be/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it('extracts the id from an embed url', () => {
    expect(extractYoutubeVideoId('https://www.youtube.com/embed/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it('returns null for an unrecognized input', () => {
    expect(extractYoutubeVideoId('not a youtube link')).toBe(null);
  });

  it('returns null for empty input', () => {
    expect(extractYoutubeVideoId('')).toBe(null);
  });
});

describe('computeSyncPosition', () => {
  it('returns the frozen position when paused', () => {
    const session = { isPlaying: false, positionSeconds: 10, asOfMs: 1000 };
    expect(computeSyncPosition(session, 5000)).toBe(10);
  });

  it('interpolates forward while playing', () => {
    const session = { isPlaying: true, positionSeconds: 0, asOfMs: 1000 };
    expect(computeSyncPosition(session, 6000)).toBeCloseTo(5, 5);
  });

  it('never goes backward if now is before asOfMs', () => {
    const session = { isPlaying: true, positionSeconds: 10, asOfMs: 5000 };
    expect(computeSyncPosition(session, 1000)).toBe(10);
  });

  it('returns 0 when there is no session', () => {
    expect(computeSyncPosition(null, 1000)).toBe(0);
  });
});

describe('formatDuration', () => {
  it('formats seconds under a minute', () => {
    expect(formatDuration(45)).toBe('0:45');
  });

  it('formats minutes and seconds with zero-padded seconds', () => {
    expect(formatDuration(125)).toBe('2:05');
  });

  it('returns an empty string for null or undefined', () => {
    expect(formatDuration(null)).toBe('');
    expect(formatDuration(undefined)).toBe('');
  });
});

describe('sessionAppliesToItem', () => {
  it('returns true when the session itemId matches the given item', () => {
    expect(sessionAppliesToItem({ itemId: 'video-1' }, 'video-1')).toBe(true);
  });

  it('returns false when the session is for a different item', () => {
    expect(sessionAppliesToItem({ itemId: 'video-1' }, 'video-2')).toBe(false);
  });

  it('returns false when there is no session', () => {
    expect(sessionAppliesToItem(null, 'video-1')).toBe(false);
  });

  it('returns false when there is no item currently displayed', () => {
    expect(sessionAppliesToItem({ itemId: 'video-1' }, null)).toBe(false);
  });
});

describe('youtubeLinkPreviewState (design doc build_mode_ui_redesign_feature_design.md section 8.7)', () => {
  it('returns an empty status for an empty or whitespace-only input, with no thumbnail', () => {
    expect(youtubeLinkPreviewState('')).toEqual({ status: 'empty', videoId: null, thumbnailUrl: null });
    expect(youtubeLinkPreviewState('   ')).toEqual({ status: 'empty', videoId: null, thumbnailUrl: null });
    expect(youtubeLinkPreviewState(undefined)).toEqual({ status: 'empty', videoId: null, thumbnailUrl: null });
  });

  it('returns an invalid status with no thumbnail for unrecognized non-empty input', () => {
    expect(youtubeLinkPreviewState('not a youtube link')).toEqual({ status: 'invalid', videoId: null, thumbnailUrl: null });
  });

  it('returns a valid status with a video id and mqdefault thumbnail url for a bare id', () => {
    expect(youtubeLinkPreviewState('dQw4w9WgXcQ')).toEqual({
      status: 'valid',
      videoId: 'dQw4w9WgXcQ',
      thumbnailUrl: 'https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg',
    });
  });

  it('returns a valid status for a full watch URL, matching extractYoutubeVideoId', () => {
    expect(youtubeLinkPreviewState('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toEqual({
      status: 'valid',
      videoId: 'dQw4w9WgXcQ',
      thumbnailUrl: 'https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg',
    });
  });
});

describe('validateMediaItemInput (design doc build_mode_ui_redesign_feature_design.md section 8.7, Gap 1)', () => {
  it('rejects a missing title', () => {
    expect(validateMediaItemInput({ title: '', youtubeInput: 'dQw4w9WgXcQ' })).toEqual({
      valid: false, error: 'Enter a title and a valid YouTube URL or video ID.', youtubeVideoId: null,
    });
  });

  it('rejects a missing or invalid youtube link', () => {
    expect(validateMediaItemInput({ title: 'My Video', youtubeInput: 'not a link' })).toEqual({
      valid: false, error: 'Enter a title and a valid YouTube URL or video ID.', youtubeVideoId: null,
    });
  });

  it('accepts a valid title and youtube link, resolving the video id', () => {
    expect(validateMediaItemInput({ title: 'My Video', youtubeInput: 'https://youtu.be/dQw4w9WgXcQ' })).toEqual({
      valid: true, error: null, youtubeVideoId: 'dQw4w9WgXcQ',
    });
  });
});
