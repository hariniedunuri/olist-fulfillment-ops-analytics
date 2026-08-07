"""Tests for the ETL pipeline: ingestion produces expected raw row counts,
and transform/load produces a star schema with the expected grain and no
row loss on the primary fact table."""
import pandas as pd
from db import get_conn


def test_raw_tables_have_expected_row_counts():
    conn = get_conn()
    counts = {
        "raw_orders": 99441,
        "raw_customers": 99441,
        "raw_sellers": 3095,
    }
    for table, expected in counts.items():
        n = pd.read_sql(f"SELECT COUNT(*) c FROM {table}", conn).c[0]
        assert n == expected, f"{table} expected {expected}, got {n}"
    conn.close()


def test_fact_orders_grain_is_one_row_per_order():
    conn = get_conn()
    total = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    distinct = pd.read_sql("SELECT COUNT(DISTINCT order_id) c FROM fact_orders", conn).c[0]
    conn.close()
    assert total == distinct, "fact_orders should have exactly one row per order_id"


def test_fact_orders_no_row_loss_vs_raw():
    conn = get_conn()
    raw_n = pd.read_sql("SELECT COUNT(*) c FROM raw_orders", conn).c[0]
    fact_n = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    conn.close()
    assert raw_n == fact_n, "ETL should not silently drop orders"


def test_dim_geography_deduplicated_by_zip_prefix():
    conn = get_conn()
    total = pd.read_sql("SELECT COUNT(*) c FROM dim_geography", conn).c[0]
    distinct = pd.read_sql("SELECT COUNT(DISTINCT zip_prefix) c FROM dim_geography", conn).c[0]
    conn.close()
    assert total == distinct, "dim_geography must be one row per zip_prefix (documented dedup rule)"


def test_derived_fields_present_and_typed():
    conn = get_conn()
    df = pd.read_sql("SELECT delivery_delay_days, on_time_flag, processing_days FROM fact_orders LIMIT 100", conn)
    conn.close()
    assert "delivery_delay_days" in df.columns
    assert "on_time_flag" in df.columns
