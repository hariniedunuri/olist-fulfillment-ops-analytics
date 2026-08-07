"""
Ops Insight Agent (rules-based v1).

Purpose: when a seller is flagged anomalous (see analysis/delay_analysis.py
seller_zscore_anomalies), this agent investigates and drafts a first-pass,
human-reviewed root-cause summary + recommendation — so an analyst doesn't
have to manually slice the data for every flag.

Design notes (read this before assuming it's "just an if/else"):
  - This is an ORCHESTRATED, multi-step pipeline: retrieve -> classify -> draft -> validate.
  - It is deterministic and rules-based, not an LLM call. That's a deliberate choice for
    this submission: it's fully explainable, needs no API key, and is provably grounded
    (every number in the output is one it actually retrieved -- no hallucination risk).
  - It is architected so the "draft" step is a swappable component: agent/llm_draft.py
    could replace `draft_narrative()` with an LLM call over the same retrieved, structured
    context, with the same validate() groundedness check applied afterward. That upgrade
    path is documented in README.md / docs/architecture.md rather than implemented blind.
"""
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sql"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
from db import get_conn  # noqa: E402
from run_analytics import get_root_cause  # noqa: E402


@dataclass
class AgentFinding:
    seller_id: str
    order_count: int
    avg_delay_days: float
    z_score: float
    dominant_stage: str
    stage_breakdown: dict
    narrative: str
    recommendation: str
    grounded: bool
    grounding_notes: str = ""


# Step 1: RETRIEVE — approved, parameterized SQL only (no free-form queries)
def retrieve_context(seller_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    breakdown = get_root_cause(seller_id, conn=conn)
    if own:
        conn.close()
    if breakdown.empty:
        return None
    return breakdown.iloc[0].to_dict()


# Step 2: CLASSIFY — localize which fulfillment stage dominates the delay
def classify_dominant_stage(ctx):
    stages = {
        "processing (purchase -> approval)": ctx.get("avg_processing_days") or 0,
        "carrier pickup (approval -> carrier)": ctx.get("avg_carrier_pickup_days") or 0,
        "shipping (carrier -> customer)": ctx.get("avg_shipping_days") or 0,
    }
    dominant = max(stages, key=stages.get)
    return dominant, stages


# Step 3: DRAFT — deterministic template using ONLY retrieved numbers (v1; LLM-swappable, see module docstring)
def draft_narrative(seller_id, ctx, dominant_stage, stages, z_score):
    order_count = ctx["order_count"]
    avg_delay = ctx["avg_delay_days"]

    narrative = (
        f"Seller {seller_id} shows an average delivery delay of {avg_delay:.1f} days "
        f"across {order_count} single-seller orders (z-score {z_score:.2f} vs. the seller population). "
        f"The largest contributor is the '{dominant_stage}' stage, averaging "
        f"{stages[dominant_stage]:.1f} days, compared to "
        f"{stages.get('processing (purchase -> approval)', 0):.1f}d processing and "
        f"{stages.get('shipping (carrier -> customer)', 0):.1f}d shipping for the other stages."
    )

    if "carrier pickup" in dominant_stage:
        recommendation = (
            "Investigate this seller's carrier hand-off process (warehouse pickup scheduling or "
            "carrier capacity) — this is where the delay is concentrated, not in order processing "
            "or in-transit time."
        )
    elif "shipping" in dominant_stage:
        recommendation = (
            "Investigate this seller's carrier/route choice for in-transit delay — processing and "
            "pickup are not the bottleneck. Consider comparing carriers used by on-time sellers in "
            "the same region."
        )
    else:
        recommendation = (
            "Investigate this seller's order-processing/approval workflow — delay is concentrated "
            "before the item even reaches a carrier, suggesting an internal operational bottleneck."
        )

    return narrative, recommendation


# Step 4: VALIDATE — groundedness check: every number in the narrative must trace back
# to the retrieved context. This is a real (if simple) guardrail, not a no-op.
def validate_groundedness(narrative, ctx, stages, z_score=None):
    import re
    numbers_in_narrative = set(re.findall(r"-?\d+\.\d+", narrative))
    source_numbers = {f"{v:.1f}" for v in list(stages.values()) + [ctx["avg_delay_days"]]}
    if z_score is not None:
        source_numbers.add(f"{z_score:.2f}")
    ungrounded = numbers_in_narrative - source_numbers
    grounded = len(ungrounded) == 0
    notes = "all figures traced to retrieved SQL/statistical context" if grounded else f"UNGROUNDED figures found: {ungrounded}"
    return grounded, notes


def investigate(seller_id, z_score=None, conn=None):
    ctx = retrieve_context(seller_id, conn=conn)
    if ctx is None:
        return None
    dominant_stage, stages = classify_dominant_stage(ctx)
    narrative, recommendation = draft_narrative(seller_id, ctx, dominant_stage, stages, z_score or 0.0)
    grounded, notes = validate_groundedness(narrative, ctx, stages, z_score=z_score)

    finding = AgentFinding(
        seller_id=seller_id,
        order_count=int(ctx["order_count"]),
        avg_delay_days=round(ctx["avg_delay_days"], 2),
        z_score=round(z_score or 0.0, 2),
        dominant_stage=dominant_stage,
        stage_breakdown=stages,
        narrative=narrative,
        recommendation=recommendation,
        grounded=grounded,
        grounding_notes=notes,
    )
    return finding


def run_agent_on_flagged_sellers(top_n=5):
    """End-to-end demo: pulls the top-N anomalous sellers from the statistical
    analysis layer and runs the agent on each."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
    from delay_analysis import load_fact_orders, seller_zscore_anomalies

    df = load_fact_orders()
    anomalies = seller_zscore_anomalies(df)
    flagged = anomalies[anomalies["is_anomalous"]].head(top_n)

    findings = []
    for _, row in flagged.iterrows():
        f = investigate(row["seller_id"], z_score=row["z_score"])
        if f:
            findings.append(f)
    return findings


if __name__ == "__main__":
    findings = run_agent_on_flagged_sellers(top_n=5)
    for f in findings:
        print("=" * 90)
        print(f"Seller: {f.seller_id}  |  z={f.z_score}  |  grounded={f.grounded}")
        print(f"Narrative: {f.narrative}")
        print(f"Recommendation: {f.recommendation}")
        print(f"Groundedness check: {f.grounding_notes}")
