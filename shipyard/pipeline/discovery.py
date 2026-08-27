"""Stages 00-50: from an idea to a dependency-ordered backlog.

Nothing here writes application code. The output of this half of the pipeline is
a specification precise enough that the build loop can run unattended.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import (
    Architecture,
    Artifact,
    Backlog,
    DesignSpec,
    Idea,
    MonetizationPlan,
    Opportunity,
    PRD,
)
from ..gates import Gate
from ..runner import RoleRequest
from ..tasks import compose, existing
from ..verify import Check, files_exist
from . import Stage, StageContext


def _require(ctx: StageContext, cls: type[Artifact]) -> Artifact:
    """Load an artifact a later role depends on, failing loudly if it is bad.

    Raising here aborts the attempt before the next role wastes a call reading a
    file that does not exist or does not validate.
    """
    try:
        return cls.load(ctx.project_dir)
    except FileNotFoundError:
        raise RuntimeError(
            f"expected {cls.rel_path} to exist by now; the previous role did not write it"
        ) from None
    except Exception as exc:
        raise RuntimeError(f"{cls.rel_path} does not satisfy its contract:\n{exc}") from None


# --------------------------------------------------------------------------


class Intake(Stage):
    key = "s00_intake"
    title = "Intake"
    owner_role = ""
    outputs = (Idea,)
    audit = False
    dod = "The idea brief exists and validates."

    async def execute(self, ctx: StageContext) -> None:
        # `shipyard new` writes idea.json; this stage only admits it to the run.
        _require(ctx, Idea)
        ctx.ledger.event("intake.accepted", slug=ctx.slug)


# --------------------------------------------------------------------------


class Research(Stage):
    key = "s10_research"
    title = "Research"
    owner_role = "analyst"
    requires = (Idea,)
    outputs = (Opportunity, MonetizationPlan)
    gate_after = Gate.G0
    dod = """
- Every competitor named is a real, currently shipping product, with its real
  pricing, and appears among the sources.
- `sources` are URLs the analyst actually opened, not search result pages.
- `market_note` either cites a figure to a source or states plainly that no
  reliable public figure exists and names the proxy used.
- The wedge is specific enough to build against: it names an underserved user
  and what they cannot do today.
- The monetization model is justified by what competitors charge, and its
  `free_tier_limits` keys all exist in `entitlements`.
