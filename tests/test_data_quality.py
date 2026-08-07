"""Tests for the data-quality framework itself: checks run, produce results,
and the specific known Olist data issues are the ones actually caught
(proves the checks work, not just that they exist)."""
import pandas as pd
from db import get_conn
from validate import run_validation
from validate_modeled import run_modeled_validation


def test_raw_validation_runs_and_returns_all_checks():
    df = run_validation(write_results=False, verbose=False)
    assert len(df) == 12
    assert set(df.columns) >= {"check_name", "category", "passed", "detail"}


def test_raw_validation_catches_known_timestamp_anomaly():
    df = run_validation(write_results=False, verbose=False)
    row = df[df.check_name.str.contains("delivered_customer_date >= delivered_carrier_date")]
    assert len(row) == 1
    assert row.iloc[0]["passed"] == 0, "known Olist timestamp anomaly should be flagged, not hidden"


def test_modeled_validation_all_pass_after_transform():
    df = run_modeled_validation(verbose=False)
    n_fail = (df.passed == 0).sum()
    assert n_fail == 0, "modeled layer should be clean -- transform step must fix/exclude raw anomalies"


def test_referential_integrity_fact_to_dims():
    conn = get_conn()
    orphans = pd.read_sql(
        "SELECT COUNT(*) c FROM fact_orders f LEFT JOIN dim_customer c "
        "ON f.customer_id = c.customer_id WHERE c.customer_id IS NULL", conn
    ).c[0]
    conn.close()
    assert orphans == 0
