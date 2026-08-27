# UX writing

The strings are most of what the product feels like. They are also the cheapest
thing to get right and the most commonly left as an afterthought.

## Rules

- **Label the outcome, not the mechanism.** "Split the bill" beats "Submit".
  A user should read only the button and know what happens.
- **Sentence case.** Not Title Case For Every Button. Proper nouns excepted.
- **Cut the throat-clearing.** "Please note that you can now export" is
  "You can now export". Then ask whether the sentence is needed at all.
- **Second person, active voice.** "You have no splits yet", not "No splits
  exist for this user".
- **No exclamation marks.** They read as nervous. One in the whole app, at most,
  and only on genuine celebration.
- **Numerals, not words.** "3 taps", not "three taps".

## Empty states

The first screen most users see, and the best chance to teach the product.
Say what belongs here and how to get the first one:

> **No splits yet.** Your first one lands here.

Not "No data available".

## Errors

Say what happened, whether anything was lost, and what to do next.

> **That purchase did not complete.** You have not been charged. Try again, or
> restore a previous purchase.

Never:
- "Oops! Something went wrong." — that is the absence of writing.
- A raw error code as the whole message.
- Blame: "You entered an invalid amount" → "Enter an amount above zero."

## Paywalls

Name the benefit, not the SKU. "Keep every split forever" beats "Unlock premium
features". State the price and the period plainly — a paywall that hides the
price converts worse and gets rejected more.

## Permissions

Ask in context, immediately before the value, and say what the user gets:

> **Allow notifications** so you know the moment someone settles up.

Never ask on first launch with no context.

## Length

Respect `max_chars`. It exists because the design has finite room. Copy that
overflows is a layout bug authored by the writer.

Rough ceilings: button 24, screen title 20, empty-state body 60, error 80.

## Never ship

Lorem ipsum. `[Bracketed placeholders]`. `TODO`. Anything you would not want to
see in an App Store screenshot. These are rejected mechanically by `CopyDeck`.
