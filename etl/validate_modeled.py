"""
Stage 5: Post-load data-quality checks against the MODELED (star schema) layer —
catches issues introduced by the transform step itself, not just source data issues.
Appends to the same data_quality_results table used by validate.py (raw layer).
"""
import pandas as pd
from datetime import datetime, timezone
from db import get_conn

CHECKS = []


def check(name, category):
    def decorator(fn):
        CHECKS.append((name, category, fn))
        return fn
    return decorator


@check("fact_orders: order_id uniqueness (PK)", "duplicate_check")
def m1(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM (SELECT order_id FROM fact_orders GROUP BY order_id HAVING COUNT(*) > 1)", conn
    ).c[0]
    return n == 0, f"{n} duplicate order_id in fact_orders"


@check("referential integrity: fact_orders.customer_id -> dim_customer", "referential_integrity")
def m2(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM fact_orders f LEFT JOIN dim_customer c "
        "ON f.customer_id = c.customer_id WHERE c.customer_id IS NULL", conn
    ).c[0]
    return n == 0, f"{n} fact_orders rows with no matching dim_customer"


@check("referential integrity: fact_order_items.product_id -> dim_product", "referential_integrity")
def m3(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM fact_order_items f LEFT JOIN dim_product p "
        "ON f.product_id = p.product_id WHERE p.product_id IS NULL", conn
    ).c[0]
    return n == 0, f"{n} fact_order_items rows with no matching dim_product"


@check("range_check: delivery_delay_days within +/-200 days", "range_check")
def m4(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM fact_orders WHERE delivery_delay_days IS NOT NULL "
        "AND ABS(delivery_delay_days) > 200", conn
    ).c[0]
    return n == 0, f"{n} extreme delay outliers (possible residual data errors)"


@check("business_rule: on_time_flag consistent with delivery_delay_days sign", "business_rule")
def m5(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM fact_orders WHERE delivery_delay_days IS NOT NULL "
        "AND ((on_time_flag = 1 AND delivery_delay_days > 0) OR (on_time_flag = 0 AND delivery_delay_days <= 0))",
        conn,
    ).c[0]
    return n == 0, f"{n} rows where on_time_flag contradicts delivery_delay_days"


@check("schema_validation: fact_orders has expected row count vs raw_orders", "schema_validation")
def m6(conn):
    raw_n = pd.read_sql("SELECT COUNT(*) c FROM raw_orders", conn).c[0]
    fact_n = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    return raw_n == fact_n, f"raw_orders={raw_n:,} vs fact_orders={fact_n:,}"


@check("coverage: pct of orders with a valid delivery_delay_days", "business_rule")
def m7(conn):
    total = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    valid = pd.read_sql("SELECT COUNT(*) c FROM fact_orders WHERE delivery_delay_days IS NOT NULL", conn).c[0]
    pct = round(100 * valid / total, 1)
    # Informational, not a strict pass/fail threshold — undelivered orders legitimately have no delay value.
    return True, f"{pct}% of orders have a computable SLA delay ({valid:,}/{total:,})"


def run_modeled_validation(conn=None, verbose=True):
    own = conn is None
    conn = conn or get_conn()
    existing = pd.read_sql("SELECT * FROM data_quality_results", conn) if _table_exists(conn, "data_quality_results") else pd.DataFrame()

    rows = []
    for name, category, fn in CHECKS:
        passed, detail = fn(conn)
        rows.append({
            "check_name": name, "category": category, "passed": int(passed),
            "detail": detail, "run_ts": datetime.now(timezone.utc).isoformat(),
        })
        if verbose:
            status = "PASS" if passed else "FLAG"
            print(f"[validate_modeled] [{status}] {name:55s} {detail}")

    new_df = pd.DataFrame(rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
    combined.to_sql("data_quality_results", conn, if_exists="replace", index=False)
    conn.commit()
    if own:
        conn.close()
    return new_df


def _table_exists(conn, name):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return r is not None


if __name__ == "__main__":
    df = run_modeled_validation()
    n_fail = (df.passed == 0).sum()
    print(f"\n[validate_modeled] {len(df)} modeled-layer checks run, {n_fail} flagged.")
