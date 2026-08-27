# Shipyard

An AI agent organization that takes a product idea from market research to a
deployable mobile app bundle, stopping for you three times along the way.

You approve the opportunity, approve the specification, and receive the release
bundle. Everything in between runs unattended. **Shipyard never ships** —
publishing to the App Store or Play Store is your action, always, and the
harness blocks any attempt by an agent to do it.

## The design bet

The orchestrator is deterministic Python. The agents are stateless workers.

- Roles never decide what happens next; the pipeline does.
- Roles never own git; Python branches, commits, merges and reverts.
- Roles never talk to each other in free text; they read typed artifacts off
  disk and write typed artifacts back, validated against Pydantic contracts.
- Nothing advances because an agent said it works. It advances because a command
  exited zero.

That is why the whole pipeline is testable without spending a cent: swap
`SDKRunner` for `ScriptedRunner` and the orchestrator runs end to end offline.

## The org

| Role | Owns |
|---|---|
| `analyst` | Market and competitor research, go/no-go recommendation |
| `monetization` | Pricing model, tiers, trial, paywall placement |
| `pm` | PRD, scope, testable acceptance criteria |
| `designer` | Screens, flows, design tokens, copy |
| `architect` | Stack decisions, ADRs, data model, module map |
| `planner` | Backlog of vertical slices |
| `dev` | Implements one ticket in one isolated worktree |
| `reviewer` | Reviews a ticket diff; blocking findings only |
| `qa` | Unit tests and Maestro E2E flows |
| `security` | Auth, secrets, purchases, store-compliance review |
| `release` | EAS config, store metadata, screenshots, runbook |
| `aso` | Listing copy and keywords |
| `critic` | Definition-of-Done audit at every stage |

## The pipeline

| Stage | Produces | Gate |
|---|---|---|
| `s00_intake` | `idea.json` | |
| `s10_research` | `research/opportunity.json`, `monetization.json` | **G0** |
| `s20_definition` | `product/prd.json` | |
| `s30_design` | `design/design.json` | **G1** |
| `s40_architecture` | `arch/architecture.json` | |
| `s50_planning` | `backlog/tickets.json` | |

Every stage ends the same way: artifacts must validate against their contract,
the stage's checks must exit zero, and the critic must raise no blocking
finding. Failing any of those re-invokes the role with the failure attached, up
to `max_repairs` times, after which a briefing lands in `inbox/` and the run
halts.

State lives in `.shipyard/state.json`, rewritten atomically after every step, so
a crash costs nothing: `shipyard resume <slug>` picks up at the first stage that
is not done.

## Usage

```bash
pip install -e .

shipyard doctor                       # check the harness itself
shipyard new tip-splitter \
  --title "Tip Splitter" \
  --brief "Split any restaurant bill in three taps, offline."
shipyard run tip-splitter             # halts at G0

cat projects/tip-splitter/inbox/G0.md
shipyard gate approve tip-splitter G0
# or: shipyard gate reject tip-splitter G0 --notes "Pivot to B2B teams"

shipyard resume tip-splitter
shipyard status tip-splitter
shipyard cost tip-splitter
```

Rejection notes are not a restart. They are injected verbatim into the re-run of
the stage that produced the rejected work.

## Budgets

Spend is capped at three levels: per role invocation (`max_budget_usd` on every
SDK call), per project (`SHIPYARD_PROJECT_BUDGET_USD`, default $150), and by
model tier per role. Every invocation is metered into `.shipyard/cost.jsonl`
regardless of which runner is in play.

## Tests

```bash
pytest          # 61 tests, no API calls
```
