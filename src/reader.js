// Phase F: Bookshelf reader pure logic helpers.
// Kept dependency-free from the DOM so they can be unit tested with vitest's
// node environment, and duplicated verbatim into client/js/reader.js per the
// project convention for pure-logic modules used from browser code.

export function clampProgress(value) {
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

export function computeScrollProgress(scrollTop, scrollHeight, clientHeight) {
  const scrollable = scrollHeight - clientHeight;
  if (scrollable <= 0) return 1;
  return clampProgress(scrollTop / scrollable);
}

export function formatEstReadTime(minutes) {
  if (minutes === null || minutes === undefined) return '';
  return `${minutes} min read`;
}

export function truncateSummary(text, maxLen = 140) {
  if (!text) return '';
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 1).trimEnd()}\u2026`;
}

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Client-side pre-check for the book add/edit form (design doc
 * build_mode_ui_redesign_feature_design.md §8.7, Gap 1): a title and content
 * are both required. Shared by the Add and Save-Changes (edit) paths so an
 * edit can never be submitted with less validation than a fresh add. */
export function validateBookInput({ title, contentBody } = {}) {
  const trimmedTitle = (title || '').trim();
  const trimmedContent = (contentBody || '').trim();
  if (!trimmedTitle || !trimmedContent) {
    return { valid: false, error: 'Enter a title and content for the book.' };
  }
  return { valid: true, error: null };
}

function paragraphsFromEscaped(escaped) {
  return escaped
    .split(/\n{2,}/)
    .map((para) => para.trim())
    .filter((para) => para.length > 0)
    .map((para) => `<p>${para.replace(/\n/g, '<br>')}</p>`)
    .join('');
}

function applyInlineMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}

function renderMarkdown(escaped) {
  const lines = escaped.split('\n');
  const blocks = [];
  let paragraphLines = [];

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return;
    const joined = paragraphLines.join('\n').trim();
    if (joined) blocks.push(`<p>${applyInlineMarkdown(joined).replace(/\n/g, '<br>')}</p>`);
    paragraphLines = [];
  };

  for (const line of lines) {
    const headerMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headerMatch) {
      flushParagraph();
      const level = headerMatch[1].length;
      blocks.push(`<h${level}>${applyInlineMarkdown(headerMatch[2].trim())}</h${level}>`);
      continue;
    }
    if (line.trim() === '') {
      flushParagraph();
      continue;
    }
    paragraphLines.push(line);
  }
  flushParagraph();
  return blocks.join('');
}

/**
 * Renders a book's content body as safe HTML for the reader view. Content is
 * always HTML-escaped first, so untrusted user-authored book text can never
 * inject markup or scripts; markdown content types only get a minimal,
 * escaping-safe subset of formatting layered on top (headers, bold, italic,
 * paragraphs).
 */
export function renderBookContent(book) {
  const escaped = escapeHtml(book?.contentBody ?? '');
  if (book?.contentType === 'markdown') {
    return renderMarkdown(escaped);
  }
  return paragraphsFromEscaped(escaped);
}
