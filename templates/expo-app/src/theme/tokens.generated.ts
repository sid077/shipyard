/**
 * GENERATED FILE - do not edit by hand.
 *
 * Written by `scripts/apply-product.mjs` from `design/ui.json` and
 * `design/ux.json`. Editing this file directly means the next pipeline run
 * overwrites your work.
 */

export const tokens = {
  colors: {
    primary: '#1f6feb',
    onPrimary: '#ffffff',
    primaryPressed: '#1a5fd0',
    background: '#ffffff',
    surface: '#f5f6f8',
    surfaceRaised: '#ffffff',
    text: '#111318',
    textMuted: '#5b6472',
    border: '#d8dbe0',
    danger: '#c9231f',
    onDanger: '#ffffff',
    success: '#1a7f37',
  },
  type: {
    caption: { size: 13, lineHeight: 18, weight: '400', letterSpacing: 0 },
    body: { size: 16, lineHeight: 24, weight: '400', letterSpacing: 0 },
    bodyStrong: { size: 16, lineHeight: 24, weight: '600', letterSpacing: 0 },
    heading: { size: 20, lineHeight: 26, weight: '600', letterSpacing: 0 },
    title: { size: 28, lineHeight: 34, weight: '700', letterSpacing: -0.2 },
  },
  spacingUnit: 4,
  radii: { sm: 8, md: 12, lg: 20, full: 999 },
  elevation: [0, 1, 3],
  minTouchTarget: 44,
  motion: {
    // Below ~80ms reads as a jump; above ~600ms reads as sluggish on repeat.
    fast: 140,
    medium: 240,
    slow: 320,
  },
  mode: 'system',
} as const;

export type Tokens = typeof tokens;
export type TypeVariant = keyof typeof tokens.type;
