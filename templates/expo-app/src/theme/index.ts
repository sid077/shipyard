import { useColorScheme } from 'react-native';

import { tokens, type TypeVariant } from './tokens.generated';

/**
 * One palette, derived. The design roles specify the light palette; the dark
 * one is computed from it so a product cannot ship a dark mode nobody checked.
 */

export type Palette = {
  primary: string;
  onPrimary: string;
  primaryPressed: string;
  background: string;
  surface: string;
  surfaceRaised: string;
  text: string;
  textMuted: string;
  border: string;
  danger: string;
  onDanger: string;
  success: string;
};

export type ThemeMode = 'light' | 'dark' | 'system';

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

const c = tokens.colors;

export const lightPalette: Palette = { ...c };

export const darkPalette: Palette = {
  primary: mix(c.primary, '#ffffff', 0.18),
  onPrimary: readableOn(mix(c.primary, '#ffffff', 0.18)),
  primaryPressed: mix(c.primary, '#ffffff', 0.3),
  background: mix(c.text, '#000000', 0.45),
  surface: mix(c.text, '#ffffff', 0.1),
  surfaceRaised: mix(c.text, '#ffffff', 0.16),
  text: mix(c.background, '#000000', 0.06),
  textMuted: mix(c.textMuted, '#ffffff', 0.45),
  border: mix(c.text, '#ffffff', 0.26),
  danger: mix(c.danger, '#ffffff', 0.28),
  onDanger: readableOn(mix(c.danger, '#ffffff', 0.28)),
  success: mix(c.success, '#ffffff', 0.28),
};

/** Multiples of the design's spacing unit. Never a raw pixel value. */
export const spacing = (steps: number) => steps * tokens.spacingUnit;
export const radii = tokens.radii;
export const motion = tokens.motion;
export const typeScale = tokens.type;
export const MIN_TOUCH_TARGET = tokens.minTouchTarget;

export function elevation(level: number) {
  const height = tokens.elevation[Math.min(level, tokens.elevation.length - 1)] ?? 0;
  if (height === 0) return {};
  return {
    shadowColor: '#000',
    shadowOpacity: 0.08 + height * 0.02,
    shadowRadius: height * 3,
    shadowOffset: { width: 0, height },
    elevation: height,
  };
}

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
export type { TypeVariant };
