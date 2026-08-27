# Accessibility

Not a compliance exercise. An app that is legible, hittable and navigable
without sight is a better app for everyone, and store reviewers do check.

## The criteria that bite on mobile

| Criterion | Requirement |
|---|---|
| 1.4.3 Contrast (Minimum) | 4.5:1 body text, 3:1 large text |
| 1.4.11 Non-text Contrast | 3:1 for meaningful UI and graphics |
| 1.4.4 Resize Text | Usable at 200% scaling, without clipping |
| 2.5.8 Target Size (Minimum) | 24×24 CSS px; platform minimums are stricter |
| 2.5.5 Target Size (Enhanced) | 44×44 — use this one |
| 1.3.1 Info and Relationships | Structure conveyed to assistive tech, not just visually |
| 2.4.7 Focus Visible | A visible focus indicator on keyboard focus |
| 3.3.1 Error Identification | Errors described in text, never colour alone |
| 1.4.1 Use of Colour | Colour is never the only carrier of meaning |

## React Native specifics

- `accessible={true}` on a composite so it reads as one element rather than
  three fragments.
- `accessibilityRole` — `button`, `header`, `link`, `image`, `switch`,
  `adjustable`. Screen readers announce affordance from this.
- `accessibilityLabel` when the visible text is not the whole story. An icon-only
  button is unusable without one.
- `accessibilityState` — `{ disabled, selected, checked, busy, expanded }`. A
  disabled button that does not say so is a trap.
- `accessibilityHint` sparingly, for non-obvious outcomes only.
- `accessibilityLiveRegion` (Android) / `AccessibilityInfo.announceForAccessibility`
  for changes that happen away from focus, such as a toast.

## Things that quietly break it

- An icon button with no label. It announces as "button" and nothing else.
- A touchable `View` with no `accessibilityRole`; it announces as plain text.
- Error state signalled only by a red border.
- `allowFontScaling={false}` to stop a layout breaking. Fix the layout.
- Placeholder text used as the only label — it disappears on focus.
- Decorative images without `accessibilityElementsHidden` / `importantForAccessibility="no"`,
  which fill the reader with noise.
- A custom control that never sets `accessibilityState`, so its state is
  invisible to anyone not looking at it.

## How this is checked here

Stage 65 exports the app to web, drives it with Playwright, and runs
`@axe-core/playwright` plus layout probes for tap-target size, clipped text,
overflow and computed contrast. Those failures block. `design_qa` then looks at
the screenshots for what a machine cannot see.
