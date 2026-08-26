import { describe, it, expect } from 'vitest';
import {
  clampProgress,
  computeScrollProgress,
  formatEstReadTime,
  truncateSummary,
  escapeHtml,
  renderBookContent,
} from '../src/reader.js';

describe('clampProgress', () => {
  it('clamps values above 1 down to 1', () => {
    expect(clampProgress(1.5)).toBe(1);
  });

  it('clamps negative values up to 0', () => {
    expect(clampProgress(-0.2)).toBe(0);
  });

  it('passes through in-range values unchanged', () => {
    expect(clampProgress(0.42)).toBe(0.42);
  });
});

describe('computeScrollProgress', () => {
  it('returns 1 when content fits entirely without scrolling', () => {
    expect(computeScrollProgress(0, 300, 300)).toBe(1);
    expect(computeScrollProgress(0, 200, 300)).toBe(1);
  });

  it('returns 0 when scrolled to the very top of overflowing content', () => {
    expect(computeScrollProgress(0, 1000, 200)).toBe(0);
  });

  it('returns 1 when scrolled to the very bottom of overflowing content', () => {
    expect(computeScrollProgress(800, 1000, 200)).toBe(1);
  });

  it('returns a proportional value while scrolling through the middle', () => {
    expect(computeScrollProgress(400, 1000, 200)).toBeCloseTo(0.5, 5);
  });

  it('clamps results into the [0, 1] range for out-of-range scrollTop', () => {
    expect(computeScrollProgress(-50, 1000, 200)).toBe(0);
    expect(computeScrollProgress(5000, 1000, 200)).toBe(1);
  });
});

describe('formatEstReadTime', () => {
  it('formats a positive minute count', () => {
    expect(formatEstReadTime(12)).toBe('12 min read');
  });

  it('returns an empty string for null/undefined', () => {
    expect(formatEstReadTime(null)).toBe('');
    expect(formatEstReadTime(undefined)).toBe('');
  });
});

describe('truncateSummary', () => {
  it('returns short text unchanged', () => {
    expect(truncateSummary('short summary')).toBe('short summary');
  });

  it('returns an empty string for falsy input', () => {
    expect(truncateSummary(null)).toBe('');
    expect(truncateSummary('')).toBe('');
  });

  it('truncates long text and appends an ellipsis', () => {
    const long = 'a'.repeat(200);
    const result = truncateSummary(long, 140);
    expect(result.length).toBe(140);
    expect(result.endsWith('…')).toBe(true);
  });
});

describe('escapeHtml', () => {
  it('escapes angle brackets and ampersands', () => {
    expect(escapeHtml('<script>alert("x")&</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&amp;&lt;/script&gt;'
    );
  });

  it('leaves plain text unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
});

describe('renderBookContent', () => {
  it('escapes HTML in inline content to prevent injection', () => {
    const html = renderBookContent({ contentType: 'inline', contentBody: '<img src=x onerror=alert(1)>' });
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('converts double newlines into paragraph breaks for inline content', () => {
    const html = renderBookContent({ contentType: 'inline', contentBody: 'Para one.\n\nPara two.' });
    expect(html).toContain('<p>Para one.</p>');
    expect(html).toContain('<p>Para two.</p>');
  });

  it('renders markdown bold, italic, and headers while escaping raw HTML', () => {
    const html = renderBookContent({
      contentType: 'markdown',
      contentBody: '# Title\n\n**bold** and *italic* and <b>raw</b>',
    });
    expect(html).toContain('<h1>Title</h1>');
    expect(html).toContain('<strong>bold</strong>');
    expect(html).toContain('<em>italic</em>');
    expect(html).not.toContain('<b>raw</b>');
    expect(html).toContain('&lt;b&gt;raw&lt;/b&gt;');
  });
});
