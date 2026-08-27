"""The org chart.

A role is a system prompt plus a least-privilege tool set plus a spend cap.
Roles are stateless: they read typed artifacts off disk and write typed
artifacts back. They never decide what happens next - the pipeline does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import MODELS, Settings

# Tool bundles, named so the intent of each role's grant is readable.
READ_ONLY = ["Read", "Grep", "Glob"]
AUTHORING = ["Read", "Write", "Edit", "Grep", "Glob"]
RESEARCH = ["Read", "Write", "Grep", "Glob", "WebSearch", "WebFetch"]
ENGINEERING = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
INSPECTION = ["Read", "Grep", "Glob", "Bash"]


@dataclass(frozen=True)
class RoleSpec:
    name: str
    title: str
    tier: str
    tools: list[str]
    effort: str = "high"
    max_turns: int = 60
    budget_usd: float = 6.0
    # Roles that only inspect must never mutate the tree even if Bash is granted.
    disallowed: list[str] = field(default_factory=list)

    @property
    def model(self) -> str:
        return MODELS[self.tier]

    def prompt_path(self, settings: Settings) -> Path:
        return settings.prompts_dir / f"{self.name}.md"


ROLES: dict[str, RoleSpec] = {
    role.name: role
    for role in (
        RoleSpec(
            "analyst",
            "Market Research Analyst",
            "opus",
            RESEARCH,
            effort="high",
            max_turns=80,
            budget_usd=8.0,
        ),
        RoleSpec(
            "monetization",
            "Monetization Strategist",
            "opus",
            RESEARCH,
            effort="high",
            budget_usd=6.0,
        ),
        RoleSpec(
            "pm",
            "Product Manager",
            "opus",
            AUTHORING,
            effort="xhigh",
            budget_usd=8.0,
        ),
        RoleSpec(
            "ux_architect",
            "UX Architect",
            "opus",
            RESEARCH,
            effort="xhigh",
            budget_usd=8.0,
        ),
        RoleSpec(
            "ui_designer",
            "UI Designer",
            "opus",
            RESEARCH,
            effort="high",
            budget_usd=8.0,
        ),
        RoleSpec(
            "ux_writer",
            "UX Writer",
            "sonnet",
            AUTHORING,
            effort="medium",
            budget_usd=4.0,
        ),
        RoleSpec(
            "design_qa",
            "Design QA Reviewer",
            "opus",
            READ_ONLY,
            effort="high",
            budget_usd=7.0,
        ),
        RoleSpec(
            "architect",
            "Tech Lead",
            "opus",
            AUTHORING,
            effort="xhigh",
            budget_usd=8.0,
        ),
        RoleSpec(
            "planner",
            "Delivery Manager",
            "sonnet",
            AUTHORING,
            effort="high",
            budget_usd=5.0,
        ),
        RoleSpec(
            "dev",
            "Mobile Engineer",
            "opus",
            ENGINEERING,
            effort="xhigh",
            max_turns=120,
            budget_usd=12.0,
        ),
        RoleSpec(
            "reviewer",
            "Code Reviewer",
            "opus",
            INSPECTION,
            effort="high",
            budget_usd=6.0,
            disallowed=["Write", "Edit", "NotebookEdit"],
        ),
        RoleSpec(
            "qa",
            "QA Engineer",
            "sonnet",
            ENGINEERING,
            effort="high",
            max_turns=90,
            budget_usd=8.0,
        ),
        RoleSpec(
            "security",
            "Security & Privacy Reviewer",
            "opus",
            INSPECTION,
            effort="xhigh",
            budget_usd=6.0,
            disallowed=["Write", "Edit", "NotebookEdit"],
        ),
        RoleSpec(
            "release",
            "Release Engineer",
            "sonnet",
            ENGINEERING,
            effort="high",
            max_turns=90,
            budget_usd=8.0,
        ),
        RoleSpec(
            "aso",
            "Growth & Store Listing Writer",
            "sonnet",
            RESEARCH,
            effort="medium",
            budget_usd=4.0,
        ),
        RoleSpec(
            "critic",
            "Definition-of-Done Auditor",
            "sonnet",
            READ_ONLY,
            effort="high",
            max_turns=30,
            budget_usd=3.0,
        ),
    )
}


def get_role(name: str) -> RoleSpec:
    try:
        return ROLES[name]
    except KeyError:
        raise KeyError(f"unknown role {name!r}; known roles: {sorted(ROLES)}") from None
