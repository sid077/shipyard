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
    CopyDeck,
    Idea,
    MonetizationPlan,
    Opportunity,
    PRD,
    UISpec,
    UXSpec,
    validate_design_bundle,
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


REFERENCES = ("layout-and-touch", "type-and-colour", "motion-and-haptics", "ux-writing", "accessibility")


def _reference_notes(ctx: StageContext, *names: str) -> list[Path]:
    base = ctx.settings.repo_root / "references" / "design"
    return existing(*(base / f"{n}.md" for n in names))


class Design(Stage):
    """Structure, then words, then looks.

    Three roles in that order for a reason: the UX Architect names the copy keys
    each screen and state needs, the UX Writer fills them, and only then can the
    UI Designer compose screens and render a preview with real copy in it.
    """

    key = "s30_design"
    title = "Design"
    owner_role = "ui_designer"
    requires = (PRD, MonetizationPlan)
    outputs = (UXSpec, CopyDeck, UISpec)
    gate_after = Gate.G1
    dod = """
- Every p0 requirement in the PRD is reachable from some screen.
- Every screen names the states it can really be in, including empty, loading
  and error where they apply, and each state says what triggers it.
- Screens behind the paywall carry `requires_entitlement` matching an
  entitlement id in `monetization.json`.
- The primary flow reaches the product's core value in as few steps as the
  product allows.
- Copy is written, not placeheld: real button labels, real empty states, real
  error messages that say what to do next.
- The component inventory covers every section the screens compose, so an
  engineer builds from it rather than inventing.
- `design/preview.html` renders every screen with the real tokens and the real
  copy, and looks like the product rather than like a diagram.
""".strip()

    async def execute(self, ctx: StageContext) -> None:
        prd = PRD.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)
        entitlements = ", ".join(f"`{k}`" for k in monetization.entitlements)
        spec_inputs = existing(
            PRD.full_path(ctx.project_dir),
            ctx.project_dir / "product" / "prd.md",
            MonetizationPlan.full_path(ctx.project_dir),
        )

        # 1. Structure, states and motion.
        await ctx.runner.invoke(
            RoleRequest(
                role="ux_architect",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                read_roots=[ctx.settings.repo_root / "references"],
                task=compose(
                    objective=(
                        f"Define the structure, states and motion of **{prd.title}**.\n\n"
                        f"{prd.summary}\n\n"
                        f"Entitlement ids available for gating: {entitlements}. "
                        f"The paywall appears {monetization.paywall_trigger}."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=spec_inputs + _reference_notes(ctx, "layout-and-touch", "motion-and-haptics", "accessibility"),
                    outputs=[UXSpec],
                    guidance=(
                        "Name a copy key for every screen title, every non-default state "
                        "that shows a message, and the primary action of each screen. The "
                        "UX Writer fills those keys next and the UI Designer may only use "
                        "keys that exist, so a key you forget is a screen that cannot "
                        "speak. Use dotted lower_snake keys like `history.empty`."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )
        ux = _require(ctx, UXSpec)

        # 2. Every string, before anything renders it.
        needed = sorted(ux.copy_keys())
        await ctx.runner.invoke(
            RoleRequest(
                role="ux_writer",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                read_roots=[ctx.settings.repo_root / "references"],
                task=compose(
                    objective=(
                        f"Write every string **{prd.title}** renders.\n\n"
                        f"Tone: {prd.summary}\n\n"
                        f"These keys are referenced by the UX spec and must all exist:\n"
                        + "\n".join(f"- `{k}`" for k in needed)
                    ),
                    project_dir=ctx.project_dir,
                    inputs=spec_inputs
                    + existing(UXSpec.full_path(ctx.project_dir))
                    + _reference_notes(ctx, "ux-writing"),
                    outputs=[CopyDeck],
                    guidance=(
                        "Add the keys above plus any button label, empty state or error "
                        "message the screens in the UX spec plainly need. Set `max_chars` "
                        "to the real ceiling for where the string appears - roughly 24 for "
                        "a button, 20 for a screen title, 60 for an empty state, 80 for an "
                        "error. Paywall copy names the benefit and states the price "
                        f"plainly: {', '.join(f'${p.price_usd:.2f}/{p.period}' for p in monetization.price_points)}."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )
        copy = _require(ctx, CopyDeck)

        # 3. The visual system, and a preview a human can judge.
        preview = ctx.project_dir / "design" / "preview.html"
        screen_list = "\n".join(
            f"- `{s.id}` ({s.route}) - {s.purpose}; states: "
            + ", ".join(st.name for st in s.states)
            for s in ux.screens
        )
        await ctx.runner.invoke(
            RoleRequest(
                role="ui_designer",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                read_roots=[ctx.settings.repo_root / "references"],
                task=compose(
                    objective=(
                        f"Design the visual system for **{prd.title}** and compose its "
                        f"screens.\n\n{prd.summary}\n\nScreens to compose:\n{screen_list}"
                    ),
                    project_dir=ctx.project_dir,
                    inputs=spec_inputs
                    + existing(
                        UXSpec.full_path(ctx.project_dir),
                        CopyDeck.full_path(ctx.project_dir),
                    )
                    + _reference_notes(ctx, "type-and-colour", "layout-and-touch", "accessibility"),
                    outputs=[UISpec],
                    guidance=(
                        f"Compose exactly the screens the UX spec defines - no more, no "
                        f"fewer. Section `copy_key` values must be keys that already exist "
                        f"in `design/copy.json` ({len(copy.entries)} available); leave "
                        f"`copy_key` null for a section that renders no fixed string.\n\n"
                        f"Contrast is computed and will reject the palette if it fails, so "
                        f"check the arithmetic before you commit to colours. Muted text "
                        f"needs 4.5:1 too.\n\n"
                        f"Then write `{preview}`: one self-contained HTML file, no external "
                        f"requests, showing every screen side by side in a 390x844 phone "
                        f"frame, rendered with your real tokens and the real copy from the "
                        f"deck. This is what the operator looks at to approve the product, "
                        f"so it should look like the app, not like a spec."
                    ),
                    feedback=ctx.feedback,
                ),
            )
        )

    def cross_validate(self, ctx: StageContext) -> list[str]:
        return validate_design_bundle(ctx.project_dir)

    def checks(self, ctx: StageContext) -> list[Check]:
        preview = ctx.project_dir / "design" / "preview.html"
        return [
            files_exist([preview], ctx.project_dir, "preview-exists"),
            # A stub page is worse than none: the operator approves by looking.
            Check(
                "preview-is-substantial",
                f"test $(wc -c < {preview}) -gt 3000",
                ctx.project_dir,
                60,
            ),
            Check(
                "preview-is-self-contained",
                f"! grep -qE '<(script|link|img)[^>]+(src|href)=\"https?://' {preview}",
                ctx.project_dir,
                60,
            ),
        ]

    def briefing(self, ctx: StageContext) -> str:
        prd = PRD.load(ctx.project_dir)
        ux = UXSpec.load(ctx.project_dir)
        ui = UISpec.load(ctx.project_dir)
        copy = CopyDeck.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)

        reqs = "\n".join(
            f"| {r.id} | {r.priority} | {r.title} |" for r in prd.requirements
        )
        screens = "\n".join(
            f"| `{s.id}` | {copy.entries[s.title_copy_key].text if s.title_copy_key in copy.entries else s.id} "
            f"| {', '.join(st.name for st in s.states)} "
            f"| {s.requires_entitlement or '-'} |"
            for s in ux.screens
        )
        flow = next(f for f in ux.flows if f.name == ux.primary_flow)
        palette = ui.colors
        sample = "\n".join(
            f"- **{k}** - {v.text}"
            for k, v in list(copy.entries.items())[:6]
        )
        return f"""## {ui.app_name} - {ui.tagline}

{prd.summary}

### Look at the design

`design/preview.html` - every screen in a phone frame, real tokens, real copy.
Open it in a browser before deciding.

## Requirements

| ID | Priority | Title |
|---|---|---|
{reqs}

## Screens ({ux.navigation})

| Screen | Title | States | Gated |
|---|---|---|---|
{screens}

**Primary flow — {flow.name}:** {' -> '.join(flow.steps)}
Succeeds when {flow.success}; fails when {flow.failure}.

- Loading: {ux.loading_strategy}
- Offline: {ux.offline_behaviour}
- Errors: {ux.error_recovery}

## Look

Primary `{palette.primary}` on `{palette.background}` · text `{palette.text}` ·
{len(ui.type_scale)}-step type ramp with {next(t.size for t in ui.type_scale if t.name == 'body')}pt body ·
{ui.spacing_unit}pt spacing unit · {len(ui.components)} components · {ui.mode} mode

Icon: {ui.icon_concept}

## Voice

{sample}

## Money

{monetization.model} - {', '.join(f'${p.price_usd:.2f}/{p.period}' for p in monetization.price_points)}
{f'with a {monetization.trial_days}-day trial' if monetization.trial_days else 'with no trial'}.
Paywall: {monetization.paywall_trigger}
"""


class ArchitectureStage(Stage):
    key = "s40_architecture"
    title = "Architecture"
    owner_role = "architect"
    requires = (PRD, UXSpec, UISpec)
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
        ux = UXSpec.load(ctx.project_dir)
        design = UISpec.load(ctx.project_dir)
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
                        f"There are {len(ux.screens)} screens and "
                        f"{len(prd.requirements)} requirements to support."
                    ),
                    project_dir=ctx.project_dir,
                    inputs=existing(
                        PRD.full_path(ctx.project_dir),
                        UXSpec.full_path(ctx.project_dir),
                        UISpec.full_path(ctx.project_dir),
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
    requires = (PRD, UXSpec, UISpec, Architecture, MonetizationPlan)
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
        design = UISpec.load(ctx.project_dir)
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
                        UXSpec.full_path(ctx.project_dir),
                        UISpec.full_path(ctx.project_dir),
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
