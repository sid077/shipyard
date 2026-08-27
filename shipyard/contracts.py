"""Typed artifacts exchanged between roles.

Roles never talk to each other in free text: every stage writes a JSON document
that validates against one of these models, and downstream stages read the
model, not a transcript. A validation error is a stage failure that feeds the
repair loop, so malformed output is caught where it is produced rather than
three stages later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

HEX = r"^#[0-9a-fA-F]{6}$"
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Artifact(BaseModel):
    """A document that lives at a fixed path inside a project directory."""

    model_config = ConfigDict(extra="forbid")

    rel_path: ClassVar[str]

    @classmethod
    def full_path(cls, project_dir: Path) -> Path:
        return Path(project_dir) / cls.rel_path

    @classmethod
    def exists(cls, project_dir: Path) -> bool:
        return cls.full_path(project_dir).is_file()

    @classmethod
    def load(cls, project_dir: Path) -> Self:
        path = cls.full_path(project_dir)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, project_dir: Path) -> Path:
        path = self.full_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        return path

    @classmethod
    def schema_hint(cls) -> str:
        """Pretty JSON schema, for embedding in a role's task prompt."""
        return json.dumps(cls.model_json_schema(), indent=2)


# --------------------------------------------------------------------------
# Stage 00 - intake
# --------------------------------------------------------------------------


class Idea(Artifact):
    rel_path: ClassVar[str] = "idea.json"

    slug: str = Field(pattern=SLUG)
    title: str
    one_liner: str
    brief: str
    platforms: list[Literal["ios", "android"]] = ["ios", "android"]
    constraints: list[str] = []
    source: Literal["human", "generated"] = "human"


# --------------------------------------------------------------------------
# Stage 10 - research
# --------------------------------------------------------------------------


class Competitor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str | None = None
    pricing: str
    strengths: list[str] = []
    weaknesses: list[str] = []


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    severity: Literal["low", "medium", "high"]
    mitigation: str


class Opportunity(Artifact):
    rel_path: ClassVar[str] = "research/opportunity.json"

    problem: str
    target_user: str
    market_note: str
    competitors: list[Competitor] = Field(min_length=3)
    wedge: str
    differentiators: list[str] = Field(min_length=2)
    risks: list[Risk] = Field(min_length=2)
    effort_estimate_weeks: float = Field(gt=0)
    recommendation: Literal["go", "no-go", "pivot"]
    recommendation_rationale: str
    sources: list[str] = Field(min_length=3)


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(pattern=r"^[a-z0-9_]+$")
    display_name: str
    price_usd: float = Field(ge=0)
    period: Literal["month", "year", "lifetime", "consumable"]


class MonetizationPlan(Artifact):
    """Consumed directly by the app template - this is not a memo, it is config."""

    rel_path: ClassVar[str] = "monetization.json"

    model: Literal["subscription", "one_time", "freemium_credits", "ad_supported"]
    rationale: str
    price_points: list[PricePoint] = Field(min_length=1)
    trial_days: int = Field(default=0, ge=0, le=90)
    # entitlement id -> feature keys it unlocks. The app gates on these keys.
    entitlements: dict[str, list[str]] = Field(min_length=1)
    # feature key -> free allowance before the paywall appears.
    free_tier_limits: dict[str, int] = {}
    paywall_trigger: str
    paywall_placement: list[str] = Field(min_length=1)
    projected_arpu_usd: float | None = None

    @model_validator(mode="after")
    def _limits_reference_known_features(self) -> Self:
        known = {f for feats in self.entitlements.values() for f in feats}
        unknown = set(self.free_tier_limits) - known
        if unknown:
            raise ValueError(
                f"free_tier_limits references unknown feature keys: {sorted(unknown)}; "
                f"known keys are {sorted(known)}"
            )
        return self


