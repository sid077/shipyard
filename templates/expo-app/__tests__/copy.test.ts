import deck from '../copy.json';
import { copyKeys, has, t } from '@/config/copy';

describe('the copy deck', () => {
  it('resolves every key it declares', () => {
    for (const key of copyKeys()) {
      expect(t(key)).toBe(deck.entries[key as keyof typeof deck.entries].text);
    }
  });

  it('throws on a missing key in development rather than rendering a blank', () => {
    expect(has('nothing.here')).toBe(false);
    expect(() => t('nothing.here')).toThrow(/not in copy.json/);
  });

  it('keeps every string inside the space the design allows', () => {
    for (const [key, entry] of Object.entries(deck.entries)) {
      expect(entry.text.length).toBeLessThanOrEqual(entry.max_chars);
      expect(entry.text).not.toMatch(/lorem ipsum|TODO|\[.*\]/i);
      expect(entry.context.length).toBeGreaterThan(0);
      expect(key).toMatch(/^[a-z][a-z0-9_.]*$/);
    }
  });
});
