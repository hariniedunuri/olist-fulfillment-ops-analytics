"""Tests for the Ops Insight Agent. Checks retrieval returns real data, full
runs come back grounded, and the groundedness check actually rejects a made-up
number when I feed it one directly (wanted to be sure it's not just a no-op)."""
from ops_insight_agent import (
    retrieve_context, classify_dominant_stage, draft_narrative,
    validate_groundedness, investigate, run_agent_on_flagged_sellers,
)
from db import get_conn


def _sample_seller():
    conn = get_conn()
    seller_id = conn.execute(
        "SELECT seller_id FROM fact_orders WHERE n_sellers = 1 GROUP BY seller_id "
        "HAVING COUNT(*) >= 5 LIMIT 1"
    ).fetchone()[0]
    conn.close()
    return seller_id


def test_retrieve_context_returns_real_data():
    ctx = retrieve_context(_sample_seller())
    assert ctx is not None
    assert ctx["order_count"] >= 5


def test_classify_dominant_stage_picks_the_max():
    ctx = {"avg_processing_days": 1.0, "avg_carrier_pickup_days": 5.0, "avg_shipping_days": 2.0}
    dominant, stages = classify_dominant_stage(ctx)
    assert "carrier pickup" in dominant


def test_full_investigation_is_grounded():
    seller_id = _sample_seller()
    finding = investigate(seller_id, z_score=2.0)
    assert finding is not None
    assert finding.grounded is True, finding.grounding_notes


def test_groundedness_validator_catches_fabricated_numbers():
    ctx = {"avg_delay_days": 3.0}
    stages = {"processing (purchase -> approval)": 1.0, "shipping (carrier -> customer)": 2.0}
    fabricated_narrative = "This seller has a delay of 99.9 days, which is very unusual."
    grounded, notes = validate_groundedness(fabricated_narrative, ctx, stages, z_score=1.5)
    assert grounded is False, "validator must catch a number that never appeared in retrieved data"


def test_agent_runs_end_to_end_on_flagged_sellers():
    findings = run_agent_on_flagged_sellers(top_n=3)
    assert len(findings) > 0
    assert all(f.grounded for f in findings)
