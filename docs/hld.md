# Shipyard — High-Level Design

An agent organization that takes a product idea from market research to a
deployable mobile app, stopping for a human three times.

**Status:** 8 of 11 stages built · 16 roles defined, 13 wired · 148 harness
tests, 46 template tests · one live run completed (a no-go, for $1.80)

---

## 1. What this is

Shipyard is a deterministic Python orchestrator that drives a set of stateless
Claude agents through a fixed pipeline. The agents do the work — research,
design, code, review. The orchestrator decides what happens next, owns git,
holds the money, and refuses to let anything advance on an agent's say-so.

The output is a runnable Expo/React Native app with monetization wired in, plus
the artifacts that justify it: competitor research, a PRD, a design system, an
architecture record, a backlog, and a design-QA report.

It is not a chat loop with tools. It is a build system whose compiler happens to
be a language model.

## 2. The bet

> **Nothing advances because an agent said so.**
>
> A stage completes only when (1) its artifacts validate against a typed
> contract, (2) its commands exit zero, and (3) an auditor raises no blocking
> finding.

Everything else in the design follows from that one line:

- Roles never choose what happens next — the pipeline does.
- Roles never own git — the orchestrator branches, commits, merges and reverts.
- Roles never talk to each other in prose — they read and write typed JSON on
  disk.
- Roles never publish — the guard denies it at the tool call.

A useful consequence: because every role interaction is a typed artifact on
disk, the entire pipeline can be exercised offline against a scripted runner.
148 of the harness tests run with no API calls and no money spent.

## 3. Control flow

```
  shipyard run
       │
       ▼
  ┌─────────────────────────────────────────┐
  │ Orchestrator  (deterministic Python)    │  owns: control flow, git, budget
  └─────────────────────────────────────────┘
       │  RoleRequest(role, stage, task, cwd, allowed_roots)
       ▼
  ┌─────────────────────────────────────────┐
  │ MeteredRunner → SDKRunner               │  one choke point for every call
  │   · system prompt from prompts/<role>.md│
  │   · least-privilege tool grant          │
  │   · PreToolUse guard                    │
  │   · cost + usage-window accounting      │
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────┐
  │ Role (stateless subprocess)             │
  └─────────────────────────────────────────┘
       │  typed artifacts only
       ▼
  projects/<slug>/
       research/  product/  design/  arch/  backlog/  qa/  app/  inbox/
       .shipyard/state.json      ← resumable snapshot, atomic rewrite
       .shipyard/events.jsonl    ← append-only trace
```

Every invocation passes through `MeteredRunner`, which is what makes cost
accounting and the rate-limit stop condition hold regardless of which runner is
underneath. Swapping `SDKRunner` for `ScriptedRunner` is how the test suite runs
the whole org for free.

## 4. How a stage advances

```
  Role works ──► Contract ──► Commands ──► Audit ──► Stage done
  writes         pydantic +    typecheck    critic:    state.json
  artifacts      cross-file    lint tests   no blocking
                 checks       probes       finding
     ▲              │            │            │
     └──────────────┴────────────┴────────────┘
        any failure → re-invoke the role with the failure text attached
                              │
                    after max_repairs (default 3)
                              ▼
                  halt · inbox/BLOCKED-<stage>.md
```

The repair loop is the whole quality mechanism. A failure is never swallowed and
never retried blindly: the exact validation error, command output or review
finding is handed back to the role that produced the work. When repairs are
exhausted the run halts and writes a human-readable briefing rather than
degrading silently.

**The critic is a net, not the gate.** The deterministic checks fail closed. The
critic catches what a schema cannot — a PRD with no testable acceptance
criteria, research with invented pricing, a backlog whose tickets are not
vertical slices. Because it is a net, an auditor that returns unparseable output
twice is skipped rather than allowed to deadlock a stage that already passed
every machine check.

## 5. The pipeline

| Stage | Title | Roles | Outputs | Gate |
|---|---|---|---|---|
| `s00_intake` | Intake | *(your brief)* | `idea.json` | — |
| `s10_research` | Research | analyst, monetization | `research/opportunity.json`, `monetization.json` | **G0** |
| `s20_definition` | Definition | pm | `product/prd.json` | — |
| `s30_design` | Design | ux_architect, ux_writer, ui_designer | `design/ux.json`, `design/copy.json`, `design/ui.json` | **G1** |
| `s40_architecture` | Architecture | architect | `arch/architecture.json` | — |
| `s50_planning` | Planning | planner | `backlog/tickets.json` | — |
| `s60_build` | Build | dev ×N, reviewer, security | `build/build.json` | — |
| `s65_design_qa` | Design QA | design_qa | `qa/design-qa.json` | — |
| `s70_hardening` | Hardening | qa, security | *not built* | — |
| `s80_release` | Release | release, aso | *not built* | **G2** |
| `s90_handoff` | Handoff | release | *not built* | — |

