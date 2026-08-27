# Type and colour

## The type ramp

- Five to seven rungs is enough for an app. More than that and the rungs stop
  being distinguishable, which defeats the point.
- **Body text: 16pt minimum** on mobile, 17pt if the audience skews older.
  15pt is the floor; below that reads as fine print.
- Line height: **1.15× the size at minimum**, and around **1.4–1.5× for body
  text**. Tight line height is the fastest way to make text feel cramped.
- Steps should be visibly different. 16 → 17 is not a step. 16 → 20 → 28 is.
- One size at two weights is a legitimate pair (`body` and `body_strong`). The
  same size at the same weight twice is a duplicate rung.
- Line length: aim for 45–75 characters. On a phone this mostly takes care of
  itself, but a wide tablet layout needs a `maxWidth`.
- Support Dynamic Type / font scaling. Test at 200%: text must reflow, not clip.
  Do not set `allowFontScaling={false}` to make a layout behave.

## Colour

Name roles by **job**, never by hue. `primary`, `on_primary`, `surface`,
`text_muted`, `danger`. A token called `blue` is a bug waiting for a rebrand.

A working role set:

| Role | Job |
|---|---|
| `primary` / `on_primary` | The main action and what sits on it |
| `primary_pressed` | The pressed state of that action |
| `background` | The page beneath everything |
| `surface` / `surface_raised` | Cards, sheets, anything above the page |
| `text` / `text_muted` | Body copy and secondary copy |
| `border` | Boundaries and dividers |
| `danger` / `on_danger` | Destructive actions and errors |
| `success` | Confirmation |

## Contrast — enforced, not advisory

WCAG 2.1 SC 1.4.3 and 1.4.11:

- **4.5:1** for normal body text against whatever it sits on.
- **3:1** for large text (≥ 18.66pt regular, or ≥ 14pt bold).
- **3:1** for non-text UI that carries meaning — icons, focus rings, the accent
  colour used to signal interactivity.

Two traps that catch most palettes:

1. **Muted text is still text.** Secondary copy does not get a discount; it
   needs 4.5:1 like everything else. A `#999` on white is 2.85:1 and fails.
2. **Check the pressed state too.** A button that darkens on press can push its
   label out of contrast, and nobody notices until a screenshot.

`shipyard/color.py` computes these, and `ColorRoles` rejects a palette that
fails, with the achieved ratio in the error.

## Restraint

One accent colour, used sparingly, reads as expensive. Three accent colours read
as a prototype. If everything is emphasised, nothing is.
