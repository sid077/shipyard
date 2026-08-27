# Layout, spacing and touch

## Touch targets

- **44 × 44 pt** is the iOS minimum. **48 × 48 dp** is the Android minimum.
  Target 48 and both are satisfied.
- WCAG 2.2 SC 2.5.8 (Target Size, Minimum, AA) requires **24 × 24 CSS px**,
  with exceptions for inline targets, targets spaced at least 24px apart,
  and equivalents available elsewhere. Platform minimums are stricter; use them.
- The target is the **tappable area**, not the glyph. A 16pt icon needs padding
  to reach 44pt. Extend the hit area rather than inflating the icon.
- Leave at least 8pt between adjacent targets. Adjacent 44pt targets with no gap
  still produce mis-taps.

## Spacing

- Pick one base unit — 4pt is conventional — and make every margin, padding and
  gap a multiple of it. Inconsistent spacing is the most common reason an app
  reads as amateur.
- A usable scale: 4, 8, 12, 16, 24, 32, 48. Resist values between rungs.
- Screen edge margin: 16pt on phones, 20–24pt when content is text-heavy.
- Related things sit closer than unrelated things. If a title and its subtitle
  are as far apart as two separate rows, the grouping has failed.

## Safe areas

- Respect the safe area on every edge. The bottom inset matters most: the home
  indicator sits over content that ignores it.
- Use `react-native-safe-area-context`, already in the template. Apply `edges`
  deliberately rather than wrapping everything in a full `SafeAreaView`.
- A bottom-anchored primary action needs the bottom inset **plus** its own
  padding, or it sits flush against the indicator.

## Thumb reach

- On a phone held one-handed, the comfortable zone is the lower half of the
  screen. Destructive actions belong away from it; primary actions belong in it.
- Do not put the primary action in a top corner. That is the hardest place on
  the screen to reach and the easiest to reach by accident when stretching.

## Density

- Prefer fewer things, larger, over more things, smaller. Cramped screens read
  as cheap and are harder to hit.
- A list row that carries a title, a subtitle and a trailing value wants around
  64pt of height. Below ~48pt it stops feeling tappable.