`STAGES` in `shipyard/pipeline/registry.py` is the only source of truth for the
graph. `validate_graph()` statically checks it on every `shipyard doctor`: no
duplicate keys, no stage requiring an artifact nothing upstream produces, no
stage re-producing one, no gate whose owner stage runs after the gate itself.

### Human gates

| Gate | Question | Rejection re-runs |
|---|---|---|
| **G0** Opportunity | Is this worth building? Market, competitors, wedge, monetization. | `s10_research` |
| **G1** Specification | Is this the right product? PRD, monetization spec, screens. | `s20_definition` |
| **G2** Release | Ship it? Builds, listing, privacy artifacts, runbook. | `s80_release` |

A gate is a record in `state.json` plus a briefing in `inbox/`. Rejecting is not
a restart — your notes are injected verbatim into the re-run of the stage that
produced the rejected work.

`--auto-approve G0` exists but is vetoable: `Stage.gate_override` refuses to
auto-approve a research verdict that is not `go`. This was added after run 001,
where auto-approval would have steamrolled the exact finding the gate exists
for.

## 6. The org — roles and models

Model tiers live in one dict (`MODELS`, `shipyard/config.py`). A role names a
**tier**, never a model ID, so retargeting the entire organization is a
three-line edit in one file.

```python
MODELS = {
    "opus":   "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku":  "claude-haiku-4-5",
}
```

| Role | Owns | Model | Effort | Turns | Runs in |
|---|---|---|---|---|---|
| `analyst` | Market and competitor research, go/no-go | `claude-opus-5` | high | 80 | s10, scout |
| `monetization` | Pricing model, tiers, trial, paywall placement | `claude-opus-5` | high | 60 | s10 |
| `pm` | PRD, scope, testable acceptance criteria | `claude-opus-5` | xhigh | 60 | s20 |
| `ux_architect` | Navigation, screen states, flows, gestures, motion | `claude-opus-5` | xhigh | 60 | s30 |
| `ux_writer` | Every string the app renders | `claude-sonnet-5` | medium | 60 | s30 |
| `ui_designer` | Type, colour, components, composition, G1 preview | `claude-opus-5` | high | 60 | s30 |
| `architect` | Stack decisions, ADRs, data model, module map | `claude-opus-5` | xhigh | 60 | s40 |
| `planner` | Backlog of vertical slices | `claude-sonnet-5` | high | 60 | s50 |
| `dev` | Implements one ticket in one isolated worktree | `claude-opus-5` | xhigh | 120 | s60 |
| `reviewer` | Reviews a ticket diff; blocking findings only | `claude-opus-5` | high | 60 | s60 |
| `security` | Auth, secrets, purchases, store compliance | `claude-opus-5` | xhigh | 60 | s60 (sensitive tickets) |
| `design_qa` | Judges rendered screenshots | `claude-opus-5` | high | 60 | s65 |
| `critic` | Definition-of-done audit | `claude-sonnet-5` | high | 30 | every audited stage |
| `qa` | Unit tests and Maestro E2E flows | `claude-sonnet-5` | high | 90 | s70 — **not wired** |
| `release` | EAS config, store metadata, screenshots, runbook | `claude-sonnet-5` | high | 90 | s80 — **not wired** |
| `aso` | Listing copy and keywords | `claude-sonnet-5` | medium | 60 | s80 — **not wired** |

**Ten roles on Opus, six on Sonnet, none on Haiku.** The `haiku` tier is
declared and currently unused — nothing in the pipeline is cheap enough to
justify it yet, and the tier stays defined so a future summarizer or triage role
has somewhere to land.

The split is not about seniority. Opus goes where a wrong answer is expensive
and hard to detect later: the go/no-go, the PRD, taste, security, and every line
of app code. Sonnet goes where the work is bounded and something mechanical is
waiting downstream to catch an error — copy checked against a contract, a
backlog whose shape is validated, an audit against an explicit definition of
done.

Every call is shaped identically in one place (`_options()` in
`shipyard/runner.py`): `thinking={"type": "adaptive"}` on all sixteen, with
`effort`, `max_turns` and the tool grant taken from the role spec.

