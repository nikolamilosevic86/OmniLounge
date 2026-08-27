import { describe, it, expect } from 'vitest';
import {
  CHARACTER_ROLES,
  isValidCharacterRole,
  formatModeLabel,
  parseChoicesInput,
  resolveCharacterMode,
  KNOWLEDGE_DOC_TYPES,
  isValidKnowledgeDocType,
  validateKnowledgeDocumentInput,
  summarizeKnowledgeDocument,
  MAX_KNOWLEDGE_DOCUMENTS,
  isKnowledgeBaseFull,
} from '../src/story.js';

describe('CHARACTER_ROLES', () => {
  it('includes the five design-doc roles', () => {
    expect(CHARACTER_ROLES).toEqual(['guide', 'quiz_master', 'narrator', 'historical_persona', 'mentor']);
  });
});

describe('isValidCharacterRole', () => {
  it('returns true for a known role', () => {
    expect(isValidCharacterRole('guide')).toBe(true);
  });

  it('returns false for an unknown role', () => {
    expect(isValidCharacterRole('wizard')).toBe(false);
  });
});

describe('formatModeLabel', () => {
  it('formats predefined mode', () => {
    expect(formatModeLabel('predefined')).toBe('Predefined Mode');
  });

  it('formats generative mode', () => {
    expect(formatModeLabel('generative')).toBe('Generative Mode');
  });

  it('formats rate-limited mode', () => {
    expect(formatModeLabel('rate_limited')).toBe('Please Wait');
  });

  it('falls back gracefully for an unknown mode', () => {
    expect(formatModeLabel(undefined)).toBe('Predefined Mode');
  });
});

describe('parseChoicesInput', () => {
  it('parses one "text | nextNodeId" pair per line', () => {
    const input = 'Continue | node-2\nGo back | node-1';
    expect(parseChoicesInput(input)).toEqual([
      { text: 'Continue', nextNodeId: 'node-2' },
      { text: 'Go back', nextNodeId: 'node-1' },
    ]);
  });

  it('treats a line with no pipe as an end-of-story choice (no nextNodeId)', () => {
    expect(parseChoicesInput('The end')).toEqual([{ text: 'The end', nextNodeId: null }]);
  });

  it('ignores blank lines', () => {
    expect(parseChoicesInput('Continue | node-2\n\n')).toEqual([{ text: 'Continue', nextNodeId: 'node-2' }]);
  });

  it('returns an empty array for empty or null input', () => {
    expect(parseChoicesInput('')).toEqual([]);
    expect(parseChoicesInput(null)).toEqual([]);
  });
});

describe('resolveCharacterMode', () => {
  it('returns generative when the character has generative mode enabled', () => {
    expect(resolveCharacterMode({ generativeEnabled: true })).toBe('generative');
  });

  it('returns predefined when the character has generative mode disabled', () => {
    expect(resolveCharacterMode({ generativeEnabled: false })).toBe('predefined');
  });

  it('returns predefined for a null or undefined character', () => {
    expect(resolveCharacterMode(null)).toBe('predefined');
    expect(resolveCharacterMode(undefined)).toBe('predefined');
  });
});

describe('KNOWLEDGE_DOC_TYPES', () => {
  it('includes the three supported document types', () => {
    expect(KNOWLEDGE_DOC_TYPES).toEqual(['text', 'markdown', 'link']);
  });
});

describe('isValidKnowledgeDocType', () => {
  it('returns true for a known type', () => {
    expect(isValidKnowledgeDocType('text')).toBe(true);
    expect(isValidKnowledgeDocType('markdown')).toBe(true);
    expect(isValidKnowledgeDocType('link')).toBe(true);
  });

  it('returns false for an unknown type', () => {
    expect(isValidKnowledgeDocType('video')).toBe(false);
    expect(isValidKnowledgeDocType(undefined)).toBe(false);
  });
});

describe('validateKnowledgeDocumentInput', () => {
  it('accepts a valid text document', () => {
    expect(validateKnowledgeDocumentInput({ title: 'Habitat', docType: 'text', content: 'Owls are nocturnal.' }))
      .toEqual({ valid: true, error: null });
  });

  it('accepts a valid markdown document', () => {
    expect(validateKnowledgeDocumentInput({ title: 'Notes', docType: 'markdown', content: '# Owls' }))
      .toEqual({ valid: true, error: null });
  });

  it('accepts a valid link document', () => {
    expect(validateKnowledgeDocumentInput({ title: 'More info', docType: 'link', url: 'https://example.com/owls' }))
      .toEqual({ valid: true, error: null });
  });

  it('rejects a missing or blank title', () => {
    expect(validateKnowledgeDocumentInput({ title: '', docType: 'text', content: 'x' }).valid).toBe(false);
    expect(validateKnowledgeDocumentInput({ title: '   ', docType: 'text', content: 'x' }).valid).toBe(false);
  });

  it('rejects a title over 120 characters', () => {
    const result = validateKnowledgeDocumentInput({ title: 'a'.repeat(121), docType: 'text', content: 'x' });
    expect(result.valid).toBe(false);
  });

  it('rejects an unknown document type', () => {
    const result = validateKnowledgeDocumentInput({ title: 'Bad', docType: 'video', content: 'x' });
    expect(result.valid).toBe(false);
  });

  it('rejects a text document with empty content', () => {
    const result = validateKnowledgeDocumentInput({ title: 'Empty', docType: 'text', content: '  ' });
    expect(result.valid).toBe(false);
  });

  it('rejects text content over 4000 characters', () => {
    const result = validateKnowledgeDocumentInput({ title: 'Long', docType: 'text', content: 'a'.repeat(4001) });
    expect(result.valid).toBe(false);
  });

  it('rejects a link document with a missing url', () => {
    const result = validateKnowledgeDocumentInput({ title: 'Link', docType: 'link', url: '' });
    expect(result.valid).toBe(false);
  });

  it('rejects a link document with a non-http(s) url', () => {
    const result = validateKnowledgeDocumentInput({ title: 'Link', docType: 'link', url: 'javascript:alert(1)' });
    expect(result.valid).toBe(false);
  });
});

describe('summarizeKnowledgeDocument', () => {
  it('returns the url for a link document', () => {
    expect(summarizeKnowledgeDocument({ docType: 'link', url: 'https://example.com' })).toBe('https://example.com');
  });

  it('returns the content for a text document', () => {
    expect(summarizeKnowledgeDocument({ docType: 'text', content: 'Owls are nocturnal.' }))
      .toBe('Owls are nocturnal.');
  });

  it('truncates content longer than 80 characters', () => {
    const content = 'a'.repeat(100);
    const result = summarizeKnowledgeDocument({ docType: 'text', content });
    expect(result).toBe(`${'a'.repeat(80)}…`);
  });

  it('returns an empty string for a null document', () => {
    expect(summarizeKnowledgeDocument(null)).toBe('');
  });
});

describe('MAX_KNOWLEDGE_DOCUMENTS', () => {
  it('matches the server-side cap of 20 documents per character', () => {
    expect(MAX_KNOWLEDGE_DOCUMENTS).toBe(20);
  });
});

describe('isKnowledgeBaseFull', () => {
  it('returns false when below the cap', () => {
    expect(isKnowledgeBaseFull(19)).toBe(false);
  });

  it('returns true when at the cap', () => {
    expect(isKnowledgeBaseFull(20)).toBe(true);
  });

  it('returns true when over the cap', () => {
    expect(isKnowledgeBaseFull(21)).toBe(true);
  });

  it('returns false for an empty knowledge base', () => {
    expect(isKnowledgeBaseFull(0)).toBe(false);
  });
});

