"""Valid artifacts, so pipeline tests exercise the real contracts."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: F401

from shipyard.contracts import (
    ADR,
    Architecture,
    AcceptanceCriterion,
    Backlog,
    Competitor,
    DesignSpec,
    DesignTokens,
    Entity,
    Idea,
    Module,
    MonetizationPlan,
    Opportunity,
    PRD,
    PricePoint,
    Requirement,
    Risk,
    Screen,
    SuccessMetric,
    Ticket,
)

PASS_VERDICT = json.dumps({"verdict": "pass", "summary": "looks buildable", "findings": []})


def idea() -> Idea:
    return Idea(
        slug="tip-splitter",
        title="Tip Splitter",
        one_liner="Split any restaurant bill in three taps, offline.",
        brief="A fast offline bill splitter with uneven splits and a pro tier.",
        platforms=["ios", "android"],
    )


def opportunity() -> Opportunity:
    return Opportunity(
        problem="Splitting an uneven bill at the table is slow and error-prone.",
        target_user="Groups of friends who eat out weekly and split unevenly.",
        market_note="No reliable public figure; used App Store category ranks as a proxy.",
        competitors=[
            Competitor(name="Splitwise", url="https://splitwise.com", pricing="Free, Pro $3/mo",
                       strengths=["ledger"], weaknesses=["slow at the table"]),
            Competitor(name="Tab", url="https://example.com/tab", pricing="$2.99 once",
                       strengths=["receipt scan"], weaknesses=["no uneven splits"]),
            Competitor(name="Settle Up", url="https://example.com/settle", pricing="Free with ads",
                       strengths=["groups"], weaknesses=["ads mid-flow"]),
        ],
        wedge="Three taps to a correct uneven split, with no account and no network.",
        differentiators=["Works offline", "No sign-up before first use"],
        risks=[
            Risk(description="Category is crowded", severity="high", mitigation="Compete on speed"),
            Risk(description="Low willingness to pay", severity="medium", mitigation="One-time unlock"),
        ],
        effort_estimate_weeks=3.0,
        recommendation="go",
        recommendation_rationale="Incumbents optimise for ledgers, not for the moment at the table.",
        sources=["https://splitwise.com/pricing", "https://example.com/tab", "https://example.com/reviews"],
    )


def monetization() -> MonetizationPlan:
    return MonetizationPlan(
        model="one_time",
        rationale="Occasional use with one clear unlock; competitors charge $2-3 once.",
        price_points=[PricePoint(sku="pro_lifetime", display_name="Tip Splitter Pro",
                                 price_usd=2.99, period="lifetime")],
        trial_days=0,
        entitlements={"pro": ["unlimited_history", "custom_split_rules", "export_csv"]},
        free_tier_limits={"unlimited_history": 5},
        paywall_trigger="on the sixth saved split",
        paywall_placement=["history", "paywall"],
    )


def prd() -> PRD:
    ac = [AcceptanceCriterion(id="AC-1", statement="Given a bill, when split, then totals match to the cent.",
                              verified_by="unit")]
    return PRD(
        title="Tip Splitter",
        summary="Split an uneven restaurant bill in three taps, offline.",
        goals=["Correct split in under 10 seconds"],
        non_goals=["Group ledgers", "Bank integration"],
        personas=["Weekly diner splitting with four friends"],
        requirements=[
            Requirement(id="R-01", title="Enter a bill", description="Amount, tip, party size.",
                        priority="p0", acceptance=ac),
            Requirement(id="R-02", title="Uneven split", description="Assign items per person.",
                        priority="p0", acceptance=ac),
            Requirement(id="R-03", title="Paywall", description="Gate unlimited_history on `pro`.",
                        priority="p0", acceptance=[
                            AcceptanceCriterion(id="AC-2",
                                                statement="Given 5 saved splits, when saving a sixth, then the paywall appears.",
                                                verified_by="e2e")]),
        ],
        success_metrics=[SuccessMetric(name="Activation", event="activation", target="60% of installs")],
    )


def design() -> DesignSpec:
    return DesignSpec(
        app_name="Tip Splitter",
        tagline="Three taps. Correct every time.",
        tokens=DesignTokens(color_primary="#1f6feb", color_bg="#ffffff", color_surface="#f5f6f8",
                            color_text="#111318", color_muted="#5b6472", color_danger="#d1242f",
                            radius=12, spacing_unit=4, font_heading="Inter", font_body="Inter",
                            mode="system"),
        screens=[
            Screen(id="split", route="/(tabs)/index", title="Split", purpose="Enter a bill and split it.",
                   elements=["amount field", "party stepper"], states=["empty", "error"],
                   navigates_to=["history"]),
            Screen(id="history", route="/(tabs)/history", title="History", purpose="Past splits.",
                   elements=["list"], states=["empty", "loading", "paywalled"],
                   requires_entitlement="pro", navigates_to=["paywall"]),
            Screen(id="paywall", route="/paywall", title="Go Pro", purpose="Sell the lifetime unlock.",
                   elements=["price", "buy button"], states=["loading", "error"]),
        ],
        primary_flow=["split", "history"],
        icon_concept="A receipt torn cleanly into three equal strips.",
        tone_of_voice="Plain and quick.",
    )


def architecture() -> Architecture:
    return Architecture(
        runtime_deps=["decimal.js"],
        modules=[Module(name="split", path="src/features/split", responsibility="Split maths and entry UI"),
                 Module(name="history", path="src/features/history", responsibility="Persisted past splits")],
        entities=[Entity(name="Split", fields={"id": "uuid", "total": "number", "created_at": "timestamptz"})],
        adrs=[ADR(id="ADR-001", title="Local-only storage", decision="Persist splits in SQLite on device.",
                  rationale="No account, works offline.", alternatives=["Supabase"],
                  consequences=["No cross-device sync in v1"])],
        offline_first=True,
        needs_backend=False,
    )


def backlog() -> Backlog:
    ac = [AcceptanceCriterion(id="AC-1", statement="Given the app, when opened, then the split screen renders.",
                              verified_by="unit")]
    return Backlog(tickets=[
        Ticket(id="T-01", title="Scaffold product config and theme", description="Apply tokens and routes.",
               touches=["src/theme/**", "app.config.ts"], requirement_ids=["R-01"], acceptance=ac, estimate="s"),
        Ticket(id="T-02", title="Bill entry and even split", description="Amount, tip, party size.",
               touches=["src/features/split/**"], depends_on=["T-01"], requirement_ids=["R-01"],
               acceptance=ac, estimate="m"),
        Ticket(id="T-03", title="Paywall and entitlement gating", description="Gate unlimited_history on pro.",
               touches=["src/features/paywall/**"], depends_on=["T-01"], requirement_ids=["R-03"],
               acceptance=ac, sensitive=True, estimate="m"),
    ])


def full_project(project_dir):
    """Write every artifact stage 60 requires."""
    idea().save(project_dir)
    opportunity().save(project_dir)
    monetization().save(project_dir)
    prd().save(project_dir)
    design().save(project_dir)
    architecture().save(project_dir)
    backlog().save(project_dir)
    (project_dir / "research").mkdir(parents=True, exist_ok=True)
    (project_dir / "research" / "research.md").write_text("# Research\n")
    (project_dir / "product").mkdir(parents=True, exist_ok=True)
    (project_dir / "product" / "prd.md").write_text("# PRD\n")
    return project_dir
