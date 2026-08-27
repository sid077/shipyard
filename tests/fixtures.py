"""Valid artifacts, so pipeline tests exercise the real contracts."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: F401

from shipyard.contracts import (
    ADR,
    Architecture,
    AcceptanceCriterion,
    Backlog,
    ColorRoles,
    Competitor,
    ComponentSpec,
    CopyDeck,
    CopyEntry,
    Entity,
    Flow,
    Idea,
    Module,
    MonetizationPlan,
    Opportunity,
    PRD,
    PricePoint,
    Requirement,
    Risk,
    ScreenComposition,
    Shortlist,
    ScreenState,
    Section,
    SuccessMetric,
    Ticket,
    Transition,
    TypeStep,
    UISpec,
    UXScreen,
    UXSpec,
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


PALETTE = ColorRoles(
    primary="#1f6feb",
    on_primary="#ffffff",
    primary_pressed="#1a5fd0",
    background="#ffffff",
    surface="#f5f6f8",
    surface_raised="#ffffff",
    text="#111318",
    text_muted="#5b6472",
    border="#d8dbe0",
    danger="#c9231f",
    on_danger="#ffffff",
    success="#1a7f37",
)

TYPE_SCALE = [
    TypeStep(name="caption", size=13, line_height=18, weight="400"),
    TypeStep(name="body", size=16, line_height=24, weight="400"),
    TypeStep(name="body_strong", size=16, line_height=24, weight="600"),
    TypeStep(name="heading", size=20, line_height=26, weight="600"),
    TypeStep(name="title", size=28, line_height=34, weight="700"),
]


def ux() -> UXSpec:
    return UXSpec(
        navigation="tabs_with_stack",
        screens=[
            UXScreen(
                id="split",
                route="/(tabs)/index",
                title_copy_key="split.title",
                purpose="Enter a bill and split it.",
                states=[
                    ScreenState(name="default", trigger="on open", renders="amount field and party stepper"),
                    ScreenState(name="error", trigger="invalid amount", renders="inline error", copy_key="split.error"),
                ],
                navigates_to=["history"],
                gestures=["swipe down to dismiss the keyboard"],
            ),
            UXScreen(
                id="history",
                route="/(tabs)/history",
                title_copy_key="history.title",
                purpose="Review past splits.",
                states=[
                    ScreenState(name="default", trigger="has splits", renders="list of splits"),
                    ScreenState(name="empty", trigger="no splits yet", renders="empty state", copy_key="history.empty"),
                    ScreenState(name="loading", trigger="reading storage", renders="skeleton rows"),
                ],
                requires_entitlement="pro",
                navigates_to=["paywall"],
            ),
            UXScreen(
                id="paywall",
                route="/paywall",
                title_copy_key="paywall.title",
                purpose="Sell the lifetime unlock.",
                states=[
                    ScreenState(name="default", trigger="quota spent", renders="price and buy button"),
                    ScreenState(name="error", trigger="purchase failed", renders="inline error", copy_key="paywall.error"),
                ],
            ),
        ],
        flows=[Flow(name="first_split", steps=["split", "history"], success="a split is saved", failure="the amount is rejected")],
        primary_flow="first_split",
        transitions=[
            Transition(name="push", describes="screen to screen", duration_ms=280, easing="standard"),
            Transition(name="modal", describes="paywall entry", duration_ms=320, easing="emphasized"),
        ],
        loading_strategy="skeleton",
        offline_behaviour="Everything works offline; splits persist on device.",
        error_recovery="Errors are inline and retryable; nothing is lost on failure.",
        haptic_moments=["split saved", "purchase completed"],
    )


def ui() -> UISpec:
    return UISpec(
        app_name="Tip Splitter",
        tagline="Three taps. Correct every time.",
        icon_concept="A receipt torn cleanly into three equal strips.",
        tone_of_voice="Plain and quick.",
        colors=PALETTE,
        type_scale=list(TYPE_SCALE),
        spacing_unit=4,
        radii={"sm": 8, "md": 12, "lg": 20, "full": 999},
        elevation=[0, 1, 3],
        min_touch_target=44,
        components=[
            ComponentSpec(name="Button", purpose="Primary actions", variants=["primary", "secondary", "ghost"],
                          sizes=["md", "lg"], states=["default", "pressed", "disabled", "loading"],
                          anatomy=["label", "optional icon"]),
            ComponentSpec(name="Card", purpose="Group related content", variants=["flat", "raised"],
                          states=["default"], anatomy=["container", "optional header"]),
            ComponentSpec(name="ListRow", purpose="One split in history", variants=["default", "pressable"],
                          states=["default", "pressed"], anatomy=["title", "subtitle", "trailing"]),
            ComponentSpec(name="EmptyState", purpose="Nothing here yet", variants=["default"],
                          states=["default"], anatomy=["icon", "title", "body", "action"]),
            ComponentSpec(name="Skeleton", purpose="Loading placeholder", variants=["row", "block"],
                          states=["default"], anatomy=["shimmering block"]),
            ComponentSpec(name="Text", purpose="All typography", variants=list(s.name for s in TYPE_SCALE),
                          states=["default"], anatomy=["glyphs"]),
        ],
        screens=[
            ScreenComposition(screen_id="split", sections=[
                Section(component="Text", copy_key="split.title", notes="screen title"),
                Section(component="Card", notes="amount entry"),
                Section(component="Button", copy_key="split.cta"),
            ]),
            ScreenComposition(screen_id="history", sections=[
                Section(component="Text", copy_key="history.title"),
                Section(component="ListRow", notes="one row per split"),
                Section(component="EmptyState", copy_key="history.empty"),
                Section(component="Skeleton", notes="while reading storage"),
            ]),
            ScreenComposition(screen_id="paywall", sections=[
                Section(component="Text", copy_key="paywall.title"),
                Section(component="Card", notes="price and benefits"),
                Section(component="Button", copy_key="paywall.cta"),
            ]),
        ],
        mode="system",
    )


def copy_deck() -> CopyDeck:
    return CopyDeck(
        entries={
            "split.title": CopyEntry(text="Split", context="Screen title", max_chars=20),
            "split.cta": CopyEntry(text="Split the bill", context="Primary action", max_chars=24),
            "split.error": CopyEntry(text="Enter an amount above zero.", context="Invalid amount", max_chars=60),
            "history.title": CopyEntry(text="History", context="Screen title", max_chars=20),
            "history.empty": CopyEntry(text="No splits yet. Your first one lands here.", context="Empty history", max_chars=60),
            "paywall.title": CopyEntry(text="Go Pro", context="Paywall title", max_chars=20),
            "paywall.cta": CopyEntry(text="Unlock Pro", context="Purchase button", max_chars=24),
            "paywall.error": CopyEntry(text="That purchase did not complete.", context="Purchase failure", max_chars=60),
        }
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
    ux().save(project_dir)
    ui().save(project_dir)
    copy_deck().save(project_dir)
    architecture().save(project_dir)
    backlog().save(project_dir)
    (project_dir / "research").mkdir(parents=True, exist_ok=True)
    (project_dir / "research" / "research.md").write_text("# Research\n")
    (project_dir / "product").mkdir(parents=True, exist_ok=True)
    (project_dir / "product" / "prd.md").write_text("# PRD\n")
    return project_dir


def preview_html() -> str:
    """A stand-in for what `ui_designer` writes: self-contained and substantial
    enough to pass the stage checks."""
    spec = ui()
    deck = copy_deck()
    frames = "\n".join(
        f"""    <section class="frame">
      <h2>{screen.screen_id}</h2>
      {"".join(f'<div class="row">{deck.entries[s.copy_key].text if s.copy_key else s.component}</div>' for s in screen.sections)}
    </section>"""
        for screen in spec.screens
    )
    padding = "<!-- " + ("a self-contained preview page. " * 90) + " -->"
    return f"""<!doctype html>