- `recommendation` follows from the evidence rather than from enthusiasm.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        idea = Idea.load(ctx.project_dir)
        research_md = ctx.project_dir / "research" / "research.md"

        await ctx.runner.invoke(
            RoleRequest(
                role="analyst",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Research the opportunity behind this idea and recommend whether "
                        f"the studio should build it.\n\n"
                        f"**{idea.title}** - {idea.one_liner}\n\n{idea.brief}\n\n"
                        f"Target platforms: {', '.join(idea.platforms)}.\n"
                        + (
                            "Operator constraints: "
                            + "; ".join(idea.constraints)
                            + "\n"
                            if idea.constraints
                            else ""
                        )
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(Idea.full_path(ctx.project_dir)),
                    outputs=[Opportunity],
                    guidance=(
                        f"Also write a prose companion at `{research_md}` covering what you "
                        f"found: the competitors you opened, what their reviewers complain "
                        f"about, pricing you observed, and the reasoning behind your "
                        f"recommendation. That file is what the operator reads at the gate, "
                        f"so make it worth three minutes of their time."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )
        opportunity = _require(ctx, Opportunity)

        await ctx.runner.invoke(
            RoleRequest(
                role="monetization",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Decide how **{idea.title}** makes money, and write the "
                        f"configuration the app will compile against.\n\n"
                        f"The wedge the studio is betting on: {opportunity.wedge}\n"
                        f"Target user: {opportunity.target_user}"
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        Opportunity.full_path(ctx.project_dir),
                        research_md,
                        Idea.full_path(ctx.project_dir),
                    ),
                    outputs=[MonetizationPlan],
                    guidance=(
                        "Ground your price points in what the competitors in "
                        "`opportunity.json` actually charge. Look up any pricing the "
                        "analyst did not record."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )

    def checks(self, ctx: StageContext) -> list[Check]:
        return [
            files_exist(
                [ctx.project_dir / "research" / "research.md"],
                ctx.project_dir,
                "research-writeup-exists",
            )
        ]

    def briefing(self, ctx: StageContext) -> str:
        o = Opportunity.load(ctx.project_dir)
        m = MonetizationPlan.load(ctx.project_dir)
        comps = "\n".join(
            f"| {c.name} | {c.pricing} | {'; '.join(c.weaknesses) or '-'} |"
            for c in o.competitors
        )
        prices = "\n".join(
            f"- **{p.display_name}** (`{p.sku}`) - ${p.price_usd:.2f} / {p.period}"
            for p in m.price_points
        )
        risks = "\n".join(f"- **{r.severity}** {r.description} -> {r.mitigation}" for r in o.risks)
        return f"""## Recommendation: **{o.recommendation.upper()}**

{o.recommendation_rationale}

## The problem

{o.problem}

**Target user:** {o.target_user}

**Wedge:** {o.wedge}

**Differentiators:** {', '.join(o.differentiators)}

## Market

{o.market_note}

| Competitor | Pricing | Weakness we exploit |
|---|---|---|
{comps}

## Monetization: {m.model}

{m.rationale}

{prices}

- Trial: {m.trial_days} days
- Paywall appears: {m.paywall_trigger}
- Entitlements: {', '.join(f'`{k}` -> {len(v)} features' for k, v in m.entitlements.items())}

## Risks

{risks}

**Estimated build effort:** {o.effort_estimate_weeks} weeks

Full write-up: `research/research.md`
"""


# --------------------------------------------------------------------------


class Definition(Stage):
    key = "s20_definition"
    title = "Definition"
    owner_role = "pm"
    requires = (Idea, Opportunity, MonetizationPlan)
    outputs = (PRD,)
    dod = """
- Every requirement has acceptance criteria that could actually fail, each with
  a `verified_by` method, and `manual` is used sparingly.
- At least one p0 requirement covers paywall placement and entitlement gating,
  and it references feature keys that exist in `monetization.json`.
- `non_goals` is not empty - a v1 that cuts nothing has not been scoped.
- Success metrics reference analytics events the app can actually emit.
- The requirements, taken together, deliver the wedge from `opportunity.json`.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        idea = Idea.load(ctx.project_dir)
        opportunity = Opportunity.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)
        keys = sorted({f for feats in monetization.entitlements.values() for f in feats})
        prd_md = ctx.project_dir / "product" / "prd.md"

        await ctx.runner.invoke(
            RoleRequest(
                role="pm",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Write the v1 specification for **{idea.title}**.\n\n"
                        f"The studio approved this bet: {opportunity.wedge}\n"
                        f"Monetization is already decided ({monetization.model}); "
                        f"the paywall appears {monetization.paywall_trigger}.\n"
                        f"Entitlement feature keys you must gate against: "
                        f"{', '.join(f'`{k}`' for k in keys)}."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        Opportunity.full_path(ctx.project_dir),
                        MonetizationPlan.full_path(ctx.project_dir),
                        ctx.project_dir / "research" / "research.md",
                        Idea.full_path(ctx.project_dir),
                    ),
                    outputs=[PRD],
                    guidance=(
                        f"Also write `{prd_md}`: the same specification as readable prose "
                        f"for the operator, with the scope cuts you made and why."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )

    def checks(self, ctx: StageContext) -> list[Check]:
        return [
            files_exist(
                [ctx.project_dir / "product" / "prd.md"], ctx.project_dir, "prd-prose-exists"
            )
        ]


# --------------------------------------------------------------------------


class Design(Stage):
    key = "s30_design"
    title = "Design"
    owner_role = "designer"
    requires = (PRD, MonetizationPlan)
    outputs = (DesignSpec,)
    gate_after = Gate.G1
    dod = """
- Every p0 requirement in the PRD is reachable from some screen in the spec.
- Screens behind the paywall carry `requires_entitlement` matching an
  entitlement id in `monetization.json`.
- Every screen names its empty, loading and error states where they apply.
- `primary_flow` is a real path from launch to the product's core value.
- Colour tokens are legible: body text contrasts against both background and
  surface, and white text is readable on the primary colour.
- Copy is written, not placeheld.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        prd = PRD.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)
        await ctx.runner.invoke(
            RoleRequest(
                role="designer",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Design the screens, flow and visual system for **{prd.title}**.\n\n"
                        f"{prd.summary}\n\n"
                        f"Entitlement ids available for gating: "
                        f"{', '.join(f'`{k}`' for k in monetization.entitlements)}. "
                        f"The paywall appears {monetization.paywall_trigger}, on: "
                        f"{', '.join(monetization.paywall_placement)}."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        PRD.full_path(ctx.project_dir),
                        ctx.project_dir / "product" / "prd.md",
                        MonetizationPlan.full_path(ctx.project_dir),
                    ),
                    outputs=[DesignSpec],
                    feedback=ctx.feedback,
                ),
            )
        )

    def briefing(self, ctx: StageContext) -> str:
        prd = PRD.load(ctx.project_dir)
        design = DesignSpec.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)
        reqs = "\n".join(
            f"| {r.id} | {r.priority} | {r.title} | {len(r.acceptance)} criteria |"
            for r in prd.requirements
        )
        screens = "\n".join(
            f"| `{s.id}` | `{s.route}` | {s.purpose}"
            f"{' | 🔒 ' + s.requires_entitlement if s.requires_entitlement else ' |'} |"
            for s in design.screens
        )
        return f"""## {design.app_name} - {design.tagline}

{prd.summary}

## Goals

{chr(10).join('- ' + g for g in prd.goals)}

## Explicitly not in v1

{chr(10).join('- ' + g for g in prd.non_goals) or '- (nothing was cut - worth questioning)'}

## Requirements

| ID | Priority | Title | Verification |
|---|---|---|---|
{reqs}

## Screens

| Screen | Route | Purpose | Gated |
|---|---|---|---|
{screens}

**Primary flow:** {' -> '.join(design.primary_flow)}

## Money

{monetization.model} - {', '.join(f'${p.price_usd:.2f}/{p.period}' for p in monetization.price_points)}
{f'with a {monetization.trial_days}-day trial' if monetization.trial_days else 'with no trial'}.
Paywall: {monetization.paywall_trigger}

## Look

Primary `{design.tokens.color_primary}` · background `{design.tokens.color_bg}` ·
text `{design.tokens.color_text}` · radius {design.tokens.radius} ·
{design.tokens.font_heading} / {design.tokens.font_body} · {design.tokens.mode} mode

Icon concept: {design.icon_concept}

Full spec: `product/prd.md`, `design/design.json`
"""


