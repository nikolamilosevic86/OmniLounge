import { describe, it, expect } from 'vitest';
import {
  MAX_DIALOGUE_LOG_ENTRIES,
  appendDialogueTurn,
  characterTurn,
  formatSpeakerLabel,
  playerTurn,
} from '../src/dialogue-log.js';

describe('turn constructors', () => {
  it('tags who is speaking', () => {
    expect(characterTurn('Welcome to my bottega.').speaker).toBe('character');
    expect(playerTurn('Tell me about flight.').speaker).toBe('player');
  });

  it('trims the text', () => {
    expect(characterTurn('  hello  ').text).toBe('hello');
  });

  it('coerces missing text to an empty string rather than undefined', () => {
    expect(playerTurn(undefined).text).toBe('');
  });
});

describe('appendDialogueTurn', () => {
  it('appends to an empty log', () => {
    const log = appendDialogueTurn([], characterTurn('Hello.'));
    expect(log).toHaveLength(1);
    expect(log[0].text).toBe('Hello.');
  });

  it('does not mutate the log it was given', () => {
    const original = [];
    appendDialogueTurn(original, characterTurn('Hello.'));
    expect(original).toHaveLength(0);
  });

  it('keeps turns in the order they were spoken', () => {
    let log = appendDialogueTurn([], characterTurn('One.'));
    log = appendDialogueTurn(log, playerTurn('Two.'));
    log = appendDialogueTurn(log, characterTurn('Three.'));
    expect(log.map((t) => t.text)).toEqual(['One.', 'Two.', 'Three.']);
  });

  it('drops blank turns so re-renders cannot pad the transcript', () => {
    expect(appendDialogueTurn([], characterTurn('   '))).toHaveLength(0);
    expect(appendDialogueTurn([], playerTurn(''))).toHaveLength(0);
  });

  it('ignores a repeat of the line already at the end of the log', () => {
    const log = appendDialogueTurn([], characterTurn('Welcome.'));
    expect(appendDialogueTurn(log, characterTurn('Welcome.'))).toHaveLength(1);
  });

  it('still allows the same line to recur later in the conversation', () => {
    let log = appendDialogueTurn([], characterTurn('Welcome.'));
    log = appendDialogueTurn(log, playerTurn('Start over.'));
    log = appendDialogueTurn(log, characterTurn('Welcome.'));
    expect(log).toHaveLength(3);
  });

  it('does not collapse an echo across different speakers', () => {
    let log = appendDialogueTurn([], playerTurn('Amboise'));
    log = appendDialogueTurn(log, characterTurn('Amboise'));
    expect(log).toHaveLength(2);
  });

  it('caps the transcript, discarding the oldest turns first', () => {
    let log = [];
    for (let i = 0; i < MAX_DIALOGUE_LOG_ENTRIES + 10; i += 1) {
      log = appendDialogueTurn(log, playerTurn(`line ${i}`));
    }
    expect(log).toHaveLength(MAX_DIALOGUE_LOG_ENTRIES);
    expect(log[log.length - 1].text).toBe(`line ${MAX_DIALOGUE_LOG_ENTRIES + 9}`);
    expect(log[0].text).toBe('line 10');
  });

  it('tolerates a missing log', () => {
    expect(appendDialogueTurn(undefined, characterTurn('Hi.'))).toHaveLength(1);
  });
});

describe('formatSpeakerLabel', () => {
  it('uses the character name for character turns', () => {
    expect(formatSpeakerLabel('character', 'Leonardo da Vinci')).toBe('Leonardo da Vinci');
  });

  it('falls back to a generic label when the character is unnamed', () => {
    expect(formatSpeakerLabel('character', '')).toBe('Character');
    expect(formatSpeakerLabel('character', undefined)).toBe('Character');
  });

  it('labels the visitor as You', () => {
    expect(formatSpeakerLabel('player', 'Leonardo da Vinci')).toBe('You');
  });
});
