import { contrastRatio, darkPalette, lightPalette, readableOn, spacing } from '@/theme';

describe('the generated palette', () => {
  it('keeps body text legible on both background and surface in light mode', () => {
    expect(contrastRatio(lightPalette.text, lightPalette.background)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(lightPalette.text, lightPalette.surface)).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps body text legible in dark mode', () => {
    expect(contrastRatio(darkPalette.text, darkPalette.background)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(darkPalette.text, darkPalette.surface)).toBeGreaterThanOrEqual(4.5);
  });

  it('picks a foreground that is readable on the primary colour', () => {
    expect(contrastRatio(lightPalette.onPrimary, lightPalette.primary)).toBeGreaterThanOrEqual(3);
    expect(readableOn('#ffffff')).toBe('#000000');
    expect(readableOn('#000000')).toBe('#ffffff');
  });

  it('scales spacing from the token unit', () => {
    expect(spacing(0)).toBe(0);
    expect(spacing(2)).toBe(8);
  });
});
