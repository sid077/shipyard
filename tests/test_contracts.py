"""The contracts must reject the shapes that would poison a later stage."""

from __future__ import annotations

import fixtures as fx
import pytest
from pydantic import ValidationError

from shipyard.contracts import (
    Backlog,
    ColorRoles,
    CopyDeck,
    CopyEntry,
    MonetizationPlan,
    Opportunity,
    PRD,
    Ticket,
    UISpec,
    UXSpec,
    Verdict,
    parse_json_blob,
    validate_design_bundle,
)


def test_opportunity_demands_real_research_depth():
    data = fx.opportunity().model_dump()
    data["competitors"] = data["competitors"][:2]
    with pytest.raises(ValidationError, match="too_short"):
        Opportunity.model_validate(data)

    data = fx.opportunity().model_dump()
    data["sources"] = ["https://only-one.example"]
    with pytest.raises(ValidationError):
        Opportunity.model_validate(data)


def test_free_tier_limits_must_reference_a_real_feature_key():
    data = fx.monetization().model_dump()
    data["free_tier_limits"] = {"a_key_nobody_defined": 3}
    with pytest.raises(ValidationError, match="unknown feature keys"):
        MonetizationPlan.model_validate(data)


def test_prd_requires_a_p0_and_unique_ids():
    data = fx.prd().model_dump()
    for req in data["requirements"]:
        req["priority"] = "p1"
    with pytest.raises(ValidationError, match="priority p0"):
        PRD.model_validate(data)

    data = fx.prd().model_dump()
    data["requirements"][1]["id"] = data["requirements"][0]["id"]
    with pytest.raises(ValidationError, match="duplicate requirement ids"):
        PRD.model_validate(data)


def test_ux_references_must_resolve():
    data = fx.ux().model_dump()
    data["primary_flow"] = "a_flow_that_does_not_exist"
    with pytest.raises(ValidationError, match="primary_flow"):
        UXSpec.model_validate(data)

    data = fx.ux().model_dump()
    data["flows"][0]["steps"] = ["split", "ghost"]
    with pytest.raises(ValidationError, match="unknown screen"):
        UXSpec.model_validate(data)

    data = fx.ux().model_dump()
    data["screens"][0]["navigates_to"] = ["ghost"]
    with pytest.raises(ValidationError, match="unknown screen"):
        UXSpec.model_validate(data)


def test_every_screen_must_declare_a_default_state():
    data = fx.ux().model_dump()
    data["screens"][0]["states"] = [
        {"name": "error", "trigger": "t", "renders": "r", "copy_key": None}
    ]
    with pytest.raises(ValidationError, match="default"):
        UXSpec.model_validate(data)


def test_a_palette_that_fails_contrast_is_rejected():
    """The centrepiece gate: bad colour choices fail before code is written."""
    good = fx.PALETTE.model_dump()

    # Muted text is still text - it gets no discount.
    with pytest.raises(ValidationError, match="muted text on background"):
        ColorRoles.model_validate({**good, "text_muted": "#a8b0bb"})

    # A pale primary cannot carry a white label.
    with pytest.raises(ValidationError, match="button label on primary"):
        ColorRoles.model_validate({**good, "primary": "#9ecbff"})

    # The pressed state is checked too, not just the resting one.
    with pytest.raises(ValidationError, match="pressed primary"):
        ColorRoles.model_validate({**good, "primary_pressed": "#cfe4ff"})

    # A border nobody can see is not a border.
    with pytest.raises(ValidationError, match="invisible"):
        ColorRoles.model_validate({**good, "border": good["surface"]})


def test_the_error_names_the_ratio_it_achieved_so_a_role_can_act_on_it():
    with pytest.raises(ValidationError) as caught:
        ColorRoles.model_validate({**fx.PALETTE.model_dump(), "text": "#9aa0a6"})
    message = str(caught.value)
    assert ":1" in message and "needs at least 4.5:1" in message


def test_type_scale_must_be_a_usable_ramp():
    data = fx.ui().model_dump()
    data["type_scale"] = list(reversed(data["type_scale"]))
    with pytest.raises(ValidationError, match="smallest to largest"):
        UISpec.model_validate(data)

    # Shrink the two smallest rungs together so the ramp stays ordered and the
    # only thing wrong is that body is now fine print.
    data = fx.ui().model_dump()
    next(s for s in data["type_scale"] if s["name"] == "caption")["size"] = 11
    body = next(s for s in data["type_scale"] if s["name"] == "body")
    body["size"] = 12
    body["line_height"] = 18
    with pytest.raises(ValidationError, match="at least 15pt"):
        UISpec.model_validate(data)

    # One size at two weights is a real rung, not a duplicate.
    assert UISpec.model_validate(fx.ui().model_dump())


def test_cramped_line_height_is_rejected():
    data = fx.ui().model_dump()
    next(s for s in data["type_scale"] if s["name"] == "body")["line_height"] = 17
    with pytest.raises(ValidationError, match="legible"):
        UISpec.model_validate(data)


