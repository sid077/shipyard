import { useColorScheme } from 'react-native';

import { tokens } from './tokens.generated';

/**
 * A palette derived from the generated design tokens. The light palette is the
 * tokens as written; the dark palette is derived so a designer only has to
 * specify one set and both render legibly.
 */

export type Palette = {
  primary: string;
  background: string;
  surface: string;
  text: string;
  muted: string;
  danger: string;
  border: string;
  onPrimary: string;
};

/** Relative luminance per WCAG 2.1, used to pick legible foregrounds. */
export function luminance(hex: string): number {
  const value = hex.replace('#', '');
  const channels = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/** Contrast ratio between two hex colours, 1 (identical) to 21 (black on white). */
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Black or white, whichever is legible on the given background. */
export function readableOn(background: string): string {
  return contrastRatio('#ffffff', background) >= contrastRatio('#000000', background)
    ? '#ffffff'
    : '#000000';
}

function mix(hex: string, target: string, amount: number): string {
  const parse = (h: string) =>
    [0, 2, 4].map((i) => parseInt(h.replace('#', '').slice(i, i + 2), 16));
  const [r1, g1, b1] = parse(hex);
  const [r2, g2, b2] = parse(target);
  const channel = (a: number, b: number) =>
    Math.round(a + (b - a) * amount)
      .toString(16)
      .padStart(2, '0');
  return `#${channel(r1, r2)}${channel(g1, g2)}${channel(b1, b2)}`;
}

export const lightPalette: Palette = {
  primary: tokens.colorPrimary,
  background: tokens.colorBg,
  surface: tokens.colorSurface,
  text: tokens.colorText,
  muted: tokens.colorMuted,
  danger: tokens.colorDanger,
  border: mix(tokens.colorSurface, tokens.colorText, 0.12),
  onPrimary: readableOn(tokens.colorPrimary),
};

export const darkPalette: Palette = {
  primary: mix(tokens.colorPrimary, '#ffffff', 0.12),
  background: mix(tokens.colorText, '#000000', 0.4),
  surface: mix(tokens.colorText, '#ffffff', 0.08),
  text: mix(tokens.colorBg, '#000000', 0.06),
  muted: mix(tokens.colorMuted, '#ffffff', 0.35),
  danger: mix(tokens.colorDanger, '#ffffff', 0.2),
  border: mix(tokens.colorText, '#ffffff', 0.22),
  onPrimary: readableOn(mix(tokens.colorPrimary, '#ffffff', 0.12)),
};

export const spacing = (steps: number) => steps * tokens.spacingUnit;
export const radius = tokens.radius;

export type ThemeMode = 'light' | 'dark' | 'system';

export function useTheme(): Palette {
  const scheme = useColorScheme();
  // `tokens` is regenerated per product, so its `mode` is not the literal the
  // current file happens to contain.
  const mode = tokens.mode as ThemeMode;
  if (mode === 'light') return lightPalette;
  if (mode === 'dark') return darkPalette;
  return scheme === 'dark' ? darkPalette : lightPalette;
}

export { tokens };