### Tool grants

Least privilege per role, named so the intent is readable:

| Bundle | Tools | Used by |
|---|---|---|
| `READ_ONLY` | Read, Grep, Glob | design_qa, critic |
| `AUTHORING` | + Write, Edit | pm, ux_writer, architect, planner |
| `RESEARCH` | + WebSearch, WebFetch | analyst, monetization, ux_architect, ui_designer, aso |
| `ENGINEERING` | + Bash | dev, qa, release |
| `INSPECTION` | Read, Grep, Glob, Bash | reviewer, security |

`reviewer` and `security` additionally carry an explicit `disallowed` list —
they get Bash to inspect and run things, but Write and Edit are revoked so a
reviewer cannot quietly fix what it was asked to judge.

## 7. Typed artifacts

Roles exchange Pydantic models, not transcripts. A validation error is a stage
failure caught where it is produced rather than three stages later.

```
idea.json                    Idea
research/opportunity.json    Opportunity   competitors, wedge, risks
monetization.json            MonetizationPlan  tiers, price points, paywall
product/prd.json             PRD           requirements, acceptance criteria
design/ux.json               UXSpec        screens, states, flows, transitions
design/ui.json               UISpec        type scale, colour roles, components
design/copy.json             CopyDeck      every string the app renders
arch/architecture.json       Architecture  ADRs, modules, entities
backlog/tickets.json         Backlog       vertical slices
build/build.json             BuildReport
qa/design-qa.json            DesignQAReport
scouting/shortlist.json      Shortlist     ranked candidates (scout mode)
```

The contracts **compute rather than check shape**. Notably:

- `ColorRoles` measures WCAG contrast on every declared pair — 4.5:1 for text,
  3:1 for non-text — including muted text and pressed states, the two that catch
  most palettes. A failing palette comes back with the ratio it achieved.
- `TypeStep` enforces a monotonic ramp with a body step of at least 15pt and a
  sane line-height, with `(size, weight)` uniqueness rather than size alone —
  `body` and `body_strong` legitimately share 16pt.
- `Shortlist` enforces that ranks are `1..n` with no gaps, names are unique, and
  a non-empty `recommended` names a candidate whose verdict is `pursue`. An
  empty recommendation stays valid — the scout is allowed to come back with
  nothing.
- Placeholder copy (`Lorem`, `TODO`, `TBD`) is rejected outright.

## 8. Git ownership and the build loop

Git belongs to the orchestrator. Agents edit files; Python branches, commits,
merges and reverts. Agents are good at writing code and bad at repository
surgery, and a botched merge costs far more to recover from than a botched
function.

Stage 60 runs tickets in waves:

1. Each ticket gets its own `git worktree` off trunk.
2. Up to `SHIPYARD_BUILD_CONCURRENCY` (default 3) `dev` roles work in parallel.
3. Each diff is reviewed by `reviewer`, plus `security` when the ticket is
   marked sensitive.
4. Merges are serialized behind one lock; trunk is re-proved after each merge;
   a merge that turns trunk red is reverted.

One bug worth recording, because the fix generalizes: the template `.gitignore`
had `node_modules/` with a trailing slash, which matches directories but **not
symlinks**. The build loop symlinks `node_modules` into each worktree, so
`git add -A` committed the link and a merge replaced trunk's real
`node_modules` with a self-referential symlink. The pattern is fixed, and
`AppRepo._exclude_in_worktree` now writes a per-worktree `info/exclude` entry so
the harness never depends on a generated app's `.gitignore` being correct.

## 9. What the org cannot do

A `PreToolUse` hook (`shipyard/guards.py`) enforces two rules no role can talk
its way around.

**It cannot ship.** Denied and logged: `git push`, `git remote add|set-url`,
`eas submit`, `expo publish`, `npm publish`, `vercel|netlify|fly|wrangler
deploy`, and `gh pr|release|repo|api`.

**It cannot own git.** `git commit|merge|rebase|worktree|checkout|branch` is
denied with the reason *"git is owned by the orchestrator, not by roles: edit
files and let the pipeline commit."*

**It cannot escape its workspace.** Every write path is resolved and must land
inside the roots the pipeline handed that role.

Plus the obvious host-level refusals: destructive recursive deletes at `/`,
`~` or `*`, curl/wget piped into a shell, `shutdown|reboot|mkfs|dd if=`, and
fork bombs.

## 10. How UI quality is enforced

The part most agent pipelines skip, because typecheck, lint and unit tests all
pass happily on an app that is ugly, cramped, and unusable with a screen reader.
Three layers, each cheaper than the one after it:

