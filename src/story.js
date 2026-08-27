export const CHARACTER_ROLES = ['guide', 'quiz_master', 'narrator', 'historical_persona', 'mentor'];

export function isValidCharacterRole(role) {
  return CHARACTER_ROLES.includes(role);
}

export function formatModeLabel(mode) {
  if (mode === 'generative') return 'Generative Mode';
  if (mode === 'rate_limited') return 'Please Wait';
  return 'Predefined Mode';
}

export function resolveCharacterMode(character) {
  return character?.generativeEnabled ? 'generative' : 'predefined';
}

export function parseChoicesInput(input) {
  if (!input) return [];
  return input
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [text, nextNodeId] = line.split('|').map((part) => part.trim());
      return { text, nextNodeId: nextNodeId || null };
    });
}

export const KNOWLEDGE_DOC_TYPES = ['text', 'markdown', 'link'];
export const MAX_KNOWLEDGE_DOC_TITLE_LENGTH = 120;
export const MAX_KNOWLEDGE_DOC_CONTENT_LENGTH = 4000;
export const MAX_KNOWLEDGE_DOCUMENTS = 20;

export function isKnowledgeBaseFull(documentCount) {
  return documentCount >= MAX_KNOWLEDGE_DOCUMENTS;
}

export function isValidKnowledgeDocType(docType) {
  return KNOWLEDGE_DOC_TYPES.includes(docType);
}

// Client-side pre-check only, mirroring the server's validation rules for
// immediate user feedback. The server (server/game/story.py) remains the
// authoritative validator -- in particular link URLs are only checked here
// for a http(s) scheme, while the server also runs the SSRF-safe
// `is_safe_external_url` check against loopback/private/reserved addresses.
export function validateKnowledgeDocumentInput({ title, docType, content, url } = {}) {
  const trimmedTitle = (title || '').trim();
  if (!trimmedTitle) return { valid: false, error: 'Enter a title for this document.' };
  if (trimmedTitle.length > MAX_KNOWLEDGE_DOC_TITLE_LENGTH) {
    return { valid: false, error: `Title must be ${MAX_KNOWLEDGE_DOC_TITLE_LENGTH} characters or fewer.` };
  }
  if (!isValidKnowledgeDocType(docType)) {
    return { valid: false, error: 'Choose a document type.' };
  }
  if (docType === 'link') {
    const trimmedUrl = (url || '').trim();
    if (!trimmedUrl) return { valid: false, error: 'Enter a URL for this link.' };
    if (!/^https?:\/\//i.test(trimmedUrl)) {
      return { valid: false, error: 'Link URLs must start with http:// or https://.' };
    }
    return { valid: true, error: null };
  }
  const trimmedContent = (content || '').trim();
  if (!trimmedContent) return { valid: false, error: 'Enter document content.' };
  if (trimmedContent.length > MAX_KNOWLEDGE_DOC_CONTENT_LENGTH) {
    return { valid: false, error: `Content must be ${MAX_KNOWLEDGE_DOC_CONTENT_LENGTH} characters or fewer.` };
  }
  return { valid: true, error: null };
}

export function summarizeKnowledgeDocument(doc) {
  if (!doc) return '';
  if (doc.docType === 'link') return doc.url || '';
  const content = doc.content || '';
  return content.length > 80 ? `${content.slice(0, 80)}…` : content;
}