def test_touch_targets_below_the_platform_minimum_are_rejected():
    data = fx.ui().model_dump()
    data["min_touch_target"] = 32
    with pytest.raises(ValidationError):
        UISpec.model_validate(data)


def test_a_screen_cannot_compose_a_component_that_does_not_exist():
    data = fx.ui().model_dump()
    data["screens"][0]["sections"][0]["component"] = "Carousel"
    with pytest.raises(ValidationError, match="not in the inventory"):
        UISpec.model_validate(data)


def test_placeholder_copy_is_rejected():
    entries = {k: v.model_dump() for k, v in fx.copy_deck().entries.items()}
    for placeholder in ("[CTA]", "TODO: write this", "Lorem ipsum dolor sit"):
        bad = {**entries, "split.cta": {"text": placeholder, "context": "c", "max_chars": 40}}
        with pytest.raises(ValidationError, match="placeholders"):
            CopyDeck.model_validate({"entries": bad})


def test_copy_that_overflows_its_own_ceiling_is_rejected():
    with pytest.raises(ValidationError, match="max_chars"):
        CopyEntry(text="A label far too long for this button", context="c", max_chars=12)


def test_the_design_bundle_cross_checks_its_seams(tmp_path):
    fx.ux().save(tmp_path)
    fx.ui().save(tmp_path)
    fx.copy_deck().save(tmp_path)
    assert validate_design_bundle(tmp_path) == []

    # A copy key referenced by the UI but never written.
    ui = fx.ui().model_dump()
    ui["screens"][0]["sections"][0]["copy_key"] = "split.subtitle"
    UISpec.model_validate(ui).save(tmp_path)
    assert any("split.subtitle" in p for p in validate_design_bundle(tmp_path))

    # A screen composed but never specified.
    fx.ux().save(tmp_path)
    ui = fx.ui().model_dump()
    ui["screens"].append(
        {"screen_id": "settings", "sections": [{"component": "Card", "copy_key": None, "notes": "prefs"}]}
    )
    UISpec.model_validate(ui).save(tmp_path)
    problems = validate_design_bundle(tmp_path)
    assert any("settings" in p and "does not specify" in p for p in problems)


def test_backlog_rejects_dependency_cycles_and_dangling_deps():
    data = fx.backlog().model_dump()
    data["tickets"][0]["depends_on"] = ["T-02"]  # T-02 already depends on T-01
    with pytest.raises(ValidationError, match="cycle"):
        Backlog.model_validate(data)

    data = fx.backlog().model_dump()
    data["tickets"][0]["depends_on"] = ["T-99"]
    with pytest.raises(ValidationError, match="unknown"):
        Backlog.model_validate(data)


def test_backlog_ready_respects_dependencies():
    backlog = fx.backlog()
    assert [t.id for t in backlog.ready(done=set())] == ["T-01"]
    assert [t.id for t in backlog.ready(done={"T-01"})] == ["T-02", "T-03"]
    assert backlog.ready(done={"T-01", "T-02", "T-03"}) == []


def test_extra_fields_are_rejected_so_hallucinated_keys_surface():
    data = fx.monetization().model_dump()
    data["projected_mrr"] = 1000
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MonetizationPlan.model_validate(data)


def test_artifacts_round_trip_through_disk(tmp_path):
    fx.backlog().save(tmp_path)
    assert Backlog.exists(tmp_path)
    assert len(Backlog.load(tmp_path).tickets) == 3


def test_verdict_feedback_leads_with_blocking_items():
    verdict = Verdict.model_validate(
        {
            "verdict": "fail",
            "summary": "pricing is unsourced",
            "findings": [
                {"severity": "advisory", "where": "a", "problem": "nit", "fix": "tidy"},
                {"severity": "blocking", "where": "b", "problem": "no source", "fix": "cite it"},
            ],
        }
    )
    text = verdict.as_feedback()
    assert text.index("Blocking issues") < text.index("Advisory")
    assert "cite it" in text
    assert len(verdict.blocking) == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"verdict": "pass"}',
        '```json\n{"verdict": "pass"}\n```',
        '```\n{"verdict": "pass"}\n```',
        'Here is my answer:\n{"verdict": "pass"}\nHope that helps.',
    ],
)
def test_parse_json_blob_survives_the_usual_wrappers(raw):
    assert parse_json_blob(raw) == {"verdict": "pass"}


def test_parse_json_blob_rejects_prose():
    with pytest.raises(ValueError):
        parse_json_blob("I was unable to decide.")


def test_ticket_id_format_is_enforced():
    with pytest.raises(ValidationError):
        Ticket(id="ticket-one", title="t", description="d", touches=["a"],
               requirement_ids=["R-01"],
               acceptance=[{"id": "AC-1", "statement": "s", "verified_by": "unit"}])