# --------------------------------------------------------------------------


class ArchitectureStage(Stage):
    key = "s40_architecture"
    title = "Architecture"
    owner_role = "architect"
    requires = (PRD, DesignSpec)
    outputs = (Architecture,)
    dod = """
- Every entry in `runtime_deps` is a real npm package that this product needs
  and that the template does not already provide.
- Modules map to plausible directories and partition the app without overlap.
- If `needs_backend` is true, the Supabase tables are listed and cover the
  entities; if false, the local persistence story is stated in an ADR.
- There is an ADR for storage, for how entitlements are checked, and for
  anything else a future engineer would otherwise reopen.
- Each ADR names the alternatives that were rejected.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        prd = PRD.load(ctx.project_dir)
        design = DesignSpec.load(ctx.project_dir)
        await ctx.runner.invoke(
            RoleRequest(
                role="architect",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Decide how **{design.app_name}** is built on top of the studio's "
                        f"`expo-app` template, and record the decisions.\n\n"
                        f"{prd.summary}\n\n"
                        f"There are {len(design.screens)} screens and "
                        f"{len(prd.requirements)} requirements to support."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        PRD.full_path(ctx.project_dir),
                        DesignSpec.full_path(ctx.project_dir),
                        MonetizationPlan.full_path(ctx.project_dir),
                    ),
                    outputs=[Architecture],
                    guidance=(
                        "The template already provides Expo SDK 57, expo-router, TypeScript "
                        "strict, a generated token theme, Supabase, RevenueCat, a typed "
                        "analytics taxonomy, Jest with React Native Testing Library, and "
                        "Maestro. Do not list any of those in `runtime_deps`; list only "
                        "what this product adds."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )


# --------------------------------------------------------------------------


class Planning(Stage):
    key = "s50_planning"
    title = "Planning"
    owner_role = "planner"
    requires = (PRD, DesignSpec, Architecture, MonetizationPlan)
    outputs = (Backlog,)
    dod = """
- Every p0 requirement in the PRD is covered by at least one ticket.
- Tickets are vertical slices: each leaves the app working and demonstrable.
- The paywall and entitlement gating ticket exists and is marked `sensitive`.
- `touches` globs are specific enough to predict collisions between parallel
  engineers; `src/**` is not specific.
- `depends_on` contains only real ordering constraints, so independent tickets
  can run in parallel.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        prd = PRD.load(ctx.project_dir)
        design = DesignSpec.load(ctx.project_dir)
        arch = Architecture.load(ctx.project_dir)
        p0 = [r.id for r in prd.requirements if r.priority == "p0"]
        await ctx.runner.invoke(
            RoleRequest(
                role="planner",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=compose(
                    objective=(
                        f"Break **{design.app_name}** into a dependency-ordered backlog of "
                        f"vertical slices that parallel engineers can build without "
                        f"colliding.\n\n"
                        f"Must-cover p0 requirements: {', '.join(p0)}.\n"
                        f"Modules the architect defined: "
                        f"{', '.join(m.path for m in arch.modules)}."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        PRD.full_path(ctx.project_dir),
                        DesignSpec.full_path(ctx.project_dir),
                        Architecture.full_path(ctx.project_dir),
                        MonetizationPlan.full_path(ctx.project_dir),
                    ),
                    outputs=[Backlog],
                    feedback=ctx.feedback,
                ),
            )
        )


DISCOVERY_STAGES: list[Stage] = [
    Intake(),
    Research(),
    Definition(),
    Design(),
    ArchitectureStage(),
    Planning(),
]
