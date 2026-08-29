import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { escapeHtml as readerEscapeHtml } from '../src/reader.js';

const here = dirname(fileURLToPath(import.meta.url));
const mainSource = readFileSync(resolve(here, '../client/js/main.js'), 'utf8');

/**
 * `client/js/main.js` is the app entry point and touches `document` at import
 * time, so it cannot be imported directly in a unit test. Extract just the
 * `escapeHtml` declaration and evaluate it, so these assertions run against
 * the real shipped implementation rather than a copy that could drift.
 */
function loadEscapeHtmlFromMain() {
  const marker = 'function escapeHtml(text) {';
  const start = mainSource.indexOf(marker);
  if (start === -1) throw new Error('escapeHtml not found in client/js/main.js');

  let depth = 0;
  let end = -1;
  for (let i = start + marker.length - 1; i < mainSource.length; i += 1) {
    if (mainSource[i] === '{') depth += 1;
    if (mainSource[i] === '}') {
      depth -= 1;
      if (depth === 0) { end = i + 1; break; }
    }
  }
  if (end === -1) throw new Error('could not find end of escapeHtml');

  // eslint-disable-next-line no-new-func
  return new Function(`${mainSource.slice(start, end)}; return escapeHtml;`)();
}

const implementations = [
  ['client/js/main.js', loadEscapeHtmlFromMain()],
  ['src/reader.js', readerEscapeHtml],
];

describe.each(implementations)('escapeHtml (%s)', (_name, escapeHtml) => {
  it('escapes the basic HTML metacharacters', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt;',
    );
  });

  it('escapes & first so existing entities are not double-decoded', () => {
    expect(escapeHtml('&lt;')).toBe('&amp;lt;');
  });

  it('escapes double quotes', () => {
    // SECURITY: several call sites interpolate into an HTML *attribute*
    // (e.g. the YouTube `<iframe ... title="${escapeHtml(item.title)}">`).
    // An unescaped `"` lets attacker-controlled text close the attribute
    // and add new ones.
    expect(escapeHtml('a"b')).toBe('a&quot;b');
  });

  it('escapes single quotes', () => {
    expect(escapeHtml("a'b")).toBe('a&#39;b');
  });

  it('neutralises an attribute-breakout srcdoc payload', () => {
    // The concrete stored-XSS chain this fix closes: breaking out of the
    // iframe `title` attribute to inject `srcdoc`, whose value is
    // entity-decoded before being parsed as HTML -- so even an
    // `&lt;`-escaped payload inside srcdoc would still execute.
    const payload = '" srcdoc="<img src=x onerror=alert(1)>';
    const escaped = escapeHtml(payload);

    // No raw quote survives, so the payload cannot terminate title="...".
    expect(escaped).not.toContain('"');
    expect(escaped).not.toContain('<');
    expect(escaped).not.toContain('>');
    expect(escaped).toBe(
      '&quot; srcdoc=&quot;&lt;img src=x onerror=alert(1)&gt;',
    );
  });

  it('leaves no character that can terminate an HTML attribute', () => {
    const escaped = escapeHtml(`<>&"'`);
    expect(escaped).toBe('&lt;&gt;&amp;&quot;&#39;');
    for (const ch of ['<', '>', '"', "'"]) {
      expect(escaped).not.toContain(ch);
    }
  });

  it('leaves ordinary text untouched', () => {
    expect(escapeHtml('Hello world 123')).toBe('Hello world 123');
  });
});

describe('escapeHtml (client/js/main.js) null handling', () => {
  const escapeHtml = loadEscapeHtmlFromMain();

  it('renders null and undefined as an empty string, not "null"/"undefined"', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });

  it('does not use the textContent/innerHTML round-trip that skips quotes', () => {
    // The vulnerable original was `div.textContent = text; return
    // div.innerHTML`, which the browser serialises without escaping quotes.
    const source = mainSource.slice(mainSource.indexOf('function escapeHtml(text) {'));
    expect(source.slice(0, 400)).not.toContain('textContent');
  });
});
