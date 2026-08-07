"""Tests that the SQL analytics layer produces sane, bounded output."""
import os
from db import get_conn
from run_analytics import run_query_file, get_root_cause

ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "..", "sql", "analytics")


def test_monthly_kpis_on_time_pct_is_valid_percentage():
    conn = get_conn()
    df = run_query_file(conn, os.path.join(ANALYTICS_DIR, "01_monthly_kpis.sql"))
    conn.close()
    valid = df["on_time_pct"].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_seller_scorecard_respects_min_order_filter():
    conn = get_conn()
    df = run_query_file(conn, os.path.join(ANALYTICS_DIR, "02_seller_scorecard.sql"))
    conn.close()
    assert (df["order_count"] >= 5).all(), "scorecard should exclude sellers below the min-order threshold"


def test_state_performance_ranking_is_ascending_on_time_pct():
    conn = get_conn()
    df = run_query_file(conn, os.path.join(ANALYTICS_DIR, "03_state_performance.sql"))
    conn.close()
    vals = df["on_time_pct"].dropna().tolist()
    assert vals == sorted(vals), "state performance should be sorted worst-first"


def test_root_cause_query_returns_data_for_a_real_seller():
    conn = get_conn()
    seller_id = conn.execute(
        "SELECT seller_id FROM fact_orders WHERE n_sellers = 1 GROUP BY seller_id "
        "HAVING COUNT(*) >= 5 LIMIT 1"
    ).fetchone()[0]
    df = get_root_cause(seller_id, conn=conn)
    conn.close()
    assert len(df) == 1
    assert df.iloc[0]["order_count"] >= 5