**Before any code exists** — the contracts compute contrast, ramp monotonicity
and touch-target minimums, and reject placeholder copy. A palette that fails
never reaches a developer.

**While code is written** — engineers compose from a real design system rather
than inventing components per ticket: thirteen primitives with accessibility
roles, states and labels wired, and a 44pt floor on every pressable. Copy is
read at runtime from the deck the writer owns, so a wording change is not a code
change.

**After it is built** — stage 65 exports the app to web, drives it with a real
browser at two phone viewports, photographs every route plus a component
gallery, and runs axe-core and DOM probes for undersized targets, clipped text,
overflow, and routes the spec declares but the app never implemented. Those
block. Then `design_qa` — a role that can actually see the images — judges
hierarchy, rhythm, and whether the screens look like one product.

On its first real run stage 65 found three genuine defects in the template:
every route shipping with no `<title>`, segmented-control targets at 36px, and a
nameless progressbar inside an already-labelled button.

## 11. The app template

`templates/expo-app` is a golden template, kept green by 46 of its own tests, so
the org starts from a working app rather than an empty directory.

Expo SDK 57 · React Native 0.86.3 · React 19.2.3 · expo-router (`src/app`) ·
static web export · RevenueCat (`react-native-purchases`) · Supabase · PostHog ·
Jest 29 with `jest-expo` and `@testing-library/react-native` 14 · Maestro ·
Playwright with `@axe-core/playwright`.

Monetization is wired before the first feature ticket rather than bolted on:
entitlement checks, a paywall surface, and the price points the `monetization`
role specified are projected into the app by `apply-product.mjs`.

## 12. Cost, budgets, and stopping

Spend ceilings are **opt-in**. `SHIPYARD_PROJECT_BUDGET_USD` and
`SHIPYARD_STAGE_BUDGET_USD` are unset by default and the per-invocation cap is
passed to the SDK only when one is configured. The reasoning: the account's
usage window is the truth, and a dollar *estimate* that halts a run early is
worse than no estimate at all.

The real stop condition is the rate-limit window. `MeteredRunner` reads
utilization from the SDK's rate-limit events (`five_hour`, `seven_day`,
`overage`), and a role that hits the ceiling raises `UsageLimitReached` rather
than failing as a repairable error. `run_stage` catches it specially and **gives
the attempt back** — the stage returns to `pending` with its repair budget
intact, so a window running out never burns a retry.

`SHIPYARD_ROLE_TIMEOUT_S` (default 1800) bounds a stalled invocation, and a
stall after an exhaustion event is diagnosed as a usage limit rather than a
mystery hang. This was added after a scouting run sat with flat CPU and 19 open
sockets for eight minutes while the CLI silently retried.

Each role spec still carries a dollar cap ($3–$12) for when budgets are turned
back on.

## 13. State and resume

Two files per project under `.shipyard/`:

- `state.json` — the resumable snapshot, rewritten atomically after every step.
- `events.jsonl` — an append-only trace of everything that happened.

If the process dies, `state.json` is the truth and `shipyard resume` picks up at
the first stage that is not `done`. `--checkpoint` additionally commits
`projects/<slug>` to the outer repo after each stage, so the run's paper trail
survives even a lost container.

## 14. Scouting

`shipyard scout` runs when nobody has chosen a product yet. It is allowed to come
back recommending nothing.

It runs in two phases, each landing its own durable output:

1. **Sweep** — range across the focus areas and append leads to
   `scouting/sweep.md` *as it goes*. Prose, not JSON: its job is to survive, not
   to be parsed.
2. **Shortlist** — read the sweep, verify the leads properly (real competitors,
   real prices, real install or review volume), and write the typed
   `scouting/shortlist.json`.

**Resumable at the phase boundary.** If `sweep.md` already exists and is
non-trivial, the sweep is skipped and only the shortlist call runs. A window that
dies mid-pass costs the phase it was in, not the research already done.

A `CAPABILITIES` constant travels with the task, stating honestly what this
studio can build (Expo, offline-first, RevenueCat, 3–6 weeks) and what it cannot
(two-sided marketplaces, content licensing, hardware or retail distribution,
regulated advice, heavy support burden, paid acquisition). It is a constraint,
not a hint about what to prefer.

## 15. Layout

