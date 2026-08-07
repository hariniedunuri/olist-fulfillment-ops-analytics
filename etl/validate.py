"""
Stage 2: Validation.
Runs data-quality checks against the RAW layer before any transformation,
so we document what's actually wrong with the source data rather than
assuming it's clean. Each check writes a pass/fail row to `data_quality_results`.
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


@check("raw_orders: order_id not null", "null_check")
def c1(conn):
    n = pd.read_sql("SELECT COUNT(*) c FROM raw_orders WHERE order_id IS NULL", conn).c[0]
    return n == 0, f"{n} null order_id rows"


@check("raw_orders: order_id uniqueness (PK)", "duplicate_check")
def c2(conn):
    dupe = pd.read_sql(
        "SELECT COUNT(*) c FROM (SELECT order_id FROM raw_orders GROUP BY order_id HAVING COUNT(*) > 1)", conn
    ).c[0]
    return dupe == 0, f"{dupe} duplicate order_id values"


@check("raw_order_items: duplicate (order_id, order_item_id) rows", "duplicate_check")
def c3(conn):
    dupe = pd.read_sql(
        "SELECT COUNT(*) c FROM (SELECT order_id, order_item_id FROM raw_order_items "
        "GROUP BY order_id, order_item_id HAVING COUNT(*) > 1)", conn
    ).c[0]
    return dupe == 0, f"{dupe} duplicate order_item rows"


@check("raw_order_items: price/freight not negative", "range_check")
def c4(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_order_items WHERE price < 0 OR freight_value < 0", conn
    ).c[0]
    return n == 0, f"{n} rows with negative price/freight"


@check("raw_order_reviews: review_score within 1-5", "range_check")
def c5(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_order_reviews WHERE review_score < 1 OR review_score > 5", conn
    ).c[0]
    return n == 0, f"{n} out-of-range review scores"


@check("referential integrity: order_items.order_id exists in orders", "referential_integrity")
def c6(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_order_items oi "
        "LEFT JOIN raw_orders o ON oi.order_id = o.order_id WHERE o.order_id IS NULL", conn
    ).c[0]
    return n == 0, f"{n} order_items rows with no matching order"


@check("referential integrity: orders.customer_id exists in customers", "referential_integrity")
def c7(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_orders o "
        "LEFT JOIN raw_customers c ON o.customer_id = c.customer_id WHERE c.customer_id IS NULL", conn
    ).c[0]
    return n == 0, f"{n} orders rows with no matching customer"


@check("business rule: delivered_customer_date >= delivered_carrier_date", "business_rule")
def c8(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_orders "
        "WHERE order_delivered_customer_date IS NOT NULL AND order_delivered_carrier_date IS NOT NULL "
        "AND order_delivered_customer_date < order_delivered_carrier_date", conn
    ).c[0]
    return n == 0, f"{n} orders where customer delivery is before carrier handoff (bad timestamps)"


@check("business rule: delivered_carrier_date >= approved_date", "business_rule")
def c9(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_orders "
        "WHERE order_delivered_carrier_date IS NOT NULL AND order_approved_at IS NOT NULL "
        "AND order_delivered_carrier_date < order_approved_at", conn
    ).c[0]
    return n == 0, f"{n} orders where carrier handoff is before approval (bad timestamps)"


@check("schema: raw_orders has expected order_status values", "schema_validation")
def c10(conn):
    expected = {"delivered", "shipped", "canceled", "unavailable", "invoiced",
                "processing", "created", "approved"}
    vals = set(pd.read_sql("SELECT DISTINCT order_status FROM raw_orders", conn).order_status)
    unexpected = vals - expected
    return len(unexpected) == 0, f"unexpected status values: {unexpected}" if unexpected else "all statuses known"


@check("null_check: delivered orders missing delivered_customer_date", "null_check")
def c11(conn):
    n = pd.read_sql(
        "SELECT COUNT(*) c FROM raw_orders WHERE order_status='delivered' "
        "AND order_delivered_customer_date IS NULL", conn
    ).c[0]
    # This is a KNOWN data quality issue in the Olist dataset — expected to be >0.
    return n == 0, f"{n} orders marked 'delivered' but missing a delivered_customer_date"


@check("freshness_check(simulated): pipeline run timestamp recorded", "freshness_check")
def c12(conn):
    return True, f"pipeline executed at {datetime.now(timezone.utc).isoformat()}"


def run_validation(conn=None, write_results=True, verbose=True):
    own_conn = conn is None
    conn = conn or get_conn()
    rows = []
    for name, category, fn in CHECKS:
        passed, detail = fn(conn)
        rows.append({
            "check_name": name,
            "category": category,
            "passed": int(passed),
            "detail": detail,
            "run_ts": datetime.now(timezone.utc).isoformat(),
        })
        if verbose:
            status = "PASS" if passed else "FLAG"
            print(f"[validate] [{status}] {name:60s} {detail}")

    df = pd.DataFrame(rows)
    if write_results:
        df.to_sql("data_quality_results", conn, if_exists="replace", index=False)
        conn.commit()
    if own_conn:
        conn.close()
    return df


if __name__ == "__main__":
    df = run_validation()
    n_fail = (df.passed == 0).sum()
    print(f"\n[validate] {len(df)} checks run, {n_fail} flagged for review "
          f"(expected: known Olist data-quality issues are documented, not silently hidden).")
