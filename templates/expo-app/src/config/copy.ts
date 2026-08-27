import deck from '../../copy.json';

/**
 * Every string the app renders comes from the copy deck the UX Writer owns.
 *
 * A hardcoded string in a screen is a string nobody reviewed, cannot be
 * changed without a build, and will not be caught when it overflows its space.
 */

export type CopyEntry = { text: string; context: string; max_chars: number };
export type Deck = { entries: Record<string, CopyEntry> };

const entries: Record<string, CopyEntry> = (deck as Deck).entries ?? {};

export class MissingCopyError extends Error {
  constructor(key: string) {
    super(`copy key ${key} is not in copy.json`);
    this.name = 'MissingCopyError';
  }
}

/**
 * Look up a string. In development a missing key throws, so it is caught by a
 * test rather than shipped as a blank label; in production it degrades to the
 * key itself rather than crashing on a user.
 */
export function t(key: string): string {
  const entry = entries[key];
  if (entry) return entry.text;
  if (__DEV__) throw new MissingCopyError(key);
  return key;
}

export function has(key: string): boolean {
  return key in entries;
}

export function copyKeys(): string[] {
  return Object.keys(entries);
}

export { entries as copyEntries };
