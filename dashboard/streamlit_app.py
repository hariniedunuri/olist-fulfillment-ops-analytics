"""
Operational dashboard for the Order Fulfillment & Delivery Performance platform.
Every panel answers a specific business question (see README) -- no filler charts.

Run with: streamlit run dashboard/streamlit_app.py
"""
import os
import sys
import pandas as pd
import plotly.express as px
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

st.set_page_config(page_title="Fulfillment Ops Analytics", layout="wide")


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

st.title("Order Fulfillment & Delivery Performance — Operations Dashboard")
st.caption("Olist Brazilian E-Commerce dataset (2016-2018) | Built for Daxwell Data Analyst submission")

# --- KPI header row ---
latest = monthly.iloc[-2] if len(monthly) > 1 else monthly.iloc[-1]  # skip partial last month if present
prior = monthly.iloc[-3] if len(monthly) > 2 else latest
delta_on_time = round((latest["on_time_pct"] or 0) - (prior["on_time_pct"] or 0), 1)
dq_pass_rate = round(100 * dq["passed"].mean(), 1) if len(dq) else None

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("On-time delivery rate", f"{latest['on_time_pct']}%", f"{delta_on_time} pts vs prior month")
c2.metric("Avg delay (days)", f"{latest['avg_delay_days']}")
c3.metric("Orders (latest full month)", f"{int(latest['total_orders']):,}")
c4.metric("Avg review score", f"{latest['avg_review_score']}")
c5.metric("Data-quality pass rate", f"{dq_pass_rate}%" if dq_pass_rate is not None else "n/a")

st.divider()

# --- Trend chart ---
st.subheader("On-time delivery rate trend")
fig = px.line(monthly, x="year_month", y="on_time_pct", markers=True,
              labels={"year_month": "Month", "on_time_pct": "On-time %"})
st.plotly_chart(fig, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Worst-performing sellers (min 5 orders)")
    st.dataframe(
        scorecard.sort_values("on_time_pct").head(15)[
            ["seller_id", "seller_state", "order_count", "on_time_pct", "avg_delay_days", "avg_review_score"]
        ],
        use_container_width=True, hide_index=True,
    )

with col_b:
    st.subheader("Delivery performance by customer state (min 20 orders)")
    fig2 = px.bar(state_perf.sort_values("on_time_pct").head(15),
                  x="on_time_pct", y="customer_state", orientation="h",
                  labels={"on_time_pct": "On-time %", "customer_state": "State"})
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# --- Anomaly + AI agent panel ---
st.subheader("Anomaly panel — statistically anomalous sellers & AI-drafted root cause")
st.caption(
    "Sellers flagged via z-score vs. the seller population (|z| >= 1.5, min 10 orders). "
    "Root-cause narratives are drafted by the rules-based Ops Insight Agent (see agent/ops_insight_agent.py) "
    "and pass a groundedness check before being shown -- every number below traces back to a SQL query result."
)

top_flagged = anomalies[anomalies["is_anomalous"]].head(5)
if st.button("Run Ops Insight Agent on top 5 flagged sellers"):
    findings = run_agent_on_flagged_sellers(top_n=5)
    for f in findings:
        with st.expander(f"Seller {f.seller_id}  |  z={f.z_score}  |  grounded={f.grounded}"):
            st.write(f"**Narrative:** {f.narrative}")
            st.write(f"**Recommendation:** {f.recommendation}")
            st.caption(f"Groundedness check: {f.grounding_notes}")
else:
    st.dataframe(top_flagged, use_container_width=True, hide_index=True)

st.divider()

# --- Forecast panel ---
st.subheader("Order volume forecast (next 3 months) — capacity planning input")
history, forecast = forecast_next_n_months(3)
hist_df = history.reset_index()
hist_df.columns = ["month", "order_count"]
hist_df["type"] = "actual"
fcst_df = forecast.rename(columns={"forecasted_order_count": "order_count", "year_month": "month"})
fcst_df["type"] = "forecast"
combined = pd.concat([hist_df, fcst_df], ignore_index=True)
fig3 = px.line(combined, x="month", y="order_count", color="type", markers=True)
st.plotly_chart(fig3, use_container_width=True)

st.divider()

# --- Data health panel ---
st.subheader("Data-quality health")
st.dataframe(dq[["check_name", "category", "passed", "detail"]], use_container_width=True, hide_index=True)