# --------------------------------------------------------------------------
# Stage 20 - definition
# --------------------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    verified_by: Literal["unit", "e2e", "manual", "static"]


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^R-\d{2,3}$")
    title: str
    description: str
    priority: Literal["p0", "p1", "p2"]
    acceptance: list[AcceptanceCriterion] = Field(min_length=1)


class SuccessMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    event: str
    target: str


class PRD(Artifact):
    rel_path: ClassVar[str] = "product/prd.json"

    title: str
    summary: str
    goals: list[str] = Field(min_length=1)
    non_goals: list[str] = []
    personas: list[str] = Field(min_length=1)
    requirements: list[Requirement] = Field(min_length=3)
    success_metrics: list[SuccessMetric] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_requirement_ids(self) -> Self:
        ids = [r.id for r in self.requirements]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate requirement ids: {sorted(dupes)}")
        if not any(r.priority == "p0" for r in self.requirements):
            raise ValueError("at least one requirement must be priority p0")
        return self


# --------------------------------------------------------------------------
# Stage 30 - design
# --------------------------------------------------------------------------


class TypeStep(BaseModel):
    """One rung of the type ramp."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    size: int = Field(ge=10, le=72)
    line_height: int = Field(ge=12, le=96)
    weight: Literal["400", "500", "600", "700", "800"] = "400"
    letter_spacing: float = Field(default=0.0, ge=-2.0, le=4.0)

    @model_validator(mode="after")
    def _line_height_is_readable(self) -> Self:
        if self.line_height < round(self.size * 1.15):
            raise ValueError(
                f"type step {self.name!r} has line_height {self.line_height} for size "
                f"{self.size}; text needs at least {round(self.size * 1.15)} to be legible"
            )
        return self


class ColorRoles(BaseModel):
    """Semantic colour roles. Named by job, never by hue.

    Contrast is checked here rather than trusted: a palette that fails is a
    stage failure before any code is written.
    """

    model_config = ConfigDict(extra="forbid")

    primary: str = Field(pattern=HEX)
    on_primary: str = Field(pattern=HEX)
    primary_pressed: str = Field(pattern=HEX)
    background: str = Field(pattern=HEX)
    surface: str = Field(pattern=HEX)
    surface_raised: str = Field(pattern=HEX)
    text: str = Field(pattern=HEX)
    text_muted: str = Field(pattern=HEX)
    border: str = Field(pattern=HEX)
    danger: str = Field(pattern=HEX)
    on_danger: str = Field(pattern=HEX)
    success: str = Field(pattern=HEX)

    @model_validator(mode="after")
    def _contrast_is_legible(self) -> Self:
        from .color import NON_TEXT_CONTRAST, TEXT_CONTRAST, check_contrast, contrast_ratio

        problems = check_contrast(
            [
                ("body text on background", self.text, self.background, TEXT_CONTRAST),
                ("body text on surface", self.text, self.surface, TEXT_CONTRAST),
                ("body text on raised surface", self.text, self.surface_raised, TEXT_CONTRAST),
                # Muted text is still text; it does not get a discount.
                ("muted text on background", self.text_muted, self.background, TEXT_CONTRAST),
                ("muted text on surface", self.text_muted, self.surface, TEXT_CONTRAST),
                ("button label on primary", self.on_primary, self.primary, TEXT_CONTRAST),
                ("button label on pressed primary", self.on_primary, self.primary_pressed, TEXT_CONTRAST),
                ("label on danger", self.on_danger, self.danger, TEXT_CONTRAST),
                # Non-text UI: these carry meaning on their own.
                ("primary against background", self.primary, self.background, NON_TEXT_CONTRAST),
                ("danger against background", self.danger, self.background, NON_TEXT_CONTRAST),
                ("success against background", self.success, self.background, NON_TEXT_CONTRAST),
            ]
        )
        # A border nobody can see is not a border.
        if contrast_ratio(self.border, self.surface) < 1.15:
            problems.append(
                f"border {self.border} is invisible against surface {self.surface}"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    purpose: str
    variants: list[str] = Field(min_length=1)
    sizes: list[str] = []
    states: list[str] = Field(min_length=1)
    anatomy: list[str] = []

    @model_validator(mode="after")
    def _has_a_default_state(self) -> Self:
        if "default" not in self.states:
            raise ValueError(f"component {self.name!r} must declare a 'default' state")
        return self


class Section(BaseModel):
    """One block of a screen, naming the component that renders it."""

    model_config = ConfigDict(extra="forbid")

    component: str
    copy_key: str | None = None
    notes: str = ""


class ScreenComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_id: str = Field(pattern=SLUG)
    sections: list[Section] = Field(min_length=1)


class UISpec(Artifact):
    """The visual system. Owned by `ui_designer`."""

    rel_path: ClassVar[str] = "design/ui.json"

    app_name: str
    tagline: str
    icon_concept: str
    tone_of_voice: str
    colors: ColorRoles
    type_scale: list[TypeStep] = Field(min_length=5)
    spacing_unit: int = Field(ge=2, le=12)
    radii: dict[str, int] = Field(min_length=1)
    elevation: list[int] = Field(min_length=2)
    min_touch_target: int = Field(default=44, ge=44, le=72)
    components: list[ComponentSpec] = Field(min_length=6)
    screens: list[ScreenComposition] = Field(min_length=3)
    mode: Literal["light", "dark", "system"] = "system"

    @model_validator(mode="after")
    def _scale_and_inventory_hold_together(self) -> Self:
        sizes = [step.size for step in self.type_scale]
        if sizes != sorted(sizes):
            raise ValueError(
                f"type_scale must be ordered smallest to largest, got {sizes}"
            )
        # One size at two weights is a real rung (body / body_strong); the same
        # size at the same weight twice is a duplicate.
        rungs = [(step.size, step.weight) for step in self.type_scale]
        duplicates = sorted({r for r in rungs if rungs.count(r) > 1})
        if duplicates:
            raise ValueError(
                f"type_scale repeats the same size and weight: {duplicates}"
            )
        names = [step.name for step in self.type_scale]
        if len(set(names)) != len(names):
            raise ValueError(f"type_scale reuses a step name: {names}")
        if "body" not in names:
            raise ValueError(f"type_scale must include a 'body' step; got {names}")
        body = next(step for step in self.type_scale if step.name == "body")
        if body.size < 15:
            raise ValueError(
                f"body text is {body.size}pt; mobile body text must be at least 15pt"
            )

        known = {c.name for c in self.components}
        composed = {s.screen_id for s in self.screens}
        if len(composed) != len(self.screens):
            raise ValueError("two compositions target the same screen_id")
        for screen in self.screens:
            for section in screen.sections:
                if section.component not in known:
                    raise ValueError(
                        f"screen {screen.screen_id!r} uses component "
                        f"{section.component!r}, which is not in the inventory "
                        f"({sorted(known)})"
                    )
        return self

    def copy_keys(self) -> set[str]:
        return {
            s.copy_key
            for screen in self.screens
            for s in screen.sections
            if s.copy_key
        }


# --------------------------------------------------------------------------


class ScreenState(BaseModel):
    """A state a screen can actually be in. Unnamed states become bugs."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    trigger: str
    renders: str
    copy_key: str | None = None