```
shipyard/
  config.py       model tiers, budgets, filesystem layout
  runner.py       the single SDK choke point; metering; rate-limit handling
  roles.py        the org chart: prompt + tool grant + tier + caps
  contracts.py    typed artifacts (957 lines, most of it validation)
  pipeline/
    __init__.py   Stage ABC, run_stage, the repair loop
    registry.py   STAGES — the only source of truth for the graph
    discovery.py  s00–s50
    build.py      s60
    tickets.py    TicketRunner: worktrees, waves, review, merge
    design_qa.py  s65
  critic.py       definition-of-done audit
  verify.py       verification by execution
  workspace.py    project and git plumbing
  guards.py       PreToolUse hard limits
  gates.py        G0/G1/G2
  ledger.py       state.json + events.jsonl
  scout.py        sweep + shortlist
  tasks.py        per-invocation task composition
  cli.py          new · run · resume · status · cost · ls · doctor · gate · scout
prompts/          one system prompt per role
templates/expo-app  the golden app
references/design/  authored design guidance, with provenance stated
docs/               this file; run post-mortems
```

## 16. Running it

```bash
shipyard doctor                     # static graph + template checks
shipyard new "<idea>" --slug my-app
shipyard run --slug my-app --until s65_design_qa
shipyard status --slug my-app
shipyard gate approve G0 --slug my-app
shipyard resume --slug my-app
shipyard cost --slug my-app

shipyard scout --focus "productivity, lifestyle and fitness" --count 6
```

`--dry-run` prints the plan without spending. `--auto-approve G0` skips a gate,
subject to the veto described in §5.

## 17. Known constraints

**An iOS build needs a Mac or an Apple developer account.** Android `.aab`
builds anywhere; an `.ipa` needs macOS with Xcode, or EAS cloud with an Apple
Developer account. Without `EXPO_TOKEN` and Apple credentials, stage 80 delivers
a verified source tree plus a one-command `build-ios.sh` to run on a Mac. That
is real and complete, but it is not a binary you can upload from a Linux
container.

**Design guidance was authored, not fetched.** This environment's egress policy
blocks `m3.material.io`, `w3.org` and `reactnative.dev`, and Apple's HIG is a
JavaScript-rendered page that yields no text to a fetcher. The reference notes
are written from stable, widely published specifications rather than scraped,
and say so in `references/design/README.md`. The design roles carry `WebFetch`
so they can pull live references where egress allows — and the numbers that
matter are enforced mechanically either way.

**Store-listing research hits the same wall.** The analyst discovered this
independently on run 001 and disclosed it unprompted rather than presenting
partial evidence as complete.

**Three roles are defined but not wired.** `qa`, `release` and `aso` have specs,
prompts and models, but stages 70/80/90 do not exist yet, so nothing invokes
them. `validate_graph` tolerates this because no stage declares gate G2.

## 18. What has actually run

**Run 001 — Warranty Keeper — NO-GO.** The first live role invocation returned a
no-go in 5m32s for $1.80 with 22 sources: four shipped competitors already
claiming all three stated differentiators at $0.99–$1.99, the free incumbent
drawing ~260 installs a month, the category's best-funded product (Centriq) shut
down in January 2025, the name already taken, and the no-account constraint
colliding with the category's most common one-star review. It refused to rescue
the brief with a pivot and disclosed its own methodological limits. Full
post-mortem in `docs/run-001-warranty-keeper.md`.

That run also exposed two real defects: `RoleResult.text` had no default, so
`SDKRunner` crashed on its first line despite 121 passing tests (all of which
used `ScriptedRunner`); and `--auto-approve G0` would have skipped straight past
the no-go. Both are fixed, with `tests/test_sdk_runner.py` added.

**Run 002 — scouting, productivity/lifestyle/fitness — partial.** The sweep
phase produced 21KB of leads and then the five-hour window filled before the
shortlist phase could run. The notes survived on disk, which is exactly what the
phase split was built for; re-running the same command resumes from them.

**Stages 20–65 have never run against a live model.** Four design roles and the
whole build loop are covered by offline tests and remain untested in anger.

## 19. Roadmap

- **M6 — Hardening (stage 70).** Maestro E2E on a real emulator, cold-start and
  scroll performance budgets, the full security pass, sandbox verification that
  the paywall actually charges.
- **M7 — Release and handoff (stages 80 and 90, gate G2).** Store metadata,
  screenshots framed from the stage-65 captures, the iOS privacy manifest and
  Play Data Safety answers, and a runbook written for someone holding the bundle
  and none of the context.
- **Then the second product costs almost nothing.** Everything above is
  per-organization, not per-product. Once stage 90 lands, a new app is one
  `shipyard new` and three decisions.
