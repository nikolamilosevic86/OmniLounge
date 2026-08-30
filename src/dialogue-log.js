// A running transcript for the AI-character dialogue modal. The modal used to
// show only the character's latest line, so a branching conversation lost
// everything said before the current node. Pure and DOM-free for vitest;
// duplicated verbatim into client/js/dialogue-log.js.

export const MAX_DIALOGUE_LOG_ENTRIES = 50;

function turn(speaker, text) {
  return { speaker, text: String(text ?? '').trim() };
}

export function characterTurn(text) {
  return turn('character', text);
}

export function playerTurn(text) {
  return turn('player', text);
}

/** Returns a new log with `entry` appended. Blank entries and an immediate
 * repeat of the last line are dropped, so a re-render of the same story node
 * cannot duplicate it into the transcript. */
export function appendDialogueTurn(log, entry) {
  const previous = log || [];
  if (!entry || !entry.text) return previous.slice();
  const last = previous[previous.length - 1];
  if (last && last.speaker === entry.speaker && last.text === entry.text) return previous.slice();
  return [...previous, entry].slice(-MAX_DIALOGUE_LOG_ENTRIES);
}

export function formatSpeakerLabel(speaker, characterName) {
  if (speaker === 'player') return 'You';
  return characterName || 'Character';
}
