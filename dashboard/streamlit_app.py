"""
Operational dashboard for the Order Fulfillment & Delivery Performance platform.
Every panel answers a specific business question (see README) -- no filler charts.

Run with: streamlit run dashboard/streamlit_app.py
"""
import os
import sys
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sql"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from db import get_conn  # noqa: E402
from run_analytics import run_query_file  # noqa: E402
from delay_analysis import load_fact_orders, seller_zscore_anomalies  # noqa: E402
from forecast import forecast_next_n_months  # noqa: E402
from ops_insight_agent import run_agent_on_flagged_sellers  # noqa: E402

ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "..", "sql", "analytics")
ACCENT = "#2563EB"
GOOD = "#16A34A"
WARN = "#DC2626"

st.set_page_config(page_title="Fulfillment Ops Analytics", layout="wide")

# ---------------------------------------------------------------------------
# Light styling polish -- card look for containers, tighter spacing, no
# default Streamlit chrome. Kept minimal on purpose: readable > decorated.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1200px; }
    [data-testid="stMetric"] {
        background: #F4F6F9; border: 1px solid #E5E7EB; border-radius: 10px;
        padding: 14px 16px 10px 16px;
    }
    [data-testid="stMetricLabel"] { font-size: 0.82rem; color: #4B5563; }
    .section-note {
        background: #F4F6F9; border-left: 3px solid #2563EB; border-radius: 4px;
        padding: 10px 14px; margin-bottom: 14px; font-size: 0.92rem; color: #374151;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600)
def load_all():
    conn = get_conn()
    monthly = run_query_file(conn, os.path.join(ANALYTICS_DIR, "01_monthly_kpis.sql"))
    scorecard = run_query_file(conn, os.path.join(ANALYTICS_DIR, "02_seller_scorecard.sql"))
    state_perf = run_query_file(conn, os.path.join(ANALYTICS_DIR, "03_state_performance.sql"))
    dq = pd.read_sql("SELECT * FROM data_quality_results ORDER BY run_ts DESC", conn)
    conn.close()
    fact = load_fact_orders()
    anomalies = seller_zscore_anomalies(fact)
    return monthly, scorecard, state_perf, dq, fact, anomalies


monthly, scorecard, state_perf, dq, fact, anomalies = load_all()

# Skip a partial/truncated trailing month if present (documented data-quality decision)
monthly_full = monthly[monthly["total_orders"] >= 100].reset_index(drop=True)
latest = monthly_full.iloc[-1]
prior = monthly_full.iloc[-2] if len(monthly_full) > 1 else latest
delta_on_time = round((latest["on_time_pct"] or 0) - (prior["on_time_pct"] or 0), 1)
dq_pass_rate = round(100 * dq["passed"].mean(), 1) if len(dq) else None
dq_fail_count = int((dq["passed"] == 0).sum()) if len(dq) else 0

# ---------------------------------------------------------------------------
# Sidebar -- project context, meant to orient a viewer in 10 seconds
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Fulfillment Ops Analytics")
    st.caption("Operations dashboard for e-commerce order delivery performance")
    st.markdown("---")
    st.markdown("**Data source**")
    st.write("Olist Brazilian E-Commerce, 99,441 real orders, 2016 to 2018")
    st.markdown("**Refreshed**")
    st.write(datetime.now().strftime("%b %d, %Y %I:%M %p"))
    st.markdown("**How to read this**")
    st.write(
        "Start with Overview for the headline numbers, then Sellers and "
        "Geography to see where risk is concentrated, then Anomalies to see "
        "the AI-assisted root-cause tool in action."
    )
    st.markdown("---")
    st.caption("Built end-to-end: SQL + Python ETL, data-quality validation, "
               "statistical anomaly detection, a rules-based AI agent, and this dashboard.")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Order Fulfillment & Delivery Performance")
st.caption("Operations dashboard | Olist Brazilian E-Commerce dataset (2016-2018)")

tab_overview, tab_sellers, tab_geo, tab_anomaly, tab_forecast, tab_quality = st.tabs(
    ["Overview", "Seller Performance", "Geography", "Anomalies & AI Agent", "Forecast", "Data Quality"]
)

# ---------------------------------------------------------------------------
# TAB: Overview
# ---------------------------------------------------------------------------
with tab_overview:
    st.markdown(
        '<div class="section-note">These five numbers are what an operations lead would '
        'check first each morning: are we hitting delivery promises, and can we trust the data '
        'behind that answer.</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("On-time delivery rate", f"{latest['on_time_pct']}%", f"{delta_on_time:+.1f} pts vs prior month")
    c2.metric("Avg delay (days)", f"{latest['avg_delay_days']:.1f}")
    c3.metric("Orders (latest month)", f"{int(latest['total_orders']):,}")
    c4.metric("Avg review score", f"{latest['avg_review_score']:.2f} / 5")
    c5.metric(
        "Data-quality pass rate",
        f"{dq_pass_rate}%" if dq_pass_rate is not None else "n/a",
        (f"{dq_fail_count} flagged" if dq_fail_count else "all clear"),
        delta_color="inverse" if dq_fail_count else "normal",
    )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.subheader("On-time delivery rate trend")
    st.caption("Is performance improving or slipping month to month, not just where it stands today.")
    fig = px.line(
        monthly_full, x="year_month", y="on_time_pct", markers=True,
        labels={"year_month": "Month", "on_time_pct": "On-time %"},
    )
    fig.update_traces(line_color=ACCENT, line_width=3, marker_size=7)
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=360, yaxis_ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB: Seller Performance
# ---------------------------------------------------------------------------
with tab_sellers:
    st.subheader("Worst-performing sellers")
    st.markdown(
        '<div class="section-note">Ranked by on-time delivery rate, limited to sellers with '
        'at least 5 orders so one unlucky order does not distort the ranking. This is where an '
        'ops team should look first: a small group of sellers, not the whole marketplace.</div>',
        unsafe_allow_html=True,
    )
    worst = scorecard.sort_values("on_time_pct").head(15)[
        ["seller_id", "seller_state", "order_count", "on_time_pct", "avg_delay_days", "avg_review_score"]
    ].rename(columns={
        "seller_id": "Seller ID", "seller_state": "State", "order_count": "Orders",
        "on_time_pct": "On-time %", "avg_delay_days": "Avg delay (days)", "avg_review_score": "Avg review",
    })
    st.dataframe(worst, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# TAB: Geography
# ---------------------------------------------------------------------------
with tab_geo:
    st.subheader("Delivery performance by customer state")
    st.markdown(
        '<div class="section-note">Limited to states with at least 20 orders. If underperformance '
        'clusters by geography rather than by seller, the fix is different: carrier coverage or '
        'realistic delivery-date estimates for that region, not a seller performance conversation.</div>',
        unsafe_allow_html=True,
    )
    fig2 = px.bar(
        state_perf.sort_values("on_time_pct").head(15),
        x="on_time_pct", y="customer_state", orientation="h",
        labels={"on_time_pct": "On-time %", "customer_state": "State"},
        color="on_time_pct", color_continuous_scale=["#DC2626", "#F59E0B", "#16A34A"],
    )
    fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=460,
                        coloraxis_showscale=False, xaxis_ticksuffix="%")
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB: Anomalies & AI Agent
# ---------------------------------------------------------------------------
with tab_anomaly:
    st.subheader("Statistically anomalous sellers")
    st.markdown(
        '<div class="section-note">Sellers flagged by z-score against the seller population '
        '(minimum 10 orders). The Ops Insight Agent below investigates each flagged seller and '
        'drafts a root-cause summary and recommendation. Every number it states is checked against '
        'the underlying SQL data before being shown, so it cannot state a figure that was not '
        'actually retrieved.</div>',
        unsafe_allow_html=True,
    )

    top_flagged = anomalies[anomalies["is_anomalous"]].head(5)
    st.write(f"**{len(anomalies)}** sellers evaluated | **{int(anomalies['is_anomalous'].sum())}** flagged anomalous")

    run_clicked = st.button("Run Ops Insight Agent on top 5 flagged sellers", type="primary")
    if run_clicked:
        with st.spinner("Retrieving supporting data, classifying root cause, drafting and validating..."):
            findings = run_agent_on_flagged_sellers(top_n=5)
        for f in findings:
            status = "Grounded" if f.grounded else "Flagged, not shown"
            with st.expander(f"Seller {f.seller_id}  |  z-score {f.z_score}  |  {status}"):
                st.write(f"**Root-cause narrative:** {f.narrative}")
                st.write(f"**Recommendation:** {f.recommendation}")
                st.caption(f"Groundedness check: {f.grounding_notes}")
    else:
        st.dataframe(
            top_flagged.rename(columns={
                "seller_id": "Seller ID", "order_count": "Orders", "avg_delay": "Avg delay (days)",
                "avg_review": "Avg review", "z_score": "Z-score", "is_anomalous": "Flagged",
            }),
            use_container_width=True, hide_index=True,
        )

# ---------------------------------------------------------------------------
# TAB: Forecast
# ---------------------------------------------------------------------------
with tab_forecast:
    st.subheader("Order volume forecast, next 3 months")
    st.markdown(
        '<div class="section-note">A capacity-planning input: do we need to staff up or add '
        'seller capacity ahead of demand. Forecast uses a stabilized 2017-01 through 2018-08 window '
        '(launch ramp-up and truncated trailing months excluded, documented in analysis/forecast.py).</div>',
        unsafe_allow_html=True,
    )
    history, forecast = forecast_next_n_months(3)
    hist_df = history.reset_index()
    hist_df.columns = ["month", "order_count"]
    fcst_df = forecast.rename(columns={"forecasted_order_count": "order_count", "year_month": "month"})

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=hist_df["month"], y=hist_df["order_count"], mode="lines+markers",
                               name="Actual", line=dict(color=ACCENT, width=3)))
    fig3.add_trace(go.Scatter(x=fcst_df["month"], y=fcst_df["order_count"], mode="lines+markers",
                               name="Forecast", line=dict(color=WARN, width=3, dash="dash")))
    fig3.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=380,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    st.plotly_chart(fig3, use_container_width=True)

    st.write("**Forecast detail**")
    st.dataframe(
        fcst_df.rename(columns={"month": "Month", "order_count": "Forecasted orders"}),
        use_container_width=True, hide_index=True,
    )

# ---------------------------------------------------------------------------
# TAB: Data Quality
# ---------------------------------------------------------------------------
with tab_quality:
    st.subheader("Data-quality health")
    st.markdown(
        '<div class="section-note">Before trusting any number on the tabs above, we validate the '
        'data feeding them: null checks, duplicate checks, referential integrity, range checks, and '
        'business-rule checks, run against both the raw source data and the modeled star schema.</div>',
        unsafe_allow_html=True,
    )
    n_pass = int((dq["passed"] == 1).sum())
    n_fail = int((dq["passed"] == 0).sum())
    q1, q2, q3 = st.columns(3)
    q1.metric("Checks passed", n_pass)
    q2.metric("Checks flagged", n_fail)
    q3.metric("Pass rate", f"{dq_pass_rate}%" if dq_pass_rate is not None else "n/a")

    display_dq = dq[["check_name", "category", "passed", "detail"]].rename(columns={
        "check_name": "Check", "category": "Category", "passed": "Passed", "detail": "Detail",
    })
    display_dq["Passed"] = display_dq["Passed"].map({1: "Yes", 0: "Flagged"})
    st.dataframe(display_dq, use_container_width=True, hide_index=True)
