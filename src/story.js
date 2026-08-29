export const CHARACTER_ROLES = ['guide', 'quiz_master', 'narrator', 'historical_persona', 'mentor'];

export const DEFAULT_CHARACTER_ROLE = 'guide';

// Plain-language descriptions of what each role actually does to the
// character's replies. These mirror `ROLE_PERSONAS` in server/game/story.py,
// which is what genuinely gets sent to the model -- keep the two in step so
// the builder UI never promises behaviour the server does not deliver.
export const CHARACTER_ROLE_CARDS = [
  {
    role: 'guide',
    label: 'Guide',
    icon: '🧭',
    description: 'Welcomes visitors and explains what is around them.',
    sampleLine: 'Welcome! The exhibit you are looking at is the oldest one here — shall I show you around?',
  },
  {
    role: 'quiz_master',
    label: 'Quiz Master',
    icon: '❓',
    description: 'Asks a question back before answering, to check understanding.',
    sampleLine: 'Good question! But first — what do you think happens when the two are combined?',
  },
  {
    role: 'narrator',
    label: 'Narrator',
    icon: '📖',
    description: 'Describes people and places in a vivid, story-like voice.',
    sampleLine: 'The hall falls quiet as you step inside, dust turning slowly in the light from the high windows.',
  },
  {
    role: 'historical_persona',
    label: 'Historical Figure',
    icon: '🏛️',
    description: 'Stays in character, speaking from their own era and viewpoint.',
    sampleLine: 'In my day we had no such machines — we charted the stars with nothing but glass and patience.',
  },
  {
    role: 'mentor',
    label: 'Mentor',
    icon: '🎓',
    description: 'Breaks things down step by step and encourages the visitor.',
    sampleLine: "Let's take it one piece at a time — you already worked out the hard part, so the rest will follow.",
  },
];

export function isValidCharacterRole(role) {
  return CHARACTER_ROLES.includes(role);
}

/**
 * View-model for the role picker: every role with its description and sample
 * line, and a flag for the one currently in effect. An unknown or missing
 * role resolves to the server's default rather than leaving nothing selected.
 */
export function characterRoleCardOptions(selectedRole) {
  const active = isValidCharacterRole(selectedRole) ? selectedRole : DEFAULT_CHARACTER_ROLE;
  return CHARACTER_ROLE_CARDS.map((card) => ({ ...card, active: card.role === active }));
}

const APPEARANCE_OPTION_LABELS = {
  neutral: 'Neutral',
  feminine: 'Feminine',
  masculine: 'Masculine',
  short: 'Short',
  long: 'Long',
  curly: 'Curly',
  mohawk: 'Mohawk',
  bald: 'Bald',
  ponytail: 'Ponytail',
  none: 'None',
  stubble: 'Stubble',
  goatee: 'Goatee',
  full: 'Full Beard',
  round: 'Round',
  square: 'Square',
  sunglasses: 'Sunglasses',
  tshirt: 'T-shirt',
  hoodie: 'Hoodie',
  suit: 'Suit',
  dress: 'Dress',
  jacket: 'Jacket',
  hat: 'Hat',
  backpack: 'Backpack',
  scarf: 'Scarf',
  headphones: 'Headphones',
};

function labelForAppearanceOption(value) {
  return APPEARANCE_OPTION_LABELS[value] || value;
}

// The seven fields `room:character:appearance` accepts, in the order they are
// shown to the author. `isColor` marks the one field whose options are hex
// colours (rendered as swatches) rather than named styles.
export const APPEARANCE_FIELDS = [
  {
    key: 'skinColor',
    label: 'Skin Tone',
    isColor: true,
    options: ['#FFDBAC', '#F1C27D', '#E0AC69', '#C68642', '#8D5524', '#5C3D2E'],
    fallback: '#FFDBAC',
  },
  { key: 'gender', label: 'Body Type', isColor: false, options: ['neutral', 'feminine', 'masculine'], fallback: 'neutral' },
  { key: 'hair', label: 'Hair', isColor: false, options: ['short', 'long', 'curly', 'mohawk', 'bald', 'ponytail'], fallback: 'short' },
  { key: 'beard', label: 'Beard', isColor: false, options: ['none', 'stubble', 'goatee', 'full'], fallback: 'none' },
  { key: 'glasses', label: 'Glasses', isColor: false, options: ['none', 'round', 'square', 'sunglasses'], fallback: 'none' },
  { key: 'clothes', label: 'Clothes', isColor: false, options: ['tshirt', 'hoodie', 'suit', 'dress', 'jacket'], fallback: 'tshirt' },
  { key: 'accessory', label: 'Accessory', isColor: false, options: ['none', 'hat', 'backpack', 'scarf', 'headphones'], fallback: 'none' },
];

/**
 * The appearance that would result from choosing `value` for `field`, with
 * every other field carried over from `appearance` (and defaults filled in
 * for anything missing, so a preview never renders half-blank).
 */
export function appearanceWithOption(appearance, field, value) {
  const next = {};
  APPEARANCE_FIELDS.forEach((entry) => {
    next[entry.key] = appearance?.[entry.key] || entry.fallback;
  });
  next[field] = value;
  return next;
}

/**
 * View-model for one appearance picker row. Each card carries the *complete*
 * appearance it would produce, so the UI can preview this character wearing
 * the option rather than showing an abstract word like "mohawk".
 */
export function appearanceOptionCards(fieldKey, appearance) {
  const field = APPEARANCE_FIELDS.find((entry) => entry.key === fieldKey);
  if (!field) return [];
  const current = appearance?.[fieldKey] || field.fallback;
  return field.options.map((value) => ({
    value,
    label: field.isColor ? value : labelForAppearanceOption(value),
    active: value === current,
    appearance: appearanceWithOption(appearance, fieldKey, value),
  }));
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