class UXScreen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=SLUG)
    route: str
    title_copy_key: str
    purpose: str
    states: list[ScreenState] = Field(min_length=1)
    requires_entitlement: str | None = None
    navigates_to: list[str] = []
    gestures: list[str] = []

    @model_validator(mode="after")
    def _has_a_default_state(self) -> Self:
        names = [s.name for s in self.states]
        if "default" not in names:
            raise ValueError(f"screen {self.id!r} must declare a 'default' state; got {names}")
        if len(set(names)) != len(names):
            raise ValueError(f"screen {self.id!r} declares a state twice: {names}")
        return self


class Flow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    steps: list[str] = Field(min_length=2)
    success: str
    failure: str


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    describes: str
    # Below ~80ms reads as a jump; above ~600ms reads as sluggish.
    duration_ms: int = Field(ge=80, le=600)
    easing: Literal["standard", "decelerate", "accelerate", "emphasized", "spring"]


class UXSpec(Artifact):
    """Structure, states and motion. Owned by `ux_architect`."""

    rel_path: ClassVar[str] = "design/ux.json"

    navigation: Literal["stack", "tabs", "tabs_with_stack", "drawer"]
    screens: list[UXScreen] = Field(min_length=3)
    flows: list[Flow] = Field(min_length=1)
    primary_flow: str
    transitions: list[Transition] = Field(min_length=2)
    loading_strategy: Literal["skeleton", "spinner", "optimistic"]
    offline_behaviour: str
    error_recovery: str
    haptic_moments: list[str] = []

    @model_validator(mode="after")
    def _references_resolve(self) -> Self:
        ids = {s.id for s in self.screens}
        if len(ids) != len(self.screens):
            raise ValueError("two screens share an id")
        flow_names = {f.name for f in self.flows}
        if self.primary_flow not in flow_names:
            raise ValueError(
                f"primary_flow {self.primary_flow!r} is not one of {sorted(flow_names)}"
            )
        for flow in self.flows:
            for step in flow.steps:
                if step not in ids:
                    raise ValueError(
                        f"flow {flow.name!r} steps through unknown screen {step!r}"
                    )
        for screen in self.screens:
            for target in screen.navigates_to:
                if target not in ids:
                    raise ValueError(
                        f"screen {screen.id!r} navigates_to unknown screen {target!r}"
                    )
        return self

    def copy_keys(self) -> set[str]:
        keys = {s.title_copy_key for s in self.screens}
        keys |= {
            state.copy_key
            for screen in self.screens
            for state in screen.states
            if state.copy_key
        }
        return keys


