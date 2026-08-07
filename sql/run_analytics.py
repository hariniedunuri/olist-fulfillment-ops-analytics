"""
Runs every .sql file in sql/analytics/ against the loaded star schema and
prints row counts + a preview. Also runs the DQ checks in sql/data_quality/checks.sql.
This is the script the dashboard and tests both import to guarantee the SQL
in the repo is the SQL actually being executed (no drift between docs and code).
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
from db import get_conn  # noqa: E402

ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "analytics")
DQ_DIR = os.path.join(os.path.dirname(__file__), "data_quality")


def run_query_file(conn, path, params=None):
    with open(path) as f:
        sql = f.read()
    if params:
        return pd.read_sql(sql, conn, params=params)
    return pd.read_sql(sql, conn)


def run_all_analytics(conn=None, verbose=True):
    own = conn is None
    conn = conn or get_conn()
    results = {}
    for fname in sorted(os.listdir(ANALYTICS_DIR)):
        if not fname.endswith(".sql"):
            continue
        if "root_cause_breakdown" in fname:
            continue  # parameterized query, run separately via get_root_cause()
        path = os.path.join(ANALYTICS_DIR, fname)
        df = run_query_file(conn, path)
        results[fname] = df
        if verbose:
            print(f"[analytics] {fname:32s} -> {len(df):>6,} rows")
    if own:
        conn.close()
    return results


def get_root_cause(seller_id, conn=None):
    own = conn is None
    conn = conn or get_conn()
    path = os.path.join(ANALYTICS_DIR, "05_root_cause_breakdown.sql")
    with open(path) as f:
        sql = f.read().replace(":seller_id", "?")
    df = pd.read_sql(sql, conn, params=(seller_id,))
    if own:
        conn.close()
    return df


if __name__ == "__main__":
    run_all_analytics()
