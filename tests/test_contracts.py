"""The contracts must reject the shapes that would poison a later stage."""

from __future__ import annotations

import fixtures as fx
import pytest
from pydantic import ValidationError

from shipyard.contracts import (
    Backlog,
    DesignSpec,
    MonetizationPlan,
    Opportunity,
    PRD,
    Ticket,
    Verdict,
    parse_json_blob,
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


def test_design_links_must_resolve():
    data = fx.design().model_dump()
    data["primary_flow"] = ["split", "nonexistent"]
    with pytest.raises(ValidationError, match="unknown screen"):
        DesignSpec.model_validate(data)

    data = fx.design().model_dump()
    data["screens"][0]["navigates_to"] = ["ghost"]
    with pytest.raises(ValidationError, match="unknown screen"):
        DesignSpec.model_validate(data)


def test_design_tokens_must_be_hex():
    data = fx.design().model_dump()
    data["tokens"]["color_primary"] = "blue"
    with pytest.raises(ValidationError):
        DesignSpec.model_validate(data)


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