<meta charset="utf-8">
<title>{spec.app_name} preview</title>
<style>
  body {{ background: {spec.colors.background}; color: {spec.colors.text};
         font-family: -apple-system, system-ui, sans-serif; display: flex; gap: 24px; padding: 32px; }}
  .frame {{ width: 390px; min-height: 844px; background: {spec.colors.surface};
            border: 1px solid {spec.colors.border}; border-radius: 32px; padding: 24px; }}
  .row {{ padding: 12px 0; border-bottom: 1px solid {spec.colors.border}; }}
  h2 {{ color: {spec.colors.primary}; font-size: 20px; }}
</style>
<body>
{frames}
</body>
{padding}
"""


def candidate(rank: int, name: str, verdict: str = "pursue") -> dict:
    return {
        "rank": rank,
        "name": name,
        "one_liner": f"{name} in one line.",
        "problem": "A real problem people already pay to avoid.",
        "target_user": "Tradespeople who quote on site.",
        "demand_evidence": "Top free incumbent has 500k installs and 4,100 reviews.",
        "why_now": "Platform vision APIs made on-device capture viable this year.",
        "wedge": "Works with no signal, which the incumbents do not.",
        "monetization": "One-time $4.99 unlock; comparable apps charge $2.99-$5.99.",
        "competitors": [
            {"name": "Incumbent A", "url": "https://example.com/a", "pricing": "Free with ads",
             "strengths": ["reach"], "weaknesses": ["needs signal"]},
            {"name": "Incumbent B", "url": "https://example.com/b", "pricing": "$3.99 once",
             "strengths": ["simple"], "weaknesses": ["no export"]},
        ],
        "fit_rationale": "Offline, no backend, small scope, one-time unlock.",
        "risks": [{"description": "Category is crowded", "severity": "medium", "mitigation": "Compete on offline"}],
        "effort_estimate_weeks": 4.0,
        "verdict": verdict,
        "sources": ["https://example.com/a", "https://example.com/b"],
    }


def shortlist(recommended: str = "Alpha") -> Shortlist:
    return Shortlist.model_validate(
        {
            "searched_for": "offline mobile utilities with a one-time unlock",
            "method": "store listings and third-party install trackers",
            "candidates": [
                candidate(1, "Alpha", "pursue"),
                candidate(2, "Beta", "watch"),
                candidate(3, "Gamma", "reject"),
            ],
            "recommended": recommended,
            "also_considered": ["Two-sided marketplaces - need liquidity the studio cannot seed"],
        }
    )