# --------------------------------------------------------------------------


class CopyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    context: str
    max_chars: int = Field(default=80, ge=1, le=600)

    @model_validator(mode="after")
    def _fits(self) -> Self:
        if len(self.text) > self.max_chars:
            raise ValueError(
                f"copy is {len(self.text)} characters but max_chars is "
                f"{self.max_chars}: {self.text!r}"
            )
        return self


class CopyDeck(Artifact):
    """Every string the app renders. Owned by `ux_writer`."""

    rel_path: ClassVar[str] = "design/copy.json"

    entries: dict[str, CopyEntry] = Field(min_length=5)

    @model_validator(mode="after")
    def _keys_are_usable(self) -> Self:
        bad = [k for k in self.entries if not re.fullmatch(r"[a-z][a-z0-9_.]*", k)]
        if bad:
            raise ValueError(f"copy keys must be lower_snake or dotted: {sorted(bad)}")
        placeholders = [
            k
            for k, e in self.entries.items()
            if re.search(r"(lorem ipsum|\bTODO\b|\[.*?\]|xxx+)", e.text, re.IGNORECASE)
        ]
        if placeholders:
            raise ValueError(
                f"these entries are placeholders, not copy: {sorted(placeholders)}"
            )
        return self


def validate_design_bundle(project_dir: Path) -> list[str]:
    """Cross-artifact checks the three design specs cannot make alone.

    Each artifact validates itself on write; this is what catches the seams
    between them - a screen composed but never specified, a copy key referenced
    but never written.
    """
    problems: list[str] = []
    try:
        ux = UXSpec.load(project_dir)
        ui = UISpec.load(project_dir)
        copy = CopyDeck.load(project_dir)
    except Exception as exc:
        return [f"could not load the design bundle: {exc}"]

    ux_ids = {s.id for s in ux.screens}
    ui_ids = {s.screen_id for s in ui.screens}
    for missing in sorted(ui_ids - ux_ids):
        problems.append(
            f"design/ui.json composes screen {missing!r}, which design/ux.json "
            f"does not specify"
        )
    for missing in sorted(ux_ids - ui_ids):
        problems.append(
            f"design/ux.json specifies screen {missing!r}, which design/ui.json "
            f"never composes"
        )

    referenced = ux.copy_keys() | ui.copy_keys()
    for missing in sorted(referenced - set(copy.entries)):
        problems.append(f"copy key {missing!r} is referenced but not in design/copy.json")

    unused = sorted(set(copy.entries) - referenced)
    if len(unused) > max(3, len(copy.entries) // 2):
        problems.append(
            f"design/copy.json has {len(unused)} entries nothing references: {unused[:8]}"
        )
    return problems


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Stage 40 - architecture
# --------------------------------------------------------------------------


class ADR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ADR-\d{3}$")
    title: str
    decision: str
    rationale: str
    alternatives: list[str] = []
    consequences: list[str] = []


class Module(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    responsibility: str


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    fields: dict[str, str] = Field(min_length=1)
    notes: str = ""


class Architecture(Artifact):
    rel_path: ClassVar[str] = "arch/architecture.json"

    template: str = "expo-app"
    runtime_deps: list[str] = []
    modules: list[Module] = Field(min_length=1)
    entities: list[Entity] = []
    supabase_tables: list[str] = []
    adrs: list[ADR] = Field(min_length=1)
    offline_first: bool = True
    needs_backend: bool = False

    @model_validator(mode="after")
    def _backend_implies_tables(self) -> Self:
        if self.needs_backend and not self.supabase_tables:
            raise ValueError("needs_backend is true but supabase_tables is empty")
        return self


# --------------------------------------------------------------------------
# Stage 50 - planning
# --------------------------------------------------------------------------


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^T-\d{2,3}$")
    title: str
    description: str
    touches: list[str] = Field(min_length=1)
    depends_on: list[str] = []
    requirement_ids: list[str] = Field(min_length=1)
    acceptance: list[AcceptanceCriterion] = Field(min_length=1)
    verify_commands: list[str] = []
    # Tickets touching auth, payments or persisted user data get a security pass.
    sensitive: bool = False
    estimate: Literal["s", "m", "l"] = "m"


class Backlog(Artifact):
    rel_path: ClassVar[str] = "backlog/tickets.json"

    tickets: list[Ticket] = Field(min_length=1)

    @model_validator(mode="after")
    def _dag_is_valid(self) -> Self:
        ids = [t.id for t in self.tickets]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate ticket ids: {sorted(dupes)}")
        known = set(ids)
        for ticket in self.tickets:
            for dep in ticket.depends_on:
                if dep not in known:
                    raise ValueError(f"ticket {ticket.id} depends on unknown {dep}")
                if dep == ticket.id:
                    raise ValueError(f"ticket {ticket.id} depends on itself")
        # Kahn's algorithm; anything left over sits in a cycle.
        pending = {t.id: set(t.depends_on) for t in self.tickets}
        while True:
            ready = [tid for tid, deps in pending.items() if not deps]
            if not ready:
                break
            for tid in ready:
                pending.pop(tid)
                for deps in pending.values():
                    deps.discard(tid)
        if pending:
            raise ValueError(f"dependency cycle among tickets: {sorted(pending)}")
        return self

    def ready(self, done: set[str]) -> list[Ticket]:
        """Tickets whose dependencies are all satisfied and are not yet done."""
        return [
            t
            for t in self.tickets
            if t.id not in done and all(d in done for d in t.depends_on)
        ]


# --------------------------------------------------------------------------
# Reviews and verdicts (per-attempt, not stage artifacts)
# --------------------------------------------------------------------------


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking", "advisory"]
    where: str
    problem: str
    fix: str


class Verdict(BaseModel):
    """Returned by the critic, the reviewer and the security role alike."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "fail"]
    summary: str
    findings: list[Finding] = []

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocking"]

    def as_feedback(self) -> str:
        lines = [f"Previous attempt was rejected: {self.summary}", "", "Blocking issues:"]
        for i, f in enumerate(self.blocking, 1):
            lines.append(f"{i}. [{f.where}] {f.problem}\n   Required fix: {f.fix}")
        advisory = [f for f in self.findings if f.severity == "advisory"]
        if advisory:
            lines.append("")
            lines.append("Advisory (address if cheap):")
            for f in advisory:
                lines.append(f"- [{f.where}] {f.problem}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Stage 70/80 - hardening and release
# --------------------------------------------------------------------------


class TicketOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["merged", "blocked"]
    attempts: int = 1
    integration_attempts: int = 1
    blocking_findings: int = 0
    commit: str | None = None
    note: str = ""


class BuildReport(Artifact):
    rel_path: ClassVar[str] = "build/build.json"

    app_path: str = "app"
    trunk_commit: str
    tickets: list[TicketOutcome] = Field(min_length=1)
    checks: str = ""

    @property
    def merged(self) -> list[TicketOutcome]:
        return [t for t in self.tickets if t.status == "merged"]

    @property
    def blocked(self) -> list[TicketOutcome]:
        return [t for t in self.tickets if t.status == "blocked"]


class HardeningReport(Artifact):
    rel_path: ClassVar[str] = "qa/hardening.json"

    e2e_flows_passing: list[str] = []
    security_findings: list[Finding] = []
    accessibility_findings: list[Finding] = []
    monetization_verified: bool = False
    notes: str = ""


class BuildArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["ios", "android"]
    kind: Literal["aab", "apk", "ipa", "source"]
    path: str
    built_locally: bool
    note: str = ""


class ReleaseManifest(Artifact):
    rel_path: ClassVar[str] = "release/release.json"

    app_name: str
    bundle_id: str
    version: str
    build_number: int = 1
    artifacts: list[BuildArtifact] = []
    store_listing_paths: list[str] = []
    privacy_paths: list[str] = []
    screenshots: list[str] = []
    runbook_path: str = "release/RUNBOOK.md"


def coerce_verdict(structured: Any, text: str) -> Verdict | None:
    """Read a `Verdict` out of a role result, or None if it did not produce one.

    Used by every role that judges rather than produces: the critic, the code
    reviewer and the security reviewer all answer in the same shape.
    """
    payload = structured
    if payload is None:
        try:
            payload = parse_json_blob(text)
        except ValueError:
            return None
    try:
        verdict = Verdict.model_validate(payload)
    except Exception:
        return None
    # A "fail" with nothing blocking is a contradiction; the findings win.
    if verdict.verdict == "fail" and not verdict.blocking:
        return Verdict(verdict="pass", summary=verdict.summary, findings=verdict.findings)
    return verdict


#: Every artifact the pipeline knows how to validate, by rel_path.
ARTIFACTS: dict[str, type[Artifact]] = {
    cls.rel_path: cls
    for cls in (
        Idea,
        Opportunity,
        MonetizationPlan,
        PRD,
        UXSpec,
        UISpec,
        CopyDeck,
        Architecture,
        Backlog,
        BuildReport,
        HardeningReport,
        ReleaseManifest,
    )
}


def parse_json_blob(text: str) -> Any:
    """Extract a JSON document from a model response.

    Roles are told to emit bare JSON, but a stray fence or a sentence of
    preamble should not fail a stage, so recover from the common shapes.
    """
    text = text.strip()
    if text.startswith("```"):
        body = text.split("```", 2)
        if len(body) >= 2:
            inner = body[1]
            if inner.lstrip().startswith("json"):
                inner = inner.lstrip()[4:]
            text = inner.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        raise ValueError("no JSON document found in response")
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("no JSON document found in response")
    return json.loads(text[start : end + 1])
