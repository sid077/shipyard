# Run 001 — Warranty Keeper

**27 August 2026 · stopped at stage 10 · $1.80 · recommendation: no-go**

The first time any Shipyard role ran against a live model. The brief asked for
an offline receipt-and-warranty tracker with a one-time unlock. The analyst
recommended against building it, and that recommendation was accepted.

## What happened

| | |
|---|---|
| Stages completed | `s00_intake`, then `s10_research` (analyst only) |
| Wall clock | 5m32s for the analyst call |
| Spend | $1.80 |
| Usage window | five-hour window went 20% → 68% in one call |
| Sources cited | 22 |
| Outcome | `no-go`, run stopped before the monetization role finished |

The run was stopped by hand once the recommendation was read. `--auto-approve G0`
had been passed on the assumption the gate would be a formality; it was not.

## Was the research any good?

Yes, and this is the finding that matters. The brief made a specific, falsifiable
case rather than a survey:

- Named four shipped competitors with real prices ($0.99–$1.99) whose marketing
  copy already claims all three of the brief's stated differentiators.
- Found the demand signal: the best-established app in the niche is free with
  unlimited items and cloud backup and still draws roughly 260 installs a month.
- Found the category's tombstone — Centriq, funded and awarded, shut down and
  deleted user data in January 2025.
- Noticed the app name was already taken on Play.
- Turned the brief's own constraints against it: "no account" collides with the
  category's most common one-star review (a lost phone taking every entry with
  it), and "photograph a receipt then type it in" is the exact complaint
  reviewers already make about the free incumbent.
- Observed that the only high-volume app in the space is a manufacturer's own
  registration app, and drew the right conclusion — distribution for this
  problem lives at the point of sale, not in store search.

Two behaviours were better than expected:

**It refused to rescue the brief.** Asked to find a wedge, it wrote "There isn't
one" and explained why, then named return-window tracking, general receipt
capture and B2B warranty registration as *different products deserving their own
brief* rather than laundering one of them into a pivot.

**It disclosed its own methodological limit, unprompted.** The write-up opens
with a note that direct App Store and Play page fetches were blocked by this
environment's egress proxy, that its install counts and ratings are therefore
second-hand from search retrieval and trackers rather than eyeballed, and that
the two specific numbers to re-check by hand before overruling it are the
AppBrain install figures and the "not enough ratings" status on the older iOS
listings. The `analyst` prompt asks for exactly this and got it.

## What broke

**`SDKRunner` had never executed.** Its first line crashed: `RoleResult.text`
had no default. Every one of the 121 tests at that point used `ScriptedRunner`,
so the real runner was completely uncovered. Fixed, and `tests/test_sdk_runner.py`
now drives it against a stubbed SDK — message streaming, rate-limit reading, a
429 result, an SDK exception, and an assertion that the env dict never carries
an auth variable.

**`--auto-approve` could steamroll the finding the gate exists for.** It was
about to approve past a no-go and spend on specifying a rejected product. A
stage can now veto auto-approval of its own gate; `Research` refuses any
recommendation that is not `go`.

## What this environment costs the research

Egress policy blocks direct fetches of App Store and Play listing pages, so the
analyst worked from search-engine retrieval and third-party trackers. It handled
that honestly, but a run in an environment with open egress would produce
better-grounded numbers. Worth knowing before reading any future brief produced
here as gospel.

## What is still unknown

Stages 20 through 65 have never run against a live model. Everything known about
the `pm`, `ux_architect`, `ux_writer`, `ui_designer`, `architect`, `planner`,
`dev`, `reviewer` and `design_qa` prompts is still inference from their design,
not evidence. The next run should reach G1 at minimum, which exercises four more
roles and produces the design preview.

## Recommendations for the next run

1. **Do not pass `--auto-approve G0`** unless the point is specifically to
   exercise later stages. The gate earned its keep here.
2. **Budget one research pass per five-hour window.** A single analyst call with
   ~22 fetches consumed roughly half a window.
3. **Pick a product where the wedge is plausible before spending.** The analyst
   is good at saying no, which is valuable but not free.
