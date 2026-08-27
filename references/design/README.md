# Design reference notes

These are handed to the design roles as reading material at the start of stage
30, and to `design_qa` in stage 65.

**Provenance.** They are written from long-stable, widely published
specifications — the platform touch-target minimums, WCAG 2.1/2.2 success
criteria, and conventional motion timings. They were authored rather than
scraped: this repository's build environment blocks `m3.material.io`,
`www.w3.org` and `reactnative.dev`, and Apple's HIG is a JavaScript-rendered
page that yields no text to a fetcher.

Two consequences worth knowing:

1. **Verify before citing.** If a number here matters to a decision you are
   making, check it against the primary source. The design roles are given
   `WebFetch`, so in an environment with open egress they can and should.
2. **The numbers that matter are enforced, not trusted.** Contrast ratios, type
   ramp shape and touch targets are validated in `shipyard/contracts.py` at
   stage 30, and measured again against the rendered app in stage 65. A spec
   that ignores them fails whether or not anyone read this file.
