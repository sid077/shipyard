"""Typed artifacts exchanged between roles.

Roles never talk to each other in free text: every stage writes a JSON document
that validates against one of these models, and downstream stages read the
model, not a transcript. A validation error is a stage failure that feeds the
repair loop, so malformed output is caught where it is produced rather than
three stages later.
"""

from __future__ import annotations

import json
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


class DesignTokens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color_primary: str = Field(pattern=HEX)
    color_bg: str = Field(pattern=HEX)
    color_surface: str = Field(pattern=HEX)
    color_text: str = Field(pattern=HEX)
    color_muted: str = Field(pattern=HEX)
    color_danger: str = Field(pattern=HEX)
    radius: int = Field(ge=0, le=48)
    spacing_unit: int = Field(ge=2, le=16)
    font_heading: str
    font_body: str
    mode: Literal["light", "dark", "system"] = "system"


class Screen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=SLUG)
    route: str
    title: str
    purpose: str
    elements: list[str] = Field(min_length=1)
    states: list[str] = Field(min_length=1)
    requires_entitlement: str | None = None
    navigates_to: list[str] = []


class DesignSpec(Artifact):
    rel_path: ClassVar[str] = "design/design.json"

    app_name: str
    tagline: str
    tokens: DesignTokens
    screens: list[Screen] = Field(min_length=3)
    primary_flow: list[str] = Field(min_length=2)
    icon_concept: str
    tone_of_voice: str

    @model_validator(mode="after")
    def _flow_and_links_resolve(self) -> Self:
        ids = {s.id for s in self.screens}
        for sid in self.primary_flow:
            if sid not in ids:
                raise ValueError(f"primary_flow references unknown screen id {sid!r}")
        for screen in self.screens:
            for target in screen.navigates_to:
                if target not in ids:
                    raise ValueError(
                        f"screen {screen.id!r} navigates_to unknown screen {target!r}"
                    )
        return self


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


#: Every artifact the pipeline knows how to validate, by rel_path.
ARTIFACTS: dict[str, type[Artifact]] = {
    cls.rel_path: cls
    for cls in (
        Idea,
        Opportunity,
        MonetizationPlan,
        PRD,
        DesignSpec,
        Architecture,
        Backlog,
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
