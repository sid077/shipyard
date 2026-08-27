# Motion and haptics

Motion exists to explain where a thing came from and where it went. If an
animation does not answer that, cut it.

## Durations

| Change | Duration |
|---|---|
| Small: a press, a toggle, a colour change | 100–150ms |
| Medium: a card expanding, a sheet appearing | 200–300ms |
| Large: a full screen transition | 300–400ms |

- Below ~80ms reads as a jump; the eye does not register motion, only a
  discontinuity.
- Above ~600ms reads as sluggish on every repeat. The first viewing feels
  premium and the hundredth feels slow — design for the hundredth.
- Exits are usually faster than entrances. The user has already decided.

## Easing

| Curve | Use |
|---|---|
| `standard` | Movement within the screen; symmetrical in and out |
| `decelerate` | Something entering — fast in, settling |
| `accelerate` | Something leaving — slow start, quick exit |
| `emphasized` | The one transition per flow you want noticed |
| `spring` | Direct manipulation, gesture-driven movement |

Never linear for anything a user looks at. Linear motion has no physics and
reads as mechanical.

## What to animate

- **Do**: entrance of new content, position changes, expansion and collapse,
  the pressed state of a control, transitions between screens.
- **Do not**: anything on a list of 500 rows, anything that delays first paint,
  anything that repeats on every keystroke, decorative loops.

## Loading

- **Skeletons** beat spinners when you know the shape of what is coming. They
  reduce the perceived wait because the layout does not jump when data lands.
- Under ~300ms, show nothing. A flash of spinner is worse than a short pause.
- Over ~10s, show progress and something cancellable.
- Optimistic updates beat both when the action almost always succeeds and is
  cheap to reverse.

## Respect the setting

Honour "Reduce Motion". In React Native, `AccessibilityInfo.isReduceMotionEnabled()`
— when it is on, cross-fade instead of translating and skip parallax entirely.
This is an accessibility requirement, not a preference: motion triggers nausea
in people with vestibular disorders.

## Haptics

`expo-haptics`. Use them to mark a moment the user **caused and cares about**.

| Moment | Feedback |
|---|---|
| A selection changes, a toggle flips | `selection` |
| A light confirm — item saved, added | `impactLight` |
| A significant confirm — purchase, submit | `notificationSuccess` |
| A recoverable problem | `notificationWarning` |
| A failure — declined, rejected | `notificationError` |

Never on navigation, never on arrival, never on scroll. Haptics on everything
are the same as haptics on nothing, except they also drain the battery.
